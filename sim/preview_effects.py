#!/usr/bin/env python3
"""目检渲染动效 —— 把动效序列逐帧画成 ASCII。

用法：
    python3 sim/preview_effects.py --data /tmp/gen1 --id 25 --effect breath
    python3 sim/preview_effects.py --data /tmp/gen1 --id 150 --effect zoom
    python3 sim/preview_effects.py --data /tmp/gen1 --id 6 --effect all

动效必须能目检。光看「序列 8 帧」完全看不出对不对 ——
呼吸浮动方向错了、缩放中心偏了、闪白盖住了轮廓，这些都只能看出来。
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "tools", "pipeline"))

from effects import (  # noqa: E402
    FLASH_WHITE, IDENTITY, INVERT, Sprite2bpp, Transform,
    breath_sequence, evolution_sequence, flash_sequence,
    shake_sequence, to_ascii, zoom_in_sequence,
)


def load_from_png(path: str) -> Sprite2bpp:
    """直接从 PNG 转 2bpp（复用管线的转换逻辑）。"""
    from convert_gen1 import to_2bpp_native
    bmp, size = to_2bpp_native(path)
    return Sprite2bpp(bytes(bmp), size)


def show_frames(sprite: Sprite2bpp, canvas: int, frames: list,
                label: str, side_by_side: int = 4) -> None:
    """并排显示多帧，便于看出帧间差异。"""
    print(f"\n{'='*70}\n{label}（{len(frames)} 帧）\n{'='*70}")

    for start in range(0, len(frames), side_by_side):
        group = frames[start:start + side_by_side]
        renders = [to_ascii(sprite, canvas, tf) for tf in group]

        # 帧号行
        header = "  ".join(
            f"frame {start+i:<{canvas-7}}" for i in range(len(group)))
        print(f"\n{header}")

        for row in range(canvas):
            print("  ".join(r[row] for r in renders))


def main() -> int:
    p = argparse.ArgumentParser(description="目检渲染动效")
    p.add_argument("--data", default="/tmp/gen1",
                   help="fetch_gen1.py 的输出目录")
    p.add_argument("--id", type=int, default=25, help="宝可梦编号 1~151")
    p.add_argument("--view", default="back", choices=["front", "back"],
                   help="用哪个视图（呼吸看 back，遭遇看 front）")
    p.add_argument("--effect", default="breath",
                   choices=["breath", "zoom", "shake", "flash", "evolve", "all"])
    p.add_argument("--rise", type=int, default=1, help="呼吸浮动像素")
    args = p.parse_args()

    path = os.path.join(args.data, args.view, f"{args.id:03d}.png")
    if not os.path.exists(path):
        print(f"错误：找不到 {path}\n先跑 tools/pipeline/fetch_gen1.py", file=sys.stderr)
        return 1

    sprite = load_from_png(path)
    # 画布留出余量，好看清偏移与缩放没有被裁
    canvas = sprite.size + 4

    print(f"#{args.id} {args.view} {sprite.size}×{sprite.size}"
          f"　画布 {canvas}×{canvas}")

    want = args.effect

    if want in ("breath", "all"):
        show_frames(sprite, canvas, breath_sequence(8, args.rise),
                    f"待机呼吸（只向上浮动 {args.rise}px —— "
                    f"下方留白仅 4 行，向下会被裁）")

    if want in ("zoom", "all"):
        show_frames(sprite, canvas, zoom_in_sequence(6),
                    "遭遇时缩放展开（初代原生动效）")

    if want in ("shake", "all"):
        show_frames(sprite, canvas, shake_sequence(2, 4),
                    "受击横向抖动 ±2px")

    if want in ("flash", "all"):
        frames = [Transform(shade_map=m) for m in flash_sequence(4)]
        show_frames(sprite, canvas, frames,
                    "受击闪白（只改灰阶映射，零素材成本）")

    if want in ("evolve", "all"):
        frames = [Transform(shade_map=m) for m in evolution_sequence(8)]
        show_frames(sprite, canvas, frames,
                    "进化闪烁（IDENTITY 帧画旧形态、INVERT 帧画新形态）")

    print(f"\n{'-'*70}")
    print("怎么读：")
    print("  · 呼吸：图应整体上移再回落，底部不该被切")
    print("  · 缩放：应从中心展开，不偏移")
    print("  · 抖动：左右交替，轮廓完整")
    print("  · 闪白：全白帧应完全空白（3=最亮当透明）")
    print(f"{'-'*70}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
