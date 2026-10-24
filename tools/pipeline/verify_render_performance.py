#!/usr/bin/env python3
"""Compare optimized render pixels to an independently built pre-change renderer."""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True)
p.add_argument('--output-dir',type=Path,default=ROOT/'reports/evidence/render-performance-2026-10-23')
a=p.parse_args()
exe,version=build();old=Renderer(a.baseline);new=Renderer(exe);checks=0;times=[0.,0.]
def compare(command):
 global checks,old,new
 if command.startswith('boot '):
  old.close();new.close();old=Renderer(a.baseline);new=Renderer(exe)
 frames=[]
 for i,r in enumerate([old,new]):
  start=time.perf_counter();frames.append(r.command(command));times[i]+=time.perf_counter()-start
 assert frames[0]['pixels']==frames[1]['pixels'],f'pixel change: {command} check {checks}'
 assert new.command('check')['mismatch']==0,command
 checks+=1
try:
 for page in [1,2,3,4,5,6,9,10,11,12,13,14,15,16,17,18,19]:
  compare(f'boot {page} 115 54 130 4 81 0 0 0')
  for tick in [16,50,250,600,1000]:compare(f'tick {tick}')
 for species in range(1,252):
  for page in [3,5,12]:
   compare(f'boot {page} {species} 60 {species} 4 81 {species%2} 0 0')
   compare('tick 550');compare('tick 650')
 result=dict(passed=True,checks=checks,species=251,pages=17,baseline_sha256=hashlib.sha256(a.baseline.read_bytes()).hexdigest(),native_build=version,host_command_seconds=times,scope='Pixel equality and repaint oracle, not device FPS')
 out=a.output_dir;out.mkdir(parents=True,exist_ok=True);(out/'pixels.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:old.close();new.close()
