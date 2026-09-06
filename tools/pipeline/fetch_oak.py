#!/usr/bin/env python3
"""拉取并转换初代大木博士训练师立绘（pret/pokered 反汇编真品）。

用法：
    /usr/bin/python3 tools/pipeline/fetch_oak.py            # 取素材 + 转换 + 预览
    /usr/bin/python3 tools/pipeline/fetch_oak.py --out /tmp/oak
    /usr/bin/python3 tools/pipeline/fetch_oak.py --preview  # 只预览（需缓存）

## 来源（下一个人要能复现）

    https://raw.githubusercontent.com/pret/pokered/master/gfx/trainers/prof.oak.png
    → 56×56，colortype=0、depth=2 —— 与宝可梦 front sprite 完全同格式
      （fetch_gen1.py 的 gray 变体同类：真 4 级灰阶，DMG 原生表现）

注意别拿成 `gfx/sprites/oak.png`（16×96 行走图 sprite 表，不是立绘）。

## 为什么是「取」而不是「画」

手绘版被用户否决（「太丑、和皮卡丘不是一个风格」）。风格不一致的根因
在**来源**：皮卡丘是初代 sprite 数据，手绘点阵必然气质不同。项目惯例
「数值不手填，从 pret 反汇编取」，美术同理。

## 转换管线（与宝可梦 sprite 同一条 —— 风格一致的保证）

    read_png_full（convert_sprites）→ 灰度 → quantize_2bpp（0=最暗 3=最亮）
    → 值域网格 ×2 整数放大（最近邻，点阵保持锐利；非整数倍会插值糊掉）
    → pixelart.to_2bpp 打包

⚠️ 色号序与 pixelart 手绘素材相反：sprite 序 0=最暗（描边）3=最亮（白），
ui.bin 其余条目是 pixelart 序（0=描边 3=透明）。固件按各自调色板渲染，
不冲突，但看数据时别混。

零第三方依赖；带 /tmp 本地缓存（与 fetch_gen1 --out 惯例一致）；
失败报错不静默。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "sim"))

URL = ("https://raw.githubusercontent.com/pret/pokered/master"
       "/gfx/trainers/prof.oak.png")

NATIVE_W = NATIVE_H = 56      # 训练师立绘统一 7×7 tile
SCALE = 2                     # 整数放大：112×112，点阵锐利
OUT_W = OUT_H = NATIVE_W * SCALE


def fetch(cache_dir: str) -> str:
    """下载（带缓存）。失败报错退出，不静默。"""
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, "prof.oak.png")
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    print(f"取 {URL}")
    req = urllib.request.Request(URL, headers={"User-Agent": "fetch_oak"})
    with urllib.request.urlopen(req, timeout=30) as r:   # noqa: S310 固定 URL
        data = r.read()
    if not data.startswith(b"\x89PNG"):
        raise SystemExit(f"取回的不是 PNG（{len(data)} B）")
    with open(path, "wb") as f:
        f.write(data)
    print(f"  缓存 {path}（{len(data)} B）")
    return path


def oak_grid(cache_dir: str = "/tmp/oak",
             _stats: dict | None = None) -> list[list[int]]:
    """转换后的值域点阵（112×112，0=最暗 3=最亮）。

    打包成 2bpp 之前必须跑 fill_interior_white（convert_palettes 的
    现成实现，151 只宝可梦验证过）：色号 3 既是画布外背景（该透明）
    也是白大褂（不该透明），固件把 3 当透明 → 洪泛区分「与边界连通」
    的外部与内部，内部的 3 并进 2。漏这一步白大褂会在真机上消失
    —— STATUS 第五节「sprite 内部高光漏底」的同款缺陷。
    """
    import convert_sprites as CS
    import convert_palettes as CP

    path = fetch(cache_dir)
    w, h, rows, pal, idx = CS.read_png_full(path)
    if (w, h) != (NATIVE_W, NATIVE_H):
        raise SystemExit(f"素材尺寸 {w}×{h} ≠ 预期 {NATIVE_W}×{NATIVE_H}"
                         f"（拿错文件？gfx/sprites/oak.png 是行走图）")
    # 灰度（colortype=0 时 RGB 三通道同值，直接走通用路径）
    gray = [[CS.to_gray_alpha(px)[0] for px in row] for row in rows]
    vals = [[v for v in row] for row in _unpack(CS.quantize_2bpp(gray),
                                                NATIVE_W, NATIVE_H)]
    filled = CP.fill_interior_white(vals)      # 内部 3 → 2，防白大褂透明
    if _stats is not None:
        _stats["filled"] = filled
    # ×2 最近邻放大：值域整数直接复制，无插值
    return [[v for v in row for _ in range(SCALE)]
            for row in vals for _ in range(SCALE)]


def _unpack(data: bytes, w: int, h: int) -> list[list[int]]:
    """quantize_2bpp 的逆操作（每字节 4 像素，高位在左）。"""
    g = []
    for y in range(h):
        row = []
        for x0 in range(0, w, 4):
            b = data[y * ((w + 3) // 4) + x0 // 4]
            for k in range(4):
                if x0 + k < w:
                    row.append((b >> (6 - k * 2)) & 3)
        g.append(row)
    return g


def oak_bytes(cache_dir: str = "/tmp/oak") -> bytes:
    import pixelart as PA
    return PA.to_2bpp(oak_grid(cache_dir))


# 大木的调色板（sprite 序 0=最暗 … 3=最亮）。固件侧写死这四个 RGB565。
#
# 洪泛填充后 idx2 的语义变了：不再是零散浅灰阴影，而是**白大褂主体**
#（原 idx3 内部白与 idx2 阴影合并成一个色号）。初代 DMG 上大褂就是
# 白的，所以 idx2 渲成近白 #e8e8e8 而不是 #a8a8a8 —— 否则真机上
# 大褂是一块灰（洪泛修了透明、又造出灰块）。与页面白底 #f0f0f0
# 留一档微差，描边 idx0 把轮廓抱住。
OAK_PALETTE = ["#202020", "#686868", "#e8e8e8", "#f0f0f0"]

# 值域：3=白（背景/大褂）2=浅灰 1=深灰 0=描边最暗 —— ASCII 预览用
_PREV = {0: "██", 1: "▒▒", 2: "░░", 3: "  "}


def rgb565(hexstr: str) -> int:
    v = int(hexstr[1:], 16)
    r, g, b = (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def main() -> int:
    ap = argparse.ArgumentParser(description="取并转换大木博士立绘")
    ap.add_argument("--out", default="/tmp/oak", help="缓存目录")
    ap.add_argument("--preview", action="store_true", help="只预览已缓存的")
    args = ap.parse_args()

    cache = os.path.join(args.out, "prof.oak.png")
    if args.preview and not os.path.exists(cache):
        raise SystemExit(f"无缓存 {cache}，先不带 --preview 跑一次")

    stats: dict = {}
    grid = oak_grid(args.out, _stats=stats)
    data = __import__("pixelart").to_2bpp(grid)
    from collections import Counter
    dist = Counter(v for row in grid for v in row)
    print(f"oak：{NATIVE_W}×{NATIVE_H} → ×{SCALE} = {OUT_W}×{OUT_H}，"
          f"2bpp {len(data)} B")
    print(f"洪泛填充：内部色号 3 → 2 共 {stats['filled'] * SCALE * SCALE}"
          f" px（原生 {stats['filled']} px ×4）"
          f"—— 为 0 说明洪泛没生效，不要交付")
    total = OUT_W * OUT_H
    for i in range(4):
        print(f"  idx{i}  {dist[i]:5d}  {dist[i] * 100 / total:.1f}%")
    print("调色板（sprite 序 0=最暗 → 3=最亮），固件写死 RGB565：")
    for i, hx in enumerate(OAK_PALETTE):
        print(f"  [{i}] {hx} → 0x{rgb565(hx):04X}")
    print(f"sha256(oak 2bpp) = "
          f"{hashlib.sha256(data).hexdigest()}")
    print("\nASCII 预览：")
    for row in grid:
        print("".join(_PREV[v] for v in row))
    return 0


if __name__ == "__main__":
    sys.exit(main())
