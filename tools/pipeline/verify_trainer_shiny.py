#!/usr/bin/env python3
"""Party shiny flag survives leader selection into the actual trainer renderer."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import build,Renderer,png
exe,version=build();out=ROOT/'reports/evidence/system-review-2026-09-08';out.mkdir(parents=True,exist_ok=True);frames=[]
for shiny in (0,1):
 r=Renderer(exe)
 try:
  for c in ['boot 12 1 100 74 3 123 0 0 0',f'party_add 25 100 80 0 {shiny}','tick 500','key 1 1','key 0 1','key 0 1','challenge_unlock 0','page 13','key 0 1','tick 3000']:
   r.command(c);assert r.command('check')['mismatch']==0,c
  assert r.inspect()['pet']==25 and r.inspect()['challenge']['mode']==2,r.inspect()
  f=r.command('check')['pixels'];frames.append(f);(out/f'trainer-shiny-{shiny}.png').write_bytes(png(f))
 finally:r.close()
diff=[i//2 for i in range(0,len(frames[0]),2) if frames[0][i:i+2]!=frames[1][i:i+2]]
assert len(diff)>100
assert all(8<=i%240<104 and 140<=i//240<236 for i in diff)
print(json.dumps({'version':version,'shiny_pixels_changed':len(diff),'only_player_sprite_changed':True}))
