#!/usr/bin/env python3
"""Real settings input: status toggle, save failure and all-page opt-out."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import Renderer, build, png
out = ROOT/'reports/evidence/battery-inline-2026-10-03'
out.mkdir(parents=True, exist_ok=True)
exe, version = build()
r = Renderer(exe)
checks = 0
def cmd(line):
    global checks
    result = r.command(line)
    assert r.command('check')['mismatch'] == 0, line
    checks += 1
    return result
def key(n): return cmd(f'key {n} 1')
def top():
    pixels=cmd('check')['pixels']
    return b''.join(pixels[(y*240+164)*2:(y*240+228)*2] for y in range(40,56))
def options():
    cmd('page 11')
    for _ in range(5): key(1)
    key(2)
    for _ in range(8): key(1)
    assert r.inspect()['menu_view']['option_selected'] == 8
def shot(name): out.joinpath(name+'.png').write_bytes(png(cmd('check')['pixels']))
try:
    cmd('boot 11 25 40 74 3 123 0 0 0')
    enabled = top(); options(); shot('options-enabled')
    cmd('save_fail 1'); key(2)
    shot('save-failed')
    cmd('page 11');assert top() == enabled
    options()
    key(2);shot('options-disabled')
    cmd('page 11');assert top() == b'\xff'*(64*16*2)
    shot('disabled')
    reads = r.inspect()['battery_reads']
    cmd('tick 10000')
    assert r.inspect()['battery_reads'] == reads
    for page in [0,1,2,3,4,5,6,9,10,11,12,13,14,15,16]:
        cmd(f'page {page}')
        assert top() != enabled, page
        assert r.inspect()['battery_reads'] == reads, page
    options(); key(2)
    shot('options-reenabled')
    # Return is still reachable after the newly inserted row.
    key(1); key(2)
    assert not r.inspect()['menu_view']['options']
    assert top() == enabled
    shot('reenabled')
finally:
    r.close()
result = dict(build=version, band_checks=checks, default_on=True,
              save_failure_preserves_display=True, opt_out_all_pages=True,
              disabled_stops_battery_reads=True, reenable_immediate=True)
out.joinpath('toggle.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
