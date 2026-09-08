#!/usr/bin/env python3
"""Check the five fixed effects against pinned source, then actual assets/battle C.

The source oracle reads upstream move rows/type constants and raw PokeAPI RB
learnsets independently of convert_moves. No display or saved-world simulation.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / 'firmware/main'
COMMIT = '7a7881d0d62e0ddbd82dcf10e7116807487ac651'
TYPES = ['normal', 'fire', 'water', 'electric', 'grass', 'ice', 'fighting',
         'poison', 'ground', 'flying', 'psychic', 'bug', 'rock', 'ghost', 'dragon']
NEW = {49: ('sonic-boom', 'SONICBOOM', 'EFFECT_STATIC_DAMAGE', 20),
       69: ('seismic-toss', 'SEISMIC_TOSS', 'EFFECT_LEVEL_DAMAGE', 1),
       82: ('dragon-rage', 'DRAGON_RAGE', 'EFFECT_STATIC_DAMAGE', 40),
       101: ('night-shade', 'NIGHT_SHADE', 'EFFECT_LEVEL_DAMAGE', 1),
       162: ('super-fang', 'SUPER_FANG', 'EFFECT_SUPER_FANG', 1)}
DRIVER = r'''
#include <stdio.h>
#include <string.h>
#include "battle.c"
int main(void) {
    if (!assets_init()) return 3;
    char cmd[20];
    while (scanf("%19s", cmd) == 1) {
        if (!strcmp(cmd, "known")) {
            unsigned sid, lv; scanf("%u %u", &sid, &lv);
            move_t moves[8]; int n = assets_known_moves(sid, lv, moves, 8);
            printf("%d", n);
            for (int i = 0; i < n; i++) printf(" %u", moves[i].id);
            puts("");
        } else if (!strcmp(cmd, "fixed")) {
            unsigned id, type, lv, hp, def, factor, accuracy;
            scanf("%u %u %u %u %u %u %u", &id, &type, &lv, &hp, &def, &factor, &accuracy);
            species_t a = {0}, d = {0};
            a.type1 = type; a.type2 = TY_NONE; d.type1 = def; d.type2 = TY_NONE;
            stats_t ast = {600, 999, 1, 700, 100}, dst = {600, 1, 3, 2, 100};
            move_t m = {0}; m.id = id; m.type = type; m.power = 200; m.accuracy = accuracy;
            m.special = true; uint16_t mult; const move_t *selected; bool miss;
            s_rng = 17;
            unsigned damage = do_hit(&a, &ast, lv, &d, &dst, &m, 1, factor, hp,
                                     &mult, &selected, &miss);
            printf("%u %u %u %u %u\n", damage, mult, miss, selected->id,
                   move_weight(&m, type, TY_NONE, def, TY_NONE, lv, hp));
        } else if (!strcmp(cmd, "session")) {
            unsigned sid, lv, target, hp, seed, reply;
            scanf("%u %u %u %u %u %u", &sid, &lv, &target, &hp, &seed, &reply);
            battle_session_t s; battle_round_t r;
            unsigned other = target == 101 ? 74 : 113;
            if (!battle_session_init(&s, reply ? other : sid, reply ? 100 : lv,
                                     reply ? sid : other, reply ? lv : 100, 614, seed)) return 4;
            s.next_by_pet = true; s.retaliation_pending = reply;
            if (reply) s.pet_hp = hp; else s.wild_hp = hp;
            battle_session_t saved = s, copy = saved, noise;
            battle_round_t rr;
            battle_session_step(&s, &r);
            battle_session_init(&noise, 25, 25, 150, 25, 1024, seed + 1);
            battle_session_step(&noise, &rr);
            battle_session_step(&copy, &rr);
            if (memcmp(&s, &copy, sizeof s) || memcmp(&r, &rr, sizeof r)) return 5;
            if (s.attack_count != 1 || s.retaliation_pending ||
                (reply && (!s.next_by_pet || r.by_pet))) return 6;
            printf("%u %u %u %u %u %u\n", r.move_id, r.damage, r.mult, r.missed,
                   reply ? s.pet_hp : s.wild_hp, target == r.move_id);
        }
    }
    return 0;
}
'''


def source_check(src: Path, cache: Path) -> tuple[dict, dict, dict]:
    assert subprocess.check_output(['git', '-C', str(src), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
    files = ['data/moves/moves.asm', 'constants/type_constants.asm',
             'engine/battle/effect_commands.asm', 'data/moves/effects.asm']
    for name in files:
        assert (src/name).read_bytes() == subprocess.check_output(
            ['git', '-C', str(src), 'show', f'{COMMIT}:{name}']), f'upstream source modified: {name}'
    data = (ROOT / 'assets/moves.bin').read_bytes()
    magic, ver, recsize, count, species_count, learns, poolsize = struct.unpack_from('<4sHHHHHH', data)
    assert (magic, ver, recsize, count, species_count, learns) == (b'MOVE', 1, 12, 104, 151, 629)
    poolstart = 16 + count * 12 + species_count * 4 + learns * 2
    assert poolstart + poolsize == len(data)
    moves, slots = {}, []
    for i in range(count):
        mid, zo, zl, ty, power, acc, pp, special, rv = struct.unpack_from('<HHBBBBBBH', data, 16 + i*12)
        moves[mid] = dict(type=ty, power=power, acc=acc, pp=pp, special=special,
                          zh=data[poolstart+zo:poolstart+zo+zl].decode())
        slots.append(mid)
    source_moves = (src / 'data/moves/moves.asm').read_text()
    type_constants = (src / 'constants/type_constants.asm').read_text().split('DEF SPECIAL EQU const_value')[1]
    special_types = {x.lower().replace('psychic_type', 'psychic')
                     for x in re.findall(r'^\s*const (\w+)', type_constants, re.M)}
    for m in moves.values():
        assert m['special'] == (TYPES[m['type']] in special_types), 'type physical/special mismatch'
    for mid, (_, symbol, effect, parameter) in NEW.items():
        row = re.search(r'^\s*move\s+' + symbol + r',\s*(.*)$', source_moves, re.M).group(1)
        values = [x.strip() for x in row.split(',')]
        m = moves[mid]
        assert values[0] == effect and int(values[1]) == parameter
        assert (m['power'], TYPES[m['type']], m['acc'], m['pp']) == (
            parameter, values[2].lower(), int(values[3]), int(values[4]))
    legacy = json.loads((cache / 'moves.json').read_text())
    corrected = []
    for original in legacy:
        m = moves[original['id']]
        assert (m['power'], m['acc'], m['pp'], TYPES[m['type']], m['zh']) == (
            original['power'], 255 if original['accuracy'] is None else original['accuracy'],
            original['pp'], original['type'], original['zh'])
        if m['special'] != (original['damage_class'] == 'special'): corrected.append(original['id'])
    assert corrected == [7, 8, 9, 13, 16, 22, 51, 63, 75, 123, 124, 127, 128, 129, 152, 161]
    slug_id = {m['slug']: m['id'] for m in legacy} | {v[0]: k for k, v in NEW.items()}
    expected, added = {}, []
    for sid in range(1, 152):
        raw = json.loads((cache / 'cache' / f'pokemon_{sid}.json').read_text())
        assert raw['id'] == sid, 'raw PokeAPI species identity mismatch'
        rows = set()
        for move in raw['moves']:
            mid = slug_id.get(move['move']['name'])
            if mid is None: continue
            for detail in move['version_group_details']:
                if detail['version_group']['name'] == 'red-blue' and detail['move_learn_method']['name'] == 'level-up':
                    rows.add((detail['level_learned_at'], mid))
        expected[sid] = sorted(rows)
        index = 16 + count*12 + (sid - 1)*4
        offset, length, _ = struct.unpack_from('<HBB', data, index)
        actual = []
        for i in range(length):
            level, slot = struct.unpack_from('<BB', data, 16 + count*12 + species_count*4 + (offset+i)*2)
            actual.append((level, slots[slot]))
        assert actual == expected[sid], f'RB source learning mismatch #{sid}'
        added += [(sid, lv, mid) for lv, mid in actual if mid in NEW]
    assert len(added) == 22
    return moves, expected, dict(commit=COMMIT, moves=count, learn_records=learns,
        added_records=added, corrected_classes=corrected,
        source_sha256={f: hashlib.sha256((src/f).read_bytes()).hexdigest() for f in files},
        moves_sha256=hashlib.sha256(data).hexdigest())


def compile_driver(directory: Path, implementation: str, assets_implementation: str | None = None) -> Path:
    (directory / 'battle.c').write_text(implementation)
    (directory / 'driver.c').write_text(DRIVER)
    assets = ['gen1.bin', 'gen1_front.bin', 'gen1_back.bin', 'palettes.bin', 'font16.bin', 'moves.bin', 'ui.bin']
    asm = []
    for name in assets:
        symbol = '_binary_' + name.replace('.', '_')
        asm += ['.balign 4', f'.global {symbol}_start', f'.global {symbol}_end',
                f'{symbol}_start:', f'.incbin "{ROOT / "assets" / name}"', f'{symbol}_end:']
    (directory / 'assets.S').write_text('\n'.join(asm)+'\n')
    exe = directory / 'probe'
    assets_path = MAIN / 'assets.c'
    if assets_implementation is not None:
        assets_path = directory / 'assets.c'
        assets_path.write_text(assets_implementation)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-Wall', '-Wextra', '-Werror',
        '-Wno-unused-variable', '-Wno-unused-but-set-variable', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
        '-I', str(MAIN), '-I', str(ROOT / 'tools/inspector/host/include'),
        str(directory / 'driver.c'), str(assets_path), str(MAIN / 'pokemon_names.c'),
        str(directory / 'assets.S'), '-o', str(exe)], check=True, capture_output=True)
    return exe


def ask(exe: Path, commands: list[str]) -> list[list[int]]:
    result = subprocess.run([str(exe)], input='\n'.join(commands)+'\n', capture_output=True, text=True, check=True)
    return [list(map(int, line.split())) for line in result.stdout.splitlines()]


def core_check(exe: Path, moves: dict, expected: dict) -> dict:
    sys.path.insert(0, str(ROOT / 'sim'))
    import systems
    commands, oracle = [], []
    for mid in NEW:
        typ = moves[mid]['type']
        for lv in (1, 2, 25, 100):
            for hp in (1, 2, 3, 71, 65535):
                damage = 20 if mid == 49 else 40 if mid == 82 else lv if mid in (69, 101) else max(1, hp//2)
                assert systems.fixed_move_damage(mid, lv, hp) == damage
                for defense in range(15):
                    immune = (mid in (49, 69, 162) and defense == 13) or (mid == 101 and defense in (0, 10))
                    for factor in (1, 614, 1024, 1536):
                        for accuracy in (0, 255):
                            commands.append(f'fixed {mid} {typ} {lv} {hp} {defense} {factor} {accuracy}')
                            oracle.append([0 if immune or not accuracy else damage,
                                           100 if not accuracy or not immune else 0,
                                           int(not accuracy), mid, 0 if immune else damage])
                    simmove = dict(id=mid, type=systems.TYPES[typ], power=moves[mid]['power'])
                    assert systems.move_weight(simmove, [systems.TYPES[typ]], [systems.TYPES[defense]], lv, hp) == (0 if immune else damage)
    actual = ask(exe, commands)
    assert len(actual) == len(oracle)
    for command, got, want in zip(commands, actual, oracle):
        assert got == want, f'fixed effect mismatch: {command}: {got} != {want}'
    known_commands, known_expected = [], []
    for sid, rows in expected.items():
        for lv in sorted({1, 100} | {level for level, _ in rows}):
            known_commands.append(f'known {sid} {lv}')
            ids = [mid for level, mid in rows if level <= lv][-8:] or [165]
            known_expected.append([len(ids)] + ids)
            assert [m['id'] for m in systems.known_moves(sid, lv)] == ids, 'Python recent-learning limit differs'
    assert ask(exe, known_commands) == known_expected, 'actual C learning lookup differs from source'
    assert 83 in ask(exe, ['known 136 54'])[0][1:], 'Flareon high-level Fire Spin was shadowed'
    flareon = ask(exe, [f'session 136 54 83 400 {seed} 0' for seed in range(1, 257)])
    assert any(row[0] == 83 and not row[3] for row in flareon), 'Fire Spin unreachable in real session'
    # Actual assets + session step in both roles, including forced single reply.
    fixtures = {49:(81,21), 69:(56,33), 82:(130,25), 101:(92,25), 162:(19,34)}
    reachable = []
    for mid, (sid, lv) in fixtures.items():
        for reply in (0, 1):
            commands = [f'session {sid} {lv} {mid} 71 {seed} {reply}' for seed in range(1, 129)]
            rows = ask(exe, commands)
            successes = [(seed, row) for seed, row in enumerate(rows, 1) if row[0] == mid and not row[3]]
            assert successes, f'new move unreachable in actual session: {mid}, side={reply}'
            for _, row in successes:
                damage = 20 if mid == 49 else 40 if mid == 82 else lv if mid in (69, 101) else 35
                assert row[1] == damage and row[4] == max(0, 71-damage), 'session target HP did not use fixed effect'
            reachable.append(dict(move=mid, species=sid, level=lv, wild_reply=bool(reply), seed=successes[0][0]))
    return dict(fixed_cases=len(oracle), source_lookup_cases=len(known_commands),
                resumed_actual_sessions=5*2*128 + 256, reachable=reachable,
                high_level_fire_spin_seed=next(i for i, row in enumerate(flareon, 1) if row[0] == 83 and not row[3]))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--src', type=Path, default=Path('/tmp/pokecrystal'))
    ap.add_argument('--cache', type=Path, default=Path('/tmp/gen1c'))
    ap.add_argument('--negative', action='store_true')
    ap.add_argument('--out', type=Path, default=ROOT / 'reports/evidence/moves-expansion-2026-09-08/mechanics.json')
    args = ap.parse_args()
    moves, expected, evidence = source_check(args.src, args.cache)
    original = (MAIN / 'battle.c').read_text()
    with tempfile.TemporaryDirectory(prefix='move_effects_') as td:
        directory = Path(td)
        evidence.update(core_check(compile_driver(directory, original), moves, expected))
        negatives = []
        if args.negative:
            for label, old, new in [
                ('fixed dispatch', 'if (fixed_move_damage(mv->id, a_lv, target_hp, &fixed)) {', 'if (false) {'),
                ('wrong half rounding', 'target_hp > 1 ? target_hp / 2 : 1', 'target_hp > 1 ? (target_hp + 1u) / 2 : 1'),
                ('STAB reapplied', 'return fixed;', 'return fixed * STAB / 100;'),
                ('immunity removed', 'if (mult == 0) return 0;', 'if (false) return 0;'),
            ]:
                assert original.count(old) == 1, f'negative anchor drift: {label}'
                mutant = compile_driver(directory, original.replace(old, new))
                try: core_check(mutant, moves, expected)
                except AssertionError as error:
                    assert 'fixed effect mismatch' in str(error), str(error)
                    negatives.append(label)
                else: raise AssertionError(f'negative escaped: {label}')
            asset_original = (MAIN / 'assets.c').read_text()
            token = 'if (n == max_out) {'
            assert asset_original.count(token) == 1
            mutant = compile_driver(directory, original,
                asset_original.replace(token, 'if (n == max_out) break; if (false) {'))
            try: core_check(mutant, moves, expected)
            except AssertionError as error:
                assert 'actual C learning lookup' in str(error), str(error)
                negatives.append('oldest learning records retained')
            else: raise AssertionError('recent-learning negative escaped')
        evidence['negative_checks'] = negatives
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2)+'\n')
    print(f'PASS source 104 moves / 629 learns, 5 real effects, {evidence["fixed_cases"]} exact damage cases, '
          f'{evidence["source_lookup_cases"]} C source lookup cases, {evidence["resumed_actual_sessions"]} resumed sessions, {len(evidence["negative_checks"])} negative controls')
    print(args.out)


if __name__ == '__main__': main()
