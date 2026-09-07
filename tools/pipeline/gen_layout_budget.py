#!/usr/bin/env python3
"""Export migrated VAR_ELEMENTS budgets; --check reports stale generated output.

Run from any directory:
    python3 tools/pipeline/gen_layout_budget.py
    python3 tools/pipeline/gen_layout_budget.py --check
Only migrated consumers are exported. Coordinates and formatting stay in recipes.
本脚本目前不在常跑门禁列表里，用 --check 手动验。
挂载前先读 sim/strings.py:326 附近 gen_pages 的教训：判据选错会让
干净树也报红，导致生成物停止更新，比不挂更坏。先确认判据再接入。
"""

from pathlib import Path
import argparse
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "sim"))
import strings as UI

OUT = REPO / "firmware/main/render_layout_budget.h"
EXPORTS = {("P3", "主宠名牌"): "LAYOUT_P3_PET_NAME_BUDGET"}


def render() -> str:
    lines = [
        "// 自动生成：手改会被覆盖；请改 sim/strings.py 的 VAR_ELEMENTS。",
        "// Regenerate: python3 tools/pipeline/gen_layout_budget.py",
        "// Check: python3 tools/pipeline/gen_layout_budget.py --check",
        "#pragma once",
        "",
    ]
    for key, macro in EXPORTS.items():
        matches = [row for row in UI.VAR_ELEMENTS if row[:2] == key]
        if len(matches) != 1:
            raise ValueError(f"{key}: expected exactly one VAR_ELEMENTS entry")
        _, _, x, right, _, _, _ = matches[0]
        left = UI.MARGIN if x is None else x
        if not isinstance(left, int) or not isinstance(right, int) or right <= left:
            raise ValueError(f"{key}: invalid budget bounds {left}, {right}")
        lines += [f"// {key[0]}.{key[1]}: budget only, not a coordinate.",
                  f"#define {macro} {right - left}", ""]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        expected = render()
    except ValueError as exc:
        print(f"layout budget: {exc}", file=sys.stderr)
        return 1
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != expected:
            print("layout budget drift: run python3 tools/pipeline/gen_layout_budget.py",
                  file=sys.stderr)
            return 1
        print("layout budget: generated header matches VAR_ELEMENTS")
    else:
        OUT.write_text(expected, encoding="utf-8")
        print(f"generated {OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
