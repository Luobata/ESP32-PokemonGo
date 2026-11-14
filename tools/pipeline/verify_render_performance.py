#!/usr/bin/env python3
"""Compare optimized render pixels to an independently built pre-change renderer."""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build
p=argparse.ArgumentParser();p.add_argument('--baseline',type=Path,required=True)
p.add_argument('--output-dir',type=Path,default=ROOT/'reports/evidence/render-performance-2026-10-23')
p.add_argument('--expect-stamina-copy-fix',action='store_true',help='Allow only the known 2→1 hour numeral at trainer selection (124..131,264..275)')
a=p.parse_args()
exe,version=build();old=Renderer(a.baseline);new=Renderer(exe);checks=0;times=[0.,0.]
current_page=None;copy_changes=0
def compare(command):
 global checks,old,new,current_page,copy_changes
 if command.startswith('boot '):
  current_page=int(command.split()[1])
  old.close();new.close();old=Renderer(a.baseline);new=Renderer(exe)
 frames=[]
 for i,r in enumerate([old,new]):
  start=time.perf_counter();frames.append(r.command(command));times[i]+=time.perf_counter()-start
 if frames[0]['pixels']!=frames[1]['pixels']:
  assert a.expect_stamina_copy_fix and current_page==13,f'pixel change: {command} check {checks}'
  before,after=frames[0]['pixels'],frames[1]['pixels']
  changed=[i//2 for i in range(0,len(before),2) if before[i:i+2]!=after[i:i+2]]
  assert len(changed)==44 and all(124<=i%240<=131 and 264<=i//240<=275 for i in changed),(command,changed)
  copy_changes+=1
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
 result=dict(passed=True,checks=checks,species=251,pages=17,baseline_sha256=hashlib.sha256(a.baseline.read_bytes()).hexdigest(),native_build=version,host_command_seconds=times,expected_stamina_copy_frames=copy_changes,scope='Pixel equality and repaint oracle, not device FPS')
 out=a.output_dir;out.mkdir(parents=True,exist_ok=True);(out/'pixels.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:old.close();new.close()
