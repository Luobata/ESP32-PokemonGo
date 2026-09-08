#!/usr/bin/env python3
"""Shared C renderer: automatic combat, read-only repertoire, both outcomes and redraws."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import build,Renderer,png
out=ROOT/'reports/evidence/combat-2026-09-08';out.mkdir(exist_ok=True,parents=True)
exe,version=build();checks=0;wins=0;losses=0
for trainer in [*range(9),13]:
 r=Renderer(exe)
 def cmd(c):
  global checks
  f=r.command(c)
  assert r.command('check')['mismatch']==0,c
  checks+=1;return f
 try:
  cmd('boot 13 3 100 74 3 123 0 0 0')
  for mon in [6,9,65,143,149]:cmd(f'party_add {mon} 100 80 0 0')
  cmd(f'challenge_unlock {(1<<trainer)-1}');cmd('page 0');cmd('page 13')
  cmd('key 0 1');assert r.inspect()['challenge']['trainer']==trainer,(trainer,r.inspect()['challenge'])
  cmd('tick 1530')
  if trainer==0:
   cmd('key 0 1');cmd('tick 4000');assert r.inspect()['challenge']['mode']==7
   cmd('key 1 1');cmd('key 0 1');assert r.inspect()['challenge']['mode']==9
   before=r.inspect()['challenge'];cmd('tick 5000');assert r.inspect()['challenge']==before
   (out/'trainer-skills.png').write_bytes(png(cmd('check')['pixels']))
   for _ in range(8):cmd('key 1 1')
   cmd('key 1 3');assert r.inspect()['challenge']==before
   cmd('key 0 1')
  for guard in range(20000):
   st=r.inspect()['challenge']
   if st['mode']==5:break
   if st['mode']==4:
    slot=next(i for i,m in enumerate(st['sides'][0]['mons']) if m['hp'])
    for _ in range(slot):cmd('key 1 1')
    cmd('key 0 1')
   else:cmd('tick 360')
   if trainer==13 and guard==50:(out/'red-battle.png').write_bytes(png(cmd('check')['pixels']))
  else:raise AssertionError(('stuck',trainer,st))
  assert st['finished'];wins+=bool(st['won']);losses+=not st['won']
  cmd('key 0 1')
 finally:r.close()
r=Renderer(exe)
try:
 r.command('boot 12 25 60 74 3 123 0 0 0');r.command('key 0 1');r.command('key 0 3')
 first=r.command('check');assert first['mismatch']==0
 (out/'party-skills.png').write_bytes(png(first['pixels']))
 for _ in range(6):r.command('key 1 1')
 assert r.command('check')['mismatch']==0
 (out/'party-skills-next.png').write_bytes(png(r.command('check')['pixels']))
 r.command('key 2 1');assert r.command('check')['pixels']!=first['pixels']
finally:r.close()
print(json.dumps({'build':version,'trainers_completed':10,'wins':wins,'losses':losses,'dirty_full_checks':checks,'moves_read_only':True,'party_skill_pages':True}))
