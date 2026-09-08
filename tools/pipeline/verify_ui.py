#!/usr/bin/env python3
"""assets/ui.bin 与原版 Crystal / sim/pixelart.py 逐条目对账。

用法：
    /usr/bin/python3 tools/pipeline/verify_ui.py [ui.bin 路径]

背景：inventory_assets.py 覆盖 gen1/front/back/palettes/font/eye 六个资产，
**对 ui.bin 零断言**（BUG-2 契约核实）。本门禁补上：

    · 结构自洽   magic UIA1 / 文件长 = 头 + 表 + 位图区 / 每条目
                 len == h·ceil(w/4)（2bpp 定长）/ 偏移按序无缝铺满位图区
    · 条目齐全   与 convert_ui.py 登记的九个名字一一对应（多/少/重名都红）
    · 逐像素对账 每条目 2bpp 解码回点阵，与 pixelart 的生成结果全等 ——
                 打包链路任何一环错（名字挂错、偏移算错、行宽不齐）都会
                 在这里现形，而不是等真机上「隐形素材」
    · 非空白     每条目解码后必须含 ≥2 个色值 —— 全 CLEAR 的素材会静默
                 变成隐形（▸/✦/♥ 那次就是这样），统计上看不出来
    · oak 专项   112×112（固定 Crystal 原图 ×2）、sha256、原白保留、配色同步

退出码 0 = 过，非 0 = 挂。ui.bin 缺失默认红（ALLOW_MISSING=1 显式容忍）。
"""

from __future__ import annotations

import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "sim"))

MAGIC = b"UIA1"
ENTRY_FMT = "<16sBBIHH"
ENTRY_SIZE = struct.calcsize(ENTRY_FMT)          # 26
CLEAR = 3

# convert_ui.py 登记的名字与来源。
EXPECTED = {
    "ball_24": "Crystal OAMSET_0A / red",
    "ball_open": "Crystal OAMSET_0C + 0D / red",
    "ball_great": "Crystal OAMSET_0A / blue",
    "ball_ultra": "Crystal OAMSET_0A / yellow",
    "cursor": "MENU_CURSOR",
    "heart": "HEART",
    "star_5": "star(5)",
    "star_7": "star(7)",
    "oak": "Crystal 开场原图（fetch_oak，固定源与产物 sha256）",
}


def parse(path: str):
    data = open(path, "rb").read()
    magic, ver, count = struct.unpack_from("<4sHH", data, 0)
    entries = []
    for i in range(count):
        name, w, h, off, ln, _pad = struct.unpack_from(
            ENTRY_FMT, data, 8 + i * ENTRY_SIZE)
        entries.append((name.rstrip(b"\0").decode(), w, h, off, ln))
    blob_at = 8 + count * ENTRY_SIZE
    return magic, ver, count, entries, data[blob_at:], len(data)


def decode_2bpp(blob: bytes, w: int, h: int) -> list[list[int]]:
    """ui.bin 的 2bpp 解码（每字节 4 像素，高位在左）。

    尾字节不足 4 像素时**跳过**越界位 —— to_2bpp 只把 CLEAR 补进字节，
    网格行宽仍是 w（初版把补位也追加进行，w%4≠0 的条目全误报）。
    """
    g = []
    for y in range(h):
        row = []
        for x0 in range(0, w, 4):
            b = blob[y * ((w + 3) // 4) + x0 // 4]
            for k in range(4):
                if x0 + k < w:
                    row.append((b >> (6 - k * 2)) & 3)
        g.append(row)
    return g


def main() -> int:
    path = (sys.argv[1] if len(sys.argv) > 1
            else os.path.join(REPO, "assets", "ui.bin"))
    if not os.path.exists(path):
        rel = os.path.relpath(path, REPO)
        if os.environ.get("ALLOW_MISSING") == "1":
            print(f"⚠️ {rel} 不存在 —— ALLOW_MISSING=1 容忍缺失，"
                  f"本门禁本轮视为未运行")
            return 0
        print(f"❌ {rel} 不存在 —— 先跑 tools/pipeline/convert_ui.py 生成")
        return 1

    import pixelart as pa

    fails: list[str] = []
    magic, ver, count, entries, blob, file_len = parse(path)

    # ---- ① 结构自洽 ------------------------------------------------------
    if magic != MAGIC or ver != 1:
        fails.append(f"magic {magic!r} / version {ver} ≠ UIA1/1")
    expect_file = 8 + count * ENTRY_SIZE + len(blob)
    if file_len != expect_file:
        fails.append(f"文件长 {file_len} ≠ 头+表+位图 {expect_file}")
    at = 0
    for name, w, h, off, ln in entries:
        if ln != h * ((w + 3) // 4):
            fails.append(f"{name}: len {ln} ≠ {h}×ceil({w}/4)（2bpp 定长）")
        if off != at:
            fails.append(f"{name}: 偏移 {off} ≠ 期望的连续位置 {at}"
                         f"（间隙/交叠）")
        at += ln
    if at != len(blob):
        fails.append(f"位图区铺满失败：条目合计 {at} ≠ 位图区 {len(blob)}"
                     f"（尾部余 {len(blob) - at} B）")
    print(f"  结构           magic UIA1 v{ver}，{count} 条目，"
          f"位图区 {len(blob)} B 无缝铺满")

    # ---- ② 条目齐全 ------------------------------------------------------
    names = [e[0] for e in entries]
    if len(names) != len(set(names)):
        fails.append("条目重名")
    for want in EXPECTED:
        if want not in names:
            fails.append(f"缺条目 {want}")
    for got in names:
        if got not in EXPECTED:
            fails.append(f"多出未登记条目 {got}（convert_ui 没有它）")
    print(f"  条目           {len(names)} 个，与 convert_ui 登记一一对应")

    # ---- ③ 逐像素对账 + ④ 非空白 ----------------------------------------
    import systems  # noqa: F401  # 与其它门禁同环境
    grids = {
        "cursor": pa.MENU_CURSOR,
        "heart": pa.HEART,
        "star_5": pa.star(5),
        "star_7": pa.star(7),
    }
    for name, w, h, off, ln in entries:
        if name not in grids:
            continue
        want = grids[name]
        if (w, h) != (len(want[0]), len(want)):
            fails.append(f"{name}: 声明 {w}×{h} ≠ pixelart "
                         f"{len(want[0])}×{len(want)}")
            continue
        got = decode_2bpp(blob[off:off + ln], w, h)
        if got != want:
            diff = sum(1 for y in range(h) for x in range(w)
                       if got[y][x] != want[y][x])
            fails.append(f"{name}: 解码点阵与 pixelart 不符（{diff} 像素）")
        vals = {v for row in got for v in row}
        if len(vals) < 2:
            fails.append(f"{name}: 全 {vals} —— 空白素材会静默隐形")
    print(f"  逐像素对账     {len(grids)} 条全等；全部非空白（≥2 色值）；"
          f"其余原版素材独立校验")

    # The original three kinds intentionally share shape; source palettes,
    # not invented stripes, distinguish them. Fixed Crystal 7a7881d0d62e.
    import hashlib
    import re
    import fetch_balls
    closed_hash = '6bde85e8c3f62f058c6d53b3729c85f3c3523b2f8a54fd0bb6575cd9ab4b6d89'
    open_hash = 'eb283cb15fc259bf5c8fe39a707158fc3987933389f630146041449698d7a3e4'
    for name, w, h, off, ln in entries:
        if not name.startswith('ball_'):
            continue
        if (w,h,ln) != (32,32,256):
            fails.append(f'{name}: 原版16px×2要求32×32 / 256B')
            continue
        pixels = bytes(blob[off:off+ln])
        if hashlib.sha256(pixels).hexdigest() != (open_hash if name=='ball_open' else closed_hash):
            fails.append(f'{name}: 与固定 Crystal 原图×2不一致')
        bounds = fetch_balls.visible_bounds(decode_2bpp(pixels,w,h))
        if bounds != ([4,0,24,32] if name=='ball_open' else [4,8,24,24]):
            fails.append(f'{name}: 可见边界不符 {bounds}')
    ball_colors = [[0x0000,0xf286,0xfcf8,0xffff],
                   [0x0000,0x091f,0x431f,0xffff],
                   [0x0000,0xfc21,0xffe7,0xffff],
                   [0x0000,0x2b80,0x6661,0xffff],
                   [0x0000,0x091f,0x431f,0xffff],
                   [0x0000,0x6b4d,0xce79,0xffff],
                   [0x0000,0xa3c3,0xc4a7,0xffff],
                   [0x0000,0xfc21,0xffe7,0xffff]]
    ball_header = open(os.path.join(REPO,'firmware/main/ball_assets.h')).read()
    actual_colors = [int(v,16) for v in re.findall(r'0x[0-9a-fA-F]+',ball_header)]
    if actual_colors != [v for pal in ball_colors for v in pal]:
        fails.append('ball: 固件八种球的原版配色不一致')
    if [list(pal) for pal in fetch_balls.BALL_PALETTES_RGB565] != ball_colors:
        fails.append('ball: Inspector 八种球的原版配色不一致')
    print('  ball 专项      原图32×32 / 八种球原版配色 / 闭球24×24、开球24×32可见边界')

    # ---- ⑤ oak 专项 ------------------------------------------------------
    # Crystal 7a7881d0d62e0ddbd82dcf10e7116807487ac651 gfx/trainers/oak.png。
    # 完整原生 56×56 四档色值 ×2；原白不再合并为浅色。
    import fetch_oak
    OAK_SHA256 = ("5e86a6f5ad87075ad33db6828984da3e170"
                  "163883521a2d4e2a5b99b2499b58f")
    oak_colors = [0x0000, 0x6c20, 0xc4eb, 0xffff]
    c_source = open(os.path.join(REPO, "firmware", "main", "play_opening.c")).read()
    c_palette = re.search(r"OAK_PALETTE\[4\]\s*=\s*\{([^}]+)\}", c_source)
    if not c_palette or [int(v, 16) for v in re.findall(r"0x[0-9a-fA-F]+", c_palette[1])] != oak_colors:
        fails.append("oak: 固件配色与固定 Crystal 原配色不一致")
    if [fetch_oak.rgb565(v) for v in fetch_oak.OAK_PALETTE] != oak_colors:
        fails.append("oak: Inspector 导出配色与固定 Crystal 原配色不一致")
    oak = [e for e in entries if e[0] == "oak"]
    if not oak:
        fails.append("oak 不存在 —— BUG-2 的核心交付物缺席")
    else:
        _, w, h, off, ln = oak[0]
        if (w, h) != (112, 112) or ln != 3136:
            fails.append(f"oak: 应 112×112 / 3136 B（56×56 ×2），"
                         f"得 {w}×{h} / {ln} B")
        data = bytes(blob[off:off + ln])
        got_hash = hashlib.sha256(data).hexdigest()
        if got_hash != OAK_SHA256:
            fails.append(f"oak: sha256 {got_hash[:16]}… ≠ 钉定值"
                         f"（换素材/换转换都要有意识更新）")
        g = decode_2bpp(data, w, h)
        vals = {v for row in g for v in row}
        if not vals <= {0, 1, 2, 3}:
            fails.append(f"oak: 色值越界 {sorted(vals)}")
        if vals != {0, 1, 2, 3}:
            fails.append(f"oak: 色值 {sorted(vals)} ≠ 原图四档")
        # 白大褂及外部画布的源白全部保留，透明语义依赖页面白底。
        n3 = sum(1 for row in g for v in row if v == 3)
        if n3 != 2331 * 4:
            fails.append(f"oak: 原白像素 {n3} ≠ 2331×4（禁止内部白改色）")
    print("  oak 专项       112×112 / 3136 B / sha256 钉定 / "
          "原白保留 / 固件与 Inspector 原配色同步")

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails:
            print("   " + f)
        return 1

    print("\n✅ ui.bin 与来源一致"
          "（结构 / 条目 / 点阵 / 非空白 / 原版 ball、oak 专项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
