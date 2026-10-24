#!/usr/bin/env python3
"""Real firmware page/button path for the two V27 activities (no JS renderer)."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
OUT=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',str(ROOT/'reports/evidence/johto-activities-2026-10-17')));OUT.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(s):
 global checks
 f=r.command(s);assert not r.command('check')['mismatch'],s;checks+=1;return f

def key(i,n=1):
 for _ in range(n):cmd(f'key {i} 1')

def shot(n):(OUT/(n+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def state():return r.inspect()['activity']
def setup():
 global r
 r.close();r=Renderer(exe)
 cmd('boot 1 145 95 74 3 81 0 0 0');cmd('party_add 154 95 80 7 0');cmd('party_add 248 95 80 7 1');cmd('johto_fixture 8 0');cmd('page 18')
def finish_capture():
 before=r.inspect();elapsed=0
 while r.inspect()['display']['busy'] and elapsed<14000:
  cmd('tick 50');elapsed+=50
  after=r.inspect();assert after['inventory']==before['inventory'] and after['party']==before['party']
 assert 13121<=elapsed<=13200,elapsed  # Master Ball success + complete fanfare.
def battle():
 for _ in range(80):
  if r.inspect()['page']==18:return
  if r.inspect()['display']['off']:key(2)
  if r.inspect()['challenge']['mode']==4:
   key(1);key(2)
  cmd('tick 30000')
 raise AssertionError(r.inspect())
try:
 setup();shot('activity-menu');key(2);key(2);key(1,3);key(2);shot('bug-entry');key(2) # Cancel by default.
 assert not state()['kind'];key(1,3);key(2);key(1);cmd('save_fail 1');key(2);assert not state()['kind'];key(2)
 assert state()['kind']==1;shot('bug-tracks');key(2);shot('bug-find');cmd('inventory 3 1');key(1);key(2,3);key(0);key(2);finish_capture();assert state()['phase']==2;shot('bug-first-candidate');key(2);candidate=state()['candidate'];assert candidate
 # Real pause/resume without restarting or resampling the candidate.
 cmd('key 1 3');assert state()['candidate']==candidate;key(2);assert state()['candidate']==candidate
 key(1,3);key(2);shot('bug-early-confirm');key(2);assert state()['phase']==0
 key(1,3);key(2);key(1);key(2);shot('bug-score');key(2);assert not state()['kind'] and any(m['species']==candidate for m in r.inspect()['party']);shot('bug-reward');key(2)
 setup();key(1);key(2);key(2);key(1);key(2);key(1);key(2);key(1);key(2);shot('sea-entry');key(1);key(2);assert r.inspect()['page']==13;cmd('tick 1200');shot('sea-sendout');battle();assert state()['node']==2;key(2);battle();assert state()['phase']==5;shot('sea-camp');key(2);assert state()['phase']==6 and state()['banked'];shot('sea-relay');credited=r.inspect()['party'][0]['exp'];key(1);key(2);shot('sea-paths');key(1);key(2);battle();assert state()['phase']==5 and state()['node']==5;key(2);battle();assert state()['won'];shot('sea-clear');key(2);assert not state()['kind'] and state()['clears']==1 and r.inspect()['party'][0]['exp']>=credited;shot('sea-reward')
 # Full warehouse: cancel keeps candidate, exact last physical slot replaces only after confirmation.
 setup()
 for sid in (1,4,7):cmd(f'party_add {sid} 30 20 0 0')
 cmd('box_fixture 753 149');cmd('page 18');key(2);key(2);key(0);key(2);key(1);key(2);key(2);cmd('inventory 3 1')
 # Switch from ordinary to Master Ball for deterministic UI acceptance.
 key(1);key(2,3);key(0);key(2);finish_capture();assert state()['phase']==2;key(2);candidate=state()['candidate'];key(1,3);key(2);key(1);key(2);key(2);shot('bug-full-warehouse');key(0);key(2);shot('bug-replace-confirm');key(2);assert state()['candidate']==candidate;key(2);key(1);key(2);assert not state()['kind'] and r.inspect()['box_count']==753
 # Retreat must return to settlement instead of getting stuck on a failed finish.
 setup();key(1);key(2);key(2);key(1);key(2);key(1);key(2);key(1);key(2);key(1);key(2)
 cmd('key 1 3');cmd('tick 20000');assert r.inspect()['challenge']['mode']==6;shot('sea-retreat-confirm');key(1);key(2);assert r.inspect()['page']==18 and state()['phase']==3;key(2);assert not state()['kind']
 result=dict(build=version,checks=checks,passed=True);(OUT/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:r.close()
