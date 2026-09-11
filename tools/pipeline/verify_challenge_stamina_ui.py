#!/usr/bin/env python3
"""Production page input/rendering for paid challenges and recovery hints."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png

exe, version = build()
out = ROOT / 'reports/evidence/challenge-stamina-2026-09-10'
out.mkdir(parents=True, exist_ok=True)
renderer = None
checks = 0

def cmd(command):
    global checks
    frame = renderer.command(command)
    assert renderer.command('check')['mismatch'] == 0, command
    checks += 1
    return frame

def state():
    return renderer.inspect()

def boot(page=15, stamina=90):
    global renderer
    if renderer: renderer.close()
    renderer = Renderer(exe)
    cmd(f'boot {page} 25 100 74 3 123 0 0 0')
    cmd(f'nurture_fixture 80 80 {stamina} 50')

def key(button):
    for event in (0, 4, 1, 5): cmd(f'key {button} {event}')

def back():
    for event in (0, 3, 4, 5): cmd(f'key 1 {event}')

def shot(name):
    frame = cmd('tick 180')
    (out / (name + '.png')).write_bytes(png(frame['pixels']))

def route_hall():
    key(0); key(2)  # Exploration -> activities.
    shot('activities-cost')
    key(2)
    assert state()['page'] == 13 and state()['challenge']['mode'] == 0

def until(predicate):
    for _ in range(160):
        if predicate(state()): return
        cmd('tick 180')
    raise AssertionError(state())

try:
    boot(stamina=4); route_hall(); shot('route-insufficient')
    energy = state()['exploration']['energy']
    for _ in range(3): key(2)
    assert not state()['challenge']['active'] and state()['nurture']['stamina'] == 4
    assert state()['exploration']['energy'] == energy
    cmd('nurture_fixture 80 80 5 50'); cmd('tick 180'); shot('route-exact-cost')
    cmd('save_fail 1'); key(2); shot('entry-save-failed')
    assert not state()['challenge']['active'] and state()['nurture']['stamina'] == 5
    key(2)
    assert state()['challenge']['active'] and state()['nurture']['stamina'] == 0
    assert state()['exploration']['energy'] == energy
    key(2); assert state()['nurture']['stamina'] == 0
    back(); until(lambda s: s['challenge']['mode'] == 6); shot('retire-no-refund')
    key(1); key(2); cmd('tick 1500'); key(2)
    assert not state()['challenge']['active'] and state()['nurture']['stamina'] == 0

    boot(13, 9); shot('gym-insufficient'); key(2)
    assert not state()['challenge']['active'] and state()['nurture']['stamina'] == 9
    cmd('nurture_fixture 80 80 10 50'); key(2)
    assert state()['challenge']['active'] and state()['nurture']['stamina'] == 0
    cmd('challenge_hp_fixture 0 0 0'); until(lambda s: s['challenge']['mode'] == 5)
    assert state()['nurture']['stamina'] == 0 and state()['nurture']['mood'] == 75
    cmd('tick 1500'); key(2); assert not state()['challenge']['active']

    boot(13, 20); cmd('challenge_unlock 255'); shot('league-entry-cost'); key(2)
    assert state()['challenge']['trainer'] == 8 and state()['nurture']['stamina'] == 0
    for i in range(len(state()['challenge']['sides'][1]['mons'])): cmd(f'challenge_hp_fixture 1 {i} 0')
    until(lambda s: s['challenge']['mode'] == 5)
    for _ in range(3): cmd('tick 1000'); key(2)
    assert state()['challenge']['mode'] == 0 and state()['challenge']['league'] == 9
    shot('league-prepaid'); key(2)
    assert state()['challenge']['trainer'] == 9 and state()['challenge']['active']
    assert state()['nurture']['stamina'] == 0

    boot(stamina=4); route_hall()
    cmd('tick 30000')
    key(2); key(2)  # Wake first, then try the still-unaffordable entry.
    assert state()['nurture']['stamina'] == 4 and not state()['challenge']['active']
    shot('fractional-balance')

    boot(stamina=0); route_hall(); shot('recovery-6-minutes')
    for _ in range(7): cmd('tick 60000')
    assert state()['display']['off'] and state()['nurture']['stamina'] == 5
    key(2); assert not state()['display']['off'] and not state()['challenge']['active']
    shot('recovered-standby'); key(2)
    assert state()['challenge']['active']
    result = dict(build=version, dirty_full_checks=checks, passed=True,
                  scope='Route/gym fees, failure rollback, no refund, defeat mood, prepaid league, standby recovery and wake gesture isolation')
    (out / 'ui.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
finally:
    if renderer: renderer.close()
