"""S5 图鉴 / S6 存档 / S9 道具 / S10 成绩。

对应 docs/systems/S5-dex.md、S6-save.md、S9-items.md、S10-records.md。

这四个放一起，因为它们本质都是**状态容器** —— S6 存档要序列化其余三个，
拆开会让存档模块反向依赖每个系统的内部结构。

固件移植取向：全部定长、位图与定长记录、无动态分配。
字节级布局与 docs 一致，可直接照搬进 C。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional

SPECIES_COUNT = 151
DEX_BYTES = (SPECIES_COUNT + 7) // 8      # 19 字节装 151 bit


# ---------------------------------------------------------------------------
# S5 图鉴
# ---------------------------------------------------------------------------

class Dex:
    """四个位图，各 19 字节 = 76 字节。

    为什么要四个而不是两个：S8 闪光的「捕获失败逃跑留下遗憾感」
    需要独立记「闪光已见」—— 否则那份遗憾存不下
    （docs/systems/S8-shiny.md 的边界情况）。
    19 字节买一个完整平行维度，划算。
    """

    __slots__ = ("seen", "caught", "shiny_seen", "shiny_caught")

    def __init__(self) -> None:
        self.seen = bytearray(DEX_BYTES)
        self.caught = bytearray(DEX_BYTES)
        self.shiny_seen = bytearray(DEX_BYTES)
        self.shiny_caught = bytearray(DEX_BYTES)

    @staticmethod
    def _set(bits: bytearray, sid: int) -> None:
        if 1 <= sid <= SPECIES_COUNT:
            bits[(sid - 1) >> 3] |= 1 << ((sid - 1) & 7)

    @staticmethod
    def _get(bits: bytearray, sid: int) -> bool:
        if not (1 <= sid <= SPECIES_COUNT):
            return False
        return bool(bits[(sid - 1) >> 3] & (1 << ((sid - 1) & 7)))

    def mark_seen(self, sid: int, shiny: bool = False) -> None:
        """遭遇即记「已见」—— 哪怕后来跑了。"""
        self._set(self.seen, sid)
        if shiny:
            self._set(self.shiny_seen, sid)

    def mark_caught(self, sid: int, shiny: bool = False) -> None:
        self._set(self.seen, sid)
        self._set(self.caught, sid)
        if shiny:
            self._set(self.shiny_seen, sid)
            self._set(self.shiny_caught, sid)

    def is_seen(self, sid: int) -> bool:
        return self._get(self.seen, sid)

    def is_caught(self, sid: int) -> bool:
        return self._get(self.caught, sid)

    def is_shiny_caught(self, sid: int) -> bool:
        return self._get(self.shiny_caught, sid)

    def count(self, which: str = "caught") -> int:
        bits = getattr(self, which)
        return sum(bin(b).count("1") for b in bits)

    def page(self, index: int, per_page: int = 20) -> list[dict]:
        """图鉴翻页（P6）。每页 20 只，共 8 页。

        未捕获的返回 owned=False，UI 用全暗剪影渲染
        （shade_map=(0,0,0,3)，零素材成本）。
        """
        start = index * per_page + 1
        out = []
        for sid in range(start, min(start + per_page, SPECIES_COUNT + 1)):
            out.append({
                "id": sid,
                "seen": self.is_seen(sid),
                "owned": self.is_caught(sid),
                "shiny": self.is_shiny_caught(sid),
            })
        return out

    @property
    def pages(self) -> int:
        return (SPECIES_COUNT + 19) // 20

    def to_bytes(self) -> bytes:
        return bytes(self.seen + self.caught + self.shiny_seen + self.shiny_caught)

    def load(self, data: bytes) -> None:
        if len(data) < DEX_BYTES * 4:
            return
        self.seen = bytearray(data[0:DEX_BYTES])
        self.caught = bytearray(data[DEX_BYTES:DEX_BYTES * 2])
        self.shiny_seen = bytearray(data[DEX_BYTES * 2:DEX_BYTES * 3])
        self.shiny_caught = bytearray(data[DEX_BYTES * 3:DEX_BYTES * 4])


# ---------------------------------------------------------------------------
# S9 道具
# ---------------------------------------------------------------------------

ITEM_CAPS = {"poke": 99, "great": 20, "ultra": 5, "berry": 20}

# 上限存在的意义是**逼出决策**：高级球只有 5 个，用不用在这只身上
# 是个真选择。若上限太高，道具就退化成纯数字（docs/systems/S9-items.md）。


@dataclass
class Inventory:
    """四种道具，各一字节。不做背包页面 —— 数量显示在用到它的页面上。"""

    poke: int = 5
    great: int = 0
    ultra: int = 0
    berry: int = 3

    def get(self, kind: str) -> int:
        return getattr(self, kind, 0)

    def add(self, kind: str, n: int = 1) -> int:
        """加道具，clamp 到上限。返回实际加了多少。"""
        if kind not in ITEM_CAPS:
            return 0
        cur = getattr(self, kind)
        new = min(ITEM_CAPS[kind], cur + n)
        setattr(self, kind, new)
        return new - cur

    def use(self, kind: str, n: int = 1) -> bool:
        """消耗道具。不足则返回 False 且不扣。"""
        cur = getattr(self, kind, 0)
        if cur < n:
            return False
        setattr(self, kind, cur - n)
        return True

    def next_ball(self, cur: str) -> str:
        """B 键循环切换球种 —— **跳过数量为 0 的**。

        避免玩家切到空球再发现不能投（docs/systems/S9-items.md 边界情况）。
        """
        order = ["poke", "great", "ultra"]
        if cur not in order:
            cur = "poke"
        for i in range(1, len(order) + 1):
            nxt = order[(order.index(cur) + i) % len(order)]
            if self.get(nxt) > 0:
                return nxt
        return cur          # 全空，保持原样

    def drop_from_encounter(self, rarity: int, is_new_place: bool = False) -> dict:
        """遭遇结束的掉落 —— **无论捕获成功与否**。

        为什么失败也掉：否则玩家会陷入「球不够 → 不敢投 → 更没球」的死锁。
        掉落是探索的报酬，不是捕获的报酬。
        """
        got: dict = {}
        n = 2 if rarity >= 3 else 1
        got["poke"] = self.add("poke", n)
        if rarity >= 3:
            got["great"] = self.add("great", 1)
        if rarity >= 5:
            got["ultra"] = self.add("ultra", 1)
        if is_new_place:
            got["ultra"] = got.get("ultra", 0) + self.add("ultra", 1)
        return {k: v for k, v in got.items() if v}

    def to_bytes(self) -> bytes:
        return struct.pack("<BBBB", self.poke, self.great, self.ultra, self.berry)

    def load(self, data: bytes) -> None:
        if len(data) < 4:
            return
        p, g, u, b = struct.unpack("<BBBB", data[:4])
        # clamp —— 存档损坏时不报错，静默修正
        self.poke = min(p, ITEM_CAPS["poke"])
        self.great = min(g, ITEM_CAPS["great"])
        self.ultra = min(u, ITEM_CAPS["ultra"])
        self.berry = min(b, ITEM_CAPS["berry"])


# ---------------------------------------------------------------------------
# S10 成绩
# ---------------------------------------------------------------------------

BIOME_ORDER = ["野外", "住宅区", "办公区", "商业区", "交通枢纽"]
TREND_DAYS = 14


@dataclass
class DailyCounters:
    """当日累计。日切时并入纪录后清零。"""

    encounters: int = 0
    captures: int = 0
    motion_events: int = 0
    new_places: int = 0
    cared: bool = False        # 今天照料过吗
    went_out: bool = False     # 今天出门过吗


@dataclass
class Records:
    """个人纪录榜（132 字节）。

    **不做联网排行榜** —— 单机无对手。这里的「排行」是与自己的历史比。
    这不是妥协：Tamagotchi 从来没有排行榜，靠的就是「我养了多久」。
    详见 docs/systems/S10-records.md。
    """

    # 单项纪录（值 + 发生日）
    best_encounters: int = 0
    best_encounters_day: int = 0
    best_motion: int = 0
    best_motion_day: int = 0
    best_new_places: int = 0
    best_new_places_day: int = 0
    longest_care_streak: int = 0
    longest_out_streak: int = 0
    max_intimacy: int = 0
    rarest_species: int = 0
    rarest_rarity: int = 0
    rarest_shiny: bool = False

    # 累计（只增不减）
    total_encounters: int = 0
    total_captures: int = 0
    total_motion: int = 0
    total_days: int = 0
    biome_counts: list = field(default_factory=lambda: [0] * 5)

    # 当前连续
    care_streak: int = 0
    out_streak: int = 0

    # 近期趋势
    trend: list = field(default_factory=list)     # [(day, enc, cap, motion, newp)]

    def on_encounter(self, biome: str, rarity: int, shiny: bool,
                     day: DailyCounters) -> None:
        day.encounters += 1
        self.total_encounters += 1
        if biome in BIOME_ORDER:
            self.biome_counts[BIOME_ORDER.index(biome)] += 1

    def on_capture(self, species_id: int, rarity: int, shiny: bool,
                   day: DailyCounters) -> None:
        day.captures += 1
        self.total_captures += 1
        # 「最稀有捕获」比较：先比稀有度，同稀有度下闪光优先
        better = (rarity > self.rarest_rarity
                  or (rarity == self.rarest_rarity and shiny and not self.rarest_shiny))
        if better:
            self.rarest_species = species_id
            self.rarest_rarity = rarity
            self.rarest_shiny = shiny

    def roll_day(self, day_index: int, day: DailyCounters,
                 intimacy: float) -> list[str]:
        """日切结算。返回本次打破的纪录名（用于 P1 顶部提示）。

        **纪录只在日切时更新，不实时比对** —— 纪录只在日切时可能变，
        实时比对不会更准，只会多写 flash
        （与 docs/02-sensing.md 的 flash 磨损策略一致）。
        """
        broken: list[str] = []

        if day.encounters > self.best_encounters:
            self.best_encounters = day.encounters
            self.best_encounters_day = day_index
            broken.append("单日遭遇最多")
        if day.motion_events > self.best_motion:
            self.best_motion = day.motion_events
            self.best_motion_day = day_index
            broken.append("单日移动量")
        if day.new_places > self.best_new_places:
            self.best_new_places = day.new_places
            self.best_new_places_day = day_index
            broken.append("单日新地点")

        # 连续天数：中断则归零，但**历史最长值保留**
        self.care_streak = self.care_streak + 1 if day.cared else 0
        self.out_streak = self.out_streak + 1 if day.went_out else 0
        if self.care_streak > self.longest_care_streak:
            self.longest_care_streak = self.care_streak
            broken.append("连续照料")
        if self.out_streak > self.longest_out_streak:
            self.longest_out_streak = self.out_streak
            broken.append("连续出门")

        iv = int(min(255, intimacy))
        if iv > self.max_intimacy:
            self.max_intimacy = iv

        self.total_motion += day.motion_events
        self.total_days += 1

        self.trend.append((day_index, day.encounters, day.captures,
                           day.motion_events, day.new_places))
        if len(self.trend) > TREND_DAYS:
            self.trend.pop(0)

        return broken

    def milestone(self) -> Optional[int]:
        """连续天数里程碑（7/30/100 天）—— 给心情加成。

        让「坚持」有机制上的回报，而不只是一个数字。
        """
        for m in (100, 30, 7):
            if self.care_streak == m or self.out_streak == m:
                return m
        return None

    def to_bytes(self) -> bytes:
        head = struct.pack(
            "<HIHIBIHHBBB",
            min(self.best_encounters, 65535), self.best_encounters_day,
            min(self.best_motion, 65535), self.best_motion_day,
            min(self.best_new_places, 255), self.best_new_places_day,
            min(self.longest_care_streak, 65535),
            min(self.longest_out_streak, 65535),
            min(self.max_intimacy, 255),
            min(self.rarest_species, 255),
            (min(self.rarest_rarity, 7) | (0x80 if self.rarest_shiny else 0)),
        )
        totals = struct.pack("<IIIH", min(self.total_encounters, 0xFFFFFFFF),
                             min(self.total_captures, 0xFFFFFFFF),
                             min(self.total_motion, 0xFFFFFFFF),
                             min(self.total_days, 65535))
        biomes = struct.pack("<5H", *[min(v, 65535) for v in self.biome_counts])
        streaks = struct.pack("<HH", min(self.care_streak, 65535),
                              min(self.out_streak, 65535))
        trend = bytearray()
        for d, e, c, m, n in self.trend[-TREND_DAYS:]:
            trend += struct.pack("<HBBBB", min(d, 65535), min(e, 255),
                                 min(c, 255), min(m, 255), min(n, 255))
        trend += bytes((TREND_DAYS - len(self.trend[-TREND_DAYS:])) * 6)
        return head + totals + biomes + streaks + bytes(trend)


# ---------------------------------------------------------------------------
# S6 存档
# ---------------------------------------------------------------------------

SAVE_MAGIC = b"KNT1"
SAVE_VERSION = 1


@dataclass
class SaveData:
    """存档容器。

    双 buffer + CRC32：养成数据与成绩是**唯一不可再生的**，
    而这类设备随时会被拔电。存档写坏等于数周进度归零。
    """

    pet_species: int = 4
    pet_level: int = 5
    satiety: int = 80
    mood: int = 70
    stamina: int = 90
    intimacy: int = 0
    explore_value: int = 0
    pet_hp: int = 100
    dex: Dex = field(default_factory=Dex)
    inventory: Inventory = field(default_factory=Inventory)
    records: Records = field(default_factory=Records)
    biome_dwell: list = field(default_factory=lambda: [0] * 5)
    day_index: int = 0

    def to_bytes(self) -> bytes:
        """序列化 + CRC。布局见 docs/systems/S6-save.md。"""
        pet = struct.pack("<BBBBBBHB", self.pet_species, self.pet_level,
                          self.satiety, self.mood, self.stamina,
                          min(int(self.intimacy), 255),
                          min(self.explore_value, 65535), self.pet_hp)
        dwell = struct.pack("<5I", *[min(v, 0xFFFFFFFF) for v in self.biome_dwell])
        body = (pet + self.dex.to_bytes() + self.inventory.to_bytes()
                + self.records.to_bytes() + dwell
                + struct.pack("<H", min(self.day_index, 65535)))
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack("<4sHI", SAVE_MAGIC, SAVE_VERSION, crc) + body

    @classmethod
    def verify(cls, blob: bytes) -> bool:
        """校验存档 —— 启动时先验两份，坏了回退到另一份。"""
        if len(blob) < 10 or blob[:4] != SAVE_MAGIC:
            return False
        (crc,) = struct.unpack("<I", blob[6:10])
        return (zlib.crc32(blob[10:]) & 0xFFFFFFFF) == crc


class DualBufferSave:
    """双 buffer 存档 —— 交替写 A/B，写完才切有效标记。

    这样任何时刻至少有一份完整存档：写 A 时 B 完好，反之亦然。
    掉电最坏情况是丢失最近一次写入，而不是丢失全部。
    """

    def __init__(self) -> None:
        self.slots: list[Optional[bytes]] = [None, None]
        self.active = 0
        self.writes = 0

    def save(self, data: SaveData) -> int:
        """写入非活动槽，成功后切换。返回写入的槽号。"""
        target = 1 - self.active
        self.slots[target] = data.to_bytes()
        self.active = target          # 切换 = 提交
        self.writes += 1
        return target

    def load(self) -> tuple[Optional[bytes], str]:
        """按「先活动槽、坏了退备份」的顺序读。返回 (数据, 来源说明)。"""
        for slot, label in ((self.active, "主槽"), (1 - self.active, "备份槽")):
            blob = self.slots[slot]
            if blob and SaveData.verify(blob):
                return blob, label
        return None, "两份都损坏"

    def total_bytes(self) -> int:
        return sum(len(b) for b in self.slots if b)
