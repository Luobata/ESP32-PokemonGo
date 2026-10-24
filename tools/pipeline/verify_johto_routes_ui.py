#!/usr/bin/env python3
"""Production C UI: immediate entry, route choices, save failure, direct battle return."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',str(ROOT/'reports/evidence/johto-routes-2026-10-18')));out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f

def key(n,times=1,ev=1):
 for _ in range(times):cmd(f'key {n} {ev}')

def shot(n):(out/(n+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def enter(route=0,visits=0):
 global r
 r.close();r=Renderer(exe)
 cmd('boot 1 130 90 74 3 81 0 0 0');cmd(f'johto_fixture 8 {visits}');cmd('page 17')
 assert not r.inspect()['display']['busy']
 key(1);key(2);key(1,route);key(2)
 assert r.inspect()['nurture']['stamina']==90
try:
 enter();shot('route-hub');key(2);shot('route-paths')
 # Merely choosing a route/branch or backing out is free and responds without a tick.
 key(1);key(1,ev=3);assert r.inspect()['nurture']['stamina']==90;key(2)
 prior=r.inspect();cmd('save_fail 1');key(2);after=r.inspect()
 assert after['johto']==prior['johto'] and after['inventory']==prior['inventory'] and after['queue']==prior['queue'] and after['nurture']==prior['nurture'];shot('save-failure')
 key(2);state=r.inspect();assert state['johto']['research'][0]==1 and state['nurture']['stamina']==85
 shot('route-result')
 # Continue is one choice, preserves the selected branch, and the fourth stop is the target.
 for step in range(1,4):
  found=state['queue'][-1]['uid']!=prior['queue'][-1]['uid']
  if found:key(1)
  key(2);prior=state;key(2);state=r.inspect();assert state['johto']['research'][0]==step+1
 assert state['johto']['clues'][0]==0 and state['nurture']['stamina']==70
 shot('route-target')
 # Every route and branch renders with the 20-row full-redraw oracle.
 for route in range(8):
  enter(route);shot('map-'+str(route));key(2)
  for i in range(3):key(1)
  shot('paths-'+str(route));key(1,ev=3);key(1,2);key(2);shot('activities-'+str(route))
  key(1);key(2);assert r.inspect()['page']==18;key(1,ev=3);assert r.inspect()['page']==17
 # Target encounter goes directly to P3, then escape returns to the same route hub.
 enter(6,3);target=r.inspect()['johto']['targets'][6];key(2);key(1,2);key(2)
 state=r.inspect();enc=state['queue'][-1];assert enc['species']==target;shot('sea-target');key(2)
 assert r.inspect()['page']==3 and r.inspect()['uid']==enc['uid'];cmd('tick 6500');shot('route-battle')
 for attempt in range(12):
  if r.inspect()['page']==17:break
  key(1,ev=3);key(1);key(2);cmd('tick 10000')
 assert r.inspect()['page']==17;shot('returned-to-route')
 visits=r.inspect()['johto']['research'][6];key(2);key(2);assert r.inspect()['johto']['research'][6]==visits+1
 # Latest window remains five entries, even after continuing without battling.
 for _ in range(12):
  state=r.inspect();found=state['queue'][-1]['ts']==state['johto']['visits']
  if found:key(1)
  key(2);key(2)
  assert len(r.inspect()['queue'])<=5
 # A background arrival can evict the displayed discovery: never open a different UID.
 enter(2,3);key(2);key(2);uid=r.inspect()['queue'][-1]['uid']
 for i in range(6):cmd(f'spawn 19 1 {2000+i} 0')
 key(2);assert r.inspect()['page']==17 and r.inspect()['active'] is None
 shot('encounter-expired');assert all(e['uid']!=uid for e in r.inspect()['queue'])
 result=dict(passed=True,native_build=version,checks=checks,scope='actual C pages + host adapter; save transactions tested separately; no hardware timing claim')
 (out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:r.close()
