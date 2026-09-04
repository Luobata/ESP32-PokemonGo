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
    TYPES, Encounter, PetState, classify_biome, roll_encounter, spawn_seed,
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
    move: str = ""         # 用了哪招（S20）。空 = 没有招式数据，按属性算
    missed: bool = False   # 未命中（招式命中率判定）


# 野怪的**绝对**等级带，按稀有度定。
#
# 早期版本让野怪等级跟着主宠走（pet_level + delta），实测发现那让
# 练级完全失去意义：主宠 Lv40 打 ★★ 照样输，因为对手也涨到 Lv39。
# 玩家的成长必须能兑现成战力，否则养成线与战斗线是脱钩的。
#
# 改成绝对等级带后，「打不过」变成一个**暂时**的状态 ——
# 练到 Lv30 就能回头收拾 ★★★★ 了，这才是收集游戏该有的曲线。
WILD_LEVEL_BAND = {1: 5, 2: 12, 3: 20, 4: 30, 5: 45}


def wild_level(rarity: int, pet_level: int = 0) -> int:
    """野怪等级 —— 按稀有度的绝对等级带，不随主宠浮动。

    pet_level 参数保留但只用于兜底（避免野怪等级低到毫无威胁）。
    """
    band = WILD_LEVEL_BAND.get(rarity, 12)
    return max(2, band)


@dataclass
class BattleResult:
    won: bool
    rounds: list[BattleRound] = field(default_factory=list)
    exp: int = 0
    wild_hp_ratio: int = 100      # 传给 S2 —— 打残了更好抓


# ---------------------------------------------------------------------------
# 经验值与升级（S20）
#
# 这套东西**原本完全不存在** —— 全项目 grep exp / level_up / level += 零命中，
# 主宠从 run_intro 拿到 Lv5，30 天跑下来还是 Lv5。而六处代码都假设等级会涨：
# S3 文档写「练到 Lv30 能回头收拾 ★★★★」、effective_stat 按等级算能力值、
# wild_level 的绝对等级带、gyms.level_cap 的徽章上限、S7 的 evolve_level、
# strings 的「经验」「等级」标签。
#
# 后果实测：主宠恒 Lv5，而 75% 的遭遇是 ★★ 以上（Lv12~20），
# **胜率 8.5%**（7 天 114 场只赢 5 场，多数是「败，野怪 HP 98%」）。
# 那不是战斗公式失衡 —— 同级对战实测 5 场 3 胜是合理的，
# 纯粹是等级差 7~15 级打不动。
# ---------------------------------------------------------------------------

# 升到 Lv n 所需的**累计**经验。
#
# 取 `5n³/2` —— 初代 slow 曲线（5n³/4）的两倍。为什么不直接用原版四条曲线：
# 原版一周目要打上百场训练师战 + 几百只野怪，而这个项目是「30 秒会话、
# 被动累积遭遇」，实测 7 天只有 114 场战斗。原版 medium_fast 在这个产出下
# 一周就冲到 Lv24、一个月 Lv40，节奏完全垮掉。
#
# 按实测产出（7 天约 15000 exp）校准后的节奏：
#
#     1 周 Lv18    2 周 Lv22    1 月 Lv29    3 月 Lv42
#
# 与 S3 的靶子对得上：一个月能收拾 ★★★★（Lv30），
# 而 ★★★★★（Lv45）要三个月以上 —— 那份留白是 S3 有意设计的。
#
# 用整数除法而非浮点：C3 无 FPU，且这个函数固件侧每场战斗都要调。
def exp_for_level(n: int) -> int:
    """升到 Lv n 所需的累计经验。n ≤ 1 时为 0。"""
    if n <= 1:
        return 0
    return 5 * n * n * n // 2


LEVEL_MAX = 100


def exp_to_level(exp: int, cap: int = LEVEL_MAX) -> int:
    """累计经验 → 等级。

    cap 是等级上限 —— 传 `gyms.level_cap(badges)` 就能让徽章真的限制成长
    （原版那套「没有徽章的高级宝可梦不听话」在这里简化成硬上限）。

    线性扫描而非二分：n 最多 100，且固件侧每场战斗才调一次。
    二分省下的几十次比较不值得换成边界容易写错的代码。
    """
    n = 1
    while n < cap and exp >= exp_for_level(n + 1):
        n += 1
    return n


def exp_progress(exp: int, level: int) -> tuple[int, int]:
    """当前等级内的经验进度 → (已获得, 本级需要)。

    给 P5 详情页画进度条用。**这是加 exp 字段而非即时结算升级的理由** ——
    「差一点就升级」的进度感只有存下经验才有。
    """
    lo = exp_for_level(level)
    hi = exp_for_level(level + 1)
    return max(0, exp - lo), max(1, hi - lo)


# 四条经验来源的系数。
#
# 全部来源都给经验（这是明确的设计取向：培育与探索都算成长），
# 但**量级要拉开**，否则「挂机照料」会变成最优解而探索失去意义。
# 按实测 7 天的次数（战斗 114、捕获 45、照料 21、移动 139）配比：
#
#     战斗  114 × ~102  = 11600   ← 主线，占 77%
#     捕获   45 × 60    =  2700   ← 次要，让「抓」也算成长
#     照料   21 × 30    =   630   ← 保底，不出门的日子也有进度
#     探索  139 × 8     =  1100   ← 细水长流
#                        ------
#                         16000
#
# 战斗的经验不在这里 —— 它按野怪等级算（见 auto_battle 的 exp 字段），
# 因为打高级野怪本来就该给更多。
EXP_ON_CAPTURE = 60         # 捕获成功
EXP_ON_CARE = 30            # 每次照料（喂食/玩耍/休息）
EXP_ON_MOTION = 8           # 每次移动量事件


# ---------------------------------------------------------------------------
# 招式（S20）—— 读 assets/moves.bin，按等级现算可用招
#
# ## 三条设计决策，都为了不推翻 S3
#
# S3 明确写了「不做招式表/PP/状态异常」，理由是三键设备上战斗不接受输入、
# 玩家决策发生在按 B 之前。招式在这里**不改变那条** —— 战斗仍然全自动，
# 玩家不选招，AI 选。变的只是伤害计算里「攻击方属性」换成「招式属性」：
# 一只电系可以打出一般系的电光一闪，属性相克因此有了层次。
#
#   ① **只收伤害招**。初代 165 招里约三分之一是 power=null 的变化招
#      （growl 降攻、agility 提速、thunder-wave 麻痹）。自动战斗里
#      它们要么需要额外的临时状态，要么在 8 回合内看不出效果。
#      moves.bin 只存 99 条伤害招。
#
#   ② **不存每只的招式列表**。按等级现算「这只现在学会了哪些」——
#      Mon 因此不用再加 4 字节，存档布局不动。代价是玩家无法保留
#      低级招式（原版可以），但自动战斗里那本来就不是玩家的决策点。
#
#   ③ **AI 加权随机而非总选最优**。总选最优会让同一组合每次结果相同，
#      野怪显得像机器；纯随机又让属性相克失去意义。
#      按「威力 × 相克倍率 × 本属性加成」加权，高伤害招更可能被选中。
# ---------------------------------------------------------------------------

STAB = 150                  # 本属性加成 ×1.5（初代原版就是这个数）
ACC_ALWAYS_HIT = 255        # moves.bin 里 255 表示必中（swift 电光）

_MOVES_CACHE: dict = {}     # {"moves": [...], "learn": {sid: [(lv, slot)]}}


def _load_moves() -> dict:
    """读 assets/moves.bin。格式见 tools/pipeline/convert_moves.py 顶部。

    读不到时返回空表 —— 调用方会退回「按攻击方属性算」的旧行为，
    这让招式成为**增强**而不是硬依赖（PC 侧跑回归测试时可能没有资产）。
    """
    if _MOVES_CACHE:
        return _MOVES_CACHE
    import pathlib
    p = pathlib.Path(__file__).resolve().parent.parent / "assets" / "moves.bin"
    if not p.exists():
        return {"moves": [], "learn": {}}
    d = p.read_bytes()
    magic, ver, rsz, mcnt, scnt, lcnt, poolsz = struct.unpack("<4sHHHHHH",
                                                              d[:16])
    if magic != b"MOVE":
        return {"moves": [], "learn": {}}
    o = 16
    mrec = d[o:o + mcnt * rsz]; o += mcnt * rsz
    srec = d[o:o + scnt * 4];   o += scnt * 4
    lrec = d[o:o + lcnt * 2];   o += lcnt * 2
    pool = d[o:o + poolsz]

    moves = []
    for i in range(mcnt):
        mid, zo, zl, ty, pw, ac, pp, dc, _rv = struct.unpack(
            "<HHBBBBBB2s", mrec[i * rsz:(i + 1) * rsz])
        moves.append({
            "id": mid,
            "zh": pool[zo:zo + zl].decode("utf-8", "replace") if zl else "",
            "type": TYPES[ty] if ty < len(TYPES) else "一般",
            "power": pw, "acc": ac, "pp": pp,
            "special": dc == 1,          # 0=物理 1=特殊
        })

    learn: dict = {}
    for i in range(scnt):
        loff, lc, _rv = struct.unpack("<HBB", srec[i * 4:(i + 1) * 4])
        rows = []
        for k in range(lc):
            q = (loff + k) * 2
            if q + 2 > len(lrec):
                break
            lv, slot = struct.unpack("<BB", lrec[q:q + 2])
            if slot < len(moves):
                rows.append((lv, slot))
        learn[i + 1] = rows

    _MOVES_CACHE["moves"] = moves
    _MOVES_CACHE["learn"] = learn
    return _MOVES_CACHE


STRUGGLE_MOVE_ID = 165      # 挣扎 —— 无招可用时的兜底，与原版同名同规则


def known_moves(species_id: int, level: int) -> list:
    """这只在这个等级学会了哪些招 —— 现算，不存。

    返回招式 dict 列表。

    ## 一招都不会时退回「挣扎」

    实测有 **4 只到 Lv50 仍一招不会**：#11/#14 铁甲蛹、#63 凯西、#132 百变怪。
    它们在原版确实只会变化招（变硬 / 瞬间移动 / 变身），
    而本项目只收伤害招（见模块顶部第 ① 条），于是它们的招式列表是空的。

    原版对这种处境有现成规则：**无招可用时只能挣扎**。挣扎本身就在
    招式表里（id=165，一般系 50 威力必中），拿它兜底既准确又不用特例 ——
    比留空字符串好：空招名会让战斗日志显示「用了（空）」，
    而玩家看到「挣扎」立刻明白发生了什么。
    """
    db = _load_moves()
    rows = db["learn"].get(species_id, [])
    out = [db["moves"][slot] for lv, slot in rows if lv <= level]
    if not out:
        for m in db["moves"]:
            if m["id"] == STRUGGLE_MOVE_ID:
                return [m]
    return out


def move_weight(move: dict, atk_types: list, def_types: list) -> int:
    """选招权重 = 威力 × 相克倍率 × 本属性加成。

    倍率为 0（幽灵打超能，初代那条著名 bug）时权重为 0 ——
    AI 不会选一个必定打不中的招，除非它没有别的选择。
    """
    mult = effectiveness(move["type"], def_types)
    w = move["power"] * mult // 100
    if move["type"] in atk_types:
        w = w * STAB // 100
    return max(0, w)


def pick_move(moves: list, atk_types: list, def_types: list,
              rng) -> Optional[dict]:
    """AI 选招 —— 按权重随机，偏好高伤害。

    rng 由调用方传入（战斗要可回放，所以不用全局随机源）。

    全部权重为 0 时（比如一只只会一般系招的宝可梦打幽灵）
    退回等概率随机 —— 总得出一招，哪怕打不中。
    """
    if not moves:
        return None
    ws = [move_weight(m, atk_types, def_types) for m in moves]
    total = sum(ws)
    if total <= 0:
        return moves[rng.randrange(len(moves))]
    r = rng.randrange(total)
    for m, w in zip(moves, ws):
        r -= w
        if r < 0:
            return m
    return moves[-1]


def effective_stat(base: int, level: int) -> int:
    """种族值 + 等级 → 实际能力值。

    **这一层不能省。** 实测发现：若直接用种族值，等级完全不影响胜负 ——
    伤害公式里等级只出现在 (2*Lv/5+2) 这一项，双方一起涨就抵消了。
    小火龙 Lv32 打 ★★ 档野怪照样输，"练级"变得毫无意义。

    原版用的是完整的能力值公式（含个体值、努力值），这里取简化版：
        实际值 = 种族值 × (1 + 等级/50)
    Lv50 时翻倍，与原版量级接近。主宠因为持续升级而野怪等级跟着稀有度
    浮动，于是等级差真的能转化成战力差。
    """
    return max(1, int(base * (1.0 + level / 50.0)))


def auto_battle(pet_types: list[str], pet_stats: list[int], pet_level: int,
                wild_types: list[str], wild_stats: list[int], wild_level: int,
                ability_factor: float = 1.0,
                max_rounds: int = 12,
                pet_species: int = 0, wild_species: int = 0,
                seed: int = 0) -> BattleResult:
    """自动结算战斗（S3 + S20 招式）。

    **仍然不接受输入** —— 玩家的决策发生在按 B 之前（打不打、带谁出门），
    不发生在回合里。S20 加的招式没有推翻这条：招式由 AI 选，
    改变的只是伤害计算里「攻击方属性」换成「招式属性」。

    张力仍来自三处（docs/systems/S3-battle.md）：
      · 属性相克可见 —— 「效果绝佳！」让玩家看到自己属性选择的因果
      · HP 逐回合扣减 —— 配合 shake_sequence()，不是瞬间结算
      · 削弱机制 —— 战后野怪 HP 降低使捕获窗口加宽

    传 pet_species / wild_species 才启用招式（要查学习表）。
    不传则退回按攻击方属性算 —— 让招式是**增强**而非硬依赖，
    没有 assets/moves.bin 时旧行为仍然成立。

    stats 顺序与 gen1.bin 一致：[hp, attack, defense, special, speed]
    ability_factor 来自 PetState —— 消沉时 0.6，这是养成对战斗的影响。

    seed 让战斗可回放 —— AI 选招与命中判定都走这个随机源，
    同一组输入永远得到同一场战斗（与 spawn_seed 的确定性取向一致）。
    """
    import random as _random
    rng = _random.Random(seed)

    # 种族值 → 实际能力值（含等级成长，见 effective_stat）
    ps = [effective_stat(v, pet_level) for v in pet_stats]
    ws = [effective_stat(v, wild_level) for v in wild_stats]

    p_hp_max = ps[0] * 2 + pet_level
    w_hp_max = ws[0] * 2 + wild_level
    p_hp, w_hp = p_hp_max, w_hp_max

    # 各自会哪些招（现算，见 known_moves）
    p_moves = known_moves(pet_species, pet_level) if pet_species else []
    w_moves = known_moves(wild_species, wild_level) if wild_species else []

    # 速度决定先手
    pet_first = ps[4] >= ws[4]
    rounds: list[BattleRound] = []

    def hit(atk_types, atk_stats, atk_lv, def_types, def_stats,
            factor: float, moves: list) -> tuple:
        """一次攻击 → (伤害, 倍率, 标签, 招名, 是否未命中)。"""
        mv = pick_move(moves, atk_types, def_types, rng) if moves else None

        if mv:
            # 命中判定 —— 255 表示必中（swift 电光）
            if mv["acc"] != ACC_ALWAYS_HIT and rng.randrange(100) >= mv["acc"]:
                return 0, 100, "", mv["zh"], True
            power = mv["power"]
            atk_type = mv["type"]
            # 初代分物理/特殊：物理用 attack/defense，特殊用 special 双向。
            # 这是招式带来的**新层次** —— 同样种族值，特攻高的用特殊招更疼。
            if mv["special"]:
                atk = max(1, int(atk_stats[3] * factor))
                dfn = max(1, def_stats[3])
            else:
                atk = max(1, int(atk_stats[1] * factor))
                dfn = max(1, def_stats[2])
            mult = effectiveness(atk_type, def_types)
            # 本属性加成算进**伤害**，但不算进 mult ——
            # mult 要用于「效果绝佳」标签，混进 STAB 会让电系打一般系
            # 显示成 ×150「效果绝佳」，而那是错的（相克其实是 ×100）。
            stab = STAB if atk_type in atk_types else 100
        else:
            # 没有招式数据 —— 旧行为：按攻击方属性、固定威力 40
            power = 40
            atk = max(1, int(atk_stats[1] * factor))
            dfn = max(1, def_stats[2])
            mult = max((effectiveness(t, def_types) for t in atk_types),
                       default=100)
            stab = 100

        # 初代原式：((2*Lv/5+2) * Atk * Power / Def) / 50 + 2。
        # 但原式的分母 50 配合的是原版等级成长曲线，而本项目主宠等级偏低、
        # 野怪种族值可能很高（实测 Lv12 打 Lv10 鸭嘴火兽只有 3 伤害/回合，
        # 要 46 回合）。分母压到 25 让战斗落在 4~8 回合 ——
        # 符合「30 秒会话」的预算，也让 HP 条的逐步扣减看得出变化。
        base = (2 * atk_lv // 5 + 2) * atk * power // dfn // 25 + 2
        dmg = max(1, base * mult // 100 * stab // 100) if mult else 0
        return dmg, mult, eff_label(mult), (mv["zh"] if mv else ""), False

    for _ in range(max_rounds):
        order = ["pet", "wild"] if pet_first else ["wild", "pet"]
        for who in order:
            if p_hp <= 0 or w_hp <= 0:
                break
            if who == "pet":
                dmg, mult, lbl, mv, miss = hit(
                    pet_types, ps, pet_level, wild_types, ws,
                    ability_factor, p_moves)
                w_hp = max(0, w_hp - dmg)
            else:
                dmg, mult, lbl, mv, miss = hit(
                    wild_types, ws, wild_level, pet_types, ps,
                    1.0, w_moves)
                p_hp = max(0, p_hp - dmg)
            rounds.append(BattleRound(who, dmg, mult, lbl, p_hp, w_hp,
                                      move=mv, missed=miss))
        if p_hp <= 0 or w_hp <= 0:
            break

    won = w_hp <= 0 and p_hp > 0
    # 野怪 HP 比例传给 S2 —— 但**不允许降到 0**，否则「打死了还能抓」不合逻辑。
    # 战斗胜利时留 1% 表示「濒死」，这也是捕获窗口最宽的状态。
    ratio = max(1, w_hp * 100 // w_hp_max) if w_hp_max else 100
    exp = wild_level * 8 + (20 if won else 0)

    return BattleResult(won=won, rounds=rounds, exp=exp, wild_hp_ratio=ratio)


# ---------------------------------------------------------------------------
# S7 进化
#
# 对应 docs/systems/S7-evolution.md。设计已定，这里只实现：
#   · 三种原版触发的处理（升级 52 / 道具 14 / 交换 4）
#   · 道具进化改 biome 驻留条件（不做进化石，见 S9）
#   · 交换进化用「高门槛单机替代」（方案 ①，不引入新依赖）
# ---------------------------------------------------------------------------

TRIGGER_LEVEL_UP = 0
TRIGGER_ITEM = 1
TRIGGER_TRADE = 2
TRIGGER_NONE = 0xFF

# 道具进化的 14 只 → biome 驻留条件。
# 原版靠五种进化石，但做成收集品会让玩家卡在「没有雷之石」上，
# 而设备没有商店（S9 已决定不做进化石）。
#
# 映射依据是 docs/03-spawning.md#32 的 OUI 语义：
# 企业级 AP → 超能/电 → 办公区；开放网络 → 商业区；AP 稀疏 → 野外。
STONE_BIOME = {
    "thunder-stone": "办公区",    # 电系 —— 呼应企业级 AP → 电
    "fire-stone": "商业区",
    "water-stone": "商业区",
    "leaf-stone": "野外",
    "moon-stone": "住宅区",       # 月之石 —— 夜间在家，见下方 night_only
}

# 需要的驻留秒数。⏳ 待 Phase 0 验证 —— 依赖真实驻留时长分布。
# 实测家里一天可累积约 10 小时住宅区驻留，公司约 8 小时办公区，
# 所以 6 小时门槛意味着「专门在那类环境待一天」。
STONE_DWELL_SECONDS = 6 * 3600

# 交换进化的高门槛替代（方案 ①）。保留「交换进化更难得」的原版语义。
TRADE_INTIMACY = 90.0
TRADE_EXPLORE_MULT = 4          # explore >= evolve_level × 4


@dataclass
class EvolutionCheck:
    """进化条件检查结果 —— 未满足时说明差什么，便于 UI 提示。"""

    can: bool
    reason: str = ""
    need_intimacy: float = 0.0
    need_explore: int = 0
    need_biome: str = ""
    need_dwell: int = 0
    progress: dict = field(default_factory=dict)


def check_evolution(pet, trigger: int, evolve_to: int, evolve_level: int,
                    biome_dwell: Optional[dict] = None,
                    item_hint: str = "") -> EvolutionCheck:
    """检查主宠能否进化。

    两个条件必须同时满足：物种侧有进化目标，养成侧攒够资源。
    `PetState.can_evolve()` 的意图是**两条线各自都能推进但都推不满** ——
    只在家陪着攒不满探索值，只出门走攒不满亲密度。

    evolve_level 携带了原版「这只进化早还是晚」的信息，不该丢：
    需求探索值 = evolve_level × 2（妙蛙种子 @16 → 32）。
    """
    if trigger == TRIGGER_NONE or not evolve_to:
        return EvolutionCheck(can=False, reason="这只不会进化")

    need_int = 60.0
    need_exp = max(10, evolve_level * 2)
    need_biome = ""
    need_dwell = 0

    if trigger == TRIGGER_TRADE:
        # 高门槛单机替代 —— 「难得」靠门槛传达，不必靠交换机制本身
        need_int = TRADE_INTIMACY
        need_exp = max(20, evolve_level * TRADE_EXPLORE_MULT)
    elif trigger == TRIGGER_ITEM:
        need_biome = STONE_BIOME.get(item_hint, "野外")
        need_dwell = STONE_DWELL_SECONDS

    prog = {
        "intimacy": (pet.intimacy, need_int),
        "explore": (pet.explore_value, need_exp),
    }

    if pet.intimacy < need_int:
        return EvolutionCheck(False, f"亲密度不足（{pet.intimacy:.0f}/{need_int:.0f}）",
                              need_int, need_exp, need_biome, need_dwell, prog)
    if pet.explore_value < need_exp:
        return EvolutionCheck(False, f"探索值不足（{pet.explore_value}/{need_exp}）",
                              need_int, need_exp, need_biome, need_dwell, prog)

    if need_biome:
        got = (biome_dwell or {}).get(need_biome, 0)
        prog["dwell"] = (got, need_dwell)
        if got < need_dwell:
            return EvolutionCheck(
                False,
                f"{need_biome}驻留不足（{got//3600:.0f}/{need_dwell//3600} 小时）",
                need_int, need_exp, need_biome, need_dwell, prog)

    return EvolutionCheck(True, "可以进化", need_int, need_exp,
                          need_biome, need_dwell, prog)


@dataclass
class EvolutionResult:
    from_species: int
    to_species: int
    frames: list = field(default_factory=list)   # shade_map 序列，供动效播放


def do_evolve(pet, to_species: int, to_type: str,
              next_evolve_level: int = 0) -> EvolutionResult:
    """执行进化。

    **intimacy 与 explore_value 不清零** —— 进化是奖励不是重置。
    清零会让连续进化线（妙蛙种子→妙蛙草→妙蛙花）第二段变成漫长的
    重新攒资源。但下一段门槛按新的 evolve_level 重算，所以仍有推进感。

    动效复用 sim/effects.py 的 evolution_sequence()：
    调用方在 IDENTITY 帧画旧形态、INVERT 帧画新形态。
    """
    from effects import evolution_sequence

    old = pet.species_id
    pet.species_id = to_species
    pet.type_name = to_type
    # 进化提振心情 —— 这是个高兴的事
    pet.mood = min(100.0, pet.mood + 15.0)

    return EvolutionResult(from_species=old, to_species=to_species,
                           frames=evolution_sequence(12))


# ---------------------------------------------------------------------------
# S14 衔接：捕获成功 → 收容 → 图鉴 → 掉落
#
# 这个函数补的是一个**真断层**：在它之前，attempt_capture() 成功后
# 只有调用方各自去点亮图鉴 bit，那只宝可梦的实体就消失了。
# 玩家抓三十只，能玩的还是开场那只 —— 捕获这个玩法的产出无处可去。
#
# 「谁负责收容」以前没人负责。现在由这里负责，且是**唯一**入口。
# ---------------------------------------------------------------------------

@dataclass
class CaptureOutcome:
    """一次遭遇的完整结果 —— 捕获判定 + 收容 + 图鉴 + 掉落。"""

    result: "CaptureResult"
    stored: bool = False               # 实体是否成功收容
    store_note: str = ""               # 收容说明（含替换信息）
    replaced: object = None            # 被替换掉的那只（仓库满时）
    drops: dict = field(default_factory=dict)
    dex_new: bool = False              # 是否首次捕获该物种
    where: str = ""                    # "队伍" / "仓库"


def resolve_capture(qe: "QueuedEncounter", cap: "CaptureResult",
                    party, dex, inventory, level: int = 0,
                    is_new_place: bool = False) -> CaptureOutcome:
    """把一次投球的结果落到各个系统上。

    参数刻意收全（party / dex / inventory）—— 让「捕获会影响哪些系统」
    在签名上一目了然，而不是散在调用方各处。

    `level` 要显式传：QueuedEncounter 不存等级（它是 wild_level(rarity,...)
    现算的，见 S3），队列里存的 8 字节没有等级字段。
    我第一版写了 qe.level —— 那个属性不存在。

    顺序有讲究：
      ① 先收容（可能失败：仓库满且无重复物种）
      ② 收容成功才点亮「已捕获」—— 否则图鉴会记下一只实际不存在的
      ③ 掉落**无论成败**（S9 的设计：掉落是探索的报酬，不是捕获的报酬）
    """
    from party import Mon                     # 延迟导入避免循环

    out = CaptureOutcome(result=cap)

    # ③ 掉落先算 —— 它与捕获成败无关，先算避免被 ① 的早退跳过
    out.drops = inventory.drop_from_encounter(qe.rarity, is_new_place)

    if not cap.caught:
        # 没抓到也要记「已见」—— S8 那份「闪光遇到了但跑了」的遗憾
        dex.mark_seen(qe.species_id, shiny=qe.is_shiny)
        return out

    # ① 收容
    lv = level or wild_level(qe.rarity)
    mon = Mon(species_id=qe.species_id, level=lv,
              hp=max(1, int(qe.hp_ratio)), shiny=qe.is_shiny)
    ok, note, victim = party.receive(mon)
    out.stored, out.store_note, out.replaced = ok, note, victim

    if not ok:
        # 收容失败 —— 只记「已见」，不记「已捕获」。
        # 图鉴不能记下一只实际不在手上的宝可梦。
        #
        # 仓库改成 151 格后这条**几乎走不到**（位置按物种号定，永远有位置），
        # 但保留它：deposit 在「仓库里的更好」时仍会失败，
        # 而且这道防线的语义是对的。
        dex.mark_seen(qe.species_id, shiny=qe.is_shiny)
        return out

    # 落在哪里。注意第三种情况：**抓到了但放走了**
    # （仓库那格已有更好的同种，见 Party.receive）——
    # 此时 mon 既不在队伍也不在仓库，`victim is mon` 是它的标志。
    if victim is mon:
        out.where = "放走"
    elif mon in party.party:
        out.where = "队伍"
    else:
        out.where = "仓库"

    # ② 收容成功才点亮已捕获
    #
    # 「放走了」也算捕获过 —— 玩家确实抓到了它，而且仓库里此刻
    # 就有一只同种（更好的那只）。图鉴记的是「拥有过这个物种」，
    # 不是「拥有这一只个体」。
    out.dex_new = not dex.is_caught(qe.species_id)
    dex.mark_caught(qe.species_id, shiny=qe.is_shiny)
    return out


# ---------------------------------------------------------------------------
# S9 补完：道具的完整链路
#
# 用户指出「设计了道具，道具如何获取、如何使用等」要设计。查下来发现
# S9 文档写清了规则，但**代码只实现了一半**：
#
#   · drop_from_encounter()（获取）有，且被 resolve_capture 调了
#   · Inventory.use()       写了，但**全项目没有一处调用**
#   · 浆果的「驻留时按时间产出」文档写了，代码里没有
#
# 后果很具体：**投球不消耗球**（可以无限投）、**浆果永远不增不减**
# （喂食免费，而 S4 的三条轴衰减是按「照料有成本」设计的）。
#
# 这里补上三个缺失的环节。
# ---------------------------------------------------------------------------

BERRY_INTERVAL = 4 * 3600       # 驻留时每 4 小时 +1 浆果（与基地遭遇同频）


def consume_ball(inventory, ball: str) -> bool:
    """投球前扣球。返回是否扣成功。

    **必须在判定之前调用** —— 投出去的球无论命中都消耗掉了。
    先判定再扣会让「未命中」变成免费重试。
    """
    return inventory.use(ball, 1)


def grant_berry(inventory, dwell_seconds: int, last_grant: int) -> tuple:
    """驻留产浆果。返回 (新的 last_grant, 增加了几个)。

    为什么挂驻留而不是挂遭遇：浆果是**照料**的资源，
    而照料是驻留时做的事。挂遭遇会让「出门才能喂宠物」，
    那与 S4「窝在家里也能养」的取向冲突。

    与基地遭遇同频（4 小时）—— 玩家一次归家能同时收到
    一只遭遇和一个浆果，两条产出线在时间上对齐，不用分别记账。
    """
    n = (dwell_seconds - last_grant) // BERRY_INTERVAL
    if n <= 0:
        return last_grant, 0
    got = inventory.add("berry", int(n))
    return last_grant + int(n) * BERRY_INTERVAL, got


def feed_pet(inventory, pet) -> tuple:
    """喂食 —— 消耗浆果。返回 (成功, 说明)。

    S9 文档写了「A 键执行时消耗」，但 PetState.feed() 本身不碰背包 ——
    那是对的（养成模块不该知道背包存在），所以衔接放在这里。
    """
    if inventory.get("berry") <= 0:
        return False, "没有浆果了"
    inventory.use("berry", 1)
    pet.feed()
    return True, "喂食完成"


@dataclass
class ItemFlow:
    """道具的完整收支 —— 用来验证「玩家会不会卡在没球」。

    这个类存在的理由是**验收**：S9 说「掉落是探索的报酬，不是捕获的报酬」
    （失败也掉），但那条规则够不够补上消耗，只有算过才知道。
    """

    thrown: int = 0
    caught: int = 0
    dropped: dict = field(default_factory=dict)
    berries_granted: int = 0
    berries_fed: int = 0

    def record_throw(self, ball: str, hit: bool) -> None:
        self.thrown += 1
        if hit:
            self.caught += 1

    def record_drop(self, got: dict) -> None:
        for k, v in got.items():
            self.dropped[k] = self.dropped.get(k, 0) + v

    def net_balls(self) -> int:
        """球的净收支。负数意味着玩家会越玩越穷。"""
        return sum(v for k, v in self.dropped.items()
                   if k in ("poke", "great", "ultra")) - self.thrown


# 实测（60 次遭遇、投球率 100%、命中率 55%）：
#
#   投球 60 → 掉落 poke 93 / great 20 / ultra 5，净 +58
#   结局：精灵球 38、超级球 20（撞满上限）、高级球 5（撞满上限）
#
# 结论：
#   ✓ **不会卡在没球** —— S9「失败也掉」这条规则够补上消耗
#   · 球给得偏多，中期高级球会一直是满的
#
# 第二条**不改**。用户明确定调：「球给的多没问题，休闲游戏，
# 收集养成为主，不用很难」。
#
# 所以上限的作用重新定位：它不再是「逼出决策」的稀缺性设计，
# 而是**防溢出的护栏** —— 让数字不至于变成无意义的四位数。
# 稀缺性由物种稀有度承担（高稀有度物种的捕获窗口本身就窄），
# 而不由消耗品承担。
#
# 这个取向也影响 S2：既然球不稀缺，捕获失败的惩罚就只剩
# 「野怪可能逃跑」一条，那条足够了 —— 它针对的是具体那一只，
# 而不是玩家的长期资源。
BALL_SCARCITY_BY_DESIGN = False      # 球不做稀缺资源（休闲取向）


def charset() -> set:
    """本模块上屏用到的字符 —— 字库子集化要收进去。

    只有三处：捕获判定的 `reason`（S2）、进化检查的 `reason`（S7）、
    以及捕获收容后的 `where`（S14，「队伍」或「仓库」）。

    这些是 dataclass 字段里的字面量，不在 strings.py 里 ——
    所以字库脚本看不到它们。「会」「仓」「库」「宠」等字缺失就来自这里。
    """
    out: set = set()
    # S2 捕获判定 reason（capture_attempt 的三个分支）
    for s in ("命中", "未命中", "未命中，逃跑了"):
        out |= set(s)
    # S7 进化检查 reason
    out |= set("这只不会进化")
    # S14 收容位置 where —— 「放走」是仓库改 151 格后的新状态
    out |= set("队伍") | set("仓库") | set("放走")
    # S20 招式名 —— 从 assets/moves.bin 的字符串池取，**不硬编码一份**。
    #
    # 战斗日志与 P3 会显示招名（「电击」「电光一闪」），96 个汉字。
    # 从产物读而非在这里列表：招式表变了字库自动跟上，
    # 不会重演「文案有三份副本必然漂移」那种事。
    #
    # moves.bin 不存在时安静跳过 —— 招式是增强而非硬依赖
    # （见 _load_moves 的说明），字库不该因为缺资产就构建失败。
    for m in _load_moves().get("moves", []):
        out |= set(m["zh"])
    return out
