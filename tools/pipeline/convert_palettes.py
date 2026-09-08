#!/usr/bin/env python3
"""彩色素材转换 —— 2bpp 位图 + 共享调色板表。

用法：
    python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1c        # 默认彩色
    python3 tools/pipeline/convert_palettes.py --src /tmp/gen1c --out assets/

产出 `palettes.bin`：所有唯一调色板 + 每只的索引。

## 为什么彩色几乎不要钱

设备是彩色屏，而**原版 sprite 本来就是 4 色索引图**（depth=2）。
所以彩色与灰阶的位图数据量**完全相同** —— 区别只在调色板。

实测 151 只只用了 **10 套配色**（原版 SGB 的做法：按颜色分组）：

    10 套 × 4 色 × RGB565(2B) = 80 字节

每只记录里存 8bit 索引即可（上限 256 套；GSC 有 135 套，4 位装不下）。这是整个项目里性价比最高的一处改动。

## 索引必须按亮度重排

PNG 的调色板索引顺序是任意的，实测每只都不同：

    妙蛙种子  [2,3,1,0]      皮卡丘  [1,2,3,0]
    小火龙    [2,3,1,0]      超梦    [3,0,1,2]

若直接把 PNG 索引当 2bpp 用，**明暗会反** —— 有的图黑白颠倒。
所以统一重排成「0=最暗 … 3=最亮」，与 `sim/effects.py` 的
`shade_map` 约定一致（闪白 = 全部映射到 3）。

## 闪光宝可梦

初代没有闪光（Gen 2 才引入），但**闪光的本质就是换调色板** ——
实测二代皮卡丘普通版是黄 `(239,214,41)`、闪光版是橙 `(255,140,0)`，
位图完全相同。

所以闪光零素材成本：同一张 2bpp 图 + 另一套 8 字节调色板。
本工具会为每套配色生成一个「闪光变体」（色相旋转 + 提高饱和度）。

零第三方依赖。
"""

from __future__ import annotations

import argparse
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert_sprites import read_png_full  # noqa: E402

MAGIC = b"PALS"
VERSION = 1


def luminance(rgb: tuple[int, int, int]) -> int:
    r, g, b = rgb
    return (r * 299 + g * 587 + b * 114) // 1000


def rgb565(rgb: tuple[int, int, int]) -> int:
    """RGB888 → RGB565，屏幕的原生格式。"""
    r, g, b = rgb
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


def sorted_palette(pal: list) -> tuple[list, list[int]]:
    """按亮度升序重排调色板。

    返回 (重排后的调色板, 旧索引→新索引的映射)。
    """
    order = sorted(range(len(pal)), key=lambda i: luminance(pal[i]))
    new_pal = [pal[i] for i in order]
    remap = [0] * len(pal)
    for new_idx, old_idx in enumerate(order):
        remap[old_idx] = new_idx
    return new_pal, remap


def shiny_variant(pal: list) -> list:
    """由普通配色推出闪光配色。

    原版二代的闪光是美术手工调的，我们没有初代闪光素材（初代根本没有
    这个机制），所以按规则生成：**色相旋转 140°、饱和度略增**。

    140° 而非 180°：完全反相会让暖色变冷色、看起来像坏图；
    140° 能明显区分又保留原本的冷暖倾向。

    最暗与最亮两档不动 —— 那通常是轮廓线（近黑）与背景（纯白），
    动它们会破坏轮廓与透明判定。
    """
    out = []
    for i, (r, g, b) in enumerate(pal):
        lum = luminance((r, g, b))
        if lum < 40 or lum > 240:     # 轮廓线与背景保持原样
            out.append((r, g, b))
            continue
        h, s, v = _rgb_to_hsv(r, g, b)
        h = (h + 140.0) % 360.0
        s = min(1.0, s * 1.25 + 0.08)
        out.append(_hsv_to_rgb(h, s, v))
    return out


def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    rf, gf, bf = r / 255, g / 255, b / 255
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == rf:
        h = (60 * ((gf - bf) / d)) % 360
    elif mx == gf:
        h = 60 * ((bf - rf) / d) + 120
    else:
        h = 60 * ((rf - gf) / d) + 240
    s = 0.0 if mx == 0 else d / mx
    return h, s, mx


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    c = v * s
    x = c * (1 - abs(((h / 60) % 2) - 1))
    m = v - c
    if h < 60:
        rf, gf, bf = c, x, 0.0
    elif h < 120:
        rf, gf, bf = x, c, 0.0
    elif h < 180:
        rf, gf, bf = 0.0, c, x
    elif h < 240:
        rf, gf, bf = 0.0, x, c
    elif h < 300:
        rf, gf, bf = x, 0.0, c
    else:
        rf, gf, bf = c, 0.0, x
    return (round((rf + m) * 255), round((gf + m) * 255), round((bf + m) * 255))


def fill_interior_white(px: list[list[int]]) -> int:
    """把 sprite **内部**的色号 3 改成色号 2。返回改了多少个像素。

    ## 为什么要这一步

    初代 sprite 是四色：黑描边 / 深色 / 浅色 / **白**。
    那个白既是画布背景，也是宝可梦身上的高光（皮卡丘的耳朵内侧、
    杰尼龟的眼睛反光）—— 原版画在白底屏幕上，两者本来就该一样。

    而我们把色号 3 当透明（这是对的，外围必须透出页面背景），
    于是**身体内部的高光也变透明了**，屏幕上漏出 GB 绿。
    实测 151 只**全部**中招，平均每只 59 个像素，最多 254 个（#124）。

    ## 为什么合并到色号 2 而不是加掩码

    加 1bpp 掩码能保住第四阶（内部白仍画成白），但要 128 字节/只
    × 151 = 19 KB，且渲染要多一层查表。

    实测对比过：内部白的区域**小而零散**（就是那些高光点），
    并进最浅的实色后杰尼龟几乎看不出差别，皮卡丘的耳朵内侧
    正确地填上了。为一档几乎看不见的色阶花 19 KB 不值。

    ## 洪泛从四边开始

    「内部」的定义是**与画布边界不连通**。不能用「被非透明像素包围」
    这种局部判断 —— 那对凹形轮廓（比如尾巴与身体之间的缺口）会误判。
    """
    h, w = len(px), len(px[0])
    outside = [[False] * w for _ in range(h)]
    stack = [(0, x) for x in range(w)] + [(h - 1, x) for x in range(w)] \
        + [(y, 0) for y in range(h)] + [(y, w - 1) for y in range(h)]
    while stack:
        y, x = stack.pop()
        if not (0 <= y < h and 0 <= x < w):
            continue
        if outside[y][x] or px[y][x] != 3:
            continue
        outside[y][x] = True
        stack += [(y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)]

    n = 0
    for y in range(h):
        for x in range(w):
            if px[y][x] == 3 and not outside[y][x]:
                px[y][x] = 2
                n += 1
    return n


def indices_to_2bpp(indices: list[list[int]], remap: list[int]) -> bytearray:
    """原始 PNG 索引 → 重排后的 2bpp 位图。

    这是历史 RBY 路径：重排本身不损失像素，但下面的内部白填充
    会合并一个源色阶。当前水晶素材使用 convert_pokemon_art.py，
    不经过此函数，也不合并白色。

    重排之后会跑一遍 fill_interior_white：把身体内部的白改成
    最浅的实色，否则那些高光在设备上会透出背景色（见那个函数的说明）。
    """
    # 先重排成色号矩阵，跑完内部填充再打包 ——
    # 打包成位之后就没法做洪泛了（要按像素访问邻居）
    px = [[remap[idx] & 3 for idx in row] for row in indices]
    fill_interior_white(px)

    out = bytearray()
    for row in px:
        acc = bits = 0
        for v in row:
            acc = (acc << 2) | v
            bits += 2
            if bits == 8:
                out.append(acc)
                acc = bits = 0
        if bits:
            out.append(acc << (8 - bits))
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="彩色调色板提取与闪光生成")
    p.add_argument("--src", default="/tmp/gen1c", help="fetch_gen1.py --color 的输出")
    p.add_argument("--out", default="assets")
    p.add_argument("--count", type=int, default=151)
    p.add_argument("--show", type=int, default=0, help="打印第 N 号的调色板细节")
    p.add_argument("--gen2", action="store_true",
                   help="输出 palettes2.bin（GSC 水晶，不覆盖初代 palettes.bin）")
    args = p.parse_args()

    front_dir = os.path.join(args.src, "front")
    if not os.path.isdir(front_dir):
        print(f"错误：{front_dir} 不存在。先跑 fetch_gen1.py --color", file=sys.stderr)
        return 1

    # 收集所有唯一调色板（重排后）
    unique: dict[tuple, int] = {}
    per_mon: dict[int, int] = {}
    failed: list[str] = []

    for i in range(1, args.count + 1):
        path = os.path.join(front_dir, f"{i:03d}.png")
        try:
            _w, _h, _rows, pal, _idx = read_png_full(path)
            if not pal:
                raise ValueError("无调色板（可能是 gray 变体）")
            new_pal, _remap = sorted_palette(pal)
            key = tuple(new_pal)
            if key not in unique:
                unique[key] = len(unique)
            per_mon[i] = unique[key]
        except Exception as e:
            failed.append(f"{i:03d}: {type(e).__name__} {e}")

    if failed:
        print(f"⚠️  {len(failed)} 只失败：{failed[:3]}", file=sys.stderr)
        if len(failed) == args.count:
            print("\n全部失败 —— 素材可能是 gray 变体。"
                  "重新拉取：fetch_gen1.py --color", file=sys.stderr)
            return 1

    n_normal = len(unique)
    print(f"提取 {len(per_mon)} 只，共 {n_normal} 套配色（按亮度重排后）")

    # 为每套生成闪光变体
    normal_list = [list(k) for k, _ in sorted(unique.items(), key=lambda kv: kv[1])]
    shiny_list = [shiny_variant(pl) for pl in normal_list]

    # 打包：头部 + 调色板表（普通 N 套 + 闪光 N 套）+ 每只索引
    body = bytearray()
    for pl in normal_list + shiny_list:
        for rgb in pl:
            body += struct.pack("<H", rgb565(rgb))

    # 每只一字节：8bit 配色索引（上限 256 套；GSC 有 135 套，4 位装不下）
    mon_idx = bytearray(args.count)
    for i, pidx in per_mon.items():
        mon_idx[i - 1] = pidx & 0xFF

    header = struct.pack("<4sHHHH", MAGIC, VERSION, n_normal, 4, args.count)
    blob = header + bytes(body) + bytes(mon_idx)

    os.makedirs(args.out, exist_ok=True)
    out_name = "palettes2.bin" if args.gen2 else "palettes.bin"
    out_path = os.path.join(args.out, out_name)
    with open(out_path, "wb") as f:
        f.write(blob)

    print(f"\n{out_path}")
    print(f"  普通配色  {n_normal} 套 × 4 色 × 2 B = {n_normal*8} B")
    print(f"  闪光配色  {n_normal} 套 × 4 色 × 2 B = {n_normal*8} B")
    print(f"  每只索引  {args.count} B")
    print(f"  合计      {len(blob)} B = {len(blob)/1024:.2f} KB")

    # 分布
    import collections
    dist = collections.Counter(per_mon.values())
    print(f"\n配色使用分布")
    for pidx, cnt in dist.most_common():
        pl = normal_list[pidx]
        hexes = " ".join(f"#{r:02x}{g:02x}{b:02x}" for r, g, b in pl)
        print(f"  #{pidx}  {cnt:>3} 只   {hexes}")

    if args.show:
        i = args.show
        path = os.path.join(front_dir, f"{i:03d}.png")
        _w, _h, _rows, pal, _idx = read_png_full(path)
        new_pal, remap = sorted_palette(pal)
        print(f"\n#{i} 调色板重排")
        print(f"  PNG 原序:  {pal}")
        print(f"  亮度:      {[luminance(c) for c in pal]}")
        print(f"  重排后:    {new_pal}")
        print(f"  旧→新映射: {remap}")
        print(f"  闪光变体:  {shiny_variant(new_pal)}")

    print(f"\n下一步：python3 tools/pipeline/convert_gen1.py --src {args.src} "
          f"--out {args.out} --color")
    return 0


if __name__ == "__main__":
    sys.exit(main())
