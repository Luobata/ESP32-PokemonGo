#!/usr/bin/env python3
"""Pin Gold's evolution bubble tiles; portrait orbit sine sampling is adapted."""
import argparse,math,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('/tmp/pokewalk-gold-review'));p.add_argument('--check',action='store_true');a=p.parse_args()
commit='656583c939d30f920a316177311a502dd222b57c'
assert subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip()==commit
s=f'// Source: pret/pokegold@{commit} gfx/evo.\n#pragma once\n#include <stdint.h>\n'
for name,file in [('large','bubble_large.2bpp'),('small','bubble.2bpp')]:
 data=(a.source/'gfx/evo'/file).read_bytes();assert len(data)==(64 if name=='large' else 16)
 s+=f'static const uint8_t evo_light_{name}[] = {{'+','.join(str(x) for x in data)+'};\n'
s+='static const int16_t evo_sine[64] = {'+','.join(str(round(128*math.sin(i*math.pi/32))) for i in range(64))+'};\n'
target=Path(__file__).resolve().parents[2]/'firmware/main/evolution_light_data.h'
if a.check:assert target.read_text()==s
else:target.write_text(s)
print('Gold bubble tiles and portrait sine table verified')
