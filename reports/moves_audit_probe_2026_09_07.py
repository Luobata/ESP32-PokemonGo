#!/usr/bin/env python3
"""Read-only move inventory; writes JSON only when --out is supplied.

No browser/device use and no production-source writes. The optional --raw-cache
argument reads an existing PokeAPI response cache; it never downloads data.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
TYPES = ["一般", "火", "水", "电", "草", "冰", "格斗", "毒", "地面", "飞行", "超能", "虫", "岩石", "幽灵", "龙"]
SPECIAL_GEN1 = {"火", "水", "草", "电", "冰", "超能", "龙"}


def js_registries(template: Path) -> dict:
    # Evaluate only the three local data literals, never the page script/DOM.
    js = r"""
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[1], 'utf8');
const ret = {};
for (const name of ['MOVE_FX','TYPE_FX','GSC_GFX']) {
  const re = name === 'GSC_GFX'
    ? /const GSC_GFX=(.*);/ : new RegExp('const '+name+'\\s*=\\s*(\\{[\\s\\S]*?\\n\\});');
  const m = src.match(re);
  if (!m) throw new Error('Missing data literal: '+name);
  ret[name] = vm.runInNewContext('('+m[1]+')', Object.create(null), {timeout:1000});
}
process.stdout.write(JSON.stringify(ret));
"""
    return json.loads(subprocess.check_output(["node", "-e", js, str(template)], text=True))


def read_moves(path: Path) -> tuple[list[dict], dict[int, list[tuple[int, int]]], dict]:
    data = path.read_bytes()
    magic, version, rec, nm, ns, nl, pool_size = struct.unpack_from("<4sHHHHHH", data)
    assert magic == b"MOVE" and version == 1 and rec == 12
    species_at = 16 + nm * rec
    learn_at = species_at + ns * 4
    pool_at = learn_at + nl * 2
    assert pool_at + pool_size == len(data)
    pool = data[pool_at:]
    moves = []
    for slot in range(nm):
        mid, off, length, typ, power, accuracy, pp, dclass, reserved = struct.unpack_from("<HHBBBBBBH", data, 16 + slot * rec)
        moves.append(dict(id=mid, zh=pool[off:off + length].decode(), type=TYPES[typ], power=power,
                          accuracy=accuracy, pp=pp, special=bool(dclass), reserved=reserved, slot=slot))
    learn = {}
    for sid in range(1, ns + 1):
        off, count, _ = struct.unpack_from("<HBB", data, species_at + (sid - 1) * 4)
        learn[sid] = [struct.unpack_from("<BB", data, learn_at + (off + i) * 2) for i in range(count)]
    return moves, learn, dict(bytes=len(data), move_count=nm, species_count=ns, learn_count=nl,
                             sha256=hashlib.sha256(data).hexdigest())


def asm_waits(repo: Path, moves: list[dict], registry: dict, template: str) -> dict:
    """Count executed anim_wait operands for current dedicated moves, param=0.

    This is a source-control-flow audit, not a Game Boy emulator/frame-timing
    assertion. Calls, aliases and finite anim_loop branches are followed.
    """
    source_path = repo / "data/moves/animations.asm"
    source = source_path.read_text()
    table = re.findall(r"^\s*dw (\w+)", source[:source.index("assert_table_length NUM_ATTACKS")], re.M)
    instructions, labels, scope = [], {}, ""
    for lineno, raw_line in enumerate(source.splitlines(), 1):
        line = raw_line.split(";", 1)[0].strip()
        if not line:
            continue
        label = re.fullmatch(r"([\w.]+)(?:::?)?", line)
        if label and not line.startswith("anim_"):
            name = label.group(1)
            if name.startswith("."):
                name = scope + name
            else:
                scope = name
            labels[name] = len(instructions)
            continue
        parts = line.split(None, 1)
        instructions.append((parts[0], parts[1].split(",") if len(parts) > 1 else [], scope, lineno))

    def number(value: str) -> int:
        value = value.strip()
        return int(value[1:], 16) if value.startswith("$") else int(value)

    def evaluate(name: str, param: int = 0) -> dict:
        pc, stack, loops, waits = labels[name], [], {}, []
        for _ in range(10000):
            command, args, scope, lineno = instructions[pc]
            next_pc = pc + 1
            resolve = lambda dest: labels[scope + dest.strip() if dest.strip().startswith(".") else dest.strip()]
            if command == "anim_wait":
                waits.append(dict(line=lineno, count=number(args[0]), called=bool(stack)))
            elif command == "anim_call":
                stack.append(next_pc)
                next_pc = resolve(args[0])
            elif command == "anim_ret":
                if not stack:
                    return dict(wait_total=sum(w["count"] for w in waits), waits=waits)
                next_pc = stack.pop()
            elif command == "anim_jump":
                next_pc = resolve(args[0])
            elif command == "anim_if_param_equal":
                if param == number(args[0]):
                    next_pc = resolve(args[1])
            elif command == "anim_loop":
                if pc not in loops:
                    loops[pc] = number(args[0])
                    assert loops[pc] > 0, "unbounded loop outside this probe's scope"
                loops[pc] -= 1
                if loops[pc] > 0:
                    next_pc = resolve(args[1])
                else:
                    del loops[pc]
            elif command.startswith(("anim_if_", "anim_jumpif", "anim_setvar", "anim_incvar")):
                raise ValueError(f"unsupported control flow: {command} at {lineno}")
            pc = next_pc
        raise ValueError(f"instruction limit exceeded: {name}")

    entries = []
    by_name = {m["zh"]: m for m in moves}
    for name, fx in registry.items():
        if name == "*":
            continue
        m = by_name[name]
        asm = table[m["id"]]
        got = evaluate(asm)
        registry_line = re.search(r"^\s*'" + re.escape(name) + r"':[^\n]+", template, re.M).group(0)
        declared = re.search(r"\[wait:(\d+)\]", registry_line)
        entry = dict(zh=name, id=m["id"], asm=asm, **got,
                     declared_wait=int(declared.group(1)) if declared else None,
                     web_duration_10fps=fx["dur"],
                     sum_wait_rounded_10fps=max(3, int(got["wait_total"] / 6 + 0.5)),
                     segment_sum=sum(pair[1] for pair in fx.get("seg", [])) or None)
        entry["declared_wait_matches"] = entry["declared_wait"] == got["wait_total"]
        entries.append(entry)
    return dict(source=str(source_path), sha256=hashlib.sha256(source_path.read_bytes()).hexdigest(),
                git_commit=subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
                definition="Executed anim_wait operand sum, param=0; aliases/calls/finite loops followed; not an emulator",
                mismatch_count=sum(not e["declared_wait_matches"] for e in entries), entries=entries)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-cache", type=Path)
    ap.add_argument("--pret-cache", type=Path)
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    template = ROOT / "tools/inspector/template.html"
    reg = js_registries(template)
    moves, learn, meta = read_moves(ROOT / "assets/moves.bin")
    by_name = {m["zh"]: m for m in moves}
    dedicated = set(reg["MOVE_FX"]) - {"*"}
    raw = {}
    if args.raw_cache:
        for path in args.raw_cache.glob("move_*.json"):
            item = json.loads(path.read_text())
            if item.get("id", 999) <= 165:
                raw[item["id"]] = item
    learn_names = {moves[slot]["zh"] for rows in learn.values() for _, slot in rows}
    obtainable = learn_names | {"挣扎"}
    instances = Counter(moves[slot]["zh"] for rows in learn.values() for _, slot in rows)
    unlocked = Counter()
    for rows in learn.values():
        for level in (5, 12, 20, 30, 45):
            names = {moves[slot]["zh"] for lv, slot in rows if lv <= level}
            unlocked.update(names or {"挣扎"})
    typ_counts = Counter(m["type"] for m in moves)
    class_mismatch = [dict(id=m["id"], zh=m["zh"], type=m["type"],
                           stored="special" if m["special"] else "physical",
                           gen1="special" if m["type"] in SPECIAL_GEN1 else "physical")
                      for m in moves if m["special"] != (m["type"] in SPECIAL_GEN1)]
    raw_missing = [dict(id=i, slug=r["name"], damage_class=r["damage_class"]["name"],
                        effect_id=(r.get("effect_entries") or [{}])[0].get("effect", ""))
                   for i, r in sorted(raw.items()) if i not in {m["id"] for m in moves}]
    # The stored present-day class is used only to identify definitely damaging
    # omitted entries; the class's physical/special split is not treated as Gen 1.
    omitted_damage = [dict(id=r["id"], slug=r["slug"], damage_class=r["damage_class"])
                      for r in raw_missing if r["damage_class"] != "status"]
    coverage = []
    for name, count in unlocked.most_common():
        m = by_name[name]
        coverage.append(dict(id=m["id"], zh=name, slug=raw.get(m["id"], {}).get("name"),
                             type=m["type"], dedicated=name in dedicated,
                             unlocked_species_level_cases=count,
                             level_up_rows=instances[name]))
    gfx = {key: dict(width=g["w"], frames=len(g["f"]),
                    frame_sizes=[[len(frame[0]), len(frame)] for frame in g["f"]],
                    pixels=sum(len(row) for frame in g["f"] for row in frame))
           for key, g in reg["GSC_GFX"].items()}
    result = dict(
        input_template_sha256=hashlib.sha256(template.read_bytes()).hexdigest(),
        moves_bin=meta, dedicated_count=len(dedicated), type_fallback_count=len(reg["TYPE_FX"]),
        type_counts=dict(typ_counts), dedicated_names=sorted(dedicated),
        dedicated_missing_from_bin=sorted(dedicated - set(by_name)),
        per_move_fallback_count=len(set(by_name) - dedicated),
        obtainable_move_count=len(obtainable), level_up_move_count=len(learn_names),
        obtainable_without_dedicated=sorted(obtainable - dedicated),
        obtainable_without_dedicated_count=len(obtainable - dedicated),
        bin_not_obtainable=[dict(id=m["id"], zh=m["zh"]) for m in moves if m["zh"] not in obtainable],
        zero_learn_species=[sid for sid, rows in learn.items() if not rows],
        reserved_nonzero_count=sum(bool(m["reserved"]) for m in moves),
        gen1_damage_class_mismatch_count=len(class_mismatch),
        gen1_damage_class_mismatches=class_mismatch,
        raw_cache_moves=len(raw), omitted_status_count=sum(r["damage_class"] == "status" for r in raw_missing),
        omitted_damage_count=len(omitted_damage), omitted_damaging_moves=omitted_damage,
        unlocked_matrix=dict(species_count=151, levels=[5, 12, 20, 30, 45],
                             definition="Distinct unlocked moves per species-level; no spawn/AI frequency weighting",
                             total=sum(unlocked.values()), dedicated=sum(c for n, c in unlocked.items() if n in dedicated)),
        priority_by_unlocks=coverage, gfx=gfx,
        registry=reg["MOVE_FX"], type_registry=reg["TYPE_FX"],
    )
    if args.pret_cache:
        result["asm_wait_audit"] = asm_waits(args.pret_cache, moves, reg["MOVE_FX"], template.read_text())
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.write_text(encoded)
        print(args.out)
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
