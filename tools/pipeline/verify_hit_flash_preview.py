#!/usr/bin/env python3
"""Check the real P3 target disappears while the attacker remains unchanged."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();r=Renderer(exe);out=ROOT/'reports/evidence/gold-animation-tracks-2026-09-09';out.mkdir(parents=True,exist_ok=True)
def crop(f,box):
 x,y,w,h=box;return b''.join(f['pixels'][((y+j)*240+x)*2:((y+j)*240+x+w)*2] for j in range(h))
try:
 r.command('boot 3 25 60 143 3 123 0 0 0')
 for side in [0,1]:
  r.command(f'move_preview 33 {side} 0 1');start=r.inspect()['move_animation_frames']-14
  hidden=r.command(f'move_preview 33 {side} {start} 1');assert r.command('check')['mismatch']==0
  shown=r.command(f'move_preview 33 {side} {start+2} 1');assert r.command('check')['mismatch']==0
  target=(8,140,96,96) if side else (124,24,112,112);actor=(124,24,112,112) if side else (8,140,96,96)
  assert set(crop(hidden,target))=={255};assert crop(hidden,target)!=crop(shown,target)
  assert crop(hidden,actor)==crop(shown,actor) and set(crop(shown,actor))!={255}
  (out/f'hit-side-{side}-hidden.png').write_bytes(png(hidden['pixels']));(out/f'hit-side-{side}-shown.png').write_bytes(png(shown['pixels']))
finally:r.close()
report={'both_targets_flash':True,'attacker_unchanged':True,'dirty_redraw_matches':True,'renderer':version};(out/'hit-preview.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
