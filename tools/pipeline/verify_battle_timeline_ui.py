#!/usr/bin/env python3
"""Actual wild/trainer/capture pages under fast, late and paused display callbacks."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build
exe,version=build();checks=0;results=[]
def cmd(r,line):
 global checks
 f=r.command(line);assert r.command('check')['mismatch']==0,(line,r.inspect());checks+=1;return f
def until(r,predicate):
 for _ in range(1800):
  s=r.inspect()
  if predicate(s):return s
  cmd(r,'tick 45')
 raise AssertionError(r.inspect())
for trainer in (False,True):
 for cadence in (45,90,150):
  r=Renderer(exe)
  try:
   cmd(r,f'boot {13 if trainer else 3} 25 30 7 3 123 0 0 1')
   if not trainer:
    until(r,lambda s:s['presentation']['phase']=='choice');cmd(r,'key 1 1')
   cmd(r,'key 2 1')
   initial=until(r,lambda s:s['presentation'] and s['presentation']['phase']=='attack')
   start=initial['presentation'];old=start;elapsed=0;stages={0}
   first_hp=(start['visible_pet_hp'],start['visible_wild_hp'])
   # One persisted gameplay step throughout all presentation phases.
   committed=initial['challenge'] if trainer else initial['active']
   while elapsed<30000:
    cmd(r,f'{"tick" if cadence==45 else "stall"} {cadence}');elapsed+=cadence
    state=r.inspect();v=state['presentation']
    if not v or v['phase']!='attack' or v['elapsed_ms']<old['elapsed_ms']:break
    assert (state['challenge'] if trainer else state['active'])==committed
    stages.add(v['stage'])
    if v['elapsed_ms']<=v['hp_ms']:
     assert (v['visible_pet_hp'],v['visible_wild_hp'])==first_hp,('early HP',v)
    assert v['stage']>=old['stage'],('phase regressed',old,v)
    old=v
   assert start['duration_ms']<=elapsed<=start['duration_ms']+cadence,(start,elapsed)
   assert {0,1,2,3,4}<=stages,stages
   results.append(dict(scene='trainer' if trainer else 'wild',cadence=cadence,planned_ms=start['duration_ms'],actual_ms=elapsed,move=start['move_id'],stages=sorted(stages)))
  finally:r.close()
# A lethal hit must finish its HP bar, feedback and seven-row faint drop before
# a replacement is sent out. Use the real resolver with a labelled 1 HP fixture.
r=Renderer(exe)
try:
 cmd(r,'boot 13 25 30 74 3 123 0 0 1');cmd(r,'key 2 1')
 until(r,lambda s:s['challenge']['mode']==2);cmd(r,'challenge_hp_fixture 1 0 1')
 start=until(r,lambda s:s['presentation'] and s['presentation']['phase']=='attack')['presentation']
 assert start['duration_ms']-start['feedback_ms']>2000,start
 frames=set();elapsed=0;old=start
 while elapsed<start['duration_ms']+100:
  f=cmd(r,'tick 45');elapsed+=45;v=r.inspect()['presentation']
  if not v or v['phase']!='attack' or v['elapsed_ms']<old['elapsed_ms']:break
  if v['stage']==5:
   assert v['visible_wild_hp']==0
   frames.add(f['pixels'])
  old=v
 assert len(frames)>=5,'faint motion was skipped or became an instant hide'
 assert start['duration_ms']<=elapsed<=start['duration_ms']+45
 results.append(dict(scene='faint/replacement',planned_ms=start['duration_ms'],actual_ms=elapsed,distinct_frames=len(frames)))
finally:r.close()
# Explicit sleep during a move: neither HP nor the timeline catches up on wake.
for trainer in (False,True):
 r=Renderer(exe)
 try:
  cmd(r,f'boot {13 if trainer else 3} 25 30 7 3 123 0 0 1')
  if not trainer:
   until(r,lambda s:s['presentation']['phase']=='choice');cmd(r,'key 1 1')
  cmd(r,'key 2 1');until(r,lambda s:s['presentation'] and s['presentation']['phase']=='attack')
  cmd(r,'tick 1080');before=r.inspect()['presentation']
  cmd(r,'key 2 3');cmd(r,'tick 5000');assert r.inspect()['display']['off']
  assert r.inspect()['presentation']==before
  cmd(r,'key 0 1');cmd(r,'tick 45');assert r.inspect()['presentation']==before
  cmd(r,'tick 90');assert r.inspect()['presentation']['elapsed_ms']>=before['elapsed_ms']+45
 finally:r.close()
# Capture at the same normal in-window input, late callbacks cannot make its
# source phases shorter or run the gameplay outcome twice.
for cadence in (40,80,160):
 r=Renderer(exe)
 try:
  cmd(r,'boot 4 25 30 133 4 123 0 0 0');cmd(r,'tick 300');cmd(r,'key 2 1')
  committed=r.inspect();elapsed=0;reveal=None
  while elapsed<14000:
   cmd(r,f'{"tick" if cadence==40 else "stall"} {cadence}');elapsed+=cadence
   s=r.inspect()
   assert s['inventory']==committed['inventory'] and s['party']==committed['party']
   if s['music']==16 and reveal is None:reveal=elapsed
   if s['page']!=4:break
  assert reveal is not None and 9117<=reveal<=9117+2*cadence,(cadence,reveal)
  assert 9921+3200<=elapsed<=9921+3200+2*cadence,(cadence,elapsed)
  results.append(dict(scene='capture',cadence=cadence,result_ms=reveal,exit_ms=elapsed))
 finally:r.close()
print(json.dumps(dict(build=version,pixel_checks=checks,cases=results,passed=True)))
