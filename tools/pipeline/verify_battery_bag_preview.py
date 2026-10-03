#!/usr/bin/env python3
"""Actual firmware pixels and keys: battery and achievement claims at capacity."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import build,Renderer,png
out=ROOT/'reports/evidence/battery-bag-shiny-2026-10-03'
out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(c):
 global checks
 result=r.command(c);assert r.command('check')['mismatch']==0,c;checks+=1;return result

def key(n,e=1):return cmd(f'key {n} {e}')
def shot(name):out.joinpath(name+'.png').write_bytes(png(cmd('check')['pixels']))
def bag():return r.inspect()['inventory']
try:
 cmd('boot 11 25 12 74 3 123 0 0 1')
 for battery in [100,76,20,1,0,101]:
  cmd(f'battery {battery}');cmd('tick 10000');shot(f'battery-{battery}')
  # Do not leave auto sleep to mask a sample.
  key(2,3);assert r.inspect()['display']['off'];key(0)
 cmd('page 14');cmd('inventory 1 30');before=bag()
 cmd('save_fail 1');key(2);assert not(r.inspect()['achievement_claimed']&1) and bag()==before;shot('achievement-save-failed')
 key(2);assert r.inspect()['achievement_claimed']&1 and bag()==before;shot('achievement-full-claimed')
 key(2);assert bag()==before;shot('achievement-no-repeat')
 r.close();r=Renderer(exe)
 cmd('boot 14 25 12 74 3 123 0 0 1');cmd('inventory 1 28')
 key(2);assert r.inspect()['achievement_claimed']&1 and bag()[1]==30;shot('achievement-partial-claimed')
 # Bag retains its original use/navigation controls; no discard workflow.
 cmd('page 10');before=bag();key(0,3);assert bag()==before;shot('bag-unchanged')
 result={'build':version,'render_checks':checks,'battery_states':[100,76,20,1,0,'unknown'],'full_and_partial_claims':True,'save_failure_atomic':True,'repeat_claim_blocked':True}
 out.joinpath('preview.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:r.close()
