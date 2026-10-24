#!/usr/bin/env python3
"""Real production renderer/keys: narrative flow, pause, choices, draw stripes."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',str(ROOT/'reports/evidence/johto-narrative-2026-10-24')));out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(s):
 global checks
 f=r.command(s);m=r.command('check')['mismatch'];assert m==0,(s,m,r.inspect());checks+=1;return f

def key(n=2,event=1):return cmd(f'key {n} {event}')
def state():return r.inspect()['narrative']
def scene(n):cmd(f'narrative_fixture {n}');cmd('tick 2400')
def shot(name):
 if r.inspect()['page']==20 and state()['view']==1:cmd('tick 2400')
 (out/(name+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def nextpage():cmd('tick 2400');key()
try:
 cmd('boot 1 25 60 74 3 81 0 0 0');scene(0);shot('opening-oak')
 assert state()['scene']==0
 # Real elapsed-time reveal, instant completion, pause/reenter, persistent page.
 key();assert state()['page']==1;key();assert state()['page']==1 and state()['visible']>=100;key();assert state()['page']==2
 cmd('tick 1000');shot('journey');key(1,3);assert state()['view']==0 and state()['saved_page']==2
 key();assert state()['view']==1 and state()['page']==2
 nextpage();assert state()['scene']==1 and r.inspect()['johto']['phase']==2
 for _ in range(3):nextpage()
 assert r.inspect()['page']==17;shot('starter');key();assert r.inspect()['johto']['phase']==3
 cmd('tick 800');key();assert r.inspect()['page']==20 and state()['scene']==2
 for _ in range(2):nextpage()
 key();assert r.inspect()['page']==17 # Direct first-route link, before spending stamina.
 key(1,3);assert r.inspect()['page']==20
 # Wrong inference provides hint, no progress; persistence error retries same page.
 scene(3);nextpage();nextpage();shot('bug-choice');assert state()['page']==2
 key();assert state()['error']==4 and state()['saved_page']==2;shot('bug-hint')
 key(1);cmd('save_fail 1');key();assert state()['error']==3 and state()['saved_page']==2
 key();assert state()['seen']&(1<<6) and not state()['saved_scene'];key();assert state()['scene']==7
 # Ruins choice has a different answer. Free replay must not change receipts.
 scene(4);nextpage();nextpage();key(1);key();assert state()['error']==4;key(1);key();assert state()['seen']&(1<<8)
 before=state()['seen'];key(1);key(1);key();assert state()['view']==2;key();assert state()['replay']
 for _ in range(3):nextpage()
 assert state()['seen']==before and not state()['replay'];key(1,3)
 scene(5);nextpage();nextpage();key(1);key(1);shot('choose-trail');key();assert state()['seen']&(1<<10)
 # Interruption-safe legend reveal transitions directly to actual encounter.
 scene(10);pending=r.inspect()['queue'][-1];shot('legend-reveal');nextpage();shot('legend-revealed');key(1,3)
 assert state()['pending']==1;key();assert state()['page']==1;nextpage();assert r.inspect()['page']==3 and r.inspect()['uid']==pending['uid']
 # The guided gym returns to the investigation, including the complete reward UI.
 r.close();r=Renderer(exe)
 cmd('boot 1 25 90 74 3 81 0 0 0');cmd('johto_fixture 0 1');cmd('challenge_unlock 16383');cmd('page 20');key();assert r.inspect()['page']==17
 key();assert r.inspect()['page']==13
 for i in range(6):cmd(f'challenge_hp_fixture 1 {i} 0')
 for _ in range(100):
  cmd('tick 250')
  if r.inspect()['challenge']['mode']==5:break
 assert r.inspect()['challenge']['won'];key();key();key();assert r.inspect()['page']==20
 # Six observations without a single throw, then direct return from settlement.
 r.close();r=Renderer(exe)
 cmd('boot 1 25 60 74 3 81 0 0 0');cmd('johto_fixture 2 0');cmd('page 20');key();assert r.inspect()['page']==18
 key();key(1);key();key(1);key()
 for _ in range(6):
  key();key(1);key(1);key()
 key();assert state()['bug']==1;key();assert r.inspect()['page']==20 and state()['action']==1 and state()['index']==2
 # Every dialogue page and its readonly ending is rendered; replay never writes.
 pages=[3,3,2,2,2,2,3,2,3,2,3,2,2,2,2,2,2,3,2,2,2,2,2,2,2]
 for sid,n in enumerate(pages):
  cmd('johto_fixture 8 12');cmd('page 20');key(1);key(1);key()
  for _ in range(sid):key(1)
  key();before=state()['seen'];assert state()['replay'] and state()['scene']==sid
  for p in range(n):
   cmd('tick 2500');assert state()['page']==p;key()
  assert state()['view']==2 and state()['seen']==before
 # Frame comparison throughout fade, person motion, scenery, reveal and sleep.
 for fixture in range(11):
  cmd(f'narrative_fixture {fixture}')
  for ms in (50,70,100,80,500,800,900):cmd(f'tick {ms}')
  shot(f'scene-{fixture}')
 scene(0);key(2,3);assert r.inspect()['display']['off'];old=state()['ms'];cmd('tick 3000');assert state()['ms']==old
 key();cmd('tick 100');assert not r.inspect()['display']['off'] and state()['ms']<=old+150
 result={'passed':True,'native_build':version,'pixel_checks':checks,'scope':'host production renderer; not device NVS/FPS','cases':['opening -> starter -> first route','pause and resume','wrong inference/hint','write failure/retry','read-only memories','trail choice','legend -> actual encounter','guided gym reward return','guided six-observation activity settlement','all 25 scenes/read-only pages','all eleven checkpoints','screen-off pause']}
 (out/'ui.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False))
finally:r.close()
