#!/usr/bin/env python3
"""长跑实测 —— 时钟漂移 + 续航，一份数据回答两个问题。

用法：
    python3 tools/device/soak.py --hours 8
    python3 tools/device/soak.py --report /tmp/soak-xxx.jsonl   # 只看结果

设备要处于 Collect 页且已按 OK 开始采集。这个脚本挂着读串口，
每收到一条采集记录就记下「设备说几点」与「主机说几点」的配对。

## 两个待实测项，一份数据

### ① 时钟漂移（决定养成线的时间尺度）

实测配置是 `CONFIG_RTC_CLK_SRC_INT_RC=y` —— **用的是内部 RC 振荡器，
不是外置 32.768kHz 晶振**（`SOC_CLK_XTAL32K_SUPPORTED=y` 只说明芯片
支持，不代表板子焊了）。内部 RC 典型精度 ±5%，还有温漂。

这条卡着 docs/01-constitution.md 的一个未决项：三条状态轴的衰减率
是按「小时」标定的（SATIETY_DECAY_PER_HOUR=4.0 等）。若走时误差大到
一天差几十分钟，那些常量就得改按「天」标定，S10 的日切判定也要跟着改。

设备侧 `ts` 是 `esp_timer_get_time()`（开机微秒数），主机侧用
`time.time()`。两者的**斜率差**就是漂移率：

    drift_ppm = (dev_elapsed / host_elapsed - 1) * 1e6

参考量级：外置晶振 ±20ppm（一天差 1.7 秒），内部 RC 可能到
±50000ppm（一天差 72 分钟）。差一个数量级，结论完全不同。

### ② 续航（决定扫描频率上限）

采集记录里带 `bat` 字段（CW2017 电量计读数）。挂着跑几小时就能算出
「按当前扫描频率，满电能撑几天」——**不用外接电流表**。

注意 CW2017 的 SOC 是百分比整数，前几个小时可能一直显示 100%。
所以这个脚本要跑够长（建议 ≥4 小时），或者从半电状态开始跑。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
RE_ROW = re.compile(rb'\{"ts":(\d+),.*?"bat":(-?\d+)\}')


def soak(hours: float, out: Path, port: str = "") -> int:
    import serial
    sys.path.insert(0, str(HERE))
    import monitor

    p = monitor.find_port(port)
    ser = serial.Serial(p, 115200, timeout=1.0)
    print(f"长跑 {hours:.1f} 小时，记录 → {out}", file=sys.stderr)
    print("设备要在 Collect 页且已按 OK 开始采集。Ctrl-C 可提前结束。",
          file=sys.stderr)

    deadline = time.time() + hours * 3600
    buf = b""
    n = 0
    out.parent.mkdir(parents=True, exist_ok=True)
    f = out.open("w", encoding="utf-8")
    try:
        while time.time() < deadline:
            d = ser.read(4096)
            if not d:
                continue
            buf += d
            # 按行处理，留下不完整的尾巴
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                m = RE_ROW.search(line)
                if not m:
                    continue
                rec = {
                    "host": time.time(),          # 主机墙钟
                    "dev": int(m.group(1)),       # 设备开机秒数
                    "bat": int(m.group(2)),       # 电量百分比
                }
                f.write(json.dumps(rec) + "\n")
                f.flush()                          # 随时可 Ctrl-C 不丢数据
                n += 1
                if n % 10 == 0:
                    el = (time.time() - (deadline - hours * 3600)) / 3600
                    print(f"  {n} 条  已跑 {el:.1f}h  电量 {rec['bat']}%",
                          file=sys.stderr)
    except KeyboardInterrupt:
        print("\n提前结束", file=sys.stderr)
    finally:
        f.close()
        ser.close()
    print(f"共 {n} 条 → {out}", file=sys.stderr)
    return n


def report(path: Path) -> None:
    rows = [json.loads(l) for l in path.open(encoding="utf-8")]
    if len(rows) < 3:
        print(f"样本太少（{len(rows)} 条），至少要 3 条", file=sys.stderr)
        return

    h0, d0 = rows[0]["host"], rows[0]["dev"]
    h1, d1 = rows[-1]["host"], rows[-1]["dev"]
    host_el = h1 - h0
    dev_el = d1 - d0

    print(f"══ {path.name} ══  {len(rows)} 条记录")
    print(f"  主机跨度 {host_el / 3600:.2f} h")
    print(f"  设备跨度 {dev_el / 3600:.2f} h")

    if host_el < 600:
        print("\n  ⚠️ 跨度不足 10 分钟，漂移结论不可信 —— 采集间隔本身"
              "就有几秒抖动，短窗口下它会淹没真实漂移。")
    if host_el > 0:
        ppm = (dev_el / host_el - 1) * 1e6
        print(f"\n  时钟漂移 {ppm:+.0f} ppm"
              f"  →  一天差 {abs(ppm) * 86400 / 1e6:.1f} 秒")
        # 量级判断 —— 这才是要的结论
        if abs(ppm) < 100:
            verdict = "外置晶振级别，养成线可安全按「小时」标定"
        elif abs(ppm) < 2000:
            verdict = ("一天差几分钟。三条轴按小时标定仍可用，"
                       "但 S10 日切判定要容忍偏移")
        else:
            verdict = ("⚠️ 一天差几十分钟以上 —— 三条轴的衰减率"
                       "可能要改按「天」标定，S10 日切判定必须重做")
        print(f"  → {verdict}")

    bats = [(r["host"] - h0, r["bat"]) for r in rows if r["bat"] >= 0]
    if bats:
        b0, b1 = bats[0][1], bats[-1][1]
        print(f"\n  电量 {b0}% → {b1}%")
        if b1 < b0 and host_el > 0:
            rate = (b0 - b1) / (host_el / 3600)      # %/小时
            print(f"  耗电 {rate:.2f} %/h  →  满电约 {100 / rate:.1f} 小时"
                  f"（{100 / rate / 24:.1f} 天）")
            print("  （按当前扫描间隔。改间隔要重测）")
        else:
            print("  尚未看到下降 —— CW2017 的 SOC 是整数百分比，"
                  "满电时会在 100% 停留很久。跑更长，或从半电开始。")


def main() -> int:
    ap = argparse.ArgumentParser(description="长跑：时钟漂移 + 续航")
    ap.add_argument("--hours", type=float, default=8.0)
    ap.add_argument("--out", default="")
    ap.add_argument("--port", default="")
    ap.add_argument("--report", default="", help="只分析已有记录")
    args = ap.parse_args()

    if args.report:
        report(Path(args.report))
        return 0

    out = Path(args.out) if args.out else Path(
        f"/tmp/soak-{time.strftime('%Y%m%d-%H%M%S')}.jsonl")
    if soak(args.hours, out, args.port):
        report(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
