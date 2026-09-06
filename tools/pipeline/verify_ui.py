#!/usr/bin/env python3
"""assets/ui.bin 与 sim/pixelart.py 逐条目对账。

用法：
    /usr/bin/python3 tools/pipeline/verify_ui.py [ui.bin 路径]

背景：inventory_assets.py 覆盖 gen1/front/back/palettes/font/eye 六个资产，
**对 ui.bin 零断言**（BUG-2 契约核实）。本门禁补上：

    · 结构自洽   magic UIA1 / 文件长 = 头 + 表 + 位图区 / 每条目
                 len == h·ceil(w/4)（2bpp 定长）/ 偏移按序无缝铺满位图区
    · 条目齐全   与 convert_ui.py 登记的七个名字一一对应（多/少/重名都红）
    · 逐像素对账 每条目 2bpp 解码回点阵，与 pixelart 的生成结果全等 ——
                 打包链路任何一环错（名字挂错、偏移算错、行宽不齐）都会
                 在这里现形，而不是等真机上「隐形素材」
    · 非空白     每条目解码后必须含 ≥2 个色值 —— 全 CLEAR 的素材会静默
                 变成隐形（▸/✦/♥ 那次就是这样），统计上看不出来
    · oak 专项   112×112（pret 真品 ×2）、sha256 钉定内容、色值合法

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

# convert_ui.py 登记的名字 → pixelart 生成物（对账基准）
EXPECTED = {
    "ball_24": "poke_ball(24)",
    "ball_open": "poke_ball(24, open_top=True)",
    "ball_great": "poke_ball(24, kind='great')",
    "ball_ultra": "poke_ball(24, kind='ultra')",
    "cursor": "MENU_CURSOR",
    "heart": "HEART",
    "star_5": "star(5)",
    "star_7": "star(7)",
    "oak": "pret 真品（fetch_oak，sha256 钉定）",
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
        "ball_24": pa.poke_ball(24),
        "ball_open": pa.poke_ball(24, open_top=True),
        "ball_great": pa.poke_ball(24, kind="great"),
        "ball_ultra": pa.poke_ball(24, kind="ultra"),
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
    # 三球区分：P4「换球」的承诺是三张**不同的**图 —— 两两相同即红
    # （这缺陷的原始形态就是三球共用一张 ball_24）
    balls = {n: decode_2bpp(blob[off:off + ln], w, h)
             for n, w, h, off, ln in entries if n.startswith("ball_")}
    for a, b in (("ball_24", "ball_great"), ("ball_24", "ball_ultra"),
                 ("ball_great", "ball_ultra")):
        if a in balls and b in balls and balls[a] == balls[b]:
            fails.append(f"{a} 与 {b} 点阵相同 —— P4 换球切图失效")
    print(f"  逐像素对账     {len(grids)} 条全等；全部非空白（≥2 色值）；"
          f"三球两两不同")

    # ---- ⑤ oak 专项 ------------------------------------------------------
    # 真品来自 pret/pokered（fetch_oak.py），内容用 sha256 钉死 ——
    # 换源/重转换都会红，逼着改动者有意识地更新这里的哈希与理由。
    import hashlib
    OAK_SHA256 = ("f5f4ad1f68d5b5ce300ba833da789786"
                  "3d47d48e4cd31d3703d4083b02ad9c95")
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
        if len(vals) < 3:
            fails.append(f"oak: 色值仅 {sorted(vals)} —— 4 级灰阶真品"
                         f"至少用到 3 档（疑似量化错）")
        # 防绕过洪泛：fill_interior_white 把白大褂（内部 3）并进 2 之后，
        # idx3 只剩画布外背景（65.3%）、idx2 升到 15.9%。不跑洪泛的旧
        # 素材 idx3 高达 78.7% / idx2 仅 2.6% —— 白大褂在真机上会透明消失
        n3 = sum(1 for row in g for v in row if v == 3)
        n2 = sum(1 for row in g for v in row if v == 2)
        ratio3 = n3 / (w * h)
        ratio2 = n2 / (w * h)
        if ratio3 > 0.70:
            fails.append(f"oak: idx3 占 {ratio3:.1%} > 70% —— 疑似没跑"
                         f"fill_interior_white（白大褂会透明）")
        if ratio2 < 0.10:
            fails.append(f"oak: idx2 占 {ratio2:.1%} < 10% —— 同上，"
                         f"白大褂应已并入 idx2")
    print("  oak 专项       112×112 / 3136 B / sha256 钉定 / "
          "洪泛已跑（idx3 ≤70%、idx2 ≥10%）")

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails:
            print("   " + f)
        return 1

    print("\n✅ ui.bin 与 pixelart 逐像素一致"
          "（结构 / 条目 / 点阵 / 非空白 / oak 专项）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
