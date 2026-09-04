#!/usr/bin/env python3
"""设备串口监控 —— 复位、抓日志、解析启动信息。

用法：
    python3 tools/device/monitor.py                 # 复位并抓 10 秒启动日志
    python3 tools/device/monitor.py --info          # 只打印解析出的硬件事实
    python3 tools/device/monitor.py --follow        # 持续跟随（Ctrl-C 停）
    python3 tools/device/monitor.py --seconds 30    # 抓 30 秒
    python3 tools/device/monitor.py --raw           # 不解析，原样输出

## 为什么不直接用 idf.py monitor

`idf.py monitor` 要求装好 ESP-IDF 环境（几 GB），而**读日志不需要它**。
这个脚本只依赖 pyserial，让「看设备在说什么」这件事零门槛 ——
在还没搭工具链、或在 CI 里只想验证设备活着的时候都能用。

真要编译烧写时仍然用 `idf.py`，那是它该干的活。

## 端口识别

设备会枚举出**两个** Espressif 串口，别选错：

    VID:PID=303A:1001  USB JTAG/serial debug unit  ← 芯片原生调试口，日志在这
    VID:PID=303A:4005  ColoPlay                    ← 固件自己注册的 CDC

我第一次读了后者，收到的全是乱码 —— 那不是波特率问题，
是那个口根本不输出 ESP-IDF 日志。默认选 PID 0x1001。

零第三方依赖除 pyserial。
"""

from __future__ import annotations

import argparse
import re
import sys
import time

# 芯片原生 USB-Serial-JTAG。日志走这个口。
VID_ESPRESSIF = 0x303A
PID_JTAG = 0x1001

# 从启动日志里挖硬件事实。每条都是「真机说的」，比文档可信。
#
# 顺序即输出顺序，按「先芯片后外设」排 —— 读的人通常从上往下找。
BOOT_FACTS = [
    ("芯片",     r"chip revision:\s*(\S+)"),
    ("ESP-IDF",  r"ESP-IDF:\s+(\S+)"),
    ("flash",    r"SPI Flash Size\s*:\s*(\S+)"),
    ("CPU",      r"cpu freq:\s*(\d+)\s*Hz"),
    ("固件",     r"Project name:\s+(\S+)"),
    ("版本",     r"App version:\s+(\S+)"),
    ("编译时间", r"Compile time:\s+(.+)"),
]

# 可用堆 —— 这条要累加，单独处理。
RE_HEAP = re.compile(r"heap_init: At [0-9A-Fa-f]+ len [0-9A-Fa-f]+ \(\s*(\d+) KiB\)")
RE_PART = re.compile(r"boot:\s+\d+ (\S+)\s+.*?([0-9a-f]{8}) ([0-9a-f]{8})")
RE_I2C = re.compile(r"发现设备 @ (0x[0-9A-Fa-f]+)")


def find_port(explicit: str = "") -> str:
    """挑串口。显式指定优先，否则找 Espressif 的 JTAG 口。"""
    from serial.tools import list_ports

    if explicit:
        return explicit
    cands = list(list_ports.comports())
    for p in cands:
        if p.vid == VID_ESPRESSIF and p.pid == PID_JTAG:
            return p.device
    # 退而求其次：任何 Espressif 口
    for p in cands:
        if p.vid == VID_ESPRESSIF:
            print(f"⚠️  没找到 JTAG 口（PID {PID_JTAG:04X}），"
                  f"退回 {p.device}（PID {p.pid:04X}）—— 可能读不到日志",
                  file=sys.stderr)
            return p.device
    raise SystemExit(
        "找不到 Espressif 串口。检查：\n"
        "  · USB 线是否只供电不传数据（换一根）\n"
        "  · 设备是否已开机\n"
        f"  · 当前串口：{', '.join(p.device for p in cands) or '无'}")


def reset(ser) -> None:
    """USB-Serial-JTAG 的复位序列。

    与 esptool 的 hard reset 一致：RTS 拉高再放开。
    DTR 必须保持 False —— 拉高会让芯片进下载模式而不是运行。
    """
    ser.setDTR(False)
    ser.setRTS(True)
    time.sleep(0.1)
    ser.setRTS(False)
    ser.setDTR(False)
    time.sleep(0.1)


def capture(port: str, seconds: float, do_reset: bool = True,
            echo: bool = False) -> str:
    import serial

    ser = serial.Serial(port, 115200, timeout=0.2)
    try:
        if do_reset:
            reset(ser)
        buf = bytearray()
        t0 = time.time()
        while time.time() - t0 < seconds:
            d = ser.read(4096)
            if d:
                buf += d
                if echo:
                    sys.stdout.write(d.decode("utf-8", "replace"))
                    sys.stdout.flush()
        return buf.decode("utf-8", "replace")
    finally:
        ser.close()


def follow(port: str) -> None:
    """持续跟随，不复位 —— 用于看运行中的设备。"""
    import serial

    ser = serial.Serial(port, 115200, timeout=0.2)
    print(f"跟随 {port}（Ctrl-C 停止）", file=sys.stderr)
    try:
        while True:
            d = ser.read(4096)
            if d:
                sys.stdout.write(d.decode("utf-8", "replace"))
                sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n已停止", file=sys.stderr)
    finally:
        ser.close()


def parse(log: str) -> dict:
    """从启动日志里解析硬件事实。"""
    out: dict = {}
    for label, pat in BOOT_FACTS:
        m = re.search(pat, log)
        if m:
            out[label] = m.group(1).strip()

    heaps = [int(x) for x in RE_HEAP.findall(log)]
    if heaps:
        out["可用堆"] = f"{sum(heaps)} KiB（{' + '.join(str(h) for h in heaps)}）"

    parts = []
    seen = set()
    for name, off, size in RE_PART.findall(log):
        if name in seen:
            continue          # 启动日志会把分区表打印两遍
        seen.add(name)
        parts.append((name, int(off, 16), int(size, 16)))
    if parts:
        out["_partitions"] = parts

    i2c = RE_I2C.findall(log)
    if i2c:
        known = {"0x18": "ES8311 音频 codec", "0x63": "CW2017 电量计"}
        out["I2C 设备"] = "  ".join(f"{a}({known.get(a, '?')})" for a in i2c)

    if "Guru Meditation" in log or "abort()" in log:
        out["⚠️ 崩溃"] = "日志里有 panic/abort，见原始输出"
    err = re.findall(r"^E \(\d+\) (\S+): (.+)$", log, re.M)
    if err:
        out["⚠️ 错误"] = f"{len(err)} 条，例：{err[0][0]}: {err[0][1][:60]}"
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="AI Passport 串口监控")
    ap.add_argument("--port", default="", help="串口路径，默认自动找")
    ap.add_argument("--seconds", type=float, default=10.0, help="抓多久")
    ap.add_argument("--info", action="store_true", help="只打印解析结果")
    ap.add_argument("--raw", action="store_true", help="原样输出不解析")
    ap.add_argument("--follow", action="store_true", help="持续跟随，不复位")
    ap.add_argument("--no-reset", action="store_true", help="不复位")
    args = ap.parse_args()

    try:
        import serial  # noqa: F401
    except ImportError:
        print("需要 pyserial：pip3 install pyserial", file=sys.stderr)
        return 1

    port = find_port(args.port)

    if args.follow:
        follow(port)
        return 0

    log = capture(port, args.seconds, do_reset=not args.no_reset,
                  echo=args.raw)

    if args.raw:
        return 0

    if not log.strip():
        print(f"{port} 没有输出。设备可能在睡眠，或这个口不输出日志。",
              file=sys.stderr)
        return 1

    facts = parse(log)
    print(f"══ {port} ══  收到 {len(log)} 字节")
    parts = facts.pop("_partitions", None)
    for k, v in facts.items():
        print(f"  {k:<10} {v}")
    if parts:
        print("  分区表")
        for name, off, size in parts:
            print(f"    {name:<12} @0x{off:06X}  {size / 1024:>7.0f} KB")

    if not args.info:
        print("\n── 原始日志 ──")
        print(log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
