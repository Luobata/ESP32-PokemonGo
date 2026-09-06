#!/usr/bin/env python3
"""make_font.py —— 把 assets/font16.bin（固件点阵字库）生成 web 用位图 TTF。

第十一派活（用户定方案 b）：fontTools 把 880 个 16×16 1bpp 字形转成
「像素→矩形轮廓」的矢量 TTF —— 渲染在 16px 整数倍时与固件位图逐像素一致。
做成**可导入模块**（不是独立产物文件）：

    from make_font import build_kanto16
    css, meta = build_kanto16()        # css = 含 data: URI 的 @font-face 规则

产物不落盘、不入库 —— build.py 调用后直接内嵌进 index.html（index.html
本就是 gitignore 的构建产物，字体跟随同一策略：clone 后跑 serve.sh --rebuild
即重新生成；fontTools 缺失时 build 优雅降级回 Silkscreen，不阻塞门禁）。

font16.bin 格式（convert_font.py 写出）：
  header <4sHHHI> = MAGIC VERSION size per count（14 B）
  + count × u16 LE 码点（升序，固件二分查找用）
  + count × per B 字形（1bpp，每行 size/8=2 B，MSB 在左）
"""
import base64
import io
import os
import struct
import sys

SRC = os.path.join(os.path.dirname(__file__), "..", "..", "assets", "font16.bin")


def read_font16(path=SRC):
    """解 font16.bin → {码点: 16×16 的 0/1 二维表}。只读不改。"""
    blob = open(path, "rb").read()
    magic, ver, size, per, count = struct.unpack_from("<4sHHHI", blob, 0)
    off = 14
    cps = struct.unpack_from(f"<{count}H", blob, off)
    off += count * 2
    glyphs = {}
    row_bytes = (size + 7) // 8
    for i, cp in enumerate(cps):
        g = blob[off + i * per: off + (i + 1) * per]
        rows = []
        for y in range(size):
            row = []
            for x in range(size):
                b = g[y * row_bytes + (x >> 3)]
                row.append(1 if (b >> (7 - (x & 7))) & 1 else 0)
            rows.append(row)
        glyphs[cp] = rows
    return size, glyphs


def _runs_to_contour(x0, x1, y):
    """一行里的 [x0,x1) 墨迹段 → 矩形轮廓（glyf 坐标 y 向上，翻转）。"""
    # 单行矩形轮廓：四点闭环。多行同列连续段由调用方合并为整块再出轮廓。
    return None


def _bitmap_to_glyf(rows, size):
    """16×16 位图 → glyf 轮廓。按「列连续块」合并：
    每个极大矩形墨块一条轮廓（点数最少、渲染最稳）。y 翻转（TTF y-up）。"""
    on = {(x, y) for y in range(size) for x in range(size) if rows[y][x]}
    used = set()
    polys = []
    # 极大矩形贪心：从每个未用墨点向右下扩张
    for y in range(size):
        for x in range(size):
            if (x, y) in on and (x, y) not in used:
                w = 1
                while (x + w, y) in on and (x + w, y) not in used:
                    w += 1
                h = 1
                while all((x + dx, y + h) in on and (x + dx, y + h) not in used
                          for dx in range(w)):
                    h += 1
                for dy in range(h):
                    for dx in range(w):
                        used.add((x + dx, y + dy))
                # y-up 翻转：TTF 基线在底，位图行 0 在顶
                polys.append((x, size - y - h, w, h))
    contours = []
    for x, y, w, h in polys:
        # 顺时针（TTF 外轮廓约定为 y-up 逆时针，但单轮廓方向经 fill-rule 仍填实；
        # fontTools 不强制方向，TrueType 光栅器 non-zero 下闭环即填充）
        contours.append([(x, y), (x, y + h), (x + w, y + h), (x + w, y)])
    return contours


def build_kanto16():
    """生成 TTF bytes → (css 文本, meta dict)。fontTools 缺失时抛 ImportError
    由调用方降级。"""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    size, glyphs = read_font16()
    upm = size  # 1 像素 = 1 font unit，16px 渲染时严格像素对齐

    chars = sorted(glyphs.keys())
    glyph_order = [".notdef", "space"] + [f"g{cp}" for cp in chars]
    fb = FontBuilder(upm, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap({cp: f"g{cp}" for cp in chars})

    advances = {".notdef": size, "space": size // 2}
    pens = {}
    lsbs = {".notdef": 0, "space": 0}
    pen = TTGlyphPen(None)
    pens[".notdef"] = pen.glyph()
    pen = TTGlyphPen(None)          # space = 空轮廓
    pens["space"] = pen.glyph()
    for cp in chars:
        contours = _bitmap_to_glyf(glyphs[cp], size)
        pen = TTGlyphPen(None)
        for c in contours:
            pen.moveTo(c[0])
            for pt in c[1:]:
                pen.lineTo(pt)
            pen.closePath()
        pens[f"g{cp}"] = pen.glyph()
        # lsb = 字形 xMin：抵消光栅器的 lsb 补偿（lsb−xMin 平移）——
        # 不设的话 Chrome 把墨迹整体左移 xMin，逐像素对不回 font16.bin
        lsbs[f"g{cp}"] = min((c[0][0] for c in contours), default=0)
        # 字宽：ASCII 半宽 8、其余全宽 16（与固件 render_text 的推进一致；
        # 模拟器 text() 自管推进，此值主要给 DOM 内可能的直接使用）
        advances[f"g{cp}"] = size // 2 if cp < 0x80 else size
    advances["space"] = size // 2
    # setupGlyf 同时生成 glyf+loca —— 之前用 newTable 手塞 glyf 漏了 loca，
    # 字体在浏览器解析失败（fontTools 自己回读也会报 'loca'）。
    fb.setupGlyf(pens)
    fb.setupHorizontalMetrics({g: (advances.get(g, size), lsbs.get(g, 0)) for g in glyph_order})
    fb.setupHorizontalHeader(ascent=size, descent=-size // 4)  # 位图占满 16px 行高
    fb.setupNameTable({"familyName": "Kanto16", "styleName": "Regular",
                       "fullName": "Kanto16", "psName": "Kanto16-Regular"})
    fb.setupOS2(sTypoAscender=size, sTypoDescender=-(size // 4),
                usWinAscent=size, usWinDescent=size // 4)
    fb.setupPost()
    fb.saveDummyDocuments = lambda *a, **k: None

    buf = io.BytesIO()
    fb.font.save(buf)
    ttf = buf.getvalue()
    b64 = base64.b64encode(ttf).decode()
    # 注：f-string 里单个 '}' 必须写成 '}}'（转义）—— 别"修"掉
    css = ("@font-face{font-family:'Kanto16';font-display:block;"
           f"src:url(data:font/ttf;base64,{b64}) format('truetype');}}")
    return css, {"chars": len(chars), "bytes": len(ttf), "b64": len(b64), "upm": upm}


if __name__ == "__main__":
    try:
        css, meta = build_kanto16()
    except ImportError as e:
        print(f"需要 fontTools：/usr/bin/python3 -m pip install --user fonttools\n({e})",
              file=sys.stderr)
        sys.exit(1)
    print(f"Kanto16：{meta['chars']} 字形，TTF {meta['bytes']} B → base64 {meta['b64']} B")
    # 自检：抽 3 个字回读位图 vs 源
    size, glyphs = read_font16()
    for ch in "皮攻A":
        rows = glyphs[ord(ch)]
        ink = sum(sum(r) for r in rows)
        print(f"  '{ch}' U+{ord(ch):04X} 墨迹 {ink}px")
