"""S18 自动存档 —— 什么时候写、写多少。

对应 docs/systems/S18-autosave.md。

## 这个系统补的又是一个断层

`DualBufferSave` 建好了（S6），双 buffer + CRC32 都验证过 ——
但**游戏逻辑里没有任何地方调用它**。全项目只有验收平台调过 `save()`。
存档机制存在，却从不存档。

## 一个计算翻转了原有假设

S6 文档一直把 flash 磨损当约束（08-systems.md 里 S6 标着「⏳ flash 磨损」）。
实际算一下：

    存档 1188 B → 占 1 个 4096 B 扇区
    NOR flash 典型寿命 10 万次擦写/扇区

    每次遭遇都存（28 次/天）→ 撑 10 年
    每小时存一次            → 撑 11 年
    每天存一次              → 撑 274 年

**磨损不是约束**。这台设备的电池、屏幕、按键都活不到 10 年。

所以真正的约束是另一个：**掉电时丢多少进度**。
这类设备随时会被拔电，而养成与成绩是唯一不可再生的。

## 分级策略：按「丢了有多痛」决定

    立即存    不可再生且不可重现 —— 捕获、进化、徽章、闪光
    延迟存    可再生或影响小     —— 遭遇入队、道具掉落、移动量
    定时存    连续量             —— 三条轴、驻留时长

「立即存」那一档是关键：玩家抓到闪光的下一秒拔电，那份运气不能丢
（1/512 的东西，重来一次可能几周才再遇到）。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 触发分级
# ---------------------------------------------------------------------------

# 立即存 —— 不可再生且不可重现的事件。
#
# 判据不是「重要」而是「丢了能不能再拿回来」：
# 升级可以再练，捕获到的闪光不能再遇。
IMMEDIATE = (
    "capture",          # 捕获成功（实体入队伍/仓库）
    "shiny_seen",       # 见到闪光 —— 哪怕跑了，那份遗憾也要存下（S8）
    "evolve",           # 进化
    "badge",            # 取得徽章
    "elite_clear",      # 四天王 / 赤红通关
    "starter_chosen",   # 开场选定伙伴（存档的诞生）
    "nickname",         # 改名 —— 玩家主动的表达，丢了很扫兴
)

# 延迟存 —— 攒够 N 个事件或 T 秒后写一次。
# 这些丢了可以再来：遭遇会再刷、道具会再掉。
DEFERRED = (
    "encounter",        # 遭遇入队
    "item_drop",        # 道具掉落
    "battle",           # 战斗结束
    "care",             # 照料（喂食/玩耍/休息）
    "motion",           # 移动量事件
    "place",            # 新地点
)

# 攒够几个就写。**实测把这个数从 5 调到 2**：
#
# 一天 39 个事件的分布里，延迟事件的间隔中位数是 30 分钟，
# 而 DEFER_SECONDS 是 15 分钟 —— 于是「攒够 5 个」这条路径
# 一次都没触发过，23 次写入全是超时触发的。那个阈值等于不存在。
#
# 调到 2 的理由是取向：这是个休闲收集游戏，宁可多写几次，
# 也不要让玩家的进度在内存里悬 15 分钟。磨损反正撑 8 年。
DEFER_COUNT = 2
DEFER_SECONDS = 900         # 或者 15 分钟到了就写（兜底，不是主路径）

# 定时存 —— 连续量（三条轴、驻留时长）本身在不停变化，
# 没有「事件」可挂。每小时一次，与感知层向 flash 提交的节奏对齐。
PERIODIC_SECONDS = 3600

# 关机前必存。这是唯一能主动做的防掉电措施 ——
# 如果设备有电量检测，低电时也该触发一次。
SHUTDOWN_TRIGGERS = ("sleep", "low_battery", "user_off")


@dataclass
class SaveStats:
    """存档统计 —— 用来验收「频率合理吗、磨损够吗」。"""

    writes: int = 0
    immediate: int = 0
    deferred_flushes: int = 0
    periodic: int = 0
    shutdown: int = 0
    skipped: int = 0            # 因为没有脏数据而跳过的
    by_reason: dict = field(default_factory=dict)

    def note(self, kind: str, reason: str) -> None:
        self.writes += 1
        setattr(self, kind, getattr(self, kind) + 1)
        self.by_reason[reason] = self.by_reason.get(reason, 0) + 1


@dataclass
class AutoSave:
    """自动存档调度器。

    定长状态、无动态分配（除统计），可直接照搬进 C。

    用法：
        auto = AutoSave(dual_buffer)
        auto.on_event("capture", ts, save_data)     # 立即写
        auto.on_event("encounter", ts, save_data)   # 攒着
        auto.tick(ts, save_data)                    # 每帧调，处理定时与超时
    """

    dual: object                        # DualBufferSave
    pending: int = 0                    # 攒了几个延迟事件
    last_write_ts: int = 0
    last_periodic_ts: int = 0
    first_defer_ts: int = 0             # 第一个延迟事件的时刻
    dirty: bool = False                 # 有未写入的变化吗
    stats: SaveStats = field(default_factory=SaveStats)

    # -- 事件入口 -----------------------------------------------------------

    def on_event(self, event: str, ts: int, data) -> bool:
        """记录一个事件。返回是否触发了写入。"""
        if event in IMMEDIATE:
            self._write(ts, data, "immediate", event)
            return True

        if event in DEFERRED:
            self.dirty = True
            if self.pending == 0:
                self.first_defer_ts = ts
            self.pending += 1
            if self.pending >= DEFER_COUNT:
                self._write(ts, data, "deferred_flushes",
                            f"攒够 {DEFER_COUNT} 个")
                return True
            return False

        if event in SHUTDOWN_TRIGGERS:
            # 关机前必存 —— 即使没有脏数据也存，因为「没脏」的判断
            # 可能本身是错的（某个模块改了状态但没通知我们）。
            # 关机路径上多写一次的代价可以忽略。
            self._write(ts, data, "shutdown", event)
            return True

        return False

    def tick(self, ts: int, data) -> bool:
        """每帧调用。处理延迟超时与定时存档。"""
        # 延迟事件超时
        if (self.pending > 0
                and ts - self.first_defer_ts >= DEFER_SECONDS):
            self._write(ts, data, "deferred_flushes",
                        f"延迟超时 {DEFER_SECONDS}s")
            return True

        # 定时存档 —— 只在有脏数据时写
        if ts - self.last_periodic_ts >= PERIODIC_SECONDS:
            self.last_periodic_ts = ts
            if self.dirty:
                self._write(ts, data, "periodic", "定时")
                return True
            # **没脏就不写** —— 三条轴虽然一直在变（时间推进），
            # 但若玩家整小时没碰设备，那些变化下次读档时用 last_ts
            # 重算就有（S4 的 advance 只需要「过了多久」）。
            # 这一条把待机时的写入降到零。
            self.stats.skipped += 1
        return False

    # -- 内部 ---------------------------------------------------------------

    def _write(self, ts: int, data, kind: str, reason: str) -> None:
        self.dual.save(data)
        self.pending = 0
        self.dirty = False
        self.last_write_ts = ts
        self.stats.note(kind, reason)

    # -- 查询 ---------------------------------------------------------------

    @property
    def unsaved_events(self) -> int:
        return self.pending

    def seconds_since_write(self, ts: int) -> int:
        return ts - self.last_write_ts


# ---------------------------------------------------------------------------
# 磨损预算
# ---------------------------------------------------------------------------

FLASH_ERASE_CYCLES = 100_000        # NOR flash 典型寿命（待真机确认）
FLASH_SECTOR = 4096                 # ESP32 擦除粒度


def wear_budget(writes_per_day: float, save_bytes: int = 1188) -> dict:
    """磨损预算 —— 这个频率能撑多久。

    结论先说：**磨损不是约束**。即使每次遭遇都存（28 次/天）也能撑 10 年，
    而这台设备的电池、屏幕、按键都活不到那时候。

    S6 文档原本把磨损列为待验证的阻塞项，那个判断需要修正。
    """
    sectors = -(-save_bytes // FLASH_SECTOR)
    days = FLASH_ERASE_CYCLES / max(writes_per_day, 1e-9)
    return {
        "writesPerDay": writes_per_day,
        "sectors": sectors,
        "days": round(days),
        "years": round(days / 365, 1),
        "ok": days > 365 * 5,           # 5 年以上就当没有约束
    }


def simulate(events: list, dual, data, verbose: bool = False) -> SaveStats:
    """跑一串事件，看写入次数。

    events: [(ts, event_name), ...]
    """
    auto = AutoSave(dual)
    if events:
        auto.last_periodic_ts = events[0][0]
        auto.last_write_ts = events[0][0]
    for ts, ev in events:
        auto.tick(ts, data)
        wrote = auto.on_event(ev, ts, data)
        if verbose and wrote:
            print(f"  {ts}: {ev} → 写入")
    return auto.stats
