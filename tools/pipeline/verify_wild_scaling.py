#!/usr/bin/env python3
"""Exercise real C session initialization, capture storage, and post-win EXP."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'tools/inspector'),str(ROOT/'sim')]
from native import Renderer,build
from systems import wild_level
exe,version=build();r=Renderer(exe)
checks=0
try:
 for player in range(1,101):
  levels=[]
  for rarity in range(1,6):
   r.close();r=Renderer(exe)
   r.command(f'boot 4 25 {player} 133 {rarity} 123 0 0 0')
   actual=r.inspect()['queue'][0]['wild_level']
   assert actual==wild_level(rarity,player),(player,rarity,actual)
   assert 1<=actual<=100
   levels.append(actual);checks+=1
   if player in (8,40,80,100):
    r.command('inventory 3 1')
    for _ in range(3):r.command('key 1 1')
    r.command('key 0 0')
    caught=r.inspect()['party'][-1]
    assert caught['species']==133 and caught['level']==actual
    assert caught['exp']==3*actual**3//2
  assert levels==sorted(levels)
 assert [wild_level(1,n) for n in range(1,101)]==sorted(wild_level(1,n) for n in range(1,101))
 # A real high-level victory gives EXP based on the scaled session, and the
 # post-battle capture stores the level fought rather than the old rarity floor.
 r.close();r=Renderer(exe)
 r.command('boot 3 139 80 129 1 3 0 0 0')
 def until(pred):
  for _ in range(4000):
   if pred(r.inspect()):return
   r.command('tick 60')
  raise AssertionError('battle timeout')
 until(lambda s:s['presentation']['phase']=='choice')
 before=r.inspect()['exp'];r.command('key 1 1')
 until(lambda s:s['presentation']['phase']=='result')
 state=r.inspect();assert state['active']['won']
 assert state['active']['wild_level']==60
 assert state['exp']-before==60*8+20
 r.command('key 0 1');r.command('inventory 3 1')
 for _ in range(3):r.command('key 1 1')
 r.command('key 0 0')
 assert r.inspect()['party'][-1]['level']==60
 assert r.command('check')['mismatch']==0
finally:r.close()
report=dict(build=version,level_cases=checks,capture_level_cases=20,scaled_victory_exp=500,post_victory_capture_level=60)
out=ROOT/'reports/evidence/wild-scaling-2026-09-08';out.mkdir(parents=True,exist_ok=True)
(out/'verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
