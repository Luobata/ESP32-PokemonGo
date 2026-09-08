#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import build,Renderer,png
exe,version=build();p=ROOT/'reports/evidence/routes-story-2026-09-08';p.mkdir(parents=True,exist_ok=True)
checks=0
for chapter,mask in enumerate((0,1,3,15,63,255,4095,8191,16383)):
 r=Renderer(exe)
 try:
  r.command('boot 15 25 30 74 3 123 0 0 0');r.command(f'challenge_unlock {mask}');r.command('page 15')
  prior=r.inspect()['exploration'];f=r.command('key 0 3');assert r.command('check')['mismatch']==0
  (p/f'chapter-{chapter}.png').write_bytes(png(f['pixels']))
  assert r.inspect()['exploration']==prior
  if chapter<8:
   before_pixels=f['pixels'];f=r.command('key 1 1');assert r.command('check')['mismatch']==0
   (p/f'next-{chapter}.png').write_bytes(png(f['pixels']))
   assert f['pixels']!=before_pixels
   r.command('key 1 3')
  r.command('key 2 1');assert r.inspect()['page']==15 and r.inspect()['exploration']==prior
  checks+=4
 finally:r.close()
report={'chapters':9,'navigation_checks':checks,'version':version};(p/'journal.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
