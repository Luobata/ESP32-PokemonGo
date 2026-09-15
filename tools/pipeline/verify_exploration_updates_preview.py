#!/usr/bin/env python3
"""Exercise new exploration screens with the actual band renderer and ABC input."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build()
out=ROOT/'reports/evidence/exploration-updates-2026-09-15';out.mkdir(parents=True,exist_ok=True)
r=Renderer(exe);checks=0;screens=[]
def cmd(line):
 global checks
 result=r.command(line);assert r.command('check')['mismatch']==0,line;checks+=1;return result
def key(n,ev=1):return cmd(f'key {n} {ev}')
def snap(name):
 f=cmd('check');(out/(name+'.png')).write_bytes(png(f['pixels']));screens.append(name)
def activities():
 key(1);key(1);key(2) # Main -> activities.
 key(1);key(1);key(1);key(2) # Fourth option -> badge activities.
try:
 cmd('boot 15 25 40 74 3 123 0 0 0');snap('random-trail')
 initial=r.inspect()['trails']['targets'];key(1);key(2);snap('route-targets');key(1,3)
 assert r.inspect()['trails']['targets']==initial
 activities();snap('badges-locked');key(1,3);key(1,3)
 cmd('challenge_unlock 255');cmd('page 15');activities();snap('badge-activities-1')
 for _ in range(4):key(1)
 snap('badge-activities-2');key(2);snap('poison-activity')
 cmd('save_fail 1');key(2);snap('activity-save-failed')
 assert r.inspect()['trails']['progress']==[0]*8
 key(2);snap('activity-discovery');key(2)
 assert r.inspect()['page']==3
 # Return to an isolated fixture to verify reward UI and once-only claim.
 r.close();r=Renderer(exe)
 cmd('boot 15 25 40 74 3 123 0 0 0');cmd('challenge_unlock 255');cmd('badge_activity_fixture 0 3 0')
 activities();key(2);snap('first-reward-ready');key(2);snap('first-reward-received')
 state=r.inspect()['trails'];assert state['claimed']==1 and state['progress'][0]==0
 # Confirm now starts the next paid encounter; it cannot claim the old reward again.
 key(2);assert r.inspect()['trails']['claimed']==1;snap('repeat-activity')
finally:r.close()
result={'build':version,'band_checks':checks,'screens':screens,'abc_navigation':True,'first_reward_once':True}
(out/'preview.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
