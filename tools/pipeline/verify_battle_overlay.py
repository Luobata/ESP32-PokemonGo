#!/usr/bin/env python3
"""Actual original Surf crest crosses both HUDs, protects text, and restores cleanly."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build()
r=Renderer(exe)
out=ROOT/'reports/evidence/gold-animation-tracks-2026-09-09'
out.mkdir(parents=True,exist_ok=True)
def crop(frame,x,y,w,h):
 return b''.join(frame['pixels'][((y+i)*240+x)*2:((y+i)*240+x+w)*2] for i in range(h))
try:
 r.command('boot 3 25 60 143 3 123 0 0 0')
 for side in [0,1]:
  start=r.command(f'move_preview 57 {side} 0 1')
  count=r.inspect()['move_animation_frames'];assert count>36
  covered=[False,False]
  for f in range(count-14):
   crest=r.command(f'move_preview 57 {side} {f} 1')
   for i,box in enumerate([(8,8,104,68),(112,170,128,64)]):
    covered[i]|=crop(crest,*box)!=crop(start,*box)
   assert crop(start,0,240,240,80)==crop(crest,0,240,240,80)
  assert all(covered),covered
  clean=r.command(f'move_preview 57 {side} {count-2} 1')
  final=r.command(f'move_preview 57 {side} {count-1} 1')
  assert clean['pixels']==final['pixels']
  assert crop(start,8,8,110,16)==crop(final,8,8,110,16)
  assert r.command('check')['mismatch']==0
  (out/f'surf-restored-side-{side}.png').write_bytes(png(final['pixels']))
 r.command('move_preview 57 0 0 2');assert r.inspect()['move_animation_frames']==20
 r.command('move_preview 33 0 0 1');assert r.inspect()['move_animation_frames']>20

finally:
 r.close()
report=dict(renderer=version,both_huds_overlaid=True,message_window_preserved=True,
            clean_recovery=True,actual_frame_counts=True,original_equivalence=False)
(out/'overlay.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
