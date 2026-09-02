"""玩法逻辑 —— 养成状态机 + 遭遇判定 + 确定性刷新。

对应 docs/03-spawning.md 与 docs/04-gameplay.md。

设计要点：
  · 时间生产内容，空间调制内容（docs/02-sensing.md#20）
  · 确定性 PRNG 刷新 —— 同一 AP 同一时段永远出同样的怪，玩家可以预测
  · 不做惩罚性死亡 —— 状态低下只是能力打折，不清零存档
  · 移动量而非步数 —— 无 IMU

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 属性系统
# ---------------------------------------------------------------------------

# 初代 15 属性。没有恶/钢/妖精 —— 恶与钢是二代加的，妖精是六代。
# 妖精系引入后官方把皮皮线、胖丁线、魔墙人偶追认为妖精系，
# 本项目做初代情怀，这 5 只已在 tools/pipeline/convert_gen1.py 还原回去。
TYPES = [
    "一般", "火", "水", "电", "草", "冰",
    "格斗", "毒", "地面", "飞行", "超能",
    "虫", "岩石", "幽灵", "龙",
]

SPECIES_COUNT = 151      # 初代关都图鉴

# OUI → 场所语义 → 属性倾向（docs/03-spawning.md#32）
#
# OUI 前缀是厂商标识，而厂商强烈暗示场所类型。
# 这里只列了少量代表性前缀作为示例；实际使用应接入完整 OUI 数据库。
# 注意：AP 的 BSSID 是稳定的，客户端 MAC 随机化不影响这套。
OUI_SEMANTICS: dict[str, tuple[str, list[str]]] = {
    # 企业级 —— 园区、写字楼、学校
    "00:74:9c": ("enterprise", ["超能", "电"]),      # Ruijie 锐捷
    "00:23:89": ("enterprise", ["超能", "电"]),      # H3C
    "00:1a:1e": ("enterprise", ["超能", "电"]),      # Aruba
    "00:0c:29": ("enterprise", ["超能", "电"]),      # Cisco 系
    "ac:4b:c8": ("enterprise", ["超能", "电"]),      # Huawei 企业
    # 家用路由 —— 住宅
    "50:64:2b": ("home", ["一般", "超能"]),          # TP-Link
    "28:6c:07": ("home", ["一般", "超能"]),          # Xiaomi
    "c8:3a:35": ("home", ["一般", "超能"]),          # Tenda
    # 运营商网关
    "00:1f:64": ("carrier", ["电"]),
    # 手机热点 —— 人流聚集
    "a4:83:e7": ("hotspot", ["格斗", "超能"]),       # Apple
    "5c:0a:5b": ("hotspot", ["格斗", "超能"]),       # Samsung
}

# SSID 关键词 → 属性。SSID 是人类写的地名，信息密度极高。
SSID_KEYWORDS: list[tuple[tuple[str, ...], list[str]]] = [
    (("小学", "中学", "大学", "school", "univ", "campus"), ["超能", "一般"]),
    (("starbucks", "coffee", "cafe", "咖啡"), ["火", "一般"]),
    (("地铁", "metro", "subway", "station", "车站"), ["电", "岩石"]),
    (("医院", "hospital", "clinic"), ["毒", "超能"]),
    (("酒店", "hotel", "guest", "inn"), ["一般", "超能"]),
    (("mall", "商场", "plaza", "shop", "store"), ["电", "一般"]),
    (("park", "公园", "garden", "花园"), ["草", "虫"]),
    (("gym", "健身", "fitness", "sport"), ["格斗"]),
    (("printer", "print", "打印", "hp-", "epson"), ["电"]),
]


def ssid_semantics(ssid: str) -> list[str]:
    """SSID 关键词匹配 → 属性倾向。"""
    low = ssid.lower()
    for keywords, types in SSID_KEYWORDS:
        if any(k in low for k in keywords):
            return types
    return []


def oui_of(bssid: str) -> str:
    """取 BSSID 前三字节（OUI）。"""
    parts = bssid.split(":")
    return ":".join(parts[:3]).lower() if len(parts) >= 3 else ""


def ap_type_bias(bssid: str, ssid: str, auth: str) -> list[str]:
    """综合 OUI / SSID / authmode 推出属性倾向。

    优先级：SSID 关键词 > OUI > authmode 兜底。
    SSID 优先是因为它是人写的、最具体（"xx小学" 比 "这是台 TP-Link" 信息量大）。
    """
    if types := ssid_semantics(ssid):
        return types

    if sem := OUI_SEMANTICS.get(oui_of(bssid)):
        return sem[1]

    # authmode 兜底：企业级加密 = 机构，开放 = 公共商业区
    if auth in ("wpa2-ent", "wpa3-ent", "wpa-ent"):
        return ["超能", "电"]
    if auth == "open":
        return ["电", "一般"]
    return ["一般"]


# ---------------------------------------------------------------------------
# biome 分类（docs/03-spawning.md#33）
# ---------------------------------------------------------------------------

BIOME_WILD = "野外"
BIOME_RESIDENTIAL = "住宅区"
BIOME_OFFICE = "办公区"
BIOME_COMMERCIAL = "商业区"
BIOME_TRANSIT = "交通枢纽"


def classify_biome(aps: list, ble_count: int = 0) -> str:
    """由聚合统计判定 biome。

    aps 是 sensing.AP 列表。这里用手调决策树而非 ML ——
    几个阈值就够，C3 跑得动，也便于调试。

    注意：ESP32-C3 只有 2.4GHz，5G-only 的现代写字楼会显得异常稀疏，
    因此办公区的 AP 密度阈值不能定太高（docs/03-spawning.md#33）。
    """
    n = len(aps)
    if n == 0:
        return BIOME_WILD

    ent = sum(1 for a in aps if a.auth in ("wpa2-ent", "wpa3-ent", "wpa-ent"))
    opn = sum(1 for a in aps if a.auth == "open")

    # SSID 聚合度：同一 SSID 对应多少个 BSSID。
    # 高聚合 = 大型统一部署（商场/机场/校园），这个信号极强。
    ssid_counts: dict[str, int] = {}
    for a in aps:
        if a.ssid:
            ssid_counts[a.ssid] = ssid_counts.get(a.ssid, 0) + 1
    max_cluster = max(ssid_counts.values()) if ssid_counts else 0

    ent_ratio = ent / n
    open_ratio = opn / n

    if n <= 3:
        return BIOME_WILD
    if max_cluster >= 5 and open_ratio > 0.2:
        return BIOME_COMMERCIAL
    if ent_ratio > 0.4:
        return BIOME_OFFICE
    if n >= 15 and ble_count > 10:
        return BIOME_TRANSIT
    return BIOME_RESIDENTIAL


BIOME_TYPE_POOL: dict[str, list[str]] = {
    BIOME_WILD:        ["草", "虫", "飞行", "地面", "一般"],
    BIOME_RESIDENTIAL: ["一般", "超能", "毒", "电"],
    BIOME_OFFICE:      ["超能", "电", "岩石", "毒"],
    BIOME_COMMERCIAL:  ["电", "火", "一般", "格斗"],
    BIOME_TRANSIT:     ["电", "格斗", "幽灵", "毒"],
}


# ---------------------------------------------------------------------------
# 确定性刷新（docs/03-spawning.md#36）
# ---------------------------------------------------------------------------

TIME_BUCKET_SECONDS = 3600   # 一小时一换


def spawn_seed(bssid: str, ts: int, bucket: int = TIME_BUCKET_SECONDS) -> int:
    """确定性种子：同一 AP 在同一时段永远算出同样的结果。

    这保证了三件事：
      · 跨设备一致 —— 两人站一起看到同一批怪，不需要服务器
      · 可预测 —— 「这个 AP 每天下午三点出火系」，社区能做攻略
      · 可重算 —— 不用存刷新表，随时从 BSSID 重算

    不能用 random.seed()：Python 的 hash() 带随机化，跨进程不稳定。
    """
    key = f"{bssid}|{ts // bucket}".encode("utf-8")
    return zlib.crc32(key) & 0xFFFFFFFF


@dataclass
class Encounter:
    """一次遭遇。"""

    ts: int
    species_id: int
    type_name: str
    rarity: int          # 1=常见 5=极稀有
    from_bssid_hash: int
    biome: str
    is_transient: bool   # 来自转瞬即逝的 AP（猎场遭遇）

    @property
    def rarity_stars(self) -> str:
        return "★" * self.rarity + "☆" * (5 - self.rarity)


def rarity_from_ap(rssi: int, auth: str, ssid: str, is_transient: bool) -> int:
    """稀有度直接挂在 AP 属性上（docs/03-spawning.md#31）。

    信号弱、隐藏 SSID、企业级加密、转瞬即逝 —— 这些天然就是稀有刷新点。
    而玩家开始追着奇怪的路由器跑这件事本身就很对味。
    """
    r = 1
    if rssi < -80:
        r += 1              # 信号极弱，只能偶尔扫到
    if not ssid:
        r += 1              # 隐藏 SSID
    if auth in ("wpa2-ent", "wpa3-ent"):
        r += 1              # 企业级部署
    if is_transient:
        r += 1              # 路过一次就消失
    return min(r, 5)


def roll_encounter(
    bssid: str,
    ssid: str,
    rssi: int,
    auth: str,
    ts: int,
    biome: str,
    is_transient: bool = False,
    pet_type: Optional[str] = None,
) -> Encounter:
    """从一个 AP 掷出一次遭遇。

    pet_type 是主宠属性 —— 带着火系出门更容易遇到火系，
    于是「今天带谁出门」成了一个真决策（docs/04-gameplay.md#433）。
    """
    seed = spawn_seed(bssid, ts)

    # 属性池：AP 自身语义 + biome 池，主宠属性额外加权
    pool = ap_type_bias(bssid, ssid, auth) + BIOME_TYPE_POOL.get(biome, ["一般"])
    if pet_type:
        pool = pool + [pet_type] * 2   # 主宠属性权重翻倍

    type_name = pool[seed % len(pool)]
    species_id = (seed >> 8) % SPECIES_COUNT + 1

    return Encounter(
        ts=ts,
        species_id=species_id,
        type_name=type_name,
        rarity=rarity_from_ap(rssi, auth, ssid, is_transient),
        from_bssid_hash=zlib.crc32(bssid.encode()) & 0xFFFFFFFF,
        biome=biome,
        is_transient=is_transient,
    )


# ---------------------------------------------------------------------------
# 养成状态机（docs/04-gameplay.md#432）
# ---------------------------------------------------------------------------

# 每小时衰减速率。这些值需要用真实数据调 —— 见 docs/07-roadmap.md#71
SATIETY_DECAY_PER_HOUR = 4.0
MOOD_DECAY_PER_HOUR = 3.0
STAMINA_RECOVER_PER_HOUR = 6.0
STAMINA_COST_PER_MOTION_EVENT = 2.0

LOW_THRESHOLD = 25.0     # 低于此值进入消沉
DESPONDENT_PENALTY = 0.6  # 消沉时能力打折系数


@dataclass
class PetState:
    """主宠状态。

    只有一只主宠 —— 三键切换队伍成本过高，且情感投射需要唯一性，
    六只均摊等于没有（docs/04-gameplay.md#431）。

    关键设计：不做惩罚性死亡。状态低下只是进入消沉、能力打折，
    恢复照料即可复原。惩罚体验密度，不惩罚存档。
    """

    species_id: int = 1
    type_name: str = "一般"
    nickname: str = "小家伙"

    satiety: float = 80.0    # 饱食
    mood: float = 70.0       # 心情
    stamina: float = 90.0    # 体能

    intimacy: float = 0.0    # 亲密度 —— 陪伴时长的积累
    explore_value: int = 0   # 探索值 —— 移动量事件累积

    _last_ts: Optional[int] = None

    # -- 派生状态 ----------------------------------------------------------

    @property
    def is_despondent(self) -> bool:
        """消沉：任一状态轴过低。"""
        return min(self.satiety, self.mood, self.stamina) < LOW_THRESHOLD

    @property
    def ability_factor(self) -> float:
        """能力系数 —— 消沉时打折，但绝不清零。"""
        return DESPONDENT_PENALTY if self.is_despondent else 1.0

    @property
    def catch_window_bonus(self) -> float:
        """心情影响捕获判定窗口 —— 照料得好给更宽的时机判定。"""
        return 1.0 + (self.mood - 50.0) / 100.0

    @property
    def mood_label(self) -> str:
        if self.is_despondent:
            return "消沉"
        if self.mood >= 80:
            return "愉快"
        if self.mood >= 50:
            return "平静"
        return "低落"

    # -- 时间推进 ----------------------------------------------------------

    def advance(self, ts: int, motion_events: int = 0, is_night: bool = False) -> None:
        """推进到时刻 ts。

        只需要「过了多久」而非「现在几点」—— 这让 RTC 漂移
        对这三条轴几乎无影响（docs/02-sensing.md#25）。
        """
        if self._last_ts is None:
            self._last_ts = ts
            return

        hours = (ts - self._last_ts) / 3600.0
        if hours <= 0:
            return
        self._last_ts = ts

        self.satiety = max(0.0, self.satiety - SATIETY_DECAY_PER_HOUR * hours)
        self.mood = max(0.0, self.mood - MOOD_DECAY_PER_HOUR * hours)

        # 体能：夜间恢复更快（与作息挂钩）
        recover = STAMINA_RECOVER_PER_HOUR * (2.0 if is_night else 1.0) * hours
        cost = STAMINA_COST_PER_MOTION_EVENT * motion_events
        self.stamina = max(0.0, min(100.0, self.stamina + recover - cost))

        # 陪伴时长累积成亲密度
        self.intimacy = min(100.0, self.intimacy + hours * 0.5)

    # -- 互动 --------------------------------------------------------------

    def feed(self, amount: float = 30.0) -> None:
        self.satiety = min(100.0, self.satiety + amount)
        self.mood = min(100.0, self.mood + 5.0)

    def play(self) -> None:
        self.mood = min(100.0, self.mood + 15.0)
        self.stamina = max(0.0, self.stamina - 5.0)
        self.intimacy = min(100.0, self.intimacy + 1.0)

    def rest(self, hours: float = 8.0) -> None:
        self.stamina = min(100.0, self.stamina + STAMINA_RECOVER_PER_HOUR * hours)

    def on_new_place(self) -> None:
        """去了新地方 —— 心情加成（可再生信号，不会衰减到零）。"""
        self.mood = min(100.0, self.mood + 12.0)

    def on_reunion(self, days_away: float) -> None:
        """久别重逢加成 —— 奖励真实生活节律而非刻意乱走。"""
        if days_away >= 3.0:
            self.mood = min(100.0, self.mood + 8.0)

    def on_motion_event(self) -> None:
        """移动量攒够一次 —— 探索值增长（孵蛋进度挂在这里）。"""
        self.explore_value += 1
        self.mood = min(100.0, self.mood + 2.0)

    # -- 进化 --------------------------------------------------------------

    def can_evolve(self, need_intimacy: float = 60.0, need_explore: int = 50) -> bool:
        """进化条件：亲密度与探索值并列。

        让「陪伴时长」和「走过多少地方」都成为进度 ——
        两条线各自都能推进，但都推不满。
        """
        return self.intimacy >= need_intimacy and self.explore_value >= need_explore

    def bars(self) -> str:
        """状态条，用于终端显示。"""
        def bar(v: float, w: int = 10) -> str:
            n = int(v / 100 * w + 0.5)
            return "█" * n + "░" * (w - n)

        return (f"饱食 {bar(self.satiety)} {self.satiety:5.1f}  "
                f"心情 {bar(self.mood)} {self.mood:5.1f}  "
                f"体能 {bar(self.stamina)} {self.stamina:5.1f}")
