#!/usr/bin/env python3
"""Exercise all dex detail pages and tracking navigation in the native renderer."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();r=Renderer(exe);out=ROOT/'reports/evidence/collection-iteration-2026-09-09';out.mkdir(parents=True,exist_ok=True)
def shot(name,frame):
 assert r.command('check')['mismatch']==0
 (out/name).write_bytes(png(frame['pixels']))
try:
 r.command('boot 6 25 60 143 3 123 0 0 0');frame=r.command('key 0 1');shot('dex-detail.png',frame)
 for sid in range(1,152):
  assert r.command('check')['mismatch']==0
  if sid==25:shot('dex-pikachu.png',frame)
  if sid==151:
   frame=r.command('key 0 1');assert r.inspect()['page']==6;shot('locked-mew.png',frame)
  if sid<151:frame=r.command('key 1 1')
 r.command('challenge_unlock 16383');frame=r.command('key 0 1');assert r.inspect()['page']==15;shot('tracked-route.png',frame)
 r.command('exploration_fixture 0 24 0 1');r.command('key 0 1');frame=r.command('tick 700');shot('mew-clue.png',frame)
 frame=r.command('page 13');shot('rematch-hall.png',frame)
 result={'renderer':version,'dex_details':151,'locked_target_rejected':True,'unlocked_target_opens_exploration':True}
 (out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:r.close()
