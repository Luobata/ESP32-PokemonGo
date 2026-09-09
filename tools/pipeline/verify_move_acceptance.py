#!/usr/bin/env python3
"""Every catalog move uses the actual shared P3 renderer, both sides/all fixture modes."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();r=Renderer(exe);out=ROOT/'reports/evidence/selected-moves-2026-09-09';out.mkdir(parents=True,exist_ok=True)
rows=json.loads((ROOT/'tools/inspector/move-catalog.json').read_text());assert len(rows)==191;checks=0
try:
 r.command('boot 3 25 60 65 3 123 0 0 0')
 for m in rows:
  for side in [0,1]:
   for mode in [0,1,2,3]:
    for frame in [0,8,14,35]:
     f=r.command(f"move_preview {m['id']} {side} {frame} {mode}")
     assert r.command('check')['mismatch']==0,(m['id'],side,mode,frame);checks+=1
     if m['id'] in [172,200,202,231,242,247] and mode==1 and frame==8:(out/f"move-{m['id']}-side-{side}.png").write_bytes(png(f['pixels']))
finally:r.close()
report={'moves':len(rows),'new_moves':sum(m['new'] for m in rows),'sides':2,'modes':4,'pixel_checks':checks,'renderer':version,'same_p3_renderer':True}
(out/'acceptance.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
