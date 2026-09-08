#!/usr/bin/env python3
"""UI 点阵素材打包 —— sim/pixelart.py 的产物变成固件能读的 ui.bin。

用法：
    python3 tools/pipeline/convert_ui.py
    python3 tools/pipeline/convert_ui.py --preview ball_24

## 为什么需要这一步

`sim/pixelart.py` 里的精灵球、光标、心形、星星**早就画好了**，
但一直只存在于 Python 里 —— 固件读不到，所以：

  · 五个页面的选中光标本该是 `▸`，而字库里根本没有这个字形
    （PingFang 不含它，见 convert_font.py 的说明）→ 屏幕上是空白
  · P4 捕获页从头到尾没画过精灵球，只有文字「精灵球 ×12」
  · P1 的亲密度用「亲」字代替 ♥

三个都是**素材已存在但没接线**的问题（docs/review-art.md 逐条记过），
这个脚本就是那根线。

## 格式

与 gen1_back.bin 同构，固件复用同一套 2bpp 解码：

    magic "UIA1" | ver u16 | count u16
    条目表 count × (name[16] | w u8 | h u8 | off u32 | len u16 | pad u16)
    位图数据

条目按名字查而不是按下标 —— 素材数量少（个位数），
线性查找的常数远小于「下标改了但忘了同步固件枚举」的代价。

## 调色板不在这里

pixelart 的每个素材自带 PALETTE（精灵球红白、心形粉红、星星金白），
但那些是**十六进制字符串**，而固件要 RGB565。
转换在 convert_palettes.py 里做，与 sprite 调色板同一个文件 ——
不为几个 UI 素材再开一个格式。
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

MAGIC = b"UIA1"
VERSION = 1
NAME_LEN = 16
ENTRY_FMT = "<16sBBIHH"          # name, w, h, off, len, pad
ENTRY_SIZE = struct.calcsize(ENTRY_FMT)

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "sim"))


def collect() -> list[tuple[str, list[list[int]]]]:
    """要打包的素材。**名字就是固件里的查找键**，改名要同步改固件。"""
    import pixelart as pa
    import fetch_oak
    import fetch_balls

    return [
        # Original Crystal capture art: full 16px source at integer 2x.
        # The three ball kinds share the original shape and differ by palette.
        ("ball_24", fetch_balls.ball_grid("ball_24")),
        ("ball_open", fetch_balls.ball_grid("ball_open")),
        ("ball_great", fetch_balls.ball_grid("ball_great")),
        ("ball_ultra", fetch_balls.ball_grid("ball_ultra")),
        # 菜单光标 —— 替掉字库里不存在的 ▸
        ("cursor", pa.MENU_CURSOR),
        # 亲密度心形 —— 替掉 P1 现在的「亲」字
        ("heart", pa.HEART),
        # 闪光星星，两个尺寸（S8 闪光判定用）
        ("star_5", pa.star(5)),
        ("star_7", pa.star(7)),
        # Crystal 开场原图与原配色，固定来源见 fetch_oak.py。
        # 完整 56×56 ×2 = 112×112；原白不改色，使用统一白底。
        ("oak", fetch_oak.oak_grid()),
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description="UI 点阵素材打包")
    ap.add_argument("--out", default="assets/ui.bin")
    ap.add_argument("--preview", default="", help="ASCII 预览某个素材")
    args = ap.parse_args()

    import pixelart as pa
    import fetch_balls

    items = collect()
    fetch_balls.write_metadata()

    if args.preview:
        for name, grid in items:
            if name == args.preview:
                print(f"「{name}」{len(grid[0])}×{len(grid)}")
                print(pa.ascii_preview(grid))
                return 0
        print(f"没有叫 {args.preview} 的素材。有的是："
              f"{', '.join(n for n, _ in items)}", file=sys.stderr)
        return 1

    entries = bytearray()
    blob = bytearray()
    print(f"{len(items)} 个素材")
    for name, grid in items:
        h, w = len(grid), len(grid[0])
        if len(name) >= NAME_LEN:
            print(f"名字 {name} 超过 {NAME_LEN-1} 字节", file=sys.stderr)
            return 1
        data = pa.to_2bpp(grid)
        # 自洽校验：2bpp 每行 ceil(w/4) 字节
        expect = h * ((w + 3) // 4)
        if len(data) != expect:
            print(f"{name}: {len(data)} B ≠ 预期 {expect} B", file=sys.stderr)
            return 1
        entries += struct.pack(ENTRY_FMT, name.encode(), w, h,
                               len(blob), len(data), 0)
        blob += data
        print(f"  {name:14s} {w:2d}×{h:<2d} {len(data):4d} B")

    header = struct.pack("<4sHH", MAGIC, VERSION, len(items))
    out = header + bytes(entries) + bytes(blob)

    # 条目表的偏移是相对**位图区**的，固件要加上头 + 表的长度。
    # 这里不预先加进去 —— 让固件算，因为固件那边本来就知道表长。
    path = os.path.join(REPO, args.out)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(out)

    print(f"\n{args.out}")
    print(f"  头部 {len(header)} B　条目表 {len(entries)} B"
          f"　位图 {len(blob)} B　合计 {len(out)} B")
    print(f"  占 8MB flash 的 {len(out)/8/1024/1024*100:.4f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
