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
MOVE_THRESHOLD = 0.50   # 相邻扫描距离 > 此值判为「在移动」
HYSTERESIS = 2          # 状态切换需连续 N 次一致才确认
PLACE_SLOTS = 8         # LRU 槽位数（对应固件 512 字节预算）

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

    def update(self, distance: float, threshold: float = MOVE_THRESHOLD) -> str:
        """喂入相邻扫描距离，返回确认后的状态。

        迟滞：需连续 HYSTERESIS 次指向同一状态才切换。
        这是防误报的关键 —— 单次扫描漏掉几个 AP 很常见。
        """
        raw = MOVING if distance > threshold else STAYING

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
    ):
        self.only_24g = only_24g
        self.motion_per_event = motion_per_event

        self.memory = PlaceMemory()
        self.motion = MotionState()

        self._prev_sig: Optional[Signature] = None
        self._prev_hashes: set[int] = set()
        self._prev_ts: Optional[int] = None

        self.motion_accum = 0.0
        self.motion_events = 0
        self.seen_hashes: set[int] = set()   # 历史见过的所有 AP（用于「新地方」判定）

    def feed(self, scan: Scan) -> SensingResult:
        if self.only_24g:
            scan = scan.only_24g()

        sig = Signature.from_scan(scan)
        cur_hashes = set(sig.weights.keys())

        # 与上次扫描的距离 → 移动判定
        if self._prev_sig is not None:
            dist = sig.distance(self._prev_sig)
        else:
            dist = 0.0   # 第一次没有参照，不算移动

        state = self.motion.update(dist)

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

        # 转瞬即逝的 AP —— 猎场遭遇的天然映射（docs/04-gameplay.md#411）
        transient = len(cur_hashes - self._prev_hashes) if self._prev_hashes else 0

        # 地点识别只在驻留时做：移动中指纹一直在变，记下来毫无意义，
        # 只会把 8 个槽位迅速塞满并把真正的地点挤掉。
        #
        # 注意这里同时看 state 和 distance：迟滞机制下状态切换要等 HYSTERESIS 次，
        # 而移动的第一帧此时仍是 staying —— 若只看 state，通勤第一帧会被误建成新地点。
        # 这是实测跑出来的 bug（7 天合成数据建出 8 个地点，实际只有 3 个）。
        place: Optional[Place] = None
        score = 0.0
        is_new = False
        settled = state != MOVING and distance_is_settled
        if settled and sig:
            place, is_new = self.memory.observe(sig, scan.ts)
            _, score = self.memory.match(sig)
            # 累积驻留时长（对应 2.2 的「驻留时长」可再生信号）
            if self._prev_ts is not None and not is_new:
                place.total_dwell += scan.ts - self._prev_ts

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
