#!/usr/bin/env python3
"""中文点阵字体子集化 —— 只打包实际用到的字。

用法：
    python3 tools/pipeline/convert_font.py --src /tmp/gen1c --out assets
    python3 tools/pipeline/convert_font.py --preview 妙蛙种子

字符集来自两处：
  · 151 只宝可梦的中文名（实测共用 209 个不同汉字）
  · UI 文案（菜单项、提示语，见 UI_STRINGS）

## 为什么是 16×16 而不是 12×12

实测从 PingFang 渲染「妙」字：

    12×12  着墨 20%  笔画糊成一团，左右结构分不开
    16×16  着墨 23%  左「女」右「少」清晰可辨

而字库体积差得不多（209 字：12×12 是 3.7 KB，16×16 是 6.5 KB），
在 8MB flash 里都是零头。**清晰度值这 2.8 KB。**

## 依赖说明

这个脚本需要 PIL（Pillow）——**管线里唯一的第三方依赖**，
且只在重新生成字库时需要。产物 `font16.bin` 入库后，
其他工具与固件都不需要 PIL。

不用 PIL 的替代方案是找现成的点阵字库（如文泉驿点阵宋），
但那些许可各异且往返查证成本高，而系统自带黑体的渲染质量实测够用。
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys

MAGIC = b"FNT1"
VERSION = 1
GLYPH_SIZE = 16          # 16×16，1bpp = 32 字节/字

# 系统字体候选，按优先级。PingFang 是 macOS 的现代黑体，
# 点阵化后笔画最匀；STHeiti 作为兼容回退。
FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
]

# UI 文案 —— 所有会显示在屏幕上的字。
# 按页面组织，便于对照 docs/08-systems.md 的页面清单增删。
UI_STRINGS = [
    # P1 待机
    "饱食", "心情", "体能", "今日行程", "照料", "图鉴", "遭遇",
    # P2 遭遇列表
    "刚才路上遇到", "选中", "返回", "丢弃", "野外", "住宅区",
    "办公区", "商业区", "交通枢纽",
    # P3 战斗
    "捕获", "战斗", "逃跑", "效果绝佳", "效果不好", "没有效果",
    "胜", "败", "经验", "回合",
    # P4 捕获
    "球", "精灵球", "超级球", "高级球", "切换", "投球", "取消",
    "命中", "未命中", "跑掉了",
    # P5 照料
    "喂食", "玩耍", "休息", "查看详情", "执行", "浆果",
    "愉快", "平静", "低落", "消沉",
    # P6 图鉴
    "详情", "翻页", "已捕获", "未捕获", "闪光",
    # P7 成绩
    "成绩", "个人纪录", "单日遭遇最多", "单日移动量", "连续照料",
    "连续出门", "最稀有捕获", "闪光捕获", "第", "天", "切榜",
    # 通用
    "等级", "属性", "进化", "亲密度", "探索值", "只",
    "无", "是", "否", "只有", "共",
]


def collect_charset(gen1_json: str) -> tuple[set, dict]:
    """收集需要的字符集。返回 (字符集, 分类统计)。"""
    chars: set = set()
    stat = {"names": 0, "ui": 0}

    if os.path.exists(gen1_json):
        with open(gen1_json, encoding="utf-8") as f:
            mons = json.load(f)
        name_chars: set = set()
        for m in mons:
            name_chars |= set(m.get("zh", ""))
        chars |= name_chars
        stat["names"] = len(name_chars)

    ui_chars: set = set()
    for s in UI_STRINGS:
        ui_chars |= set(s)
    # 数字与常用符号 —— 屏幕上到处都是
    ui_chars |= set("0123456789/×★☆✦%·")
    chars |= ui_chars
    stat["ui"] = len(ui_chars)
    stat["overlap"] = len(name_chars & ui_chars) if stat["names"] else 0

    return chars, stat


def render_glyph(font, ch: str, size: int = GLYPH_SIZE) -> bytearray:
    """渲染单字为 1bpp 位图，每行 2 字节（16 位）。"""
    from PIL import Image, ImageDraw

    img = Image.new("L", (size, size), 255)
    d = ImageDraw.Draw(img)

    # 居中：PIL 的 textbbox 给出实际墨迹范围
    try:
        bbox = d.textbbox((0, 0), ch, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = (size - w) // 2 - bbox[0]
        y = (size - h) // 2 - bbox[1]
    except Exception:
        x = y = 0

    d.text((x, y), ch, font=font, fill=0)

    px = list(img.getdata())
    out = bytearray()
    row_bytes = (size + 7) // 8
    for row in range(size):
        for byte_i in range(row_bytes):
            b = 0
            for bit in range(8):
                col = byte_i * 8 + bit
                if col < size and px[row * size + col] < 128:
                    b |= 0x80 >> bit
            out.append(b)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="中文点阵字体子集化")
    ap.add_argument("--src", default="/tmp/gen1c",
                    help="fetch_gen1.py 的输出（取 gen1.json 的中文名）")
    ap.add_argument("--out", default="assets")
    ap.add_argument("--size", type=int, default=GLYPH_SIZE)
    ap.add_argument("--font", default="", help="指定字体路径")
    ap.add_argument("--preview", default="", help="预览这几个字的点阵")
    args = ap.parse_args()

    try:
        from PIL import ImageFont
    except ImportError:
        print("需要 PIL：pip3 install Pillow\n"
              "（这是管线里唯一的第三方依赖，且只在重新生成字库时需要）",
              file=sys.stderr)
        return 1

    # 找字体
    path = args.font
    if not path:
        for c in FONT_CANDIDATES:
            if os.path.exists(c):
                path = c
                break
    if not path or not os.path.exists(path):
        print(f"找不到中文字体。候选：\n  " + "\n  ".join(FONT_CANDIDATES),
              file=sys.stderr)
        return 1

    size = args.size
    try:
        font = ImageFont.truetype(path, size)
    except Exception as e:
        print(f"加载字体失败 {path}: {e}", file=sys.stderr)
        return 1

    print(f"字体 {os.path.basename(path)} @ {size}px")

    # 预览模式
    if args.preview:
        for ch in args.preview:
            g = render_glyph(font, ch, size)
            rb = (size + 7) // 8
            print(f"\n「{ch}」")
            for row in range(size):
                line = ""
                for col in range(size):
                    b = g[row * rb + col // 8]
                    line += "██" if (b >> (7 - col % 8)) & 1 else "  "
                print("  " + line)
        return 0

    chars, stat = collect_charset(os.path.join(args.src, "gen1.json"))
    ordered = sorted(chars)

    print(f"\n字符集 {len(ordered)} 个")
    print(f"  宝可梦名字 {stat['names']}　UI 文案 {stat['ui']}"
          f"　重叠 {stat.get('overlap', 0)}")

    # 渲染
    glyphs = bytearray()
    failed = []
    per = size * ((size + 7) // 8)
    for ch in ordered:
        try:
            g = render_glyph(font, ch, size)
            if len(g) != per:
                raise ValueError(f"长度 {len(g)} != {per}")
            glyphs += g
        except Exception as e:
            failed.append(f"{ch}: {e}")
            glyphs += bytearray(per)

    # 码点索引表：排序后的 UTF-16 码点数组，固件二分查找
    # （全部在 BMP 内，u16 够用）
    index = bytearray()
    for ch in ordered:
        index += struct.pack("<H", ord(ch))

    header = struct.pack("<4sHHHI", MAGIC, VERSION, size, per, len(ordered))
    blob = header + bytes(index) + bytes(glyphs)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, f"font{size}.bin")
    with open(out_path, "wb") as f:
        f.write(blob)

    print(f"\n{out_path}")
    print(f"  头部     {len(header):>6} B")
    print(f"  码点索引 {len(index):>6} B  ({len(ordered)} × 2)")
    print(f"  字形     {len(glyphs):>6} B  ({len(ordered)} × {per})")
    print(f"  合计     {len(blob):>6} B = {len(blob)/1024:.1f} KB")
    if failed:
        print(f"\n  ⚠️  {len(failed)} 个字渲染失败：{failed[:3]}")

    # 对照：全字库要多大
    full = 6700
    print(f"\n  对照：GB2312 全字库 {full} 字 = {full*per/1024:.0f} KB"
          f"　子集省了 {(full-len(ordered))*per/1024:.0f} KB")

    # 字符集清单便于查证
    txt_path = os.path.join(args.out, f"font{size}_charset.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("".join(ordered))
    print(f"  字符集清单 → {txt_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
