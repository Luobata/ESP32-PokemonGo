#!/usr/bin/env python3
"""Compare complete capture animation against an independent pre-change executable."""
from pathlib import Path
import sys,json,argparse
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'tools/inspector'))
from native import Renderer,build
parser=argparse.ArgumentParser();parser.add_argument('--baseline',type=Path,required=True)
args=parser.parse_args();exe,version=build();base=args.baseline;count=0
for species in [1,25,91,115,130,143,201,235,249,251]:
 old=Renderer(base);new=Renderer(exe)
 try:
  commands=[f'boot 4 115 55 {species} 4 81 0 0 0','key 2 1']+['tick 40']*125
  for cmd in commands:
   a=old.command(cmd);b=new.command(cmd);assert a['pixels']==b['pixels'],(species,count,cmd);assert new.command('check')['mismatch']==0,(species,count,'dirty');count+=1
 finally:old.close();new.close()
print(json.dumps(dict(passed=True,checks=count,renderer=version,scope='capture throw/shrink/rock/reveal/outcome every 40ms and DMA immutability')))
