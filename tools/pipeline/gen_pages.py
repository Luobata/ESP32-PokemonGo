#!/usr/bin/env python3
"""从 sim/strings.py 生成 docs/pages/ 的页面文档。

用法：
    python3 tools/pipeline/gen_pages.py

## 为什么生成而不手写

页面文档要写「这一页显示什么文案、三个键各是什么」。手写就会与
`sim/strings.py` 漂移 —— 而漂移的后果是字库漏收字、真机上一片空白。

生成的部分是**文案与按键表**；每页的设计理由是手写的，
放在 `docs/pages/_notes/<页>.md`，生成时原样插入。
这样机器管一致性，人管判断。

零第三方依赖。
"""

from __future__ import annotations

import os
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(REPO / "sim"))

import naming as NM      # noqa: E402
import strings as UI     # noqa: E402

OUT = REPO / "docs" / "pages"
NOTES = OUT / "_notes"

# 页面元信息：文件名、标题、进入路径、对应系统
META = {
    "P1": ("P1-idle.md", "待机（主界面）", "冷启动 / 任意页 C 返回",
           ["S4 养成", "S1 遭遇累积"]),
    "P2": ("P2-encounter-list.md", "遭遇列表", "P1 按 C（有待处理时）",
           ["S1 遭遇累积", "S8 闪光"]),
    "P3": ("P3-battle.md", "遭遇详情 / 战斗", "P2 按 A",
           ["S3 自动战斗", "S8 闪光"]),
    "P4": ("P4-capture.md", "捕获", "P3 按 A",
           ["S2 捕获判定", "S9 道具", "S5 图鉴"]),
    "P5": ("P5-care.md", "照料", "P1 按 A",
           ["S4 养成", "S7 进化", "S12 取名"]),
    "P6": ("P6-dex.md", "图鉴", "P1 按 B",
           ["S5 图鉴", "S8 闪光"]),
    "P7": ("P7-records.md", "成绩", "P6 末页按 B",
           ["S10 成绩"]),
    "P8": ("P8-naming.md", "取名", "P5 选「取名」按 A",
           ["S12 取名"]),
}


def hint_line(page: str) -> str:
    keys = UI.KEYS[page]
    return " ".join(f"[{k}]{a}" for k, a in keys.items())


def render(page: str) -> str:
    fname, title, entry, systems = META[page]
    d = UI.PAGES.get(page, {})
    keys = UI.KEYS[page]
    hint = hint_line(page)
    px = UI.text_px(hint)

    lines = [
        f"# {page} {title}",
        "",
        "> **本文档由 [`tools/pipeline/gen_pages.py`]"
        "(../../tools/pipeline/gen_pages.py) 生成。**",
        f"> 文案与按键的单一来源是 [`sim/strings.py`](../../sim/strings.py) ——"
        f" 改文案改那里，然后重新生成。",
        "",
        f"**进入路径**：{entry}",
        "",
        f"**涉及系统**：{'、'.join(systems)}",
        "",
        "## 三键",
        "",
        "| 键 | 动作 |",
        "|---|---|",
    ]
    for k, a in keys.items():
        lines.append(f"| **{k}** | {a} |")
    lines += [
        "",
        f"底部提示行：`{hint}`　**{px}px / {UI.USABLE_W}px**"
        f"（余 {UI.USABLE_W - px}px）",
        "",
    ]

    if d:
        lines += ["## 文案", ""]
        for key, val in d.items():
            if isinstance(val, str):
                lines.append(f"- `{key}` —— 「{val}」"
                             f"（{UI.text_px(val)}px）")
            elif isinstance(val, (list, tuple)):
                items = "、".join(f"「{s}」" for s in val)
                lines.append(f"- `{key}` —— {items}")
            elif isinstance(val, dict):
                lines.append(f"- `{key}`：")
                for k2, v2 in val.items():
                    shown = f"「{v2}」" if v2 else "_（不显示）_"
                    lines.append(f"  - `{k2}` → {shown}")
        lines.append("")

    if page == "P8":
        lines += [
            "## 预设候选",
            "",
            f"共 {len(NM.NICKNAMES)} 个，分 {len(NM.GROUP_LABELS)} 组"
            f"（来源：[`sim/naming.py`](../../sim/naming.py)）：",
            "",
            "| 组 | 候选 |",
            "|---|---|",
        ]
        for i, lbl in enumerate(NM.GROUP_LABELS):
            lo, hi = NM.GROUP_BOUNDS[i], NM.GROUP_BOUNDS[i + 1]
            lines.append(f"| {lbl} | {'、'.join(NM.NICKNAMES[lo:hi])} |")
        lines += [
            "",
            f"最坏按键 **{NM.worst_case_presses()} 次**"
            f"（双向循环；单向要 {len(NM.NICKNAMES) + 1} 次）。",
            "",
        ]

    # 手写的设计理由。
    #
    # 注意 `_notes/*.md` 里的相对链接要按**插入后的位置**（docs/pages/）写，
    # 而不是按文件自己的位置（docs/pages/_notes/）—— 因为内容是被插进
    # 生成文件里的。我第一版按文件位置改成了 ../../systems/，全部变成死链。
    note = NOTES / f"{page}.md"
    if note.exists():
        lines += [note.read_text(encoding="utf-8").rstrip(), ""]

    return "\n".join(lines)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    NOTES.mkdir(parents=True, exist_ok=True)

    audit = UI.audit()
    if not audit["ok"]:
        print("排版审计不通过，先修文案：", file=sys.stderr)
        for v in audit["key_violations"] + audit["line_violations"]:
            print(f"  ✗ {v}", file=sys.stderr)
        return 1

    for page in META:
        fname = META[page][0]
        (OUT / fname).write_text(render(page), encoding="utf-8")
        print(f"  {fname}")

    # 索引
    idx = ["# 页面清单", "",
           "> 本文件由 [`tools/pipeline/gen_pages.py`]"
           "(../../tools/pipeline/gen_pages.py) 生成。", "",
           "| 页 | 标题 | 三键 | 进入路径 |", "|---|---|---|---|"]
    for page, (fname, title, entry, _) in META.items():
        keys = UI.KEYS[page]
        k = " / ".join(f"{kk} {aa}" for kk, aa in keys.items())
        idx.append(f"| [{page}]({fname}) | {title} | {k} | {entry} |")
    idx += ["",
            f"文案共 **{audit['strings']} 条**、"
            f"**{audit['chars']} 个字符**，"
            f"排版审计通过（可用宽 {audit['usable_px']}px，"
            f"最宽字串「{audit['widest']}」{audit['widest_px']}px）。", ""]
    (OUT / "README.md").write_text("\n".join(idx), encoding="utf-8")
    print("  README.md")

    print(f"\n{len(META)} 个页面文档 → {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
