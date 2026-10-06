#!/usr/bin/env python3
"""Production menu/care pixels, elapsed-time updates and screen-idle transitions."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
OUT=ROOT/'reports/evidence/playtime-2026-10-06'

def run():
 OUT.mkdir(parents=True,exist_ok=True);exe,version=build();checks=0
 def cmd(r,line):
  nonlocal checks
  result=r.command(line);assert r.command('check')['mismatch']==0,line;checks+=1;return result
 def shot(r,name):
  f=cmd(r,'check');(OUT/(name+'.png')).write_bytes(png(f['pixels']));return f['pixels']
 def outside_title(data):
  d=bytearray(data)
  for y in range(8,24):d[(y*240+80)*2:(y*240+228)*2]=b'\0'*(148*2)
  return d
 for page in [5,11]:
  r=Renderer(exe)
  try:
   cmd(r,f'boot {page} 139 100 74 3 123 0 0 1');cmd(r,'battery 100');cmd(r,'tick 10000')
   baseline=None
   for seconds in [0,59,60,3599,3600,452967,4294967295]:
    cmd(r,f'playtime_fixture {seconds}');assert r.inspect()['playtime_s']==seconds
    pixels=shot(r,f'P{page}-{seconds}')
    if baseline is None:baseline=outside_title(pixels)
    assert outside_title(pixels)==baseline # Duration never moves or overlaps any other row.
  finally:r.close()
 r=Renderer(exe)
 try:
  cmd(r,'boot 11 25 36 74 3 123 0 0 1');cmd(r,'playtime_fixture 59');before=cmd(r,'check')['pixels']
  cmd(r,'tick 1000');assert r.inspect()['playtime_s']==60
  assert cmd(r,'check')['pixels']!=before
  # Switching pages continues the same clock, including pages without the widget.
  cmd(r,'page 5');cmd(r,'tick 1000');assert r.inspect()['playtime_s']==61
  cmd(r,'page 1');cmd(r,'tick 1000');assert r.inspect()['playtime_s']==62
  cmd(r,'key 2 3');assert r.inspect()['display']['off'];seconds=r.inspect()['playtime_s']
  cmd(r,'tick 60000');cmd(r,'tick 60000');assert r.inspect()['playtime_s']==seconds
  cmd(r,'key 0 1');cmd(r,'tick 1000');assert r.inspect()['playtime_s']==seconds+1
  cmd(r,'page 11')
  # Disabling the battery must neither hide the duration nor stop counting.
  for _ in range(5):cmd(r,'key 1 1')
  cmd(r,'key 2 1')
  for _ in range(8):cmd(r,'key 1 1')
  cmd(r,'key 2 1');cmd(r,'page 11');cmd(r,'playtime_fixture 3599')
  reads=r.inspect()['battery_reads'];cmd(r,'tick 1000');assert r.inspect()['playtime_s']==3600
  assert r.inspect()['battery_reads']==reads;shot(r,'battery-hidden')
  cmd(r,'page 11');cmd(r,'tick 60000');assert r.inspect()['display']['off']
  seconds=r.inspect()['playtime_s'];cmd(r,'tick 60000');assert r.inspect()['playtime_s']==seconds
 finally:r.close()
 result=dict(build=version,checks=checks,pixel_band_mismatches=0,visible_pages=[5,11],minute_refresh=True,screen_off_excluded=True,battery_independent=True,long_values_fit=True)
 (OUT/'preview.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':run()
