#!/usr/bin/env python3
"""从设备抓屏幕截图，存成 PNG。

用法：
    python3 tools/device/screenshot.py                # 触发并抓一张
    python3 tools/device/screenshot.py --out /tmp/p1.png
    python3 tools/device/screenshot.py --wait         # 只等，不触发（你手动按键）

## 为什么要这个

渲染类问题靠拍照调**极其低效**：拍一张、传一张、我猜一轮。
而且照片有反光、偏色、摩尔纹、透视变形 —— 判断「这个像素对不对」
根本靠不住。

设备把帧缓冲 base64 吐到串口，这边解码成 PNG，**像素级准确**。
一次往返几十秒，比拍照快得多，也能看清 1px 的偏差。

## 怎么触发

设备端：**B 键长按**（play_idle.c 里绑的）。
这个脚本也能自己触发 —— 走串口发一个字节让固件截图（还没做，
现在靠手按）。

## 输出格式（固件端 screen.c）

    @@SHOT <w> <h> rgb565le <band_h>
    @@BAND <y>
    <base64 行...>
    @@BAND <y>
    ...
    @@SHOTEND

逐带输出而非整屏一次 —— 固件不缓存整屏（那要 150KB static，
实测 DRAM 直接溢出 32624 字节）。
"""

from __future__ import annotations

import argparse
import base64
import re
import struct
import sys
import time
import zlib
from pathlib import Path

HERE = Path(__file__).resolve().parent

RE_SHOT = re.compile(rb"@@SHOT (\d+) (\d+) (\S+) (\d+)")
RE_BAND = re.compile(rb"@@BAND (\d+)")


def rgb565_to_rgb888(v: int) -> tuple[int, int, int]:
    """RGB565 → RGB888。低位补高位，避免最亮色达不到 255。"""
    r = (v >> 11) & 0x1F
    g = (v >> 5) & 0x3F
    b = v & 0x1F
    return (r << 3) | (r >> 2), (g << 2) | (g >> 4), (b << 3) | (b >> 2)


def write_png(path: Path, w: int, h: int, rows: list[bytes]) -> None:
    """最小 PNG 编码器 —— 不引第三方依赖（项目惯例：零依赖）。"""
    raw = b"".join(b"\x00" + r for r in rows)      # 每行前缀 filter type 0

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    png = b"\x89PNG\r\n\x1a\n"
    png += chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(raw, 9))
    png += chunk(b"IEND", b"")
    path.write_bytes(png)


def capture(port: str, seconds: float, trigger: bool) -> tuple:
    import serial

    ser = serial.Serial(port, 115200, timeout=0.3)
    if trigger:
        # 还没做串口触发命令，先提示手按
        print("请在设备上**长按 B 键（下键）**触发截图…", file=sys.stderr)

    buf = bytearray()
    t0 = time.time()
    got_start = False
    while time.time() - t0 < seconds:
        d = ser.read(8192)
        if d:
            buf += d
            if not got_start and b"@@SHOT " in buf:
                got_start = True
                print("  收到截图头，接收中…", file=sys.stderr)
            if got_start and b"@@SHOTEND" in buf:
                break
    ser.close()
    return bytes(buf), got_start


def parse(blob: bytes):
    m = RE_SHOT.search(blob)
    if not m:
        return None
    w, h, fmt, band_h = int(m.group(1)), int(m.group(2)), m.group(3), int(m.group(4))
    # 固件吐的是**交换之后**的字节，也就是屏幕真正收到的大端 RGB565。
    # 早期版本吐交换前的小端 —— 那让截图看不见字节序类的错误
    # （屏幕紫的时候截图还是绿的）。两种都认，老图还能解。
    if fmt not in (b"rgb565be", b"rgb565le"):
        print(f"未知格式 {fmt!r}", file=sys.stderr)
        return None
    big_endian = (fmt == b"rgb565be")

    body = blob[m.end():]
    end = body.find(b"@@SHOTEND")
    if end < 0:
        print("没收到 @@SHOTEND —— 传输被截断", file=sys.stderr)
        return None
    body = body[:end]

    # 按 @@BAND 切段
    bands: dict[int, bytes] = {}
    parts = RE_BAND.split(body)
    # split 后是 [前导, y1, 数据1, y2, 数据2, ...]
    for i in range(1, len(parts) - 1, 2):
        y = int(parts[i])
        b64 = b"".join(l.strip() for l in parts[i + 1].splitlines()
                       if l.strip() and not l.startswith(b"I (")
                       and not l.startswith(b"E ("))
        try:
            bands[y] = base64.b64decode(b64)
        except Exception as e:
            print(f"  band {y} 解码失败: {e}", file=sys.stderr)

    if not bands:
        return None

    rows = []
    for y in range(h):
        band_y = (y // band_h) * band_h
        data = bands.get(band_y)
        if data is None:
            rows.append(b"\x00\x00\x00" * w)      # 缺的带填黑
            continue
        off = (y - band_y) * w * 2
        row = bytearray()
        for x in range(w):
            i = off + x * 2
            if i + 1 >= len(data):
                row += b"\x00\x00\x00"
                continue
            v = ((data[i] << 8) | data[i + 1]) if big_endian \
                else (data[i] | (data[i + 1] << 8))
            row += bytes(rgb565_to_rgb888(v))
        rows.append(bytes(row))
    return w, h, rows, len(bands)


def main() -> int:
    ap = argparse.ArgumentParser(description="设备截图 → PNG")
    ap.add_argument("--out", default="")
    ap.add_argument("--port", default="")
    ap.add_argument("--seconds", type=float, default=60.0)
    ap.add_argument("--wait", action="store_true", help="只等，不提示触发")
    args = ap.parse_args()

    try:
        import serial  # noqa: F401
    except ImportError:
        print("需要 pyserial：pip3 install pyserial", file=sys.stderr)
        return 1

    sys.path.insert(0, str(HERE))
    import monitor
    port = monitor.find_port(args.port)

    blob, got = capture(port, args.seconds, not args.wait)
    if not got:
        print(f"{args.seconds:.0f} 秒内没收到截图。设备上长按 B 键了吗？",
              file=sys.stderr)
        return 1

    r = parse(blob)
    if not r:
        return 1
    w, h, rows, nbands = r

    out = Path(args.out) if args.out else Path(
        f"/tmp/shot-{time.strftime('%H%M%S')}.png")
    write_png(out, w, h, rows)
    print(f"{w}×{h}  {nbands} 条带  →  {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
