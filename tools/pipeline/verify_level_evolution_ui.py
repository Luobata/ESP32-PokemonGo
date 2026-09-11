#!/usr/bin/env python3
"""Actual C UI: level eligibility, old saves, failure retry and growth notices."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();out=ROOT/'reports/evidence/level-evolution-2026-09-10';out.mkdir(parents=True,exist_ok=True)
r=None;checks=0
def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f
def boot(level,species=1,page=5):
 global r
 if r:r.close()
 r=Renderer(exe);cmd(f'boot {page} {species} {level} 74 3 123 0 0 0');cmd('care_progress 0 0')
def key(k):
 for e in (0,4,1,5):cmd(f'key {k} {e}')
def shot(name): (out/(name+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
try:
 boot(15);cmd('care_progress 100 65535');key(0);key(2);cmd('tick 13000')
 assert r.inspect()['party'][0]['species']==1,'nurture must not bypass level'
 for level,species,target in [(16,1,2),(20,1,2),(32,2,3)]:
  boot(level,species);shot(f'ready-{species}-{level}');key(0);key(2);shot('evolution-animation');cmd('tick 13000')
  assert r.inspect()['party'][0]['species']==target,r.inspect()
  assert r.inspect()['evolutions']==1
 boot(16);key(0);cmd('save_fail_after 0');key(2);cmd('tick 13000')
 assert r.inspect()['party'][0]['species']==1 and r.inspect()['evolutions']==0
 key(2);cmd('tick 13000');assert r.inspect()['party'][0]['species']==2 and r.inspect()['evolutions']==1
 boot(15,page=1);cmd('grant_exp 1082');cmd('tick 300')
 assert r.inspect()['growth'] and r.inspect()['growth']['after']==16,r.inspect()
 for _ in range(8):
  g=r.inspect()['growth']
  if g['page']>=max(1,(g['moves']+2)//3):break
  key(2)
 else:raise AssertionError('missing evolution notice')
 shot('level-16-evolution-notice');key(2);assert not r.inspect()['growth']
 result=dict(build=version,checks=checks,passed=True)
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:
 if r:r.close()
