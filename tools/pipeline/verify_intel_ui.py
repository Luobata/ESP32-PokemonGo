#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();out=ROOT/'reports/evidence/exploration-intel-2026-09-11';out.mkdir(parents=True,exist_ok=True)
r=None;checks=0
def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f
def boot(page,team=0):
 global r
 if r:r.close()
 r=Renderer(exe);cmd(f'boot {page} 25 16 74 3 123 0 0 {team}')
def key(k):
 for e in [0,4,1,5]:cmd(f'key {k} {e}')
def shot(name):(out/(name+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def until(fn):
 for _ in range(400):
  if fn(r.inspect()):return
  cmd('tick 90')
 raise AssertionError(r.inspect())
try:
 boot(15);cmd('exploration_fixture 0 0 0 1');cmd('nurture_fixture 80 80 5 50');cmd('tick 180');shot('zero-intel-ready');key(2);shot('zero-intel-discovery')
 assert r.inspect()['exploration']['energy']==0 and r.inspect()['nurture']['stamina']==0,r.inspect()
 boot(13,1);key(2);until(lambda s:s['challenge']['mode']==3)
 key(2);until(lambda s:s['challenge']['mode']==7)
 key(1);key(1);key(2);assert r.inspect()['challenge']['mode']==4
 shot('trainer-manual-switch-levels')
 key(1);key(2);until(lambda s:s['challenge']['mode']==3)
 side=r.inspect()['challenge']['sides'][0];cmd(f"challenge_hp_fixture 0 {side['active']} 0");until(lambda s:s['challenge']['mode']==4)
 shot('trainer-forced-switch-levels')
 result=dict(build=version,checks=checks,passed=True);(out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:
 if r:r.close()
