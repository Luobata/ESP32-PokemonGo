#!/usr/bin/env python3
"""回放采集数据，验证感知层算法。

用法：
    python3 sim/replay.py data/raw/day1.ndjson
    python3 sim/replay.py data/raw/*.ndjson --only-24g
    python3 sim/replay.py data/raw/day1.ndjson --verbose

回答 docs/07-roadmap.md#72 的验证目标：
  · 三态判别是否稳定
  · 转换检测有多少误报
  · 真实环境 AP 密度
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sensing import (  # noqa: E402
    CHANNEL_24G_MAX, MOVING, STAYING, SensingCore, load_ndjson,
)


def fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M:%S")


def fmt_dur(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    if seconds < 3600:
        return f"{seconds/60:.0f}m"
    return f"{seconds/3600:.1f}h"


def main() -> int:
    p = argparse.ArgumentParser(
        description="回放 WiFi 采集数据，验证感知层算法",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("files", nargs="+", help="NDJSON 采集文件")
    p.add_argument("--only-24g", action="store_true",
                   help="只保留 2.4GHz —— 模拟 ESP32-C3 的视角（强烈建议开启）")
    p.add_argument("--verbose", "-v", action="store_true", help="逐次扫描输出")
    p.add_argument("--motion-per-event", type=float, default=3.0,
                   help="累积多少移动量触发一次遭遇（默认 3.0）")
    args = p.parse_args()

    # 读取
    scans = []
    for f in args.files:
        if not os.path.exists(f):
            print(f"错误：找不到 {f}", file=sys.stderr)
            return 1
        s = load_ndjson(f)
        print(f"读取 {f}：{len(s)} 次扫描", file=sys.stderr)
        scans.extend(s)

    if not scans:
        print("错误：没有可用数据。先用 tools/collector 采集。", file=sys.stderr)
        return 1

    scans.sort(key=lambda s: s.ts)

    if any(s.degraded for s in scans):
        print("\n⚠️  数据含降级模式采集（伪 BSSID）——"
              "可验证逻辑，但判别质量不代表真实水平。\n", file=sys.stderr)

    # 跑
    core = SensingCore(only_24g=args.only_24g, motion_per_event=args.motion_per_event)
    results = core.run(scans)

    if args.verbose:
        print(f"\n{'时间':<16} {'AP':>4} {'状态':<8} {'距离':>6} {'地点':<12} {'得分':>6} {'瞬现':>5}")
        print("-" * 70)
        for r in results:
            place = r.place.name if r.place else "—"
            if r.is_new_place:
                place += " ✦"
            print(f"{fmt_ts(r.ts):<16} {r.ap_count:>4} {r.state:<8} "
                  f"{r.distance:>6.3f} {place:<12} {r.match_score:>6.3f} {r.transient_aps:>5}")

    # ---- 汇总 ----
    span = scans[-1].ts - scans[0].ts
    ap_counts = [r.ap_count for r in results]
    g24 = [sum(1 for a in s.aps if 0 < a.channel <= CHANNEL_24G_MAX) for s in scans]

    print("\n" + "=" * 62)
    print("感知层回放结果")
    print("=" * 62)

    print(f"\n扫描次数      {len(results)}")
    print(f"时间跨度      {fmt_dur(span)}（{fmt_ts(scans[0].ts)} → {fmt_ts(scans[-1].ts)}）")
    if len(results) > 1:
        print(f"平均间隔      {span / (len(results)-1):.0f}s")

    print(f"\nAP 密度       平均 {sum(ap_counts)/len(ap_counts):.1f}　"
          f"最少 {min(ap_counts)}　最多 {max(ap_counts)}")
    if not args.only_24g:
        print(f"其中 2.4GHz   平均 {sum(g24)/len(g24):.1f}　"
              f"（ESP32-C3 只能看到这部分，占 "
              f"{sum(g24)/max(sum(ap_counts),1)*100:.0f}%）")
        print("              ↑ 建议加 --only-24g 重跑以模拟设备真实视角")

    # 状态分布
    moving = sum(1 for r in results if r.state == MOVING)
    staying = sum(1 for r in results if r.state == STAYING)
    unknown = len(results) - moving - staying
    print(f"\n状态分布      移动 {moving}（{moving/len(results)*100:.0f}%）　"
          f"驻留 {staying}（{staying/len(results)*100:.0f}%）　"
          f"未定 {unknown}")
    print(f"状态转换      {core.motion.transitions} 次")

    # 转换误报的粗判：转换次数远超真实生活节律就是有问题
    hours = span / 3600.0
    if hours > 1:
        per_hour = core.motion.transitions / hours
        verdict = "正常" if per_hour < 2 else "偏高，疑似误报"
        print(f"              {per_hour:.1f} 次/小时 → {verdict}")
        if per_hour >= 2:
            print("              ↑ 真实生活一天只有 2~4 次转换（家→通勤→公司）。")
            print("                调高 MOVE_THRESHOLD 或 HYSTERESIS（sim/sensing.py）")

    # 地点
    print(f"\n识别地点      {len(core.memory.places)} 个")
    if core.memory.places:
        print(f"\n{'ID':<6} {'访问':>4} {'驻留':>8} {'指纹':>4}  {'首见':<16}")
        print("-" * 50)
        for pl in sorted(core.memory.places, key=lambda p: p.total_dwell, reverse=True):
            print(f"#{pl.pid:<5} {pl.visits:>4} {fmt_dur(pl.total_dwell):>8} "
                  f"{len(pl.sig):>4}  {fmt_ts(pl.first_seen):<16}")

    # 移动量
    print(f"\n移动量事件    {core.motion_events} 次"
          f"（当前累积 {core.motion_accum:.2f} / {args.motion_per_event}）")
    transient = sum(r.transient_aps for r in results)
    print(f"瞬现 AP 总数  {transient}　→ 猎场遭遇的原料")

    print(f"\n累计见过      {len(core.seen_hashes)} 个不同 AP")

    # 判读提示
    print("\n" + "-" * 62)
    print("怎么读这份结果（docs/07-roadmap.md#72）：")
    print("  · 地点数应该是 3~5 个。远多于此 = 阈值太严，同一地点被拆成多个")
    print("  · 状态转换应该 < 2 次/小时。远高于此 = 误报，需调迟滞")
    print("  · 若在单一地点采集，状态应几乎全是驻留、地点数为 1")
    print("-" * 62)

    return 0


if __name__ == "__main__":
    sys.exit(main())
