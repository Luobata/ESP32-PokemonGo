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

（上面 209 字是当时只算物种名的基数。字库后来收齐了八个上屏来源 ——
UI 文案、昵称、开场台词、道馆、队伍菜单、判定提示、存档槽 ——
现在是 **550 字 / 17.6 KB**，仍是 8MB 的 0.2%。结论不变。）

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

# 系统字体候选，按优先级：(路径, 子字体索引, 名称)。
#
# **索引不能省** —— PingFang.ttc 是字体集合，12 个子字体的排列是
#   0 HK-Regular  1 TC-Regular  2 SC-Regular  3 HK-Medium  …
# Pillow 默认取 index=0，也就是**香港繁体**。用它渲简体中文的后果实测：
#   · 简体「鉴」PingFang HK 根本没有这个字形 → 渲成全空白
#     （P6 图鉴页标题、S5 的「图鉴」到处都是它）
#   · 另有 142 个字形被渲成港台写法：「龙」少一横、「这/过/选」走之底
#     笔形不同、标点「！，？」繁体居中而简体偏左下
# 合计 27% 的字库是错的，而字数统计、文件大小、缺字差集全都正常 ——
# 只有把字形逐个画出来对比才看得见（同 handoff「点阵要看 ASCII 预览」）。
#
# STHeiti Light.ttc 同样是集合，其 index 0 是简体（M/L 两个子字体）。
FONT_CANDIDATES = [
    ("/System/Library/Fonts/PingFang.ttc", 2, "PingFang SC Regular"),
    ("/System/Library/Fonts/STHeiti Light.ttc", 0, "STHeiti Light"),
    ("/System/Library/Fonts/Supplemental/Songti.ttc", 0, "Songti SC"),
]

# 子字体自检用字 —— 简繁写法不同且必须存在。
# 「鉴」验证简体字形存在（HK 没有它），「龙」验证不是繁体写法（繁体作「龍」，
# 点阵完全不同）。两个都是项目真的要上屏的字：
# 「鉴」在 P6 标题，「龙」在多个物种名（可达鸭→不是，是快龙/迷你龙/哈克龙）。
SANITY_CHARS = "鉴龙"

# UI 文案不在这里定义 —— 单一来源是 sim/strings.py 与 sim/naming.py。
#
# 之前这里有一份 UI_STRINGS，与页面文档、inspector 原型共三份，必然漂移。
# 漂移的后果很具体：字库没收的字在屏幕上是一片空白，
# 且只有真机点亮才发现。


def _names_from_bin(path: str) -> set:
    """从已入库的 gen1.bin 读 151 只中文名。

    **优先用这个而不是 /tmp 的中间 json** —— 中间文件会被清掉
    （我清磁盘时就删了 /tmp/gen1c，导致字库从 420 字掉到 297，
    151 只中文名全丢），而 gen1.bin 是入库产物，永远在。

    记录格式见 tools/pipeline/convert_gen1.py：32 字节定长记录 +
    名字池，中文名的偏移与长度在记录的 zo/zl 字段。
    """
    if not os.path.exists(path):
        return set()
    d = open(path, "rb").read()
    magic, ver, rsz, cnt, poolsz = struct.unpack("<4sHHII", d[:16])
    if magic != b"GEN1":
        return set()
    recs = d[16:16 + cnt * rsz]
    pool = d[16 + cnt * rsz:]
    out: set = set()
    for i in range(cnt):
        o = i * rsz
        # zo/zl 在记录偏移 20、22 —— 记录格式是
        # "<HBBBBBBBBBBBBBBHHHBB8s"（见 tools/inspector/build.py:52），
        # 逐字段累加得出。我第一版目测数成 24，收不到任何名字。
        zo, zl = struct.unpack("<HB", recs[o + 20:o + 23])
        if zl:
            out |= set(pool[zo:zo + zl].decode("utf-8", "ignore"))
    return out


def _firmware_chars(repo: str) -> tuple[set, int]:
    """扫固件源码里字符串字面量中的汉字。

    扫描页面 C 源码及头文件中的生成招式名。
    跳过注释行（注释里的汉字不上屏，收了纯属浪费）。

    **宁可多收不可少收**：ESP_LOGI 的字面量也会被收进来，
    那些其实只走串口不上屏。多收的成本是 32 字节/字，
    而少收一个字的成本是「真机上一片文字变空白」+ 重跑管线 + 重烧。
    """
    import glob
    import re

    chars: set = set()
    n = 0
    pat = re.compile(r'"((?:[^"\\]|\\.)*)"')
    for path in sorted(glob.glob(os.path.join(repo, "firmware", "main", "*.c")) + glob.glob(os.path.join(repo, "firmware", "main", "*.h"))):
        n += 1
        with open(path, encoding="utf-8") as f:
            for line in f:
                st = line.lstrip()
                if st.startswith("//") or st.startswith("*"):
                    continue
                for lit in pat.findall(line):
                    chars |= {c for c in lit if "\u4e00" <= c <= "\u9fff"}
    return chars, n


def collect_charset(gen1_json: str) -> tuple[set, dict]:
    """收集需要的字符集。返回 (字符集, 分类统计)。"""
    chars: set = set()
    stat = {"names": 0, "ui": 0}

    # 物种中文名：先试入库的 gen1.bin，回退到 /tmp 的中间 json
    repo = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    name_chars = _names_from_bin(os.path.join(repo, "assets", "gen1.bin"))
    if not name_chars and os.path.exists(gen1_json):
        with open(gen1_json, encoding="utf-8") as f:
            mons = json.load(f)
        for m in mons:
            name_chars |= set(m.get("zh", ""))
    chars |= name_chars
    stat["names"] = len(name_chars)

    # UI 文案与昵称：从 sim/ 的单一来源取
    #
    # 逐模块收集而非一个 try 包住全部 —— 原先五个 import 共享一个
    # except ImportError，任一模块失败就丢掉**全部** UI 字，
    # 而只打印一行警告。真机上的表现是「大片文字渲染成空白」，
    # 极难反查到是字库脚本。现在哪个模块塌了就报哪个。
    ui_chars: set = set()
    sim = os.path.join(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__)))), "sim")
    if sim not in sys.path:
        sys.path.insert(0, sim)

    # (模块名, 说明) —— 新增系统若有上屏文案，**必须在这里登记**，
    # 否则它的字不会进字库。这张表漏登记过两轮，各自的表现都是
    # 「真机上那一片文字渲染成空白」，而字数统计、文件大小全都正常：
    #   · S17 道馆漏登记 → 29 字（八馆主 + 八城市 + 八徽章 + 四天王 + 赤红）
    #   · S14 队伍 / S2·S7 判定 / S18 存档漏登记 → 16 字
    #     （「设为主宠」「存入仓库」「仓库满了」「这只不会进化」「两份都损坏」…）
    #
    # 判断标准：**模块里有没有会出现在屏幕上的字面量**。
    # 注意不只是 strings.py 那种集中定义的文案 —— dataclass 字段的
    # 默认值、函数动态拼的菜单项、失败提示的 reason 串全都算。
    SOURCES = [
        ("strings", "UI 文案"),
        ("naming", "昵称候选（S12）"),
        ("opening", "大木博士台词（S16）"),
        ("gyms", "道馆／四天王／徽章名（S17）"),
        ("party", "队伍与仓库菜单（S14）"),
        ("systems", "捕获／进化判定提示（S2·S7）"),
        ("state", "存档槽来源说明（S18）"),
    ]
    ok, failed = [], []
    for mod_name, desc in SOURCES:
        try:
            mod = __import__(mod_name)
            ui_chars |= mod.charset()
            ok.append(mod_name)
        except (ImportError, AttributeError) as e:
            failed.append(f"{mod_name}（{desc}）: {e}")
    if failed:
        for f in failed:
            print(f"⚠️  取不到字符集 —— {f}", file=sys.stderr)
        print("   → 这些系统的文案在真机上会渲染成空白", file=sys.stderr)
    stat["src"] = " + ".join(f"sim/{m}.py" for m in ok) or "缺失"
    stat["missing_src"] = failed

    # **固件页面里硬写的汉字也要收**。
    #
    # 上面那张 SOURCES 表只覆盖 sim/ —— 而页面是用 C 写的，
    # 里面的「我方」「对方」「效果绝佳」这些字面量 sim 那边根本没有。
    # 实测漏掉的后果：P3 战斗页显示「方 紧束 没打中」，
    # 「对」字渲染成空白（render_text 静默跳过缺字）。
    #
    # 与其每加一句文案就记得来登记，不如**直接扫源码**：
    # 页面文件里所有字符串字面量中的汉字全收。
    # 多收几个字的代价是 32 字节/字，而漏一个字要重跑管线 + 重烧固件。
    fw_chars, fw_files = _firmware_chars(repo)
    if fw_chars:
        ui_chars |= fw_chars
        stat["fw"] = f"{len(fw_chars)} 字 / {fw_files} 个固件源文件"
    # 数字与常用符号 —— 屏幕上到处都是
    #
    # 三个符号刻意**不收**，因为 PingFang 没有它们的字形（收了就是空白字形）：
    #   ▸ 菜单选中光标 → sim/pixelart.py 的 menu_cursor() 生成
    #   ✦ 闪光标记     → sim/pixelart.py 的 star() 生成（S8 本来就有）
    #   ♥ 亲密度心形   → sim/pixelart.py 的 HEART 手绘点阵
    # ✦ 原先在这里，但它只出现在 orchestrate 日志与 inspector 网页上 ——
    # 那些走系统字体，不读 font16.bin。设备上的闪光是点阵星星。
    #
    # A/B/C 与 [] 不在这里 —— 它们由 strings.charset() 收（键名来自
    # KEYS 的字典键，见那边的说明）。
    # — 是 progress_summary 的空占位（四天王/冠军未定时显示）。
    # **整段 ASCII 可见字符**（0x20~0x7E），不是挑着收。
    #
    # 原先只收了数字与 A/B/C（三键提示用的），结果 P1 状态栏写
    # 「皮卡丘 Lv12」时 L 和 v 画不出来 —— render_text 跳过没有的字形，
    # 而 render_text_width 照算宽度，屏幕上留下一段莫名的空隙。
    #
    # 挑着收省不下多少：全部 95 个 ASCII 才 2.6 KB，
    # 而每次撞上「某个字母没有」都要重跑管线、重烧固件、再看一次屏幕。
    ui_chars |= {chr(c) for c in range(0x20, 0x7F)}
    ui_chars |= set("×★☆·—")
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
    ap.add_argument("--font-index", type=int, default=0,
                    help="集合字体(.ttc)的子字体索引 —— 配 --font 使用。"
                         "PingFang.ttc 的简体是 2，不是默认的 0")
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
    #
    # --font 允许手动指定路径，配 --font-index 指定子字体
    # （集合字体必须给索引，否则又会静默落到 index 0）。
    size = args.size
    font = None
    if args.font:
        if not os.path.exists(args.font):
            print(f"找不到字体 {args.font}", file=sys.stderr)
            return 1
        cands = [(args.font, args.font_index, os.path.basename(args.font))]
    else:
        cands = [(p, i, nm) for p, i, nm in FONT_CANDIDATES
                 if os.path.exists(p)]
    if not cands:
        print("找不到中文字体。候选：\n  " +
              "\n  ".join(f"{p} (index {i}, {nm})"
                          for p, i, nm in FONT_CANDIDATES),
              file=sys.stderr)
        return 1

    # 逐个候选试，**每个都过简体自检**才采用。
    # 自检失败就换下一个 —— 静默用错子字体是这个脚本历史上最贵的 bug：
    # 27% 字形错成港台写法，而所有统计指标都正常。
    rejected = []
    for path, index, name in cands:
        try:
            f = ImageFont.truetype(path, size, index=index)
        except Exception as e:
            rejected.append(f"{name}: 加载失败 {e}")
            continue
        bad = [ch for ch in SANITY_CHARS if not any(render_glyph(f, ch, size))]
        if bad:
            rejected.append(f"{name} (index {index}): "
                            f"渲不出「{''.join(bad)}」—— 可能不是简体子字体")
            continue
        font, font_path, font_index, font_name = f, path, index, name
        break
    for r in rejected:
        print(f"⚠️  跳过 {r}", file=sys.stderr)
    if font is None:
        print("没有候选字体通过简体自检 —— 无法生成字库", file=sys.stderr)
        return 1

    print(f"字体 {font_name} (index {font_index}) @ {size}px")

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
