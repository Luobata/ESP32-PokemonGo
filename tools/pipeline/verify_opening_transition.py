#!/usr/bin/env python3
"""Opening completion/skip smoothly enters starter without consuming held clicks."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=ROOT/'reports/evidence/opening-transition-2026-09-09';out.mkdir(parents=True,exist_ok=True)
exe,version=build();checks=0
for skip in (True,False):
 r=Renderer(exe)
 try:
  r.command('boot 0 25 12 74 3 123 0 0 0');wait=0;enter=False;pages=[]
  if skip:r.command('key 2 1')
  for n in range(1800):
   frame=r.command('tick 33');st=r.inspect();assert st['party_count']==0
   assert r.command('check')['mismatch']==0;checks+=1
   if skip and n in (18,45,88,99): (out/f'skip-{n:03d}.png').write_bytes(png(frame['pixels']))
   if st['display']['busy']:
    # During the handoff and reveal, repeated confirm must never select a starter.
    if skip:r.command('key 0 1');r.command('key 2 1')
    wait=0
   elif st['page']==0 and not skip:
    wait+=1
    if wait==45:r.command('key 0 1');wait=0
   elif st['page']==9:
    enter=True;(out/f'starter-{skip}.png').write_bytes(png(frame['pixels']));break
  assert enter
  r.command('key 1 1');r.command('key 0 1');assert r.inspect()['pet']==4 and r.inspect()['party_count']==1
 finally:r.close()
result={'status':'PASS','renderer':version,'frame_checks':checks,'normal_and_skip':True,'input_lock':True,'starter_after_reveal':True}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
