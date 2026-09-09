#!/usr/bin/env python3
"""Navigate the actual firmware pages for route battles, research and catch-up."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
OUT=ROOT/'reports/evidence/leveling-2026-09-09';OUT.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0;checks+=1;return f

def boot(s):
 global r
 r.close();r=Renderer(exe);return cmd(s)

def key(k,event=1):return cmd(f'key {k} {event}')
def shot(name):
 f=cmd('tick 90');(OUT/(name+'.png')).write_bytes(png(f['pixels']))

def until(fn,n=2500):
 for _ in range(n):
  if fn(r.inspect()):return
  cmd('tick 360')
 raise AssertionError(r.inspect())

try:
 for route in range(4):
  boot('boot 15 6 100 74 3 123 0 0 0');cmd('challenge_unlock 31');cmd(f'exploration_fixture {route} 12 0 0')
  key(0,3);shot('activities-'+str(route));key(0);assert r.inspect()['page']==13
  shot('trainers-'+str(route));key(1);key(1);key(0)
  assert r.inspect()['challenge']['trainer']==14+route*3+2
  cmd('tick 1400');shot('trainer-intro-'+str(route));until(lambda s:s['challenge']['mode']==3);shot('trainer-battle-'+str(route))
  until(lambda s:s['challenge']['mode']==5)
  s=r.inspect();assert s['challenge']['won'] and s['challenge']['defeated']==31
  before=s['exp'];cmd('tick 900');key(0);cmd('tick 900');key(0);cmd('tick 900');shot('trainer-result-'+str(route));key(2)
  assert r.inspect()['challenge']['mode']==0 and r.inspect()['exp']==before
  key(2);assert r.inspect()['page']==15
 # No badge: only the first tier can be selected; long B wraps that same entry.
 boot('boot 15 25 20 74 3 123 0 0 0');cmd('challenge_unlock 0');key(0,3);key(0);key(1);key(1,3);key(0)
 assert r.inspect()['challenge']['trainer']==14
 # Build research through ordinary dex/target fixture inputs, then use the UI claim.
 boot('boot 15 25 50 74 3 123 0 0 0')
 for species in (10,13,16):cmd(f'party_add {species} 20 0 0 0')
 for species in (43,46):cmd(f'spawn {species} 1 2000')
 cmd('exploration_fixture 0 3 3 0');key(0);cmd('tick 600');assert r.inspect()['exploration']['research_flags']&16
 key(1);key(0,3);key(1);key(0);shot('research-ready')
 before=r.inspect()['exp'];cmd('save_fail 1');key(0);assert r.inspect()['exp']==before and not r.inspect()['exploration']['research_flags']&1
 shot('research-save-retry');key(0);assert r.inspect()['exp']>before and r.inspect()['exploration']['research_flags']&1
 shot('research-reward');before=r.inspect()['exp'];key(0);assert r.inspect()['exp']==before
 cmd('page 12');shot('party-catchup')
 result={'status':'PASS','renderer':version,'dirty_full_checks':checks,'four_route_battles':True,'hidden_locked_tiers':True,'research_retry_and_once_only':True,'returns_to_exploration':True}
 (OUT/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:r.close()
