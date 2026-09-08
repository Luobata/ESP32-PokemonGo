#!/usr/bin/env python3
"""Initial, manual, fainted and enemy replacement animations, actual C pages."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();r=Renderer(exe);checks=0
out=ROOT/'reports/evidence/gold-silver-2026-09-09';out.mkdir(parents=True,exist_ok=True)
def cmd(c):
 global checks
 f=r.command(c);assert r.command('check')['mismatch']==0,c;checks+=1;return f
def until(mode):
 for _ in range(1000):
  if r.inspect()['challenge']['mode']==mode:return
  cmd('tick 90')
 raise AssertionError(r.inspect()['challenge'])
def region(f,x,y,w,h):return b''.join(f['pixels'][((y+j)*240+x)*2:((y+j)*240+x+w)*2] for j in range(h))
def verify(mask,label):
 assert r.inspect()['challenge']['sendout_mask']==mask
 f=cmd('check');(out/(label+'.png')).write_bytes(png(f['pixels']))
 box=(124,24,112,112) if mask==1 else (8,140,96,96);baseline=region(f,*box)
 for _ in range(12):
  f=cmd('tick 90');assert region(f,*box)==baseline,label
try:
 cmd('boot 13 1 100 74 3 123 0 0 0');cmd('party_add 25 100 80 0 1');cmd('party_add 6 100 80 0 0');cmd('key 0 1');until(2)
 assert r.inspect()['challenge']['sendout_mask']==3
 cmd('key 0 1');until(7)
 cmd('key 1 1');cmd('key 1 1');cmd('key 0 1');cmd('key 1 1');cmd('key 0 1');verify(1,'manual-player-sendout')
 # Set the active actor to zero in an isolated fixture, then let real trainer_step request replacement.
 cmd('challenge_hp_fixture 0 1 0');until(4)
 cmd('key 0 1');verify(1,'fainted-player-sendout')
 cmd('challenge_hp_fixture 1 0 0')
 # Existing sendout must finish before the enemy's next replacement event.
 for _ in range(100):
  if r.inspect()['challenge']['sendout_mask']==2:break
  cmd('tick 90')
 else:raise AssertionError('enemy sendout missing')
 verify(2,'enemy-sendout')
finally:r.close()
print(json.dumps({'checks':checks,'version':version,'initial_mask':3,'manual_and_fainted_mask':1,'enemy_mask':2,'unchanged_side_stays_visible':True}))
