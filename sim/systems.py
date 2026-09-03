"""S1 遭遇累积 / S2 捕获判定 / S3 自动战斗。

对应 docs/systems/S1-encounter.md、S2-capture.md、S3-battle.md。

这三个系统放一个模块，因为它们共享遭遇队列：S1 生产、S2 与 S3 消费。
拆开会让队列成为跨模块可变状态，那更难验证。

固件移植取向与 sensing.py 一致：定长结构、无浮点必需、状态量固定大小。
浮点只出现在 PC 侧的概率计算里，固件可用定点整数替代。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

import struct
import zlib
from dataclasses import dataclass, field
from typing import Optional

from gameplay import (
    Encounter, PetState, classify_biome, roll_encounter, spawn_seed,
)

# ---------------------------------------------------------------------------
# S1 遭遇累积
# ---------------------------------------------------------------------------

QUEUE_CAP = 16              # 环形队列容量（固件 16 × 8 B = 128 字节）
BASE_SPAWN_INTERVAL = 4 * 3600   # 基地遭遇间隔：驻留时按时间排程

# 猎场遭遇的触发条件：一次扫描里有多少个瞬现 AP 才算一次遭遇机会。
# 1 意味着只要有新 AP 就可能遇到 —— 通勤时 transient 通常 3~10，
# 所以这个值主要影响「密集程度」而非「有无」。
# ⏳ 待 Phase 0 验证：实测通勤 27 次扫描产生 67 个瞬现 AP，
#    若每个都触发会太密（一趟通勤 67 只），所以用移动量做闸门。
HUNT_MOTION_COST = 1.0      # 每次猎场遭遇消耗的移动量


@dataclass
class QueuedEncounter:
    """队列里的一条遭遇。

    固件侧定长 8 字节（docs/systems/S1-encounter.md）：
      ts_offset u16 | species u8 | packed u8 | bssid_hash u16(含闪光位) | biome u8 | hp u8
    """

    enc: Encounter
    hp_ratio: int = 100        # 0~100，S3 战斗后降低 → S2 捕获窗口加宽
    is_shiny: bool = False

    @property
    def species_id(self) -> int:
        return self.enc.species_id

    @property
    def rarity(self) -> int:
        return self.enc.rarity


class EncounterQueue:
    """环形队列。满了丢**最旧的低稀有度**那条，而非单纯最旧。

    理由：玩家一天可能遇 30 次而只处理 10 次，若单纯丢最旧，
    攒到的稀有个体会被后来的常见个体挤掉 —— 那与「稀有度驱动收集」矛盾。
    """

    def __init__(self, cap: int = QUEUE_CAP):
        self.cap = cap
        self.items: list[QueuedEncounter] = []
        self.dropped = 0        # 统计用：被挤掉了多少条

    def __len__(self) -> int:
        return len(self.items)

    def push(self, qe: QueuedEncounter) -> Optional[QueuedEncounter]:
        """入队。满了则返回被丢弃的那条。"""
        self.items.append(qe)
        if len(self.items) <= self.cap:
            return None

        # 找最低稀有度中最旧的一条
        min_rarity = min(q.rarity for q in self.items)
        for i, q in enumerate(self.items):
            if q.rarity == min_rarity:
                self.dropped += 1
                return self.items.pop(i)
        return self.items.pop(0)   # 不会到这里，兜底

    def pop(self, index: int = 0) -> Optional[QueuedEncounter]:
        if 0 <= index < len(self.items):
            return self.items.pop(index)
        return None

    def to_bytes(self) -> bytes:
        """序列化 —— 供 S6 存档。定长 8 字节/条。"""
        out = bytearray()
        base = self.items[0].enc.ts if self.items else 0
        for q in self.items:
            packed = ((q.enc.rarity & 0x7) << 1) | (1 if q.enc.is_transient else 0)
            h = (q.enc.from_bssid_hash & 0x7FFF) | (0x8000 if q.is_shiny else 0)
            out += struct.pack(
                "<HBBHBB",
                min(q.enc.ts - base, 65535),
                q.species_id & 0xFF,
                packed,
                h,
                0,                          # biome 索引，调用方填
                q.hp_ratio & 0xFF,
            )
        return bytes(out)


# 闪光概率（S8）。1/512 而非原版 1/8192 —— 原版一天遇几百只，
# 本项目一天 10~30 次，8192 意味着平均一年才见一只。
SHINY_DENOM = 512


def roll_shiny(bssid: str, ts: int, rarity: int) -> bool:
    """闪光判定 —— 遭遇生成时就定，玩家看到 sprite 的瞬间即知（S8）。

    用独立 salt 而非复用 spawn_seed 的低位，保证闪光判定与种类判定
    统计独立 —— 否则某些种类会永远不闪光。
    """
    denom = SHINY_DENOM // 2 if rarity >= 5 else SHINY_DENOM
    key = f"{bssid}|{ts // 3600}|shiny".encode("utf-8")
    return (zlib.crc32(key) & 0xFFFFFFFF) % denom == 0


# 种族值总和 → 强度档位。实测 151 只的分布（gen1.bin）：
#   最低 175（绿毛虫）中位 345  最高 590（超梦）
#   四分位 275 / 345 / 420
#
# 为什么需要这个：roll_encounter() 原本用 (seed>>8) % 151 均匀采样，
# 于是 Lv12 的初期主宠会遇到鸭嘴火兽（种族值 395）甚至超梦 ——
# 实测打 46 回合都赢不了。原版靠「不同区域不同等级带」解决，
# 本项目没有地图，改用 **AP 稀有度决定物种池**：
# 稀有 AP（弱信号/隐藏 SSID/企业级/瞬现）才出强种，这与
# docs/03-spawning.md#31「稀有度挂在 AP 属性上」是同一套逻辑的延伸。
STRENGTH_TIERS = [(0, 250), (250, 320), (320, 400), (400, 480), (480, 9999)]


def species_pool(rarity: int, stats_sum: dict[int, int]) -> list[int]:
    """按稀有度取物种池。stats_sum 是 {species_id: 种族值总和}。"""
    lo, hi = STRENGTH_TIERS[max(0, min(4, rarity - 1))]
    pool = [sid for sid, tot in stats_sum.items() if lo <= tot < hi]
    return pool or list(stats_sum.keys())


def pick_species(bssid: str, ts: int, rarity: int,
                 stats_sum: dict[int, int]) -> int:
    """从稀有度对应的池里确定性挑一只。

    仍然确定性（同一 AP 同一时段结果唯一），只是采样空间变了。
    """
    pool = species_pool(rarity, stats_sum)
    seed = spawn_seed(bssid, ts)
    return pool[(seed >> 8) % len(pool)]


class EncounterAccumulator:
    """S1 主体。喂 SensingResult + 扫描，产出遭遇入队。

    两种产出路径（docs/04-gameplay.md#411）：
      · 猎场（移动中）—— 瞬现 AP 驱动，密集
      · 基地（驻留）—— 按时间排程，稀少但**永不断流**

    基地必须按时间而非移动量驱动，否则窝在家里一整天毫无产出，
    而「设备永远不会没东西可看」是 docs/02-sensing.md#20 要保证的事。
    """

    def __init__(self, queue: Optional[EncounterQueue] = None,
                 base_interval: int = BASE_SPAWN_INTERVAL,
                 stats_sum: Optional[dict[int, int]] = None):
        self.queue = queue or EncounterQueue()
        self.base_interval = base_interval
        # 传入时按稀有度分档挑种；不传则退回 roll_encounter 的均匀采样
        self.stats_sum = stats_sum
        self._last_base_bucket = -1
        self._motion_pool = 0.0
        self.hunt_count = 0
        self.base_count = 0

    def feed(self, result, scan, pet: Optional[PetState] = None) -> list[QueuedEncounter]:
        """喂一次扫描，返回本次新产生的遭遇（通常 0 或 1 条）。"""
        from sensing import MOVING

        aps = scan.aps
        if not aps:
            return []

        biome = classify_biome(aps)
        pet_type = pet.type_name if pet else None
        made: list[QueuedEncounter] = []

        # 猎场：移动中 + 有瞬现 AP。用移动量做闸门，避免一趟通勤刷出几十只
        if result.state == MOVING and result.transient_aps > 0:
            self._motion_pool += result.distance
            while self._motion_pool >= HUNT_MOTION_COST:
                self._motion_pool -= HUNT_MOTION_COST
                ap = aps[result.ts % len(aps)]
                made.append(self._make(ap, result.ts, biome, True, pet_type))
                self.hunt_count += 1

        # 基地：按时间排程
        bucket = result.ts // self.base_interval
        if bucket != self._last_base_bucket:
            self._last_base_bucket = bucket
            ap = aps[result.ts % len(aps)]
            made.append(self._make(ap, result.ts, biome, False, pet_type))
            self.base_count += 1

        for qe in made:
            self.queue.push(qe)
        return made

    def _make(self, ap, ts: int, biome: str, transient: bool,
              pet_type: Optional[str]) -> QueuedEncounter:
        enc = roll_encounter(
            bssid=ap.bssid, ssid=ap.ssid, rssi=ap.rssi, auth=ap.auth,
            ts=ts, biome=biome, is_transient=transient, pet_type=pet_type,
        )
        # 按稀有度重挑物种 —— 让 AP 稀有度真正决定「遇到多强的怪」
        if self.stats_sum:
            enc.species_id = pick_species(ap.bssid, ts, enc.rarity, self.stats_sum)

        return QueuedEncounter(
            enc=enc,
            is_shiny=roll_shiny(ap.bssid, ts, enc.rarity),
        )


# ---------------------------------------------------------------------------
# S2 捕获判定
# ---------------------------------------------------------------------------

BAR_WIDTH = 200             # 判定条像素宽（240 屏留边距）
POINTER_PERIOD_MS = 1200    # 指针一个往复的毫秒数
WINDOW_MIN = 3              # 窗口下界 —— 极稀有种也不是数学上不可能
WINDOW_MAX = 200            # 上界 —— 防止条被填满导致「必中」

BALL_KINDS = ("poke", "great", "ultra")
BALL_FACTOR = {"poke": 1.0, "great": 1.5, "ultra": 2.0}
BALL_NAME_CN = {"poke": "精灵球", "great": "超级球", "ultra": "高级球"}

# 逃跑概率随稀有度递增。⏳ 待 Phase 0 验证 —— 这条曲线纯凭手感
FLEE_CHANCE = {1: 0.10, 2: 0.18, 3: 0.28, 4: 0.38, 5: 0.50}


# 基础窗口的映射上界。capture_rate 直接当像素会让高捕获率的种类
# （皮卡丘 190）一上来就撞满 200px 的条，于是球种与养成加成全部失效 ——
# 乘数再大也顶不动上界。实测发现的（190×任何系数都是 200）。
#
# 压到 0.55 后：皮卡丘基础 104px，精灵球刚过半条、高级球才接近满条，
# 球种选择重新变成有意义的决策。
BASE_SCALE = 0.55


def window_width(capture_rate: int, mood_bonus: float = 1.0,
                 ball: str = "poke", hp_ratio: int = 100) -> int:
    """算判定窗口宽度（像素）。

    四个乘数，对应四条不同来源的玩家能动性：
      capture_rate  种族固有，改不了
      mood_bonus    养成产出 —— 这是「养成反哺探索」的唯一落点
      ball          探索产出
      hp_ratio      战斗产出 —— 打残了更好抓，于是「先打再抓」成为真策略

    基础值按 BASE_SCALE 压缩，避免高捕获率种类撞满上界（见上方说明）。
    """
    base = capture_rate * BASE_SCALE
    hp_factor = 1.0 + (100 - hp_ratio) / 100.0   # HP 打到濒死则窗口近翻倍
    w = base * mood_bonus * BALL_FACTOR.get(ball, 1.0) * hp_factor
    return max(WINDOW_MIN, min(WINDOW_MAX, int(round(w))))


def pointer_position(elapsed_ms: int, period_ms: int = POINTER_PERIOD_MS) -> int:
    """指针在条上的像素位置 —— 三角波往复。

    固件侧用整数运算即可，这里也不用浮点三角函数。
    """
    if period_ms <= 0:
        return 0
    phase = elapsed_ms % period_ms
    half = period_ms // 2
    if phase < half:
        return phase * BAR_WIDTH // half
    return BAR_WIDTH - (phase - half) * BAR_WIDTH // (period_ms - half)


@dataclass
class CaptureResult:
    caught: bool
    fled: bool
    pointer: int
    window_start: int
    window_end: int
    window_w: int
    ball: str
    reason: str = ""


def attempt_capture(qe: QueuedEncounter, capture_rate: int, pet: PetState,
                    ball: str, elapsed_ms: int,
                    rng_seed: Optional[int] = None) -> CaptureResult:
    """一次投球。

    命中判定是**确定性的** —— 给定按键时刻与状态，结果唯一。
    只有「失败后是否逃跑」用随机数，因为那不该被玩家预测。
    """
    w = window_width(capture_rate, pet.catch_window_bonus, ball, qe.hp_ratio)
    # 窗口居中
    start = (BAR_WIDTH - w) // 2
    end = start + w
    p = pointer_position(elapsed_ms)

    hit = start <= p <= end
    fled = False
    reason = "命中" if hit else "未命中"

    if not hit:
        # 逃跑判定用确定性种子（便于回放复现），但玩家无法预测
        seed = rng_seed if rng_seed is not None else (qe.enc.ts * 31 + elapsed_ms)
        chance = FLEE_CHANCE.get(qe.rarity, 0.2)
        fled = ((zlib.crc32(str(seed).encode()) & 0xFFFF) / 65535.0) < chance
        if fled:
            reason = "未命中，逃跑了"

    return CaptureResult(caught=hit, fled=fled, pointer=p,
                         window_start=start, window_end=end, window_w=w,
                         ball=ball, reason=reason)


# ---------------------------------------------------------------------------
# S3 自动战斗
# ---------------------------------------------------------------------------

# 初代 15 属性相克。值 = 倍率 × 100。
# **含 4 条初代特有差异**（现代已改），见 docs/systems/S3-battle.md：
#   幽灵→超能 0%（著名 bug，现代 200%）
#   毒→虫 200%、虫→毒 200%（现代都是 50%）
#   冰→火 100%（现代 50%）
_EFF: dict[str, dict[str, int]] = {}


def _set(a: str, targets: tuple, v: int) -> None:
    _EFF.setdefault(a, {})
    for b in targets:
        _EFF[a][b] = v


_set("一般", ("岩石",), 50)
_set("一般", ("幽灵",), 0)
_set("火", ("草", "虫", "冰"), 200)
_set("火", ("水", "岩石", "火", "龙"), 50)
_set("水", ("火", "地面", "岩石"), 200)
_set("水", ("水", "草", "龙"), 50)
_set("草", ("水", "地面", "岩石"), 200)
_set("草", ("火", "草", "毒", "飞行", "虫", "龙"), 50)
_set("电", ("水", "飞行"), 200)
_set("电", ("草", "电", "龙"), 50)
_set("电", ("地面",), 0)
_set("冰", ("草", "地面", "飞行", "龙"), 200)
_set("冰", ("水", "冰"), 50)
_set("格斗", ("一般", "冰", "岩石"), 200)
_set("格斗", ("毒", "飞行", "超能", "虫"), 50)
_set("格斗", ("幽灵",), 0)
_set("毒", ("草",), 200)
_set("毒", ("毒", "地面", "岩石", "幽灵"), 50)
_set("地面", ("火", "电", "毒", "岩石"), 200)
_set("地面", ("草", "虫"), 50)
_set("地面", ("飞行",), 0)
_set("飞行", ("草", "格斗", "虫"), 200)
_set("飞行", ("电", "岩石"), 50)
_set("超能", ("格斗", "毒"), 200)
_set("超能", ("超能",), 50)
_set("虫", ("草", "超能"), 200)
_set("虫", ("火", "格斗", "飞行", "幽灵"), 50)
_set("岩石", ("火", "冰", "飞行", "虫"), 200)
_set("岩石", ("格斗", "地面"), 50)
_set("幽灵", ("幽灵",), 200)
_set("幽灵", ("一般",), 0)
_set("龙", ("龙",), 200)

# ★ 初代特有的 4 条覆写 —— 必须在通用规则之后设置
_set("幽灵", ("超能",), 0)      # 现代是 200%，初代是 bug
_set("毒", ("虫",), 200)        # 现代 50%
_set("虫", ("毒",), 200)        # 现代 50%
_set("冰", ("火",), 100)        # 现代 50%

GEN1_OVERRIDES = {("幽灵", "超能"), ("毒", "虫"), ("虫", "毒"), ("冰", "火")}


def effectiveness(atk: str, defs: list[str]) -> int:
    """属性相克倍率（×100）。双属性相乘。"""
    mult = 100
    for d in defs:
        mult = mult * _EFF.get(atk, {}).get(d, 100) // 100
    return mult


def eff_label(mult: int) -> str:
    if mult == 0:
        return "没有效果…"
    if mult >= 200:
        return "效果绝佳！"
    if mult <= 50:
        return "效果不好…"
    return ""


@dataclass
class BattleRound:
    attacker: str          # "pet" / "wild"
    damage: int
    mult: int
    label: str
    pet_hp: int
    wild_hp: int


def wild_level(rarity: int, pet_level: int) -> int:
    """野怪等级 —— 跟着主宠等级走，稀有度决定高低。

    **不能让野怪等级独立于主宠**：实测均匀采样 151 只时，Lv12 主宠会
    遇到鸭嘴火兽这类终极形态（种族值 65/95/57/85/93），打 46 回合都赢不了。
    原版靠「不同区域不同等级带」解决，本项目没有地图，改用稀有度：

        ★     主宠等级 -3   常见杂鱼
        ★★★   主宠等级 ±0
        ★★★★★ 主宠等级 +5   真正的挑战

    这样「打不过」永远是有信息的信号（遇到稀有种），而不是随机劝退。
    """
    delta = {1: -3, 2: -1, 3: 0, 4: 2, 5: 5}.get(rarity, 0)
    return max(2, pet_level + delta)


@dataclass
class BattleResult:
    won: bool
    rounds: list[BattleRound] = field(default_factory=list)
    exp: int = 0
    wild_hp_ratio: int = 100      # 传给 S2 —— 打残了更好抓


def auto_battle(pet_types: list[str], pet_stats: list[int], pet_level: int,
                wild_types: list[str], wild_stats: list[int], wild_level: int,
                ability_factor: float = 1.0,
                max_rounds: int = 12) -> BattleResult:
    """自动结算战斗（S3）。

    不做招式/PP/状态异常。张力来自三处（docs/systems/S3-battle.md）：
      · 属性相克可见 —— 「效果绝佳！」让玩家看到自己属性选择的因果
      · HP 逐回合扣减 —— 配合 shake_sequence()，不是瞬间结算
      · 削弱机制 —— 战后野怪 HP 降低使捕获窗口加宽

    stats 顺序与 gen1.bin 一致：[hp, attack, defense, special, speed]
    ability_factor 来自 PetState —— 消沉时 0.6，这是养成对战斗的影响。
    """
    p_hp_max = pet_stats[0] * 2 + pet_level
    w_hp_max = wild_stats[0] * 2 + wild_level
    p_hp, w_hp = p_hp_max, w_hp_max

    # 速度决定先手
    pet_first = pet_stats[4] >= wild_stats[4]
    rounds: list[BattleRound] = []

    def hit(atk_types, atk_stats, atk_lv, def_types, def_stats,
            factor: float) -> tuple[int, int, str]:
        # 初代伤害公式的简化版：不含随机数与暴击，保证可回放
        atk = max(1, int(atk_stats[1] * factor))
        dfn = max(1, def_stats[2])
        mult = max((effectiveness(t, def_types) for t in atk_types), default=100)
        # 初代原式：((2*Lv/5+2) * Atk * Power / Def) / 50 + 2，Power 取 40。
        # 但原式的分母 50 配合的是原版等级成长曲线，而本项目主宠等级偏低、
        # 野怪种族值可能很高（实测 Lv12 打 Lv10 鸭嘴火兽只有 3 伤害/回合，
        # 要 46 回合）。分母压到 25 让战斗落在 4~8 回合 ——
        # 符合「30 秒会话」的预算，也让 HP 条的逐步扣减看得出变化。
        base = (2 * atk_lv // 5 + 2) * atk * 40 // dfn // 25 + 2
        dmg = max(1, base * mult // 100) if mult else 0
        return dmg, mult, eff_label(mult)

    for _ in range(max_rounds):
        order = ["pet", "wild"] if pet_first else ["wild", "pet"]
        for who in order:
            if p_hp <= 0 or w_hp <= 0:
                break
            if who == "pet":
                dmg, mult, lbl = hit(pet_types, pet_stats, pet_level,
                                     wild_types, wild_stats, ability_factor)
                w_hp = max(0, w_hp - dmg)
            else:
                dmg, mult, lbl = hit(wild_types, wild_stats, wild_level,
                                     pet_types, pet_stats, 1.0)
                p_hp = max(0, p_hp - dmg)
            rounds.append(BattleRound(who, dmg, mult, lbl, p_hp, w_hp))
        if p_hp <= 0 or w_hp <= 0:
            break

    won = w_hp <= 0 and p_hp > 0
    # 野怪 HP 比例传给 S2 —— 但**不允许降到 0**，否则「打死了还能抓」不合逻辑。
    # 战斗胜利时留 1% 表示「濒死」，这也是捕获窗口最宽的状态。
    ratio = max(1, w_hp * 100 // w_hp_max) if w_hp_max else 100
    exp = wild_level * 8 + (20 if won else 0)

    return BattleResult(won=won, rounds=rounds, exp=exp, wild_hp_ratio=ratio)
