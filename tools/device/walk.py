#!/usr/bin/env python3
"""走一遍完整玩法链路，逐页截图。

用法：
    python3 tools/device/walk.py                 # 默认路径
    python3 tools/device/walk.py --keys c,A,b,a  # 自定义
    python3 tools/device/walk.py --out /tmp/walk # 截图目录

## 为什么要这个

P1→P2→P3→P4→P6 要按十几次键，而每验证一次改动就得走一遍。
靠人按的问题不是累 —— 是**我自己没法验证**，改完只能烧进去请人帮忙。

固件侧的 dbg.c 从串口读单字符当按键，这边把一串键发过去，
每一步之后截一张图。渲染与交互从此都能自助验证。

## 键位

    a/b/c  单击 A/B/C
    A/B/C  双击
    s      截图（不经过按键）

默认路径 `c a b a a`：
    c  P1 按 C     → P2 遭遇列表
    a  P2 A 单击   → P3 战斗（选中遭遇；双击被忽略，P2 只认单击）
    b  P3 按 B     → 开打
    a  P3 按 A     → P4 捕获
    a  P4 按 A     → 投球
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

RE_SHOT = re.compile(rb"@@SHOT (\d+) (\d+) (\S+) (\d+)")


def main() -> int:
    ap = argparse.ArgumentParser(description="走一遍玩法链路并逐页截图")
    ap.add_argument("--keys", default="c,a,b,a,a",
                    help="逗号分隔的按键序列")
    ap.add_argument("--out", default="/tmp/walk")
    ap.add_argument("--port", default="")
    ap.add_argument("--settle", type=float, default=2.5,
                    help="每步之后等多久再截图（秒）")
    ap.add_argument("--no-reset", action="store_true",
                    help="不复位 —— 保留设备当前状态（比如已攒的遭遇）")
    args = ap.parse_args()

    try:
        import serial
    except ImportError:
        print("需要 pyserial：pip3 install pyserial", file=sys.stderr)
        return 1

    import monitor
    import screenshot as shot

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    port = monitor.find_port(args.port)
    ser = serial.Serial(port, 115200, timeout=0.3)

    if not args.no_reset:
        # 复位让状态可复现 —— 但**会清掉已攒的遭遇队列**。
        # 队列空的话 P2 进不去，所以复位后要等第一次扫描（约 3 秒）
        # 产出基地遭遇。--no-reset 可以保留现场。
        ser.setDTR(False); ser.setRTS(True); time.sleep(0.1); ser.setRTS(False)
        print("复位，等第一次扫描产出遭遇…", file=sys.stderr)
        time.sleep(8)

    keys = [k for k in args.keys.split(",") if k]
    results = []

    def grab(label: str) -> str | None:
        """发一个截图命令并收 PNG。

        **要处理「一次收到多张」** —— 页面自己也有 1 秒后的自动截图，
        与这里的 `s` 命令撞上时串口里会有两张交错。
        第一版没处理，parse 从第一个 @@SHOT 找到最后一个 @@SHOTEND，
        中间夹着第二张的头，解码必然失败（表现是「传输被截断」，
        而实际上是收多了不是收少了）。
        取**最后一张完整的**：它对应最新的画面。
        """
        ser.reset_input_buffer()
        ser.write(b"s")
        ser.flush()
        buf = bytearray()
        t0 = time.time()
        while time.time() - t0 < 30:
            d = ser.read(8192)
            if d:
                buf += d
                if buf.count(b"@@SHOTEND") >= 1 and b"@@SHOT " in buf:
                    # 再多收 0.4 秒，让可能的第二张也进来
                    t_extra = time.time()
                    while time.time() - t_extra < 0.4:
                        buf += ser.read(8192)
                    break
        if b"@@SHOTEND" not in buf:
            print(f"  {label}: 没收到截图", file=sys.stderr)
            return None

        # 切出最后一段完整的 @@SHOT…@@SHOTEND
        blob = bytes(buf)
        end = blob.rfind(b"@@SHOTEND")
        start = blob.rfind(b"@@SHOT ", 0, end)
        if start < 0:
            print(f"  {label}: 找不到完整的一张", file=sys.stderr)
            return None
        r = shot.parse(blob[start:end + len(b"@@SHOTEND")])
        if not r:
            print(f"  {label}: 解码失败", file=sys.stderr)
            return None
        w, h, rows, _ = r
        path = out_dir / f"{label}.png"
        shot.write_png(path, w, h, rows)
        return str(path)

    print(f"起点截图 → ", end="", file=sys.stderr, flush=True)
    p = grab("00-start")
    print(p or "失败", file=sys.stderr)
    results.append(("(起点)", p))

    for i, k in enumerate(keys, 1):
        ser.write(k.encode())
        ser.flush()
        time.sleep(args.settle)
        label = f"{i:02d}-key-{k}"
        print(f"按 {k} → ", end="", file=sys.stderr, flush=True)
        p = grab(label)
        print(p or "失败", file=sys.stderr)
        results.append((k, p))

    ser.close()

    print(f"\n{len(results)} 张截图 → {out_dir}")
    for k, p in results:
        print(f"  {k:8s} {p or '（失败）'}")
    return 0 if all(p for _, p in results) else 1


if __name__ == "__main__":
    sys.exit(main())
