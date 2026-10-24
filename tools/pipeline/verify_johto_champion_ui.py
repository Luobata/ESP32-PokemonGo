#!/usr/bin/env python3
"""Actual C pages and input flow, shared band renderer and complete redraw oracle."""
import json,os,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',str(ROOT/'reports/evidence/johto-champion-2026-10-18')));out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f

def key(n,times=1):
 for _ in range(times):cmd(f'key {n} 1')

def shot(name):(out/(name+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def lake(stage):
 cmd(f'lake_fixture {stage}');cmd('page 19');key(1,4);key(2)
try:
 cmd('boot 1 25 90 74 3 81 0 0 0');cmd('johto_fixture 8 12');cmd('challenge_unlock 255');cmd('page 17');cmd('tick 1200');key(1,2);key(2);key(2);shot('gym-ordinary')
 cmd('challenge_unlock 16383');cmd('page 17');cmd('tick 1200');key(1,2);key(2);key(2);shot('gym-champion-rules');key(2)
 state=r.inspect();assert state['endgame']['rule']==1;assert [m['level'] for m in state['challenge']['sides'][1]['mons']]==[78,79,80,80,81,82]
 # UI fixture removes opponents only to exercise result navigation. Combat has a separate production harness.
 for i in range(6):cmd(f'challenge_hp_fixture 1 {i} 0')
 for _ in range(80):
  cmd('tick 250')
  if r.inspect()['challenge']['mode']==5:break
 assert r.inspect()['challenge']['won'];assert r.inspect()['endgame']['champion_gyms']==1
 key(2,3);cmd('page 14');key(1,32);shot('champion-achievement');key(2);assert r.inspect()['endgame']['claimed']==1
 lake(0);shot('lake-entry');cmd('save_fail 1');key(2);assert r.inspect()['endgame']['lake_stage']==0;key(2);assert r.inspect()['endgame']['lake_stage']==1;shot('lake-rumor');key(2);assert r.inspect()['endgame']['lake_stage']==2
 lake(3);shot('lake-console');key(2);assert r.inspect()['endgame']['lake_stage']==3;key(1);key(2);assert r.inspect()['endgame']['lake_stage']==4;shot('lake-battle-ready');key(2)
 seen=False
 for _ in range(200):
  cmd('tick 50')
  if r.inspect()['shiny_entry_side']&2:seen=True;shot('red-gyarados-entry');break
 assert seen
 cmd('challenge_hp_fixture 1 0 0')
 for _ in range(90):
  cmd('tick 250')
  if r.inspect()['challenge']['mode']==5:break
 assert r.inspect()['endgame']['lake_stage']==5;key(2,3);shot('lake-calm');key(2);cmd('tick 6400');shot('lake-ball-shake');key(2);assert r.inspect()['endgame']['lake_stage']==5;cmd('tick 2800');shot('lake-caught-stars');assert r.inspect()['display']['busy'];cmd('tick 4200');assert not r.inspect()['display']['busy']
 # Fill all 759 individuals before receiving, then require explicit second confirmation.
 for i in range(5):cmd('party_add 25 20 50 0 0')
 cmd('box_fixture 753 150');key(2);shot('lake-full-box');assert r.inspect()['endgame']['lake_stage']==5;key(2);shot('lake-replace-confirm');key(2);assert r.inspect()['endgame']['lake_stage']==5;key(2);key(1);cmd('save_fail 1');key(2);assert r.inspect()['endgame']['lake_stage']==5;key(2);assert r.inspect()['endgame']['lake_stage']==6;assert r.inspect()['box_count']==753
 # Leaving and re-entering completed quest does not create another individual.
 lake(6);shot('lake-complete');key(2);assert r.inspect()['box_count']==753
 result={'passed':True,'native_build':version,'checks':checks,'scope':'native UI with fixtures; production battle/persistence validated separately'};(out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:r.close()
