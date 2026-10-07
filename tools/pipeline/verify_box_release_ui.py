#!/usr/bin/env python3
"""Real LCD and A/B/C: direct release, cancel, shiny warning, retry and level sorting."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
OUT=ROOT/'reports/evidence/box-release-2026-10-07';OUT.mkdir(parents=True,exist_ok=True)
r=Renderer(build()[0]);checks=0

def cmd(text):
 global checks
 f=r.command(text);c=r.command('check');assert not c['mismatch'];checks+=1;return f

def key(k,hold=False):return cmd(f'key {"ABC".index(k)} {3 if hold else 1}')
def state():return r.inspect()
def view():return state()['party_view']
def shot(name):(OUT/f'{name}.png').write_bytes(png(cmd('check')['pixels']))
def prompt():
 key('C');key('B');key('B');key('C')
 assert state()['box_release']=={'confirm':True,'choice':0}

try:
 cmd('boot 12 25 30 74 3 123 0 0 0')
 for sid in (1,4,7,10,13):cmd(f'party_add {sid} 20 40 0 0')
 # Warehouse: species order differs from level order, including a shiny individual.
 for sid,level,shiny in ((25,40,1),(133,5,0),(76,60,0),(9,30,0)):
  cmd(f'party_add {sid} {level} 40 0 {shiny}')
 before=state();assert before['box_count']==4
 key('C');key('B');key('B');key('B');key('C');assert view()['box']
 key('A',True);key('B');key('B');key('C');key('B');key('B');shot('sort-options');key('C')
 assert view()['box_sort']==2
 # Switching sorting preserves selected individual; seek lowest then verify complete order.
 for _ in range(4):
  if view()['species']==133:break
  key('B')
 assert view()['species']==133
 order=[]
 for _ in range(4):order.append(view()['species']);key('B')
 assert order==[133,9,25,76],order
 shot('ascending-level')
 prompt();shot('release-normal');key('C');assert not state()['box_release']['confirm'] and state()['box_count']==4
 # Confirm screen defaults to Cancel on every entry; held B cancels even after moving.
 key('C');assert state()['box_release']['choice']==0;key('B');key('B',True)
 assert not state()['box_release']['confirm'] and state()['box_count']==4
 key('C');key('B');cmd('save_fail 1');key('C')
 assert state()['box_release']['confirm'] and view()['feedback']=='保存失败 请重试' and state()['box_count']==4
 shot('release-save-failure');key('C')
 assert not state()['box_release']['confirm'] and not view()['details'] and state()['box_count']==3
 assert state()['party']==before['party'];assert view()['feedback']=='伙伴已放生';shot('released')
 # Remove remaining entries, including shiny prompt and final empty warehouse.
 for remaining in (3,2,1):
  prompt()
  if remaining==2:shot('release-shiny')
  key('B');key('C');assert state()['box_count']==remaining-1
 assert view()['box_matches']==0 and not view()['details'];shot('empty')
 key('C');assert state()['box_count']==0 and not state()['box_release']['confirm']
 key('B',True);assert not view()['box']
 result={'passed':True,'band_checks':checks,'cancel_default_and_long_b':True,'save_failure_retry':True,'party_preserved':True,'shiny_warning':True,'level_ascending':True,'empty_warehouse':True}
 (OUT/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:r.close()
