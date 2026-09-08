#!/usr/bin/env python3
"""Reach new moves through real P3 learning/selection and save C RGB565 evidence."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png

OUT = ROOT / 'reports/evidence/moves-expansion-2026-09-08'
# Actual Red/Blue level-up learners, no injected move/session state.
FIXTURES = [(49,81,21), (69,56,33), (82,130,25), (101,92,25),
            (162,19,34), (56,7,42), (63,130,60), (120,100,22), (83,136,54)]


def main():
    exe, version = build()
    r = Renderer(exe)
    records, checks = [], 0
    OUT.mkdir(parents=True, exist_ok=True)

    def command(text):
        nonlocal checks
        frame = r.command(text)
        assert r.command('check')['mismatch'] == 0, f'dirty/full mismatch: {text}'
        checks += 1
        return frame

    try:
        for mid, sid, level in FIXTURES:
            for seed in range(1, 257):
                r.close()
                r = Renderer(exe)
                command(f'boot 3 {sid} {level} 74 5 {seed} 0')
                # Entry and source species animation both complete before choice.
                for _ in range(200):
                    if r.inspect()['presentation']['phase'] == 'choice': break
                    command('tick 60')
                else: raise AssertionError('entry never reached choice')
                start = r.inspect()
                command('key 1 1')
                first = command('tick 60')
                state = r.inspect()
                view = state['presentation']
                if view['move_id'] == mid and view['by_pet'] and state['active']['wild_hp'] < start['queue'][0]['wild_hp']:
                    break
            else: raise AssertionError(f'actual P3 did not select move {mid}')
            before_hp = start['queue'][0]['wild_hp']
            committed_hp = state['active']['wild_hp']
            if mid in (49,69,82,101,162):
                expected = 20 if mid == 49 else 40 if mid == 82 else level if mid in (69,101) else max(1,before_hp//2)
                assert committed_hp == max(0,before_hp-expected), f'P3 fixed damage wrong: {mid}'
            images = [(0, first)]
            hashes = []
            visible_hp = []
            for frame in range(1, 18):
                shot = command('tick 60')
                view = r.inspect()['presentation']
                if view['move_id'] != mid: break
                hashes.append(hashlib.sha256(shot['pixels']).hexdigest())
                visible_hp.append(view['visible_wild_hp'])
                if frame in (4,7,10,13): images.append((frame, shot))
            assert len(set(hashes)) > 3, f'P3 animation not visibly changing: {mid}'
            assert min(visible_hp) < before_hp, f'P3 HP stayed unchanged: {mid}'
            for frame, shot in images:
                (OUT / f'move-{mid:03}-frame-{frame:02}.png').write_bytes(png(shot['pixels']))
            records.append(dict(move=mid, species=sid, level=level, wild=74, rarity=5, seed=seed,
                hp_before=before_hp, hp_after=committed_hp, frame_hashes=hashes,
                visible_hp=visible_hp, samples=[frame for frame,_ in images]))
            print(f'PASS actual P3 move {mid}: species {sid} Lv{level}, seed {seed}, HP {before_hp}->{committed_hp}', flush=True)
    finally:
        r.close()
    result = dict(status='PASS', build=version, dirty_full_checks=checks, fixtures=records,
                  scope='Actual C P3 selection, animation and HP; native host clock/world fixture, no physical device timing measurement')
    (OUT / 'native.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f'PASS {len(records)} actual learned moves, {checks} dirty/full checks, {version}')


if __name__ == '__main__': main()
