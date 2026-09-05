#!/usr/bin/env python3
"""收 P1 的 @@AXES 日志，拟合三条轴的实际衰减速率。

用法：
    python3 tools/device/decay.py --minutes 60
    python3 tools/device/decay.py --report /tmp/decay-xxx.jsonl

## 这个脚本回答什么

nurture.c 与 sim/gameplay.py 已经逐拍对账过（verify_nurture.py），
但那是**在宿主上**、用构造的时间序列。真机上还有两件事没验证：

  · **esp_timer 的走时准不准** —— 实测配置是内部 RC 振荡器
    （CONFIG_RTC_CLK_SRC_INT_RC），典型 ±5%。若真差 5%，
    「4/小时」实际是 3.8~4.2/小时
  · **tick 会不会被饿死** —— LVGL 定时器与 WiFi 扫描抢 CPU，
    极端情况下 tick 可能几秒才跑一次。nurture 按时长算所以不怕漏，
    但要确认它真的没漏

## 为什么不用截图

截图靠开机 1 秒后那次自动触发，再截一张就得复位 ——
而复位会 nurture_init，把要测的状态清掉。
日志是设备自己吐的，不打扰状态。

## 判据

饱食 4.0/小时、心情 3.0/小时、体能 +6.0/小时（白天）。
拟合斜率与这三个数比，偏差 5% 以内算走时正常；
超过 10% 说明 esp_timer 漂得厉害，S10 的日切判定要重新考虑。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

RE_AXES = re.compile(r"@@AXES (\d+) (\d+) (\d+) (\d+) (\d+)")

# 期望速率（每小时），来自 sim/gameplay.py
EXPECT = {"饱食": -4.0, "心情": -3.0, "体能": +6.0}


def fit_slope(xs: list[float], ys: list[float]) -> float:
    """最小二乘斜率。不引 numpy —— 项目惯例是零依赖。"""
    n = len(xs)
    if n < 2:
        return 0.0
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    den = sum((x - mx) ** 2 for x in xs)
    return num / den if den else 0.0


def report(rows: list[dict]) -> int:
    if len(rows) < 3:
        print(f"只有 {len(rows)} 个采样点，至少要 3 个才能拟合", file=sys.stderr)
        return 1

    # 设备时间（微秒）→ 小时
    h = [(r["dev_us"] - rows[0]["dev_us"]) / 3.6e9 for r in rows]
    span = h[-1]
    print(f"{len(rows)} 个采样点，跨度 {span:.2f} 小时\n")

    ok = True
    for key, want in EXPECT.items():
        ys = [float(r[key]) for r in rows]
        got = fit_slope(h, ys)
        # 百分比取整会让短跨度的拟合很粗糙 —— 跨度不足 0.5 小时时
        # 一格的量化误差就能占 20%，这时只报数不判定。
        if span < 0.5:
            print(f"  {key}  实测 {got:+.2f}/小时  期望 {want:+.1f}"
                  f"　（跨度不足 30 分钟，量化误差太大，不判定）")
            continue
        dev = abs(got - want) / abs(want) * 100
        mark = "✅" if dev <= 10 else "❌"
        if dev > 10:
            ok = False
        print(f"  {key}  实测 {got:+.2f}/小时  期望 {want:+.1f}"
              f"  偏差 {dev:.0f}%  {mark}")

    # 主机时钟 vs 设备时钟 —— 顺带把时钟漂移也测了
    #
    # **只算首尾，不算逐段** —— 主机侧的时间戳是「读到这一行的时刻」，
    # 受串口缓冲与 GIL 调度影响，单段抖动能到 ±1 秒。
    # 在 2 分钟的段上那就是 ±8000ppm 的假象（实测见过 +5103 / -2859
    # 交替出现，而设备侧的间隔稳定在 120.445s 分毫不差）。
    # 拉长基线抖动就摊薄了：跑 2 小时，±1 秒只剩 ±140ppm。
    if all("host_s" in r for r in rows) and len(rows) >= 2:
        dev_el = (rows[-1]["dev_us"] - rows[0]["dev_us"]) / 1e6
        host_el = rows[-1]["host_s"] - rows[0]["host_s"]
        if host_el > 0:
            ppm = (dev_el / host_el - 1) * 1e6
            # 采样抖动的量级：假设单次读取误差 ±1 秒
            jitter = 2.0 / host_el * 1e6
            print(f"\n  时钟漂移 {ppm:+.0f} ppm"
                  f"（一天差 {abs(ppm) * 86400 / 1e6:.0f} 秒）")
            print(f"    采样抖动约 ±{jitter:.0f} ppm —— "
                  f"{'漂移可信' if abs(ppm) > jitter * 2 else '还在噪声里，跑久一点'}")
            print("    参考：外置晶振 ±20ppm，内部 RC 可能到 ±50000ppm")

    if span < 0.5:
        print("\n⚠️  跨度不足 30 分钟，结论不可靠 —— 再跑久一点")
        return 0
    print("\n✅ 三条轴的实测速率与 S4 常量一致" if ok else
          "\n❌ 实测速率偏离 S4 常量 —— 检查 esp_timer 走时或 tick 是否被饿死")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="P1 三条轴衰减速率实测")
    ap.add_argument("--minutes", type=float, default=60.0)
    ap.add_argument("--port", default="")
    ap.add_argument("--out", default="")
    ap.add_argument("--report", default="", help="只分析已有的 jsonl")
    args = ap.parse_args()

    if args.report:
        rows = [json.loads(l) for l in Path(args.report).read_text().splitlines()
                if l.strip()]
        return report(rows)

    try:
        import serial
    except ImportError:
        print("需要 pyserial：pip3 install pyserial", file=sys.stderr)
        return 1

    sys.path.insert(0, str(HERE))
    import monitor
    port = monitor.find_port(args.port)

    out = Path(args.out) if args.out else Path(
        f"/tmp/decay-{time.strftime('%H%M%S')}.jsonl")
    print(f"收 {args.minutes:.0f} 分钟的 @@AXES → {out}", file=sys.stderr)
    print("（设备要停在 P1 待机页，不要复位 —— 复位会清掉状态）",
          file=sys.stderr)

    ser = serial.Serial(port, 115200, timeout=1.0)
    rows: list[dict] = []
    t0 = time.time()
    buf = b""
    with out.open("w") as f:
        while time.time() - t0 < args.minutes * 60:
            buf += ser.read(4096)
            *lines, buf = buf.split(b"\n")
            for raw in lines:
                m = RE_AXES.search(raw.decode("utf-8", "replace"))
                if not m:
                    continue
                r = {"dev_us": int(m.group(1)), "host_s": time.time(),
                     "饱食": int(m.group(2)), "心情": int(m.group(3)),
                     "体能": int(m.group(4)), "亲密": int(m.group(5))}
                rows.append(r)
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  [{len(rows):3d}] 饱食{r['饱食']} 心情{r['心情']} "
                      f"体能{r['体能']} 亲密{r['亲密']}", file=sys.stderr)
    ser.close()
    return report(rows)


if __name__ == "__main__":
    sys.exit(main())
