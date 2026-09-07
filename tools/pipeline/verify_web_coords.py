#!/usr/bin/env python3
"""web 与固件的坐标一致性门禁（D72，第二十五派活）。

用法：
    /usr/bin/python3 tools/pipeline/verify_web_coords.py
    退出码 0 = 过，非 0 = 挂。

## 为什么需要它

`tools/inspector/template.html` 5052 行、251 个绘制调用点，**零门禁覆盖**
（`grep -ln template.html tools/pipeline/*.py` 为空）。而呈现层坐标是
「同一个值两边各写一遍」的重灾区：

    firmware: draw_bar(120, Y(WILD_BAR_Y), 112, 10, ...)
    web:      bar(120, 28, 112, 10, ...)

test 上一轮量过七页 79 项：A 类抄错 6 处（已修）+ **C 类 14 处
「值现在对、没机制保证下次还对」**。C 类不是 bug，是**下一个 bug 的产地** ——
本门禁守的就是 C 类。实际发生过两次：
  · 固件「96px 重叠修三轮」改完 web 没跟（第二十三派活修）
  · P4 判定条 200 在三处各写一遍（同轮接单一来源修）

## 与既有门禁的区别（不重复造）

| 门禁 | 看什么 |
|---|---|
| `verify_layout` | **只扫固件**：坐标是否跨 80px 横带 |
| `verify_sim_pages` | **只对账 payload vs sim 重算**，不看任何绘制坐标 |
| **本门禁** | **web 绘制坐标 vs 固件绘制坐标**，两边都读源码 |

前两个都不读 `template.html`。本门禁是第一个。

## 与渲染引擎迁移的关系（关键设计）

cep-coder 本轮交付 `render_scene.h`，把 P3 主宠 HP 条抽成共享配方，
固件侧 `play_battle.c:69-71` 已改成别名：

    #define PET_BAR_Y SCENE_P3_PET_HP_Y

**已迁移的元素不需要本门禁守** —— 它们由共享 C 保证同源。
所以本门禁**自动跳过别名到 `SCENE_*` 的常量**（见 `_migrated()`）：
迁移推进一个元素，本门禁的覆盖面自动缩小一个，
**不会误报、不需要人手加豁免、不会因此变成恒绿。**

> 这是本门禁存在的前提。若哪天 `SCENE_*` 改名，`_migrated()` 会失配
> 从而**把已迁移元素也纳入检查** —— 那是安全方向的失败（多查不是少查）。

注意：**跳过的前提是「双边都走配方」，不是「C 侧已别名」**（见 `_reverse_scan`
上方的长注释）。截至 D86：HP 条双边已接 → 跳过；sprite 与名牌
**只有 C 侧迁移、web 未接** → 不跳过，用 `SCENE_` 常量值继续比对。

## 关于本文件的行数（D86 定，**不要按总行数判断**）

**上限的判据是「判定逻辑行数」（当前约 150），不是总行数（当前约 500）。**

拆分：空行 50 / `#` 注释 70 / docstring 约 75 / **数据表 176**
（`CHECKS` 145 + `FW_ONLY` 31）/ **判定逻辑约 150**。

原契约的「300 行」防的是**判定逻辑膨胀成子系统**
（既有十四个门禁平均 360 行，守的是整个子系统；只守坐标的不该那么大）。
**这里膨胀的是登记数据，而登记数据多恰恰是覆盖面大的证据。**

**若判定逻辑超过 250 行**，说明它在长成子系统，那时该拆或该重新设计。
**不要为了「瘦身」去砍数据表** —— 砍掉一行登记就是少守一个元素，
而反扫会立刻把它报成「未登记」（这是有意的）。

## 这个门禁是迁移期脚手架

D77 走配方的元素结构上不可能分叉。**迁移完成时它应该能整个删掉** ——
所以不要让别的东西依赖它的输出格式。
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FW = os.path.join(REPO, "firmware", "main")
WEB = os.path.join(REPO, "tools", "inspector", "template.html")

# 登记表：(页, 元素, 固件文件, 固件绘制行正则, web 绘制行正则, 取哪几个参数)
#   fw_args / web_args: 参数名 -> 该参数在调用里的序号（0 基）
#   只登记「两边都是静态可解析的整数字面量或已知常量」的元素 ——
#   运行时算出来的（如 SCR_W-8-render_text_width(buf) 右对齐）无法静态比对，
#   由 sim/strings.py 的 VAR_ELEMENTS 那条线管，不在这里重复。
CHECKS = [
    {
        "page": "P3", "elem": "野怪 HP 条",
        "fw_file": "play_battle.c",
        "fw_re": r"draw_bar\(\s*(\d+)\s*,\s*Y\((\w+)\)\s*,\s*(\d+)\s*,\s*(\d+)",
        "fw_names": ["x", "y", "w", "h"],
        "web_re": r"bar\((\d+),(\d+),(\d+),(\d+),wildHpPct",
        "web_names": ["x", "y", "w", "h"],
    },
    {
        "page": "P3", "elem": "主宠 HP 条",
        "fw_file": "play_battle.c",
        # 已迁移：固件不再调 draw_bar，改调共享配方 scene_screen_p3_pet_hp()，
        # 坐标由 render_scene.h 的 SCENE_P3_PET_HP_* 单一来源给出。
        # 匹配那个调用点作为「已迁移」的证据，常量则从头文件解析。
        "fw_re": r"scene_screen_p3_pet_hp\(",
        "fw_names": [],
        "migrated_via": ["PET_BAR_X", "PET_BAR_Y", "PET_BAR_W"],
        # web 已接（D77 第 2 步，本轮）：template.html 调 scenePetHp() 消费
        # 构建期由 scene_cli 求出的矩形 —— 双边同源，可以跳过。
        "web_connected_marker": "scenePetHp(",
        "scene_consts": {},
        # web 侧已无坐标字面量（改为消费构建期矩形）—— 匹配消费点本身作为
        # 「web 已接」的证据。**这正是迁移完成的形态**：两边都没有可比的字面量，
        # 因为两边都从 render_scene.h 来。
        "web_re": r"function scenePetHp\(",
        "web_names": [],
    },
    {
        "page": "P3", "elem": "主宠名牌",
        "fw_file": "play_battle.c",
        # cep-coder 本轮迁移的第三个元素（HP 条 → sprite → 名牌）：
        # 固件改调 scene_screen_p3_pet_name()，坐标由 SCENE_P3_PET_NAME_* 给出。
        # web 尚未接 → 按「双边判据」不跳过，用 SCENE_ 常量值继续比对。
        "fw_re": r"scene_screen_p3_pet_name\(",
        "fw_names": [],
        "migrated_via": ["PET_NAME_X", "PET_NAME_Y"],
        # D91 本轮 web 已接：template.html 的 scenePetName() 消费构建期导出的
        # 文本+位置（scene_cli p3_pet_name）—— 双边同源，转为跳过。
        "web_connected_marker": "function scenePetName(",
        "scene_consts": {"x": "SCENE_P3_PET_NAME_X", "y": "SCENE_P3_PET_NAME_Y"},
        "web_re": r"text\('皮卡丘 Lv'\+sc\.playerLevel,(\d+),(\d+)",
        "web_names": ["x", "y"],
    },
    {
        "page": "P3", "elem": "主宠 sprite",
        "fw_file": "play_battle.c",
        # 已迁移（cep-coder 本轮第二个元素）：固件改调 scene_screen_p3_pet_back()，
        # 坐标/尺寸由 SCENE_P3_PET_BACK_{X,Y,SIZE} 单一来源给出。
        # 本门禁上一轮建时它还是 render_sprite_2bpp(8+dx, Y(PET_SPRITE_Y), .., 32, 3)，
        # **迁移后正则失配 → 门禁报「代码改了而门禁没跟」** —— 那次报红是对的，
        # 它正确地发现了固件侧结构变化。这里跟进为「已迁移」。
        "fw_re": r"scene_screen_p3_pet_back\(",
        "fw_names": [],
        "migrated_via": ["PET_SPRITE_Y", "PET_SPRITE_DISPLAY"],
        # web 侧接上的证据：template.html 里出现该标记才算「双边都走配方」。
        # sprite 目前 web 未接（标记不存在）→ 不跳过，改用 SCENE_ 常量值继续比对。
        "web_connected_marker": "scenePetBack(",
        "scene_consts": {"y": "SCENE_P3_PET_BACK_Y",
                         "scale_from_size": "SCENE_P3_PET_BACK_SIZE"},
        "web_re": r"spr\(25,'back',8\+pdx,(\d+),(\d+)\)",
        "web_names": ["y", "scale"],
    },
    {
        "page": "P3", "elem": "回合文字",
        "fw_file": "play_battle.c",
        "fw_re": r"render_text\(8\s*,\s*Y\((MSG_Y)\)\s*,\s*buf",
        "fw_names": ["y"],
        "web_re": r"text\(p3Msg\(r,sc\),8,(\d+)",
        "web_names": ["y"],
    },
    {
        "page": "P4", "elem": "判定条",
        "fw_file": "play_capture.c",
        "fw_re": r"#define BAR_Y (\d+)",
        "fw_names": ["y"],
        "web_re": r"BX=Math\.floor\(\(W-BW\)/2\), BY=(\d+)",
        "web_names": ["y"],
    },
    {
        "page": "P4", "elem": "球图标",
        "fw_file": "play_capture.c",
        "fw_re": r"#define BALL_Y (\d+)",
        "fw_names": ["y"],
        "web_re": r"ui\(\(s\.thrown&&s\.hit&&b\.caught\)\?'ball_open':bn,8,(\d+),1\)",
        "web_names": ["y"],
    },
    # ---- D86 反扫报出来后补登记的（本轮）----
    {
        "page": "P4", "elem": "结果文案",
        "fw_file": "play_capture.c",
        "fw_re": r"#define MSG_Y (\d+)",
        "fw_names": ["y"],
        "web_re": r"if\(s\.thrown\) text\(s\.thrown,8,(\d+)\)",
        "web_names": ["y"],
    },
    {
        "page": "P3", "elem": "野怪名牌 y",
        "fw_file": "play_battle.c",
        "fw_re": r"#define WILD_NAME_Y (\d+)",
        "fw_names": ["y"],
        "web_re": r"text\(nm,W-8-textW\(nm\),(\d+),t\.ink\)",
        "web_names": ["y"],
    },
    {
        "page": "P3", "elem": "野怪 HP 条 y",
        "fw_file": "play_battle.c",
        "fw_re": r"#define WILD_BAR_Y (\d+)",
        "fw_names": ["y"],
        "web_re": r"bar\(120,(\d+),112,10,wildHpPct",
        "web_names": ["y"],
    },
    {
        "page": "P3", "elem": "回合详情行 y",
        "fw_file": "play_battle.c",
        "fw_re": r"#define MSG_DETAIL_Y (\d+)",
        "fw_names": ["y"],
        "web_re": r"if\(r\.label\) text\(r\.label,8,(\d+),t\.ink\)",
        "web_names": ["y"],
    },
    {
        "page": "P6", "elem": "图鉴网格起点 x",
        "fw_file": "play_dex.c",
        "fw_re": r"#define GRID_X (\d+)",
        "fw_names": ["x"],
        "web_re": r"fn\(sid, (\d+)\+\(i%SP\.dex\.cols\)",
        "web_names": ["x"],
    },
    {
        "page": "P6", "elem": "图鉴格宽",
        "fw_file": "play_dex.c",
        "fw_re": r"#define CELL_W (\d+)",
        "fw_names": ["w"],
        "web_re": r"fn\(sid, \d+\+\(i%SP\.dex\.cols\)\*(\d+)",
        "web_names": ["w"],
    },
    {
        "page": "P6", "elem": "图鉴网格起点 y",
        "fw_file": "play_dex.c",
        "fw_re": r"#define GRID_Y (\d+)",
        "fw_names": ["y"],
        "web_re": r"\*46, (\d+)\+\(\(i/SP\.dex\.cols\)",
        "web_names": ["y"],
    },
    {
        "page": "P2", "elem": "遭遇首行 y",
        "fw_file": "play_enc.c",
        "fw_re": r"#define ROW0_Y (\d+)",
        "fw_names": ["y"],
        "web_re": r"const y=(\d+)\+i\*24",
        "web_names": ["y"],
    },
]

FAILS: list[str] = []
SKIPPED: list[str] = []

# ---------------------------------------------------------------------------
# 反扫（D86）：以固件具名坐标常量为锚，找出「固件有名字、web 没登记」的元素
#
# ## 为什么锚在固件而不是 web
# `template.html` 有 251 处绘制调用，其中大量是动画/特效（fxSpec 那套），
# **在固件里根本没有对应物**。全量反扫会逼出一堆豁免，而豁免多了就是恒绿。
# 反过来以固件常量为锚：**每个具名常量都代表「固件认为这个位置值得起名字」**，
# 数量有界（实测 30 个绘制锚），且不需要判定「同名」——
# 匹配不到就报「未登记」让人补。
#
# ## 三态而不是两态（Hub 补的判据，成立）
#   已登记      → CHECKS 里有，逐值比
#   未登记但该登记 → 固件有常量、web 有对应绘制 → **报红**
#   固件独有     → web 无对应页面/元素 → **显式声明 + 打印理由，不报红**
# 第三态若不显式化，「逼出豁免」会换个形式发生：人们把该登记的塞进独有里。
# 所以 FW_ONLY 照 verify_layout 的做法：**行号绑定 + 理由必填 + 逐条打印 +
# 过期条目点名**。行号绑定是有意的 —— 代码一挪声明就失效，逼人重新确认。
#
# ## 这个反扫是迁移期脚手架
# D77 走配方的元素结构上不可能分叉。**迁移完成时整个门禁应该能安全删掉** ——
# 所以不要让别的东西依赖它的输出格式。
# ---------------------------------------------------------------------------

# 屏幕尺寸/派生别名，不是绘制锚（每个 play_*.c 都重定义一遍）
_NOT_ANCHOR = {"SCR_W", "SCR_H", "BAND_H", "TEXT_H", "USABLE_W"}

# (文件, 行号, 常量名, 理由) —— 固件独有，web 无对应元素。理由必填。
FW_ONLY: list[tuple[str, int, str, str]] = [
    ("play_battle.c", 64, "WILD_SPRITE_BOX_Y",
     "野怪 sprite 盒的定位基准；web 用 88+(64-fsize)/2 内联算，盒本身不单独绘制"),
    ("play_battle.c", 65, "WILD_SPRITE_BOX_H",
     "同上，盒高只参与居中算式，无独立绘制调用"),
    ("play_capture.c", 55, "SPRITE_Y",
     "P4 野怪 sprite y；web 用 32+(64-fsize)/2 同式内联，已由 P4 物种名锚覆盖该页"),
    ("play_capture.c", 58, "BAR_X",
     "表达式常量 ((SCR_W-CAP_BAR_WIDTH)/2)，非静态可解析；web 侧同样按该式推导"
     "（BX=Math.floor((W-BW)/2)，第二十三派活接的单一来源），形状一致而非值一致"),
    ("play_care.c", 39, "EVO_HINT_Y",
     "P5 进化提示「进化了/可以进化了」—— **web 侧无此元素**，"
     "模拟器 P5 不演示进化态（S7 进化是固件侧玩法，web 未建对应演示）"),
    ("play_care.c", 36, "CARE_SPRITE_X",
     "P5 宠物 sprite x=168；web spr(...,168,88,2) 同值，但 sprite 缩放语义未迁移，"
     "登记后无法静态比 scale（同 P3 sprite 的教训），留待配方迁移时一并处理"),
    ("play_care.c", 37, "CARE_SPRITE_Y", "同上，与 CARE_SPRITE_X 成对"),
    ("play_idle.c", 77, "SPRITE_Y",
     "P1 宠物 sprite y=54；web sprC() 走光学居中（墨迹 bbox），与固件盒定位"
     "语义不同，静态比会误报 —— 这是真实差异，已在第五派活记录为设计选择"),
    ("play_idle.c", 86, "BAR_OFFSET_Y",
     "轴条相对行的偏移量，不是绝对坐标；web 内联在 bar(48,y+3,...) 的 +3"),
    ("play_idle.c", 87, "BAR_H", "轴条高度常量，随 BAR_OFFSET_Y 一同内联"),
    ("play_enc.c", 59, "ROW_H", "行距而非绝对坐标；web 内联在 ROW0_Y+ROW_H*i 同式"),
    ("play_dex.c", 47, "CELL_H",
     "图鉴格高；web p6Cells() 用同值但 G 方向已改无边框版式，"
     "两侧格高语义不同（第五派活用户定「图鉴可以没有边框」）"),
    ("play_opening.c", 32, "TEXT_BOX_Y",
     "P0 文本框 y=164；web hlineS(164,...) 画的是分隔线不是框，"
     "固件此处也只用作 hline 基准，无框绘制"),
]


def _anchors(fw_files: list[str]) -> list[tuple[str, int, str, str]]:
    """扫固件的具名坐标常量（绘制锚）。返回 (文件, 行号, 名字, 值)。"""
    out = []
    for fn in fw_files:
        p = os.path.join(FW, fn)
        if not os.path.isfile(p):
            continue
        for i, ln in enumerate(_read(p).split("\n"), 1):
            m = re.match(r"^#define\s+(\w+)\s+(.+?)\s*(?://.*)?$", ln)
            if not m:
                continue
            name = m.group(1)
            if name in _NOT_ANCHOR:
                continue
            if not re.search(r"_(X|Y|W|H)$|_WIDTH$|_HEIGHT$", name):
                continue
            out.append((fn, i, name, m.group(2).strip()))
    return out


def _reverse_scan() -> tuple[list[str], list[str]]:
    """三态分类。返回 (报红项, 打印项)。"""
    files = sorted({c["fw_file"] for c in CHECKS} |
                   {f for f, _, _, _ in FW_ONLY})
    # 已登记 = 该文件的 CHECKS 条目里出现过该常量名。
    # **必须按 (文件, 名字) 而不是裸名** —— play_capture.c 与 play_idle.c
    # 都有 SPRITE_Y，按裸名匹配会让一个文件的登记「覆盖」另一个文件的同名常量，
    # 于是本该报未登记的那个被误判成已登记（实测发生过，两条 FW_ONLY 被误报过期）。
    registered: set[tuple[str, str]] = set()
    all_anchors = _anchors(files)
    for c in CHECKS:
        blob = c["fw_re"] + " ".join(c.get("migrated_via", [])) + \
            " ".join(c.get("scene_consts", {}).values())
        for fn, _, name, _ in all_anchors:
            if fn == c["fw_file"] and name in blob:
                registered.add((fn, name))

    declared = {(f, n): (ln, why) for f, ln, n, why in FW_ONLY}
    bad, notes = [], []
    seen_decl: set[tuple[str, str]] = set()
    for fn, line, name, val in all_anchors:
        if (fn, name) in registered:
            continue
        key = (fn, name)
        if key in declared:
            want_ln, why = declared[key]
            seen_decl.add(key)
            if want_ln != line:
                bad.append(f"FW_ONLY 声明过期：{fn}:{want_ln} 的 {name} "
                           f"实际在 :{line} —— 代码挪了，请重新确认后更新行号")
            else:
                notes.append(f"固件独有 {fn}:{line} {name} —— {why}")
            continue
        bad.append(f"未登记的固件坐标锚：{fn}:{line} {name} = {val} "
                   f"—— 要么进 CHECKS 逐值比，要么进 FW_ONLY 并写明理由")
    for key in set(declared) - seen_decl:
        bad.append(f"FW_ONLY 有过期条目：{key[0]} 的 {key[1]} 已不存在或已登记，请删除")
    return bad, notes





def _read(p: str) -> str:
    with open(p, encoding="utf-8") as f:
        return f.read()


def _defines(src: str) -> dict[str, str]:
    """收集 `#define NAME value`（值原样保留，供 _migrated 判断）。"""
    out = {}
    for m in re.finditer(r"^#define\s+(\w+)\s+(.+?)\s*(?://.*)?$", src, re.M):
        out[m.group(1)] = m.group(2).strip()
    return out


def _migrated(name: str, defs: dict[str, str]) -> bool:
    """该常量是否已别名到共享渲染配方（SCENE_*）。

    已迁移 = 由共享 C 保证两端同源，不需要本门禁再比一次。
    见模块 docstring「与渲染引擎迁移的关系」。
    """
    v = defs.get(name, "")
    return v.startswith("SCENE_")


def _resolve(tok: str, defs: dict[str, str], depth: int = 0) -> int | None:
    """把常量名/字面量解析成整数；解不出返回 None（调用方记 SKIP，不算过）。"""
    tok = tok.strip()
    if re.fullmatch(r"\d+", tok):
        return int(tok)
    if depth > 8 or tok not in defs:
        return None
    v = defs[tok]
    if re.fullmatch(r"\d+", v):
        return int(v)
    if re.fullmatch(r"\w+", v):
        return _resolve(v, defs, depth + 1)
    return None      # 表达式（如 (SCR_W-CAP_BAR_WIDTH)/2）不静态求值


def main() -> int:
    if not os.path.isdir(FW) or not os.path.isfile(WEB):
        print("✗ 找不到 firmware/main 或 template.html", file=sys.stderr)
        return 1
    web_src = _read(WEB)
    fw_cache: dict[str, tuple[str, dict]] = {}

    checked = 0
    for c in CHECKS:
        tag = f"{c['page']}.{c['elem']}"
        if c["fw_file"] not in fw_cache:
            p = os.path.join(FW, c["fw_file"])
            s = _read(p)
            # 固件常量可能来自 include 的头（如 render_scene.h / capture.h）
            allsrc = s
            for h in ("render_scene.h", "capture.h", "screen.h"):
                hp = os.path.join(FW, h)
                if os.path.isfile(hp):
                    allsrc += "\n" + _read(hp)
            fw_cache[c["fw_file"]] = (s, _defines(allsrc))
        fw_src, defs = fw_cache[c["fw_file"]]

        mf = re.search(c["fw_re"], fw_src)
        mw = re.search(c["web_re"], web_src)
        if not mf:
            FAILS.append(f"{tag}: 固件侧正则未匹配 —— 代码改了而门禁没跟"
                         f"（{c['fw_file']} / {c['fw_re']}）")
            continue
        if not mw:
            FAILS.append(f"{tag}: web 侧正则未匹配 —— 代码改了而门禁没跟"
                         f"（template.html / {c['web_re']}）")
            continue

        fw_vals = dict(zip(c["fw_names"], mf.groups()))
        web_vals = dict(zip(c["web_names"], mw.groups()))

        # 已迁移元素的处置：**跳过的前提是「双边都走配方」，不是「C 侧已别名」。**
        #
        # 起初我的判据只看固件是否别名到 SCENE_* —— cep-coder 指出那只证明
        # C 侧迁移了。单边迁移（C 动了、web 没跟）**恰好是最需要监督的窗口**，
        # 而那时跳过等于关掉监督。P3 主宠 sprite 就是实例：
        # 固件 :226 已走 scene_screen_p3_pet_back()，web 仍是 spr(...) 字面量。
        #
        # 所以：web 侧标记存在 → 双边同源，跳过；不存在 → 拿 SCENE_ 常量的值
        # 与 web 现值继续比对（单边迁移期照样守）。
        mig = c.get("migrated_via", [])
        if mig:
            marker = c.get("web_connected_marker")
            web_on = bool(marker) and marker in web_src
            for name in mig:
                if not _migrated(name, defs):
                    FAILS.append(
                        f"{tag}: 登记为已迁移，但 {name} 并未别名到 SCENE_*"
                        f"（实际 = {defs.get(name, '未定义')}）—— 迁移被回退了而门禁没跟")
            if web_on:
                for name in mig:
                    if _migrated(name, defs):
                        SKIPPED.append(f"{tag}（{name} → {defs[name]}，双边均走配方）")
                continue
            # 单边迁移：用 SCENE_ 常量值继续比对 web 现值
            sc_map = c.get("scene_consts", {})
            for k in c["web_names"]:
                cname = sc_map.get(k) or sc_map.get(f"{k}_from_size")
                if not cname:
                    SKIPPED.append(f"{tag}.{k}（单边迁移但未登记对应 SCENE_ 常量）")
                    continue
                fv = _resolve(cname, defs)
                wv = _resolve(web_vals[k], defs)
                if fv is None or wv is None:
                    SKIPPED.append(f"{tag}.{k}（{cname} 非静态可解析）")
                    continue
                if sc_map.get(f"{k}_from_size"):
                    # web 的 scale 是倍率，配方给的是目标显示尺寸；
                    # 源尺寸 32（gen1 back）→ scale = SIZE / 32
                    fv = fv // 32
                checked += 1
                if fv != wv:
                    FAILS.append(
                        f"{tag} 的 {k}：web={wv} ≠ 配方={fv}（{cname}）"
                        f" —— C 已迁移而 web 未接，单边偏离")
            continue

        for k in c["web_names"]:
            if k not in fw_vals:
                continue
            raw = fw_vals[k]
            if re.fullmatch(r"[A-Z_]\w*", raw) and _migrated(raw, defs):
                SKIPPED.append(f"{tag}.{k}（{raw} → {defs[raw]}，已走共享配方）")
                continue
            fv = _resolve(raw, defs)
            wv = _resolve(web_vals[k], defs)
            if fv is None or wv is None:
                SKIPPED.append(f"{tag}.{k}（{raw} 非静态可解析）")
                continue
            checked += 1
            if fv != wv:
                FAILS.append(
                    f"{tag} 的 {k}：web={wv} ≠ 固件={fv}"
                    f"（固件 {c['fw_file']} 的 {raw}）")

    rev_bad, rev_notes = _reverse_scan()
    FAILS.extend(rev_bad)
    print(f"  登记元素 {len(CHECKS)} 个 · 逐值比对 {checked} 项 · "
          f"跳过 {len(SKIPPED)} 项 · 固件独有声明 {len(rev_notes)} 条")
    for s in SKIPPED:
        print(f"    – 跳过 {s}")
    for s in rev_notes:                 # 豁免逐条打印，绝不静默生效
        print(f"    – {s}")
    if FAILS:
        print(f"\n✗ {len(FAILS)} 处 web 与固件坐标不一致：", file=sys.stderr)
        for f in FAILS:
            print(f"    {f}", file=sys.stderr)
        return 1
    print("\n✅ web 绘制坐标与固件逐值一致（已迁移元素由共享配方保证，已跳过）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
