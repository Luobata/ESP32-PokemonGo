#!/usr/bin/env python3
"""精灵图 → 2bpp 四阶灰，Game Boy 风格。

用法：
    python3 tools/pipeline/convert_sprites.py \
        --src /tmp/tuxemon/mods/tuxemon/gfx/sprites/battle \
        --out assets/sprites.bin --size 56

输入是 412 张 128×88 PNG。输出定长 2bpp 位图，固件可按
(base + index * bytes_per_sprite) 直接索引。

零第三方依赖 —— 自己解 PNG（zlib 在标准库里）。不引 Pillow 的理由是
这条管线要能在任何装了 python3 的机器上跑，而 Pillow 需要编译。
"""

from __future__ import annotations

import argparse
import os
import struct
import sys
import zlib

MAGIC = b"SPRT"
VERSION = 1

# DMG 四阶灰的亮度阈值。原始素材是彩色，先转灰度再量化到 4 级。
# 阈值不均匀分布：偏向保留暗部细节，因为 GB 屏幕上亮部容易糊成一片。
QUANT_THRESHOLDS = (60, 120, 190)


# ---------------------------------------------------------------------------
# 极简 PNG 解码（够读 Tuxemon 的素材：8 位、RGB/RGBA/调色板）
# ---------------------------------------------------------------------------

def read_png(path: str) -> tuple[int, int, list[list[tuple[int, int, int, int]]]]:
    """返回 (宽, 高, 逐行 RGBA 像素)。"""
    with open(path, "rb") as f:
        data = f.read()

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG")

    pos = 8
    width = height = 0
    bit_depth = color_type = 0
    idat = bytearray()
    palette: list[tuple[int, int, int]] = []
    trns: bytes = b""

    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        ctype = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        pos += 12 + length          # 4 长度 + 4 类型 + body + 4 CRC

        if ctype == b"IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", body[:10])
        elif ctype == b"PLTE":
            palette = [tuple(body[i:i + 3]) for i in range(0, len(body), 3)]
        elif ctype == b"tRNS":
            trns = body
        elif ctype == b"IDAT":
            idat += body
        elif ctype == b"IEND":
            break

    if bit_depth != 8:
        raise ValueError(f"只支持 8 位色深，这个是 {bit_depth}")

    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type)
    if channels is None:
        raise ValueError(f"不支持的 color_type {color_type}")

    raw = zlib.decompress(bytes(idat))
    stride = width * channels

    # 反 filter
    out = bytearray()
    prev = bytearray(stride)
    p = 0
    for _ in range(height):
        ftype = raw[p]
        p += 1
        line = bytearray(raw[p:p + stride])
        p += stride

        if ftype == 1:      # Sub
            for i in range(channels, stride):
                line[i] = (line[i] + line[i - channels]) & 0xFF
        elif ftype == 2:    # Up
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif ftype == 3:    # Average
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif ftype == 4:    # Paeth
            for i in range(stride):
                a = line[i - channels] if i >= channels else 0
                b = prev[i]
                c = prev[i - channels] if i >= channels else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        elif ftype != 0:
            raise ValueError(f"未知 filter {ftype}")

        out += line
        prev = line

    # 转 RGBA
    rows: list[list[tuple[int, int, int, int]]] = []
    for y in range(height):
        row = []
        base = y * stride
        for x in range(width):
            o = base + x * channels
            if color_type == 0:
                g = out[o]; row.append((g, g, g, 255))
            elif color_type == 2:
                row.append((out[o], out[o + 1], out[o + 2], 255))
            elif color_type == 3:
                idx = out[o]
                r, g, b = palette[idx] if idx < len(palette) else (0, 0, 0)
                a = trns[idx] if idx < len(trns) else 255
                row.append((r, g, b, a))
            elif color_type == 4:
                g = out[o]; row.append((g, g, g, out[o + 1]))
            else:
                row.append((out[o], out[o + 1], out[o + 2], out[o + 3]))
        rows.append(row)

    return width, height, rows


# ---------------------------------------------------------------------------
# 缩放 + 量化
# ---------------------------------------------------------------------------

def to_gray_alpha(px: tuple[int, int, int, int]) -> tuple[int, int]:
    r, g, b, a = px
    return (r * 299 + g * 587 + b * 114) // 1000, a


def box_downscale(rows, sw: int, sh: int, dw: int, dh: int) -> list[list[int]]:
    """区域平均缩放。

    透明像素不计入平均 —— 否则精灵边缘会被背景拉暗，
    在四阶灰下这个误差非常明显（边缘糊掉一整圈）。
    """
    out: list[list[int]] = []
    for dy in range(dh):
        y0, y1 = dy * sh // dh, max(dy * sh // dh + 1, (dy + 1) * sh // dh)
        line: list[int] = []
        for dx in range(dw):
            x0, x1 = dx * sw // dw, max(dx * sw // dw + 1, (dx + 1) * sw // dw)
            tot = n = 0
            for y in range(y0, y1):
                for x in range(x0, x1):
                    g, a = to_gray_alpha(rows[y][x])
                    if a > 128:
                        tot += g
                        n += 1
            line.append(tot // n if n else 255)   # 全透明 → 最亮（当背景）
        out.append(line)
    return out


def quantize_2bpp(gray: list[list[int]]) -> bytearray:
    """灰度 → 2bpp，每字节 4 像素，高位在左（与常见 LCD 驱动一致）。"""
    h, w = len(gray), len(gray[0])
    out = bytearray()
    for y in range(h):
        acc = bits = 0
        for x in range(w):
            g = gray[y][x]
            # 0 = 最暗，3 = 最亮
            if g < QUANT_THRESHOLDS[0]:
                v = 0
            elif g < QUANT_THRESHOLDS[1]:
                v = 1
            elif g < QUANT_THRESHOLDS[2]:
                v = 2
            else:
                v = 3
            acc = (acc << 2) | v
            bits += 2
            if bits == 8:
                out.append(acc)
                acc = bits = 0
        if bits:
            out.append(acc << (8 - bits))   # 行尾补齐
    return out


def split_frames_by_gaps(rows) -> list:
    """按透明空隙切出各帧，返回第一帧（左上）的内容包围盒。

    比按网格等分可靠：Tuxemon 的 sheet 名义上是 2×2 的 128×88，
    但帧内容并不贴着网格线 —— 实测 agnidon 的左上帧占 y∈[10,53]，
    而 rows[:44] 会把 y∈[44,53]（正是腿部）切掉。目检时腿没了。
    所以先找非透明行/列的连续区间，取第一个区间。
    """
    h, w = len(rows), len(rows[0])

    def runs(flags: list[bool]) -> list[tuple[int, int]]:
        out, start = [], None
        for i, v in enumerate(flags):
            if v and start is None:
                start = i
            elif not v and start is not None:
                out.append((start, i - 1))
                start = None
        if start is not None:
            out.append((start, len(flags) - 1))
        return out

    col_has = [any(rows[y][x][3] > 128 for y in range(h)) for x in range(w)]
    col_runs = runs(col_has)
    if not col_runs:
        return rows
    x0, x1 = col_runs[0]

    # 在第一列簇范围内再找行簇
    row_has = [any(rows[y][x][3] > 128 for x in range(x0, x1 + 1)) for y in range(h)]
    row_runs = runs(row_has)
    if not row_runs:
        return rows
    y0, y1 = row_runs[0]

    return [r[x0:x1 + 1] for r in rows[y0:y1 + 1]]


def main() -> int:
    p = argparse.ArgumentParser(description="精灵图 → 2bpp 四阶灰")
    p.add_argument("--src", required=True, help="PNG 目录")
    p.add_argument("--out", default="assets/sprites.bin")
    p.add_argument("--size", type=int, default=56,
                   help="输出边长（正方形）。56 对应初代宝可梦战斗精灵尺寸")
    p.add_argument("--limit", type=int, default=0, help="只转前 N 张（调试用）")
    p.add_argument("--preview", type=int, default=-1,
                   help="把第 N 张以 ASCII 打印出来目检")
    args = p.parse_args()

    if not os.path.isdir(args.src):
        print(f"错误：{args.src} 不是目录。先跑 fetch-tuxemon.sh", file=sys.stderr)
        return 1

    files = sorted(f for f in os.listdir(args.src) if f.endswith(".png"))
    if args.limit:
        files = files[:args.limit]
    if not files:
        print(f"错误：{args.src} 里没有 PNG", file=sys.stderr)
        return 1

    size = args.size
    per = (size * size * 2 + 7) // 8
    blobs: list[bytearray] = []
    failed: list[str] = []

    for i, fn in enumerate(files):
        try:
            w, h, rows = read_png(os.path.join(args.src, fn))

            # Tuxemon 的 sheet 是 2×2 网格 = 4 帧，每帧 64×44。
            # 实测确认（agnidon-sheet.png，128×88）：
            #   横向非透明像素分成 x∈[1,58] 和 x∈[65,121] 两簇
            #   纵向分成 y∈[10,53] 和 y∈[64,87] 两簇，中间 y∈[54,63] 是空隙
            # 早期版本只切横向，结果每张图底部都混进下一行的帧 —— 目检时
            # 一条龙下面又长出半条龙。这里按 cols×rows 等分取左上帧。
            # 按透明空隙切帧，而不是按网格等分 —— 见 split_frames_by_gaps
            cropped = split_frames_by_gaps(rows)
            src_h = len(cropped)
            src_w = len(cropped[0])

            # 保持长宽比：按较长边定标，短边居中留白。
            # 直接拉成正方形会把横向立姿压变形，四阶灰下很显眼。
            scale = min(size / src_w, size / src_h)
            tw, th = max(1, round(src_w * scale)), max(1, round(src_h * scale))
            small = box_downscale(cropped, src_w, src_h, tw, th)

            # 居中贴到 size×size 画布（255 = 最亮，作背景）
            gray = [[255] * size for _ in range(size)]
            ox, oy = (size - tw) // 2, (size - th) // 2
            for y in range(th):
                for x in range(tw):
                    gray[oy + y][ox + x] = small[y][x]

            blob = quantize_2bpp(gray)
            if len(blob) != per:
                raise ValueError(f"长度 {len(blob)} != 预期 {per}")
            blobs.append(blob)
        except Exception as e:
            failed.append(f"{fn}: {e}")
            blobs.append(bytearray(per))   # 占位，保持索引与怪物表对齐

        if (i + 1) % 100 == 0:
            print(f"  ...{i+1}/{len(files)}", file=sys.stderr)

    if args.preview >= 0 and args.preview < len(blobs):
        print(f"\n预览 #{args.preview} ({files[args.preview]})")
        shades = " .oO"
        b = blobs[args.preview]
        row_bytes = (size * 2 + 7) // 8
        for y in range(size):
            line = ""
            for x in range(size):
                byte = b[y * row_bytes + (x * 2) // 8]
                shift = 6 - ((x * 2) % 8)
                line += shades[3 - ((byte >> shift) & 3)]
            print("  " + line)

    header = struct.pack("<4sHHHHI", MAGIC, VERSION, size, size, per, len(blobs))
    data = header + b"".join(bytes(b) for b in blobs)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as fh:
        fh.write(data)

    print(f"\n写入 {args.out}")
    print(f"  {len(blobs)} 张 @ {size}×{size} 2bpp")
    print(f"  单张 {per} B　合计 {len(data)/1024:.0f} KB")

    if failed:
        print(f"\n⚠️  {len(failed)} 张失败（已用空白占位保持索引对齐）：")
        for f in failed[:5]:
            print(f"    {f}")
        if len(failed) > 5:
            print(f"    ... 另 {len(failed)-5} 张")

    return 0


if __name__ == "__main__":
    sys.exit(main())
