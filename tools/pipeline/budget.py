#!/usr/bin/env python3
"""8MB flash 预算核算。

用法：
    python3 tools/pipeline/budget.py
    python3 tools/pipeline/budget.py --sprite-size 56 --font-size 12

这个工具的价值在于：容量核算应该在美术动工前算清楚，
否则可能做完才发现装不下（docs/06-engineering.md#64）。
"""

from __future__ import annotations

import argparse
import os

FLASH_KB = 8 * 1024      # ESP32-C3FH8X：8MB 片内 flash
SRAM_KB = 400            # 约 400KB，无 PSRAM

# 固件本体的经验估值。ESP-IDF + WiFi + BLE 栈占大头。
# 这是量级估算，硬件到手后应替换为 idf.py size 的实测值。
FIRMWARE_KB = 1200

MONSTER_COUNT = 411
CHINESE_FULL = 6700      # GB2312 常用字集规模
CHINESE_SUBSET = 800     # 只保留 UI 与图鉴用到的字


def kb(b: int) -> float:
    return b / 1024


def main() -> int:
    p = argparse.ArgumentParser(description="flash 预算核算")
    p.add_argument("--sprite-size", type=int, default=48, help="精灵边长")
    p.add_argument("--sprite-bpp", type=int, default=2, help="精灵位深")
    p.add_argument("--font-size", type=int, default=12, help="中文点阵边长")
    p.add_argument("--font-subset", action="store_true", default=True,
                   help="字体只打子集（默认）")
    p.add_argument("--font-full", dest="font_subset", action="store_false",
                   help="字体打全字库")
    p.add_argument("--assets", default="assets",
                   help="已生成产物目录，存在则用实测大小替代估值")
    args = p.parse_args()

    s, bpp = args.sprite_size, args.sprite_bpp
    sprite_each = (s * s * bpp + 7) // 8
    sprite_total = sprite_each * MONSTER_COUNT

    fs = args.font_size
    glyph = (fs * fs + 7) // 8          # 1bpp 点阵
    nchars = CHINESE_SUBSET if args.font_subset else CHINESE_FULL
    font_total = glyph * nchars
    ascii_total = 8 * 96                # 8×8 ASCII

    monster_rec = 24 * MONSTER_COUNT + 16 + 3300   # 记录 + 头 + 字符串池

    rows = [
        ("固件本体（ESP-IDF + WiFi/BLE 栈）", FIRMWARE_KB * 1024, "估值，待 idf.py size 实测"),
        (f"精灵图 {MONSTER_COUNT} 张 @{s}×{s} {bpp}bpp", sprite_total, f"单张 {sprite_each} B"),
        ("怪物数据（定长记录 + 字符串池）", monster_rec, "24 B/条，可 O(1) 索引"),
        (f"中文点阵 {fs}×{fs} ×{nchars}", font_total, "子集" if args.font_subset else "全字库"),
        ("ASCII 8×8", ascii_total, ""),
    ]

    # 有实测产物就用真实大小
    for name, path in [("精灵图", "sprites.bin"), ("怪物数据", "monsters.bin")]:
        full = os.path.join(args.assets, path)
        if os.path.exists(full):
            real = os.path.getsize(full)
            for i, (n, b, note) in enumerate(rows):
                if n.startswith(name):
                    rows[i] = (n + " ✓实测", real, note + "（实测）")

    print("=" * 68)
    print(f"8MB flash 预算　（ESP32-C3FH8X，无 PSRAM）")
    print("=" * 68)
    print()
    print(f"{'项':<38}{'KB':>9}{'占比':>8}")
    print("-" * 68)

    used = 0
    for name, b, note in rows:
        used += b
        print(f"{name:<38}{kb(b):>9.1f}{b/(FLASH_KB*1024)*100:>7.1f}%")
        if note:
            print(f"  └ {note}")

    free = FLASH_KB * 1024 - used
    print("-" * 68)
    print(f"{'已用':<38}{kb(used):>9.1f}{used/(FLASH_KB*1024)*100:>7.1f}%")
    print(f"{'剩余':<38}{kb(free):>9.1f}{free/(FLASH_KB*1024)*100:>7.1f}%")
    print()

    if free < 0:
        print("❌ 超出 8MB！需要缩小精灵尺寸或裁剪字体")
    elif kb(free) < 512:
        print("⚠️  余量不足 512KB，OTA 双分区会放不下")
    else:
        print(f"✓ 余量充裕（{kb(free)/1024:.1f} MB）")

    # 精灵尺寸对照
    print()
    print("精灵尺寸对照（411 张）")
    print(f"  {'尺寸':<10}{'单张':>8}{'总计':>10}")
    for sz in (32, 40, 48, 56, 64):
        each = (sz * sz * 2 + 7) // 8
        print(f"  {sz}×{sz:<7}{each:>7}B{kb(each*MONSTER_COUNT):>9.0f}KB"
              + ("   ← 当前" if sz == s else ""))

    # 字体对照 —— 这块曾被高估
    print()
    print("中文点阵对照")
    print(f"  {'规格':<16}{'子集800':>10}{'全字库6700':>12}")
    for f in (10, 12, 14, 16):
        g = (f * f + 7) // 8
        print(f"  {f}×{f} 1bpp{'':<6}{kb(g*800):>9.0f}KB{kb(g*6700):>11.0f}KB")
    print()
    print("  注：12×12 全字库仅约 117KB —— 中文字体在这个项目里不是瓶颈。")
    print("      早期担心「字体和精灵吃掉大半 flash」是按矢量或 16×16 估的，")
    print("      点阵字体便宜得多。")

    # SRAM 侧的硬约束
    print()
    print("=" * 68)
    print(f"SRAM 约束（约 {SRAM_KB}KB，无 PSRAM）")
    print("=" * 68)
    fb = 240 * 320 * 2
    print(f"  240×320×16bit 全屏帧缓冲　{kb(fb):>7.0f}KB"
          f"　占 SRAM {fb/(SRAM_KB*1024)*100:.0f}%")
    print(f"  → 装不下，必须分块渲染（docs/01-constitution.md#11）")
    band = 240 * 16 * 2
    print(f"  240×16 横带缓冲　　　　　　{kb(band):>7.1f}KB"
          f"　占 SRAM {band/(SRAM_KB*1024)*100:.1f}%　← 可行")
    print(f"  单张精灵解压缓冲 {s}×{s}×2B　{kb(s*s*2):>7.1f}KB")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
