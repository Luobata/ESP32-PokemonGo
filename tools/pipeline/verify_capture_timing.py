#!/usr/bin/env python3
"""Judge against LCD pixels under realistic PRESS/CLICK and blocking-save delays."""
import json,struct,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build
exe,version=build()
cases=hits=misses=old_mismatches=0
for species in (25,133,150):
 for elapsed in (0,259,279,280,299,300,319,320,339,340,359,360,899,919,939,959,1199):
  for delay in (0,180,400):
   for event in (0,1):
    r=Renderer(exe)
    try:
     f=r.command(f'boot 4 25 30 {species} 4 123 0 0 0')
     def pixel(frame,x,y=217):return struct.unpack_from('>H',frame['pixels'],2*(y*240+x))[0]
     blue=pixel(f,120)
     window=[x for x in range(20,221) if pixel(f,x)==blue]
     left,right=min(window),max(window)
     f=r.command(f'tick {elapsed}')
     pointers=[x for x in range(20,221) if pixel(f,x)==0]
     assert len(pointers)==1,pointers
     expected=left<=pointers[0]<=right
     before=r.inspect()
     r.command(f'save_delay {delay}')
     r.command(f'key 2 {event}')
     after=r.inspect()
     assert (after['party_count']>before['party_count'])==expected,(species,elapsed,delay,event,left,right,pointers)
     assert after['inventory'][0]==before['inventory'][0]-1
     # Hardware's eventual release/click must not repeat a press-time attempt.
     if event==0:
      r.command('tick 180');r.command('key 2 4');r.command('key 2 1');r.command('key 2 5')
      assert r.inspect()['party_count']==after['party_count']
      assert r.inspect()['inventory']==after['inventory']
     assert r.command('check')['mismatch']==0
     t=(elapsed+delay)%1200
     old_p=20+(t*200//600 if t<600 else 200-(t-600)*200//600)
     old_mismatches+=(left<=old_p<=right)!=expected
     hits+=expected;misses+=not expected;cases+=1
    finally:r.close()
# A failed immediate PRESS must not silently retry on the delayed CLICK.
r=Renderer(exe)
try:
 r.command('boot 4 25 30 133 4 123 0 0 0');r.command('tick 280')
 before=r.inspect();r.command('save_fail 1');r.command('key 2 0')
 r.command('tick 180');r.command('key 2 4');r.command('key 2 1');r.command('key 2 5')
 assert r.inspect()['inventory']==before['inventory']
 assert r.inspect()['party_count']==before['party_count']
 r.command('key 2 0')
 assert r.inspect()['inventory'][0]==before['inventory'][0]-1
finally:r.close()
assert hits and misses and old_mismatches
report=dict(build=version,cases=cases,visible_hits=hits,visible_misses=misses,old_clock_rule_disagreed=old_mismatches,duplicate_save_retry=False)
path=ROOT/'reports/evidence/controls-growth-2026-09-10/capture-timing.json'
path.parent.mkdir(parents=True,exist_ok=True)
path.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
