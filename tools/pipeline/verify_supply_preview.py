#!/usr/bin/env python3
"""Drive the real idle page through durable exploration-credit transitions."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png

out = ROOT / 'reports/evidence/exploration-supply-2026-09-09'
out.mkdir(parents=True, exist_ok=True)
exe, version = build()
r = Renderer(exe)
checks = 0

def cmd(line):
    global checks
    frame = r.command(line)
    assert r.command('check')['mismatch'] == 0, line
    checks += 1
    return frame

def state():
    return r.inspect()['exploration']

def shot(name):
    (out / (name + '.png')).write_bytes(png(cmd('check')['pixels']))

try:
    cmd('boot 1 25 20 74 3 123 0 0 0')
    cmd('supply_scan 1 0 0'); cmd('tick 3500')
    assert state()['energy'] == 4
    empty = cmd('check')['pixels']; shot('empty')
    cmd('supply_scan 1 1 256'); cmd('tick 250')
    assert state()['energy'] == 4 and state()['supply_q10'] == 256
    assert cmd('check')['pixels'][240*240*2:] != empty[240*240*2:]
    shot('quarter')
    cmd('supply_scan 1 1 512'); cmd('tick 250'); shot('three-quarters')
    assert state()['supply_q10'] == 768
    cmd('supply_scan 1 1 256'); cmd('tick 250'); shot('received')
    assert state()['energy'] == 5 and state()['supply_q10'] == 0
    notice = cmd('check')['pixels']
    cmd('tick 3250'); shot('new-cycle')
    assert cmd('check')['pixels'][264*240*2:280*240*2] != notice[264*240*2:280*240*2]
    cmd('supply_scan 1 1 1280'); cmd('tick 250')
    assert state()['energy'] == 6 and state()['supply_q10'] == 256
    before = state(); cmd('save_fail 1'); cmd('supply_scan 1 1 768'); cmd('tick 250')
    assert state() == before
    cmd('supply_scan 1 1 768'); cmd('tick 250')
    assert state()['energy'] == 7 and state()['supply_q10'] == 0
    cmd('exploration_fixture 0 24 0 0'); cmd('tick 3500')
    cmd('supply_scan 1 1 65535'); cmd('tick 250'); shot('full')
    assert state()['energy'] == 24 and state()['supply_q10'] == 4096
    cmd('page 15'); cmd('key 0 1'); cmd('tick 600')
    assert state()['energy'] == 23
    cmd('page 1'); shot('banked')
    cmd('supply_scan 1 0 0'); cmd('tick 250'); shot('refilled')
    assert state()['energy'] == 24 and state()['supply_q10'] == 3072
    cmd('tick 3250'); shot('full-after-refill')
    report = {'status': 'PASS', 'renderer': version, 'dirty_full_checks': checks,
              'loop_and_remainder': True, 'saved_grant_feedback': True,
              'save_failure_retry': True, 'full_capacity_banked': True,
              'stationary_refill_after_real_exploration': True}
    (out / 'ui.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
finally:
    r.close()
