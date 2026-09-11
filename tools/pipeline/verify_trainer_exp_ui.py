#!/usr/bin/env python3
"""Trainer EXP HUD, committed reward animation and dialogue/learning ordering."""
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build()
out=ROOT/'reports/evidence/trainer-exp-2026-09-10';out.mkdir(parents=True,exist_ok=True)
r=None;checks=0;cases=[]
def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f
def state():return r.inspect()
def key(k):
 for e in (0,4,1,5):cmd(f'key {k} {e}')
def until(predicate):
 for _ in range(400):
  if predicate(state()):return
  cmd('tick 90')
 raise AssertionError(state())
def shot(name):
 f=cmd('tick 0');(out/(name+'.png')).write_bytes(png(f['pixels']));return f
def bar(f):
 return b''.join(f['pixels'][(y*240+120)*2:(y*240+232)*2] for y in range(224,240))
def run_case(route=False,lose=False,retry=False,replace=False):
 global r
 if r:r.close()
 r=Renderer(exe);name=('route' if route else 'gym')+('-loss' if lose else '-win')+('-retry' if retry else '')+('-replacement' if replace else '')
 cmd(f'boot {15 if route else 13} 25 12 74 3 123 0 0 {int(replace)}')
 cmd('party_exp 0 3245')  # Lv12, 50 EXP from Lv13.
 if replace:cmd('party_exp 1 2700')
 if route:key(0);key(2);key(2)
 key(2);until(lambda s:s['challenge']['mode']==2)
 cmd('tick 1200')
 initial=shot(name+'-battle-hud')
 assert b'\x7f\x24' in bar(initial),'the shared blue EXP tiles must be visible'
 if replace:
  cmd('challenge_hp_fixture 0 0 0');until(lambda s:s['challenge']['mode']==4)
  key(1);key(2);assert state()['challenge']['sides'][0]['active']==1
  switched=shot(name+'-switched-hud');assert bar(initial)!=bar(switched)
 before=state();old=sum(m['exp'] for m in before['party'])
 side=0 if lose else 1
 for i in range(len(before['challenge']['sides'][side]['mons'])):cmd(f'challenge_hp_fixture {side} {i} 0')
 if retry:cmd('save_fail_after 1')
 if retry:
  until(lambda s:s['challenge']['mode']==5)
  assert sum(m['exp'] for m in state()['party'])==old
  shot(name+'-save-failed');key(2)
 until(lambda s:s['challenge']['mode']==10)
 committed=state();new=sum(m['exp'] for m in committed['party']);assert new>old
 assert not committed['growth']
 frames=[]
 for i in range(19):
  f=cmd('tick 0');frames.append(bar(f))
  if i in (0,8,18):shot(name+f'-exp-{i}')
  if i<5:key(2);assert state()['challenge']['mode']==10,'early confirm must not skip EXP'
  assert sum(m['exp'] for m in state()['party'])==new,'redraw/input must not grant EXP twice'
  cmd('tick 90')
 assert len(set(frames))>1,('EXP meter must animate',name,new-old)
 until(lambda s:s['challenge']['mode']==5)
 cmd('tick 900');shot(name+'-dialogue')
 if not lose:
  assert not state()['growth'],'trainer dialogue must precede learned-move notice'
  key(2);cmd('tick 900');shot(name+'-items')
  assert not state()['growth'];key(2)
 cmd('tick 900')
 if committed['party'][0]['level']>before['party'][0]['level']:
  until(lambda s:s['growth'] is not None);shot(name+'-learned')
 assert sum(m['exp'] for m in state()['party'])==new
 cases.append({'name':name,'party_exp_gain':new-old,'animated_bar_samples':len(set(frames))})
try:
 run_case(route=True);run_case(retry=True);run_case(lose=True);run_case(replace=True)
 result={'build':version,'dirty_full_checks':checks,'cases':cases,'passed':True}
 (out/'trainer-exp-ui.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:
 if r:r.close()
