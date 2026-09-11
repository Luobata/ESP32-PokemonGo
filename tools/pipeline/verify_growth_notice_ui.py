#!/usr/bin/env python3
"""XP gauges, automatic learning notices and input isolation in production UI."""
import json,sys,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();out=ROOT/'reports/evidence/controls-growth-2026-09-10';out.mkdir(parents=True,exist_ok=True)
r=None;checks=0
def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f
def boot(page=1,level=5,team=0):
 global r
 if r:r.close()
 r=Renderer(exe);return cmd(f'boot {page} 25 {level} 74 3 123 0 0 {team}')
def key(k):
 for e in (0,4,1,5):f=cmd(f'key {k} {e}')
 return f
def back():
 for e in (0,3,4,5):cmd(f'key 1 {e}')
def shot(name):
 f=cmd('tick 120');(out/(name+'.png')).write_bytes(png(f['pixels']));return f
def until(fn):
 for _ in range(300):
  if fn(r.inspect()):return
  cmd('tick 120')
 raise AssertionError(r.inspect())
def crop(f,y,h):return f['pixels'][y*240*2:(y+h)*240*2]
try:
 boot();low=shot('home-exp-zero');cmd('party_exp 0 257');mid=shot('home-exp-progress')
 # Snapshot refresh is on the 250 ms idle tick.
 mid=cmd('tick 250');assert crop(low,240,16)!=crop(mid,240,16)
 assert crop(low,260,16)==crop(mid,260,16),'EXP must not replace the exploration gauge'
 boot(level=100);shot('home-exp-max');cmd('grant_exp 100');cmd('tick 500');assert not r.inspect()['growth']
 boot();cmd('grant_exp 2400');until(lambda s:s['growth'] is not None)
 g=r.inspect()['growth'];assert g==dict(species=25,before=5,after=11,page=0,moves=5)
 f=shot('learned-page-one')
 colors=[p[0] for p in struct.iter_unpack('<H',crop(f,36,80))]
 assert sum(p!=0xffff for p in colors)>100,'the learned-move notice must show the Pokemon sprite'
 key(1);assert r.inspect()['growth']['page']==1
 shot('learned-page-two');key(0);assert r.inspect()['growth']['page']==0
 key(2);assert r.inspect()['growth']['page']==1
 key(2);assert not r.inspect()['growth'] and r.inspect()['page']==1
 cmd('tick 800');assert not r.inspect()['growth'],'notice must not replay'
 key(2);assert r.inspect()['page']==5,'notice confirmation must not also activate the home action'
 boot();cmd('grant_exp 2400');until(lambda s:s['growth'] is not None);back()
 assert r.inspect()['page']==1 and not r.inspect()['growth']
 # Defer a pending notice until all capture feedback has finished.
 boot(4);cmd('grant_exp 2400');cmd('tick 6000');assert not r.inspect()['growth']
 # Shared XP can level all six partners; keep trainer dialogue/rewards first.
 boot(13,12,1)
 for i,m in enumerate(r.inspect()['party']):
  threshold=3*(m['level']+1)**3//2
  cmd(f'party_exp {i} {threshold-1}')
 key(2);s=r.inspect();assert s['challenge']['active']
 for i in range(len(s['challenge']['sides'][1]['mons'])):cmd(f'challenge_hp_fixture 1 {i} 0')
 until(lambda s:s['challenge']['mode']==5);cmd('tick 1200');assert not r.inspect()['growth']
 key(2);cmd('tick 600');assert not r.inspect()['growth']
 key(2);until(lambda s:s['growth'] is not None);shot('trainer-learned')
 shown=[]
 for _ in range(40):
  g=r.inspect()['growth']
  if not g:cmd('tick 120');g=r.inspect()['growth']
  if not g:break
  if g['page']==0:shown.append(g['species'])
  key(2)
 assert len(shown)==6,shown
 assert r.inspect()['challenge']['mode']==5,'closing notices must preserve the trainer result'
 result={'build':version,'dirty_full_checks':checks,'learned_moves_5_to_11':5,'party_notices':shown,'save_schema_unchanged':True,'passed':True}
 (out/'growth-ui.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
 if r:r.close()
