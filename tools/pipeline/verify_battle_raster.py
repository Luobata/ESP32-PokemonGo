#!/usr/bin/env python3
"""Compare every selected move frame with an independent baseline renderer."""
from pathlib import Path
import sys,json,argparse
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'tools/inspector'));from native import Renderer,build
parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True)
args=parser.parse_args();exe,version=build();a=Renderer(args.baseline);b=Renderer(exe);count=0
moves=json.loads((root/'tools/inspector/move-catalog.json').read_text())
try:
 for r in (a,b):r.command('boot 3 25 60 143 4 81 0')
 for move in moves:
  for side in (0,1):
   cmd=f"move_preview {move['id']} {side} 0 1"
   x=a.command(cmd);y=b.command(cmd);assert x['pixels']==y['pixels'],(move['id'],side,0)
   n=b.inspect()['move_animation_frames']
   for frame in range(n):
    cmd=f"move_preview {move['id']} {side} {frame} 1"
    x=a.command(cmd);y=b.command(cmd);assert x['pixels']==y['pixels'],(move['id'],side,frame)
    assert b.command('check')['mismatch']==0,(move['id'],side,frame,'dirty');count+=1
 print(json.dumps({'passed':True,'checks':count,'moves':len(moves),'both_sides':True,'renderer':version,'scope':'all emitted frames, original palettes and HUD overlays; pixel oracle not FPS'}))
finally:a.close();b.close()
