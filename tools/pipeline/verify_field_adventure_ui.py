#!/usr/bin/env python3
"""Real firmware radar/maps: navigation, motion, clipping, resource failures."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',ROOT/'reports/evidence/radar-fieldmaps-2026-10-25'));out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=None;checks=0

def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,(s,state()['field']);checks+=1;return f

def state():return r.inspect()
def key(n,ev=1):return cmd(f'key {n} {ev}')
def shot(name):(out/(name+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def boot(page,badges=8):
 global r
 if r:r.close()
 r=Renderer(exe);cmd(f'boot {page} 25 60 74 3 81 0 0 0');cmd(f'johto_fixture {badges} 0');cmd(f'page {page}')
def walk(point):
 for _ in range(6):
  if state()['field']['point']==point:break
  key(1)
 key(2)
 assert state()['field']['walking']
 for i in range(240):
  cmd('tick 50')
  if not state()['field']['walking']:break
 assert not state()['field']['walking']
try:
 for map_id in range(3):
  boot(22)
  for _ in range(map_id):key(1)
  key(2);shot('map-'+str(map_id));before=state()
  for point in range(3):
   walk(point);cmd('save_fail 1');key(2);assert state()['field']['error']==5 and state()['field']['visited'][map_id]==(1<<point)-1
   key(2);assert state()['field']['visited'][map_id]==(1<<(point+1))-1
  assert state()['nurture']==before['nurture'] and state()['johto']==before['johto']
  walk(3);shot('map-'+str(map_id)+'-ready');cmd('save_fail 1');key(2);assert state()['field']['error']==5 and state()['field']['serial']==0
  key(2);assert state()['field']['serial']==1 and state()['field']['view']==3 and state()['nurture']['stamina']==before['nurture']['stamina']-5
  assert state()['johto']['visits']==before['johto']['visits']+1;shot('map-'+str(map_id)+'-found');key(1,3);key(2);assert state()['field']['error']==6
  # Existing narrative/activity paths remain reachable from the map.
  walk(4);key(2);assert state()['page']==(18 if map_id==1 else 19)
 boot(22,0);key(2);assert state()['field']['error']==1 and state()['field']['view']==0
 boot(22);key(2);key(2);cmd('tick 200');old=state()['field'];key(2,3);assert state()['display']['off'];cmd('tick 1000');assert state()['field']['y']==old['y'];key(2);cmd('tick 50');assert not state()['display']['off'];key(1,3);assert state()['field']['view']==0 and state()['field']['serial']==0
 boot(21);cmd('radar_fixture 0 1');cmd('tick 1000');shot('radar-no-signal');key(2);assert state()['field']['error']==7
 cmd('radar_fixture 16 2');cmd('tick 1000');shot('radar');before=state();cmd('save_fail 1');key(2);assert state()['field']['error']==5 and state()['nurture']==before['nurture']
 key(2);assert state()['field']['view']==3 and state()['field']['serial']==1;key(1,3);key(2);assert state()['field']['error']==6
 cmd('page 21');key(2);assert state()['field']['error']==6;key(1);key(2);assert state()['page']==2
 # Multiple delayed callbacks: same 640ms first walk around the sign; elapsed time, not frame increments.
 for quantum in (40,80,160):
  boot(22);key(2);key(2)
  for _ in range(640//quantum):cmd(f'tick {quantum}')
  cmd('tick 50');assert state()['field']['y']==144 and not state()['field']['walking']
 # Scrolling menu exposes both entries with and without Johto invitation.
 boot(11);cmd('challenge_unlock 16383');cmd('page 11')
 for _ in range(10):key(1)
 shot('menu-radar');key(2);assert state()['page']==21
 result=dict(passed=True,native_build=version,pixel_checks=checks,maps=3,scope='production renderer + simulated signals; world/save verified separately; no device FPS claim')
 (out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:
 if r:r.close()
