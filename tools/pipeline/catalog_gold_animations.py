#!/usr/bin/env python3
"""Resolve Gold animation script dependencies for every supported move.

This is a source catalogue, NOT a renderer or a claim of restored animations.
Local branches, calls and fall-through are traversed; no unknown branch target
is ignored. Raw commands retain source lines and arguments for porting/QA.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
COMMIT = '656583c939d30f920a316177311a502dd222b57c'
BASE = f'https://github.com/pret/pokegold/blob/{COMMIT}/'
FILES = ['data/moves/animations.asm', 'constants/battle_anim_constants.asm',
         'data/battle_anims/objects.asm', 'data/battle_anims/framesets.asm',
         'data/battle_anims/oam.asm', 'data/battle_anims/object_gfx.asm',
         'engine/battle_anims/functions.asm', 'engine/battle_anims/bg_effects.asm',
         'engine/battle_anims/anim_commands.asm', 'engine/battle_anims/core.asm',
         'engine/battle_anims/helpers.asm']
BRANCHES = {'anim_call', 'anim_jump', 'anim_loop', 'anim_jumpuntil',
            'anim_if_param_equal', 'anim_if_var_equal', 'anim_if_param_and'}


def build(src):
    sources = {}
    for path in FILES:
        expected = subprocess.check_output(['git', '-C', str(src), 'show', f'{COMMIT}:{path}'])
        if (src / path).read_bytes() != expected:
            raise ValueError(f'{path} differs from pinned Gold source')
        sources[path] = expected.decode()
    asm = sources[FILES[0]]
    constants = sources[FILES[1]]
    commands, labels, scope = [], {}, ''
    for line, raw in enumerate(asm.splitlines(), 1):
        code = raw.split(';')[0].strip()
        label = re.fullmatch(r'([A-Za-z_]\w*|\.\w+):{0,2}', code)
        if label and not code.startswith('anim_'):
            name = label[1]
            if name.startswith('.'):
                name = scope + name
            else:
                scope = name
            labels[name] = len(commands)
        elif code.startswith('anim_'):
            op, *tail = code.split(None, 1)
            args = [v.strip() for v in tail[0].split(',')] if tail else []
            commands.append(dict(op=op, args=args, line=line, scope=scope))
    for c in commands:
        if c['op'] in BRANCHES:
            target = c['args'][-1]
            if target.startswith('.'):
                target = c['scope'] + target
            if target not in labels:
                raise ValueError(f"unresolved branch {target} at {c['line']}")
            c['target'] = labels[target]
            c['target_label'] = target

    def table(prefix, path, pattern):
        keys = re.findall(r'^\s*const (' + prefix + r'\w+)', constants, re.M)
        values = re.findall(pattern, sources[path].split('assert_table_length', 1)[0], re.M)
        if len(keys) != len(values):
            raise ValueError(f'{prefix}: {len(keys)} constants != {len(values)} records')
        return dict(zip(keys, values))

    objects = table('BATTLE_ANIM_OBJ_', 'data/battle_anims/objects.asm', r'^\s*battleanimobj ([^\n;]+)')
    functions = table('BATTLE_ANIM_FUNC_', 'engine/battle_anims/functions.asm', r'^\s*dw (BattleAnimFunction_\w+)')
    backgrounds = table('BATTLE_BG_EFFECT_', 'engine/battle_anims/bg_effects.asm', r'^\s*dw (BattleBGEffect_\w+)')
    framesets = table('BATTLE_ANIM_FRAMESET_', 'data/battle_anims/framesets.asm', r'^\s*dw (\.Frameset_\w+)')
    definitions = {}
    for name, raw in objects.items():
        flags, yfix, frame, function, palette, gfx = [v.strip() for v in raw.split(',')]
        definitions[name] = dict(flags=flags, enemy_y_fix=yfix, frameset=framesets[frame],
                                 function=functions[function], palette=palette, graphics=gfx)
    roots = re.findall(r'^\s*dw (BattleAnim_\w+)', asm, re.M)[:252]
    catalog = json.loads((ROOT / 'tools/inspector/move-catalog.json').read_text())
    moves = []
    for move in catalog:
        root = roots[move['id']]
        pending, seen = [labels[root]], set()
        while pending:
            pc = pending.pop()
            if pc in seen:
                continue
            if not 0 <= pc < len(commands):
                raise ValueError(f'{root} falls outside script')
            seen.add(pc)
            c = commands[pc]
            if 'target' in c:
                pending.append(c['target'])
            # Loop count zero is an original infinite loop; retain the back edge
            # but do not invent a fall-through path past it.
            if c['op'] not in {'anim_ret', 'anim_jump'} and not (c['op'] == 'anim_loop' and c['args'][0] in {'0', '$0'}):
                pending.append(pc + 1)
        sequence = [commands[i] for i in sorted(seen)]
        objs = sorted({c['args'][0] for c in sequence if c['op'] == 'anim_obj'})
        bgs = sorted({c['args'][0] for c in sequence if c['op'] == 'anim_bgeffect'})
        for obj in objs:
            if obj not in definitions:
                raise ValueError(f'{root}: unresolved object {obj}')
        for bg in bgs:
            if bg not in backgrounds:
                raise ValueError(f'{root}: unresolved background {bg}')
        moves.append(dict(id=move['id'], name=move['name'], script=root,
                          source_url=BASE + FILES[0] + '#L' + str(commands[labels[root]]['line'] - 1),
                          command_indices=sorted(seen), objects=objs,
                          functions=sorted({definitions[o]['function'] for o in objs}),
                          background_effects=bgs,
                          palette_commands=sorted({c['op'] for c in sequence if c['op'] in {'anim_bgp','anim_obp0','anim_obp1','anim_resetobp0'}}),
                          sound_effects=sorted({c['args'][-1] for c in sequence if c['op']=='anim_sound'}),
                          verified_original=False))
    return dict(source_commit=COMMIT, source_files={p:hashlib.sha256(s.encode()).hexdigest() for p,s in sources.items()},
                policy='Gold is the animation reference. HUD overlay is allowed; the message window is protected. Source catalogue completeness is not renderer equivalence.',
                moves=moves, commands=commands, objects=definitions, backgrounds=backgrounds,
                summary=dict(moves=len(moves), scripts_with_backgrounds=sum(bool(m['background_effects']) for m in moves),
                             object_functions=len({f for m in moves for f in m['functions']}),
                             background_functions=len({b for m in moves for b in m['background_effects']}),
                             verified_original=0))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,default=Path('/tmp/pokewalk-gold-review'))
    p.add_argument('--check',action='store_true')
    a=p.parse_args()
    report=build(a.source)
    out=ROOT/'tools/inspector/move-animation-sources.json'
    data=json.dumps(report,ensure_ascii=False,indent=2)+'\n'
    if a.check:
        if out.read_text()!=data:
            raise SystemExit('Gold source catalogue is stale')
    else:
        out.write_text(data)
    print(json.dumps(report['summary']))


if __name__=='__main__':
    main()
