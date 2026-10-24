#!/usr/bin/env python3
"""Native C journal pages and keys, each frame compared with a complete redraw."""
from pathlib import Path
import sys,json,os
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',str(ROOT/'reports/evidence/johto-completion-2026-10-17')));out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f

def key(n,times=1):
 for _ in range(times):cmd(f'key {n} 1')

def shot(name):(out/(name+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def home():cmd('key 1 3')
try:
 cmd('boot 1 25 60 74 3 81 0 0 0');cmd('johto_fixture 8 12');cmd('page 19');shot('journal')
 for rescue in range(2):
  key(2);shot('rescue-ready');key(2)
  for stage in range(2):
   desired=r.inspect()['story']['answer'];key(1,desired);shot('rescue-choice');key(2);key(0,desired)
  assert r.inspect()['story']['step']==3;shot('rescue-partner');key(2);assert r.inspect()['story']['rescues']==rescue+1
 # First group: use visible sequence, save-failure leaves the puzzle unfinished.
 key(1);key(2);shot('ruins');key(2);shot('puzzle');cmd('save_fail 1');key(2);assert r.inspect()['story']['ruin_step']==0;key(2);key(1);key(2);key(1);key(2);assert r.inspect()['story']['ruins']==1
 key(2);shot('unown-found');assert any(e['species']==201 for e in r.inspect()['queue']);home();key(1,3);key(2);shot('burned-tower');key(2);assert r.inspect()['story']['tower'];key(1,2);key(2);shot('letters');home();key(1,5);key(2);shot('final-requirements')
 # All newly reused expedition entrances are real selectable menus.
 for offset,kind in [(2,3),(3,4)]:
  cmd('page 18');key(1,offset);key(2);shot('ice-team' if kind==3 else 'tower-team');home()
 result={'passed':True,'build':version,'checks':checks};(out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:r.close()
