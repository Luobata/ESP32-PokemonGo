#!/usr/bin/env python3
"""Actual exploration C page: queued target, full FIFO and opening the new UID."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=ROOT/'reports/evidence/exploration-duplicates-2026-10-21'
out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(s):
 global checks
 frame=r.command(s)
 assert r.command('check')['mismatch']==0,s
 checks+=1
 return frame

def shot(name):
 (out/(name+'.png')).write_bytes(png(cmd('tick 0')['pixels']))

try:
 cmd('boot 15 1 35 74 3 81 0 0 0')
 cmd('exploration_fixture 0 0 3 0')
 target=r.inspect()['trails']['targets'][0]
 cmd(f'spawn {target} 2 2000 1')
 before=r.inspect();old=before['queue'][-1]
 assert len(before['queue'])==5 and old['species']==target
 shot('target-already-queued')
 cmd('save_fail 1');cmd('key 2 1');failed=r.inspect()
 for field in ['queue','exploration','nurture','trails','inventory']:
  assert failed[field]==before[field],field
 shot('save-failure')
 cmd('key 2 1');cmd('tick 1000');after=r.inspect()
 new=after['queue'][-1]
 assert new['species']==target and new['uid']!=old['uid']
 assert len(after['queue'])==5 and after['queue'][0]['uid']==before['queue'][1]['uid']
 assert any(e==old for e in after['queue'])
 assert after['exploration']['steps']==before['exploration']['steps']+1
 assert after['nurture']['stamina']==before['nurture']['stamina']-5
 shot('new-target-discovered')
 cmd('key 2 1');state=r.inspect()
 assert state['page']==3 and state['uid']==new['uid']
 cmd('tick 6500');shot('new-individual-battle')
 result=dict(passed=True,native_build=version,checks=checks,old_uid=old['uid'],new_uid=new['uid'],scope='Production C UI with host world adapter; real world/save transactions are checked separately; no hardware claim')
 (out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
 r.close()
