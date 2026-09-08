#!/usr/bin/env python3
"""Pack the four original Crystal battle HUD ball tiles without resampling."""
from pathlib import Path
import argparse,hashlib,json
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
im=Image.open(a.source).convert('RGB');assert im.size==(32,8)
rows=[]
for tile in range(4):
 data=[]
 for y in range(8):
  for x in range(0,8,4):
   v=0
   for dx in range(4):
    pixel=im.getpixel((tile*8+x+dx,y));assert pixel in [(k,k,k) for k in (0,85,170,255)]
    v=v<<2|pixel[0]//85
   data.append(v)
 rows.append('{'+','.join(hex(v) for v in data)+'}')
text='// Original Crystal gfx/battle/balls.png at 7a7881d0d62e0ddbd82dcf10e7116807487ac651.\n// 8x8 tiles: normal, status, fainted, empty. Packed row-major 2bpp.\n#pragma once\n#include <stdint.h>\nstatic const uint8_t PARTY_BALLS[4][16] = {\n'+',\n'.join(rows)+'\n};\n'
(ROOT/'firmware/main/party_ball_assets.h').write_text(text)
print(json.dumps({'source_sha256':hashlib.sha256(a.source.read_bytes()).hexdigest(),'tiles':4,'resampled':False}))
