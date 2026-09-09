#!/usr/bin/env python3
"""Actual P3 Surf overlays both HUDs, protects text, then restores cleanly."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build()
r=Renderer(exe)
out=ROOT/'reports/evidence/animation-restoration-2026-09-09'
out.mkdir(parents=True,exist_ok=True)
def crop(frame,x,y,w,h):
 return b''.join(frame['pixels'][((y+i)*240+x)*2:((y+i)*240+x+w)*2] for i in range(h))
try:
 r.command('boot 3 25 60 143 3 123 0 0 0')
 for side in [0,1]:
  start=r.command(f'move_preview 57 {side} 0 1')
  assert r.inspect()['move_animation_frames']==36
  crest=r.command(f'move_preview 57 {side} 18 1')
  assert r.command('check')['mismatch']==0
  # At the crest both the enemy HUD and player's HP/value area must be
  # water pixels, not white cutouts or text redrawn on top of the wave.
  for x,y,w,h in [(0,30,120,86),(104,160,136,80)]:
   data=crop(crest,x,y,w,h)
   colors={int.from_bytes(data[i:i+2],'big') for i in range(0,len(data),2)}
   assert 0xffff not in colors and len(colors)<=3,(side,x,y,colors)
  # Text is outside the effect layer, unchanged between its last active frame
  # and first clean frame (the same result/HP state).
  last=r.command(f'move_preview 57 {side} 33 1')
  clean=r.command(f'move_preview 57 {side} 34 1')
  final=r.command(f'move_preview 57 {side} 35 1')
  assert crop(last,0,240,240,80)==crop(clean,0,240,240,80)
  assert clean['pixels']==final['pixels']
  assert crop(start,8,8,110,16)==crop(final,8,8,110,16)
  assert r.command('check')['mismatch']==0
  (out/f'surf-overlay-side-{side}.png').write_bytes(png(crest['pixels']))
  (out/f'surf-restored-side-{side}.png').write_bytes(png(final['pixels']))
 r.command('move_preview 57 0 0 2');assert r.inspect()['move_animation_frames']==20
 r.command('move_preview 33 0 0 1');assert r.inspect()['move_animation_frames']==20
finally:
 r.close()
report=dict(renderer=version,both_huds_overlaid=True,message_window_preserved=True,
            clean_recovery=True,actual_frame_counts=True,original_equivalence=False)
(out/'overlay.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
