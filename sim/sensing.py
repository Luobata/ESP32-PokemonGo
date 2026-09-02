"""感知层算法 —— 用 WiFi 环境指纹替代 GPS。

对应 docs/02-sensing.md。这份实现是固件的参考实现：
所有算法都刻意保持在能用定点整数重写的范围内（无浮点必需、无动态分配、
状态量固定大小），以便后续移植到 ESP32-C3。

核心组件：
  Signature   —— 一次扫描的加权指纹（top-N BSSID 哈希 + 权重）
  PlaceMemory —— 8 槽 LRU 地点记忆（对应降级阶梯 Level A，512 字节预算）
  MotionState —— 移动/驻留判定 + 迟滞（Level B）
  SensingCore —— 组装以上，逐次喂扫描数据，产出判定与移动量

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

import zlib
from dataclasses import dataclass, field
from typing import Iterable, Optional

# ---------------------------------------------------------------------------
# 可调参数（docs/02-sensing.md#24）
#
# 注意：这些值目前全部是估算，必须用真实口袋数据重新标定 —— 见 docs/02-sensing.md#26。
# 电脑采集的数据天线更好、能看 5GHz，不能直接用来定阈值。
# ---------------------------------------------------------------------------

TOP_N = 8               # 指纹保留最强的 N 个 AP
MATCH_THRESHOLD = 0.35  # 加权 Jaccard >= 此值判为同一地点
MOVE_THRESHOLD = 0.40   # 相邻扫描距离 > 此值判为「在移动」
HYSTERESIS = 2          # 状态切换需连续 N 次一致才确认
PLACE_SLOTS = 8         # LRU 槽位数（对应固件 512 字节预算）

# 滑动窗口大小 —— 用最近 N 次扫描的 AP 出现率建指纹，而非单次快照。
#
# 这是**真实数据驱动的修正**，不是设计时想到的。家里静坐 20 分钟的
# 40 次扫描实测：单帧指纹给出 11 次状态转换、30% 时间判为「移动中」，
# 而人根本没动。
#
# 根因：家里 28 个 AP 中只有 9 个出现率 >=59%，另 19 个 <=37% 且几乎
# 全在 -80dBm 以下。单次取 top-8 时噪声 AP 频繁挤进指纹，相邻距离
# 飙到 0.6~0.7。docs/02-sensing.md#24 预警过稀疏环境问题，但真实情况
# 比估计严重 —— 不是「一个 AP 掉线占比大」，而是「近半数 AP 每次都在闪」。
#
# 静态过滤（RSSI 地板、收紧 topN）实测基本无效，因为问题不在阈值而在
# 逐次比对本身：单次漏检是随机的，任何瞬时比较都被它主导。
#
# 窗口平滑的实测效果（理想是转换 <=1、移动 0%）：
#   窗口 1（旧）  转换 11  移动 19%
#   窗口 3        转换  1  移动  0%
#   窗口 4        转换  1  移动  0%   ← 采用
#   窗口 6        转换  1  移动  0%
#
# 代价是移动检测延迟约 window × 扫描间隔。窗口 4 = 90 秒（30s 间隔），
# 通勤持续几十分钟，可接受。窗口 6 要 120 秒，没必要。
SMOOTH_WINDOW = 4

# 「新鲜 AP 占比」阈值 —— 移动判定的第二条判据。
# 一次扫描里若有 >=25% 的 AP 是历史从未见过的，说明在往新地方走。
# 驻留时这个值接近 0（AP 集合封闭），通勤时持续偏高。
FRESH_RATIO_THRESHOLD = 0.25

RSSI_FLOOR = -100       # 权重曲线下界（dBm）
RSSI_CEIL = -40         # 权重曲线上界（dBm）

# 2.4GHz 信道上界。ESP32-C3 只有 2.4GHz，5GHz 的 AP 它完全看不见。
CHANNEL_24G_MAX = 14


def hash32(bssid: str) -> int:
    """BSSID → 32 位哈希。

    只存哈希不存原始 BSSID：BSSID 属位置关联数据，
    哈希化后即便存档泄露也无法反推具体地点（docs/02-sensing.md#28）。

    用 crc32 而非 Python 内置 hash()：后者带随机化种子，
    跨进程不稳定，会让「首次分类后冻结」的地点表在重启后全部失配。
    """
    return zlib.crc32(bssid.encode("utf-8")) & 0xFFFFFFFF


def rssi_weight(rssi: int) -> float:
    """RSSI → [0,1] 权重。

    稀疏环境下一个 AP 掉线占比很大，等权 Jaccard 会误判，
    所以按信号强度加权，让最强的两三个 AP 当锚点。
    """
    if rssi <= RSSI_FLOOR:
        return 0.0
    if rssi >= RSSI_CEIL:
        return 1.0
    return (rssi - RSSI_FLOOR) / (RSSI_CEIL - RSSI_FLOOR)


@dataclass
class AP:
    """一次扫描里的单个 AP。字段名对应采集器 NDJSON 的压缩键。"""

    bssid: str
    ssid: str = ""
    rssi: int = -100
    channel: int = 0
    auth: str = "unknown"

    @property
    def is_24g(self) -> bool:
        return 0 < self.channel <= CHANNEL_24G_MAX

    @classmethod
    def from_json(cls, d: dict) -> "AP":
        return cls(
            bssid=d.get("b", ""),
            ssid=d.get("s", ""),
            rssi=int(d.get("r", -100)),
            channel=int(d.get("c", 0)),
            auth=d.get("a", "unknown"),
        )


@dataclass
class Scan:
    """一次完整扫描。"""

    ts: int
    aps: list[AP] = field(default_factory=list)
    degraded: bool = False   # 采集器降级模式（伪 BSSID）
    error: Optional[str] = None

    @classmethod
    def from_json(cls, d: dict) -> "Scan":
        return cls(
            ts=int(d.get("ts", 0)),
            aps=[AP.from_json(x) for x in d.get("aps", [])],
            degraded=bool(d.get("degraded", False)),
            error=d.get("err"),
        )

    def only_24g(self) -> "Scan":
        """只保留 2.4GHz —— 模拟 ESP32-C3 的视角。"""
        return Scan(
            ts=self.ts,
            aps=[a for a in self.aps if a.is_24g],
            degraded=self.degraded,
            error=self.error,
        )


class Signature:
    """一次扫描的加权指纹：top-N 个 (哈希, 权重)。

    固件侧这就是一个定长数组，8 个 (uint32, uint8) = 40 字节。
    """

    __slots__ = ("weights",)

    def __init__(self, weights: Optional[dict[int, float]] = None):
        self.weights: dict[int, float] = weights or {}

    @classmethod
    def from_scan(cls, scan: Scan, top_n: int = TOP_N) -> "Signature":
        # 同一 BSSID 可能出现多次（多 SSID 共用射频），取最强的那次
        best: dict[int, int] = {}
        for ap in scan.aps:
            if not ap.bssid:
                continue
            h = hash32(ap.bssid)
            if h not in best or ap.rssi > best[h]:
                best[h] = ap.rssi

        # 按信号强度取 top-N
        top = sorted(best.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        return cls({h: rssi_weight(r) for h, r in top if rssi_weight(r) > 0})

    def __len__(self) -> int:
        return len(self.weights)

    def __bool__(self) -> bool:
        return bool(self.weights)

    def similarity(self, other: "Signature") -> float:
        """加权 Jaccard：Σmin / Σmax，值域 [0,1]。

        两个空指纹的相似度定义为 0 而非 1 —— 「什么都没扫到」
        不应该被当作「回到了某个熟悉的地方」。
        """
        if not self.weights or not other.weights:
            return 0.0
        keys = self.weights.keys() | other.weights.keys()
        inter = sum(min(self.weights.get(k, 0.0), other.weights.get(k, 0.0)) for k in keys)
        union = sum(max(self.weights.get(k, 0.0), other.weights.get(k, 0.0)) for k in keys)
        return inter / union if union > 0 else 0.0

    def distance(self, other: "Signature") -> float:
        return 1.0 - self.similarity(other)

    def merge(self, other: "Signature", alpha: float = 0.2) -> None:
        """指数移动平均更新，让地点指纹随环境缓慢演化。

        alpha 小 = 记忆顽固。这是有意的：地点应该稳定，
        偶尔一次异常扫描不该把它带走（对应「首次分类后冻结」的软化版）。
        """
        for k, v in other.weights.items():
            cur = self.weights.get(k, 0.0)
            self.weights[k] = cur + alpha * (v - cur)
        # 衰减本次未见到的 AP
        for k in list(self.weights):
            if k not in other.weights:
                self.weights[k] *= 1 - alpha
                if self.weights[k] < 0.05:
                    del self.weights[k]
        # 保持定长，超出就丢最弱的
        if len(self.weights) > TOP_N:
            keep = sorted(self.weights.items(), key=lambda kv: kv[1], reverse=True)[:TOP_N]
            self.weights = dict(keep)


class SlidingSignature:
    """滑动窗口指纹 —— 用最近 N 次扫描的 AP 出现率建指纹。

    这是对单帧 `Signature` 的补充，不是替代：
      · 单帧指纹仍用于计算 transient_aps（瞬现 AP 是猎场遭遇的原料，
        平滑会把它抹掉）
      · 平滑指纹用于移动判定与地点匹配（抗噪）

    权重公式：
        weight(h) = (窗口内出现次数 / 窗口大小) × (该 AP 平均 rssi_weight)

    出现率这一项是关键。稳定 AP 每次都在，出现率接近 1；噪声 AP
    时有时无，出现率被压到 0.2~0.4，于是挤不进 top-N。

    固件侧实现：窗口是定长环形缓冲（4 × top8 × (uint32+uint8) = 160 字节），
    仍在 RTC slow memory 预算内。
    """

    __slots__ = ("window", "top_n", "_buf")

    def __init__(self, window: int = SMOOTH_WINDOW, top_n: int = TOP_N):
        from collections import deque
        self.window = window
        self.top_n = top_n
        self._buf: "deque[list[AP]]" = deque(maxlen=window)

    def push(self, scan: Scan) -> None:
        self._buf.append(list(scan.aps))

    def __len__(self) -> int:
        return len(self._buf)

    def current(self) -> Signature:
        """当前窗口的平滑指纹。"""
        if not self._buf:
            return Signature()

        # 同一 BSSID 在一次扫描里可能出现多次（多 SSID 共用射频），
        # 每次扫描内先去重取最强，避免重复计数抬高出现率
        counts: dict[int, int] = {}
        wsum: dict[int, float] = {}
        for snapshot in self._buf:
            best: dict[int, int] = {}
            for ap in snapshot:
                if not ap.bssid:
                    continue
                h = hash32(ap.bssid)
                if h not in best or ap.rssi > best[h]:
                    best[h] = ap.rssi
            for h, rssi in best.items():
                counts[h] = counts.get(h, 0) + 1
                wsum[h] = wsum.get(h, 0.0) + rssi_weight(rssi)

        n = len(self._buf)
        weights = {h: (counts[h] / n) * (wsum[h] / counts[h]) for h in counts}
        top = sorted(weights.items(), key=lambda kv: kv[1], reverse=True)[:self.top_n]
        return Signature({h: w for h, w in top if w > 0})


@dataclass
class Place:
    """一个已知地点。"""

    pid: int
    sig: Signature
    first_seen: int
    last_seen: int
    visits: int = 1
    total_dwell: int = 0      # 累积驻留秒数
    biome: Optional[str] = None   # 首次分类后冻结（docs/03-spawning.md#36）
    label: Optional[str] = None   # 人工标注（"家" / "公司"）

    @property
    def name(self) -> str:
        return self.label or f"地点#{self.pid}"


class PlaceMemory:
    """8 槽 LRU 地点记忆 —— 降级阶梯 Level A。

    不建完整指纹数据库，只记最近去过的几个地方。
    匹配不上就是「没去过的地方」，本身就是一个可玩的事件。
    """

    def __init__(self, slots: int = PLACE_SLOTS, threshold: float = MATCH_THRESHOLD):
        self.slots = slots
        self.threshold = threshold
        self.places: list[Place] = []
        self._next_pid = 1

        # 按 biome 的累计驻留秒数 —— **与地点表解耦，只增不减**。
        #
        # 为什么不直接遍历 places 求和：LRU 满了会 pop 掉最久未访问的槽，
        # 连同它的 total_dwell 一起丢。于是有个反直觉的失败模式 ——
        # 攒了三周的办公区驻留，出差一趟回来发现槽位被沿途新地点挤掉，
        # 进度归零。这违反「不做惩罚性死亡」的精神
        # （docs/04-gameplay.md#432 那条虽然只约束状态轴，但精神一致）。
        #
        # S7 进化的 biome 驻留条件依赖这份累计（docs/systems/S7-evolution.md），
        # 所以它必须独立于地点表的生命周期。
        # 固件侧是 5 × uint32 = 20 字节，进存档。
        self.biome_dwell: dict[str, int] = {}

    def match(self, sig: Signature) -> tuple[Optional[Place], float]:
        """找最相似的地点。返回 (地点或 None, 最佳得分)。"""
        best: Optional[Place] = None
        best_score = 0.0
        for p in self.places:
            s = sig.similarity(p.sig)
            if s > best_score:
                best_score, best = s, p
        if best is not None and best_score >= self.threshold:
            return best, best_score
        return None, best_score

    def observe(self, sig: Signature, ts: int) -> tuple[Place, bool]:
        """记录一次观测。返回 (地点, 是否新建)。"""
        hit, _ = self.match(sig)
        if hit is not None:
            hit.sig.merge(sig)
            hit.last_seen = ts
            return hit, False

        place = Place(pid=self._next_pid, sig=sig, first_seen=ts, last_seen=ts)
        self._next_pid += 1
        self.places.append(place)

        # LRU 淘汰：满了就丢最久未访问的
        if len(self.places) > self.slots:
            self.places.sort(key=lambda p: p.last_seen)
            self.places.pop(0)

        return place, True

    def days_since_visit(self, place: Place, now: int) -> float:
        return (now - place.last_seen) / 86400.0

    def add_dwell(self, biome: Optional[str], seconds: int) -> None:
        """累计某 biome 的驻留时长。biome 为 None 时忽略。

        调用方在确认驻留时调用。与 Place.total_dwell 并存 ——
        后者是「这个地点待了多久」（会随 LRU 淘汰丢失），
        前者是「这类环境累计待了多久」（永不丢失）。
        """
        if not biome or seconds <= 0:
            return
        self.biome_dwell[biome] = self.biome_dwell.get(biome, 0) + seconds


# ---------------------------------------------------------------------------
# 移动判定
# ---------------------------------------------------------------------------

MOVING = "moving"
STAYING = "staying"
UNKNOWN = "unknown"


@dataclass
class MotionState:
    """移动/驻留判定 + 迟滞 —— 降级阶梯 Level B。

    完全不需要地点数据库，极其鲁棒。
    「通勤中」本身就是一个 biome —— 路成了一个地方。
    """

    state: str = UNKNOWN
    _pending: str = UNKNOWN
    _streak: int = 0
    transitions: int = 0

    def update(self, distance: float, threshold: float = MOVE_THRESHOLD,
               fresh: bool = False) -> str:
        """喂入相邻扫描距离，返回确认后的状态。

        迟滞：需连续 HYSTERESIS 次指向同一状态才切换。
        这是防误报的关键 —— 单次扫描漏掉几个 AP 很常见。

        `fresh` 是第二条判据：本次扫描是否带进大量没见过的 AP。
        平滑距离会把「连续变化」压低（实测通勤只有 0.2~0.39，低于阈值），
        而新鲜度不受平滑影响 —— 它看的是「有没有新东西」而非「变了多少」。
        两条判据取或：距离超阈值**或**持续见到新 AP，都算移动。
        """
        raw = MOVING if (distance > threshold or fresh) else STAYING

        if raw == self._pending:
            self._streak += 1
        else:
            self._pending, self._streak = raw, 1

        if self._streak >= HYSTERESIS and self.state != raw:
            self.state = raw
            self.transitions += 1

        return self.state


# ---------------------------------------------------------------------------
# 感知核心
# ---------------------------------------------------------------------------


@dataclass
class SensingResult:
    """单次扫描的判定结果。"""

    ts: int
    ap_count: int
    state: str                      # moving / staying / unknown
    place: Optional[Place]
    match_score: float
    distance: float                 # 与上次扫描的距离
    is_new_place: bool
    motion_accum: float             # 累积移动量（对应 4.1.2）
    motion_events: int              # 已触发的移动量阈值次数
    transient_aps: int              # 本次新出现且上次没有的 AP 数 → 猎场遭遇源


class SensingCore:
    """感知层主循环。逐次喂 Scan，产出 SensingResult。

    移动量（motion_accum）是「走动 → 遇怪」的实现：
    没有 IMU 所以做不了步数，改用相邻扫描的加权 Jaccard 距离累积。
    这不是退而求其次 —— 步数奖励原地踏步也能刷的动作，
    移动量奖励空间位移，而且摇不出来（docs/04-gameplay.md#412）。
    """

    def __init__(
        self,
        only_24g: bool = False,
        motion_per_event: float = 3.0,
        smooth_window: int = SMOOTH_WINDOW,
    ):
        self.only_24g = only_24g
        self.motion_per_event = motion_per_event

        self.memory = PlaceMemory()
        self.motion = MotionState()
        self.smooth = SlidingSignature(window=smooth_window)

        self._prev_sig: Optional[Signature] = None
        self._prev_hashes: set[int] = set()
        self._prev_ts: Optional[int] = None

        self.motion_accum = 0.0
        self.motion_events = 0
        self.seen_hashes: set[int] = set()   # 历史见过的所有 AP（用于「新地方」判定）

    def feed(self, scan: Scan) -> SensingResult:
        if self.only_24g:
            scan = scan.only_24g()

        # 单帧指纹 —— 只用于 transient_aps（瞬现 AP 是猎场遭遇的原料，
        # 平滑会把它抹掉，见 docs/04-gameplay.md#411）
        frame_sig = Signature.from_scan(scan)
        cur_hashes = set(frame_sig.weights.keys())

        # 平滑指纹 —— 用于移动判定与地点匹配。
        # 单帧比对在真实稀疏环境下会被 AP 闪烁主导（实测静坐 20 分钟报出
        # 11 次状态转换），见 SMOOTH_WINDOW 的说明。
        self.smooth.push(scan)
        sig = self.smooth.current()

        # 与上次扫描的距离 → 移动判定
        if self._prev_sig is not None:
            dist = sig.distance(self._prev_sig)
        else:
            dist = 0.0   # 第一次没有参照，不算移动

        # 移动的第二条判据：AP 新鲜度。
        #
        # 单靠平滑距离不够 —— 平滑会把「连续变化」也压低。实测合成通勤数据
        # 距离只有 0.2~0.39（阈值 0.4），于是通勤被误判为驻留并沿路建了 5 个地点。
        #
        # 但通勤有个驻留没有的特征：**持续见到全新 AP**。驻留时 AP 集合封闭，
        # 偶有闪烁但都是老面孔；移动时每次扫描都带进没见过的 BSSID。
        # 这一条不受平滑影响，因为它看的是「有没有新东西」而非「变了多少」。
        fresh_ratio = (len(cur_hashes - self.seen_hashes) / len(cur_hashes)
                       if cur_hashes else 0.0)
        # 第一次扫描时 seen_hashes 为空，所有 AP 都"新" —— 那不是移动，
        # 只是还没有历史。等积累到一个窗口再启用这条判据。
        is_fresh = (len(self.smooth) >= self.smooth.window
                    and fresh_ratio >= FRESH_RATIO_THRESHOLD)

        state = self.motion.update(dist, fresh=is_fresh)

        # 距离本身是否指向「静止」。迟滞机制下 state 切换有延迟，
        # 移动的第一帧 state 仍是 staying —— 只看 state 会把通勤第一帧
        # 误建成新地点。用原始距离做即时否决。
        distance_is_settled = dist <= MOVE_THRESHOLD

        # 移动量累积。只在确认移动时累积，避免静坐时的抖动刷满进度
        if state == MOVING and self._prev_sig is not None:
            self.motion_accum += dist
            while self.motion_accum >= self.motion_per_event:
                self.motion_accum -= self.motion_per_event
                self.motion_events += 1

        # 转瞬即逝的 AP —— 用单帧哈希，不用平滑（平滑会抹掉一次性出现的 AP）
        transient = len(cur_hashes - self._prev_hashes) if self._prev_hashes else 0

        # 地点识别只在驻留时做：移动中指纹一直在变，记下来毫无意义，
        # 只会把 8 个槽位迅速塞满并把真正的地点挤掉。
        #
        # 注意这里同时看 state 和 distance：迟滞机制下状态切换要等 HYSTERESIS 次，
        # 而移动的第一帧此时仍是 staying —— 若只看 state，通勤第一帧会被误建成新地点。
        # 这是实测跑出来的 bug（7 天合成数据建出 8 个地点，实际只有 3 个）。
        #
        # 用平滑指纹匹配地点：地点应当是稳定的，用抗噪的那份更合理。
        place: Optional[Place] = None
        score = 0.0
        is_new = False
        settled = state != MOVING and distance_is_settled
        if settled and sig:
            place, is_new = self.memory.observe(sig, scan.ts)
            _, score = self.memory.match(sig)
            # biome 首次分类后冻结（docs/03-spawning.md#36）——
            # 世界是被「发现」的，不是每次重新掷骰。
            # 分类器在 gameplay 层，这里延迟导入避免循环依赖。
            if place.biome is None:
                try:
                    from gameplay import classify_biome
                    place.biome = classify_biome(scan.aps)
                except ImportError:
                    pass       # 纯感知层测试时 gameplay 可能不可用

            # 累积驻留时长（对应 2.2 的「驻留时长」可再生信号）
            if self._prev_ts is not None and not is_new:
                elapsed = scan.ts - self._prev_ts
                place.total_dwell += elapsed
                # 同时记进 biome 累计器 —— 它不随 LRU 淘汰丢失，
                # S7 进化的 biome 驻留条件依赖这份数据
                self.memory.add_dwell(place.biome, elapsed)

        self.seen_hashes |= cur_hashes
        self._prev_sig = sig
        self._prev_hashes = cur_hashes
        self._prev_ts = scan.ts

        return SensingResult(
            ts=scan.ts,
            ap_count=len(scan.aps),
            state=state,
            place=place,
            match_score=score,
            distance=dist,
            is_new_place=is_new,
            motion_accum=self.motion_accum,
            motion_events=self.motion_events,
            transient_aps=transient,
        )

    def run(self, scans: Iterable[Scan]) -> list[SensingResult]:
        return [self.feed(s) for s in scans]


# ---------------------------------------------------------------------------
# NDJSON 读取
# ---------------------------------------------------------------------------


def load_ndjson(path: str) -> list[Scan]:
    """读取采集器输出。跳过坏行而不是整个失败 —— 长跑采集偶有截断行。"""
    import json

    scans: list[Scan] = []
    bad = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                scans.append(Scan.from_json(json.loads(line)))
            except (ValueError, TypeError):
                bad += 1
    if bad:
        import sys
        print(f"警告：跳过 {bad} 行无法解析的数据", file=sys.stderr)
    return scans
