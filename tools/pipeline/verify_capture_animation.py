#!/usr/bin/env python3
"""Capture presentation, exactly-once effects, save retry and retaliation.

Runs production C pages/render/music/nav against isolated host world/NVS;
never operates hardware or a player's save. Full versus dirty redraw each frame.
"""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build

exe, version = build()
checks = 0

def command(r, line):
    global checks
    frame = r.command(line)
    assert r.command('check')['mismatch'] == 0, line
    checks += 1
    return frame

def tick(r, ms=40): return command(r, f'tick {ms}')
def key(r, k): return command(r, f'key {k} 1')
def until(r, condition):
    for _ in range(2500):
        if condition(r.inspect()): return
        tick(r)
    raise AssertionError('timed out: ' + str(r.inspect()))

def scene():
    r = Renderer(exe)
    command(r, 'boot 4 25 30 133 4 123 0 0 0')
    return r

def animate(r, success):
    committed = r.inspect()
    frames = set()
    for elapsed in range(40, 3481, 40):
        frames.add(tick(r)['pixels'])
        # Queued and held physical buttons cannot skip, reroll or spend again.
        if elapsed < 3480:
            for k in range(3):
                key(r, k)
            state = r.inspect()
            assert state['page'] == 4 and not state['can_leave'] and state['display']['busy']
            assert state['inventory'] == committed['inventory']
            assert state['party'] == committed['party']
            assert state['active'] == committed['active']
            assert (state['music'] == 16) == (success and elapsed >= 2880)
    assert len(frames) >= 30, len(frames)

cases = []
for success in (True, False):
    r = scene()
    try:
        before = r.inspect()
        tick(r, 300 if success else 0); key(r, 0)
        after = r.inspect()
        assert after['inventory'][0] == before['inventory'][0] - 1
        assert after['party_count'] == before['party_count'] + success
        animate(r, success)
        if success:
            # Let the finite four-channel capture fanfare finish before auto exit.
            tick(r, 2600); assert r.inspect()['page'] == 4
            until(r, lambda s: s['page'] == 2)
            assert r.inspect()['party_count'] == 2
        else:
            key(r, 0)
            until(r, lambda s: s['page'] == 3)
            assert r.inspect()['active']['attacks'] == 1
            until(r, lambda s: s['presentation']['phase'] == 'choice')
            tick(r, 6000)
            assert r.inspect()['active']['attacks'] == 1
            key(r, 0); assert r.inspect()['page'] == 4  # May try again without choosing battle.
        cases.append('success and deferred fanfare' if success else 'breakout and exactly one retaliation')
    finally: r.close()

# Ball-spend failure: unchanged inventory and no animation. Catch-save failure:
# hold the ball, no false victory, and retry the same mon without another item.
r = scene()
try:
    before = r.inspect(); command(r, 'save_fail 1'); key(r, 0)
    assert r.inspect()['inventory'] == before['inventory'] and not r.inspect()['display']['busy']
    tick(r, 300); command(r, 'save_fail_after 1'); key(r, 0)
    assert r.inspect()['party_count'] == 1 and r.inspect()['inventory'][0] == 11
    animate(r, False)
    tick(r, 6000); assert r.inspect()['page'] == 4 and r.inspect()['music'] != 16
    key(r, 2); assert r.inspect()['page'] == 4
    key(r, 0)
    assert r.inspect()['party_count'] == 2 and r.inspect()['inventory'][0] == 11
    assert r.inspect()['music'] == 16
    cases.append('atomic save failures and same-ball retry')
finally: r.close()

# After a real automatic battle, a miss removes the target and cannot reopen it.
r = Renderer(exe)
try:
    command(r, 'boot 3 139 100 137 1 3 0 0 0')
    until(r, lambda s: s['presentation']['phase'] == 'choice')
    key(r, 1)
    until(r, lambda s: s['presentation']['phase'] == 'result')
    assert r.inspect()['active']['won']
    before = r.inspect(); key(r, 0); key(r, 0)
    assert r.inspect()['active'] is None
    animate(r, False)
    until(r, lambda s: s['page'] == 2)
    assert r.inspect()['party_count'] == before['party_count']
    command(r, 'page 4'); assert r.inspect()['page'] == 2
    cases.append('post-victory miss consumes the only chance')
finally: r.close()

report = {'build': version, 'cases': cases, 'frame_checks': checks, 'mismatches': 0}
path = ROOT / 'reports/evidence/capture-animation-2026-09-08/verification.json'
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps(report, ensure_ascii=False))
