#!/usr/bin/env python3
"""Battery is inline in menu/care only; drawing is pure and sleep stops polling."""
import json
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import Renderer, build, png
OUT = ROOT/'reports/evidence/battery-inline-2026-10-03'
OUT.mkdir(parents=True, exist_ok=True)
exe, version = build()
pages = [0,1,2,3,4,5,6,9,10,11,12,13,14,15,16]
def region(pixels):
    return b''.join(pixels[(y*240+164)*2:(y*240+228)*2] for y in range(40,56))
widget = None
for page in [11,5] + [p for p in pages if p not in [11,5]]:
    r = Renderer(exe)
    try:
        r.command(f'boot {page} 25 12 74 3 123 0 0 1')
        r.command('tick 500')
        frame = r.command('check')
        assert not frame['mismatch'], page
        row = region(frame['pixels'])
        if page == 11: widget = row
        if page in [5,11]:
            assert row == widget
            assert r.inspect()['battery_reads'] == 1
        else:
            assert row != widget
            assert r.inspect()['battery_reads'] == 0
        OUT.joinpath(f'P{page}.png').write_bytes(png(frame['pixels']))
        reads = r.inspect()['battery_reads']
        for _ in range(3): r.command('check')
        assert r.inspect()['battery_reads'] == reads
    finally:
        r.close()
# Long official/legacy names and 100% (widest reading).
for style in [0,1]:
    r = Renderer(exe)
    try:
        r.command(f'boot 5 122 100 74 3 123 0 {style} 0')
        r.command('battery 100');r.command('tick 10000')
        for page in [5,11]:
            r.command(f'page {page}')
            frame = r.command('check');assert not frame['mismatch']
            OUT.joinpath(f'long-name-{style}-P{page}.png').write_bytes(png(frame['pixels']))
    finally: r.close()
r = Renderer(exe)
try:
    r.command('boot 11 25 12 74 3 123 0 0 1')
    previous = widget
    for value in [100,20,1,0,101]:
        r.command(f'battery {value}');r.command('tick 10000')
        f=r.command('check');assert not f['mismatch']
        current=region(f['pixels']);assert current != previous
        previous=current
        OUT.joinpath(f'battery-{value}.png').write_bytes(png(f['pixels']))
    r.command('key 2 3');assert r.inspect()['display']['off']
    before=r.inspect()['battery_reads'];r.command('battery 76');r.command('tick 30000')
    assert r.inspect()['battery_reads']==before
    r.command('key 0 1');r.command('tick 10000')
    assert region(r.command('check')['pixels'])==widget
    r.command('page 1');before=r.inspect()['battery_reads'];r.command('tick 10000')
    assert r.inspect()['battery_reads']==before
finally:r.close()
result=dict(build=version,pages=pages,visible_pages=[5,11],band_parity=True,static_page_refresh=True,no_reads_during_render=True,sleep_stops_reads=True,other_pages_stop_reads=True)
OUT.joinpath('validation.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
