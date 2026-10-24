#!/usr/bin/env python3
"""Actual C fieldwork UI, helper selection, pixel clipping and scene time."""
import json,os,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
from build import load_data
out=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',ROOT/'reports/evidence/johto-fieldwork-2026-10-24'));out.mkdir(parents=True,exist_ok=True)
source=(ROOT/'firmware/main/johto_routes.c').read_text().split('static const johto_probe_t PROBES')[1].split('const johto_probe_t *johto_probe(')[0]
for line in re.findall(r'"([^"\n]+)"',source):
 assert sum(8 if ord(c)<128 else 16 for c in line)<=208,('clipped evidence text',line)
# Do not reveal concrete answers in the optional hint or wrong-partner feedback.
names=[m['zh'] for m in load_data(ROOT/'assets/gen1.bin') if m['zh']]
for row in source.splitlines():
 strings=re.findall(r'"([^"\n]+)"',row)
 if len(strings)==8:
  for hint in strings[3:5]:
   assert not any(name in hint for name in names),('species spoiler',hint)
   assert '属性' not in hint,('ability hint states the answer',hint)
exe,version=build();r=None;checks=0
paths=[0,1,2,2,2,0,2,0,0,1,2,0,1,2,0,2,1]
helpers=[0,1,1,2,2,2,5,3,5,0,5,2,4,2,3,4,3]
legends=[0,0,0,1,1,1,2,2,3,3,3,4,4,4,5,5,5]
def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f
def state():return r.inspect()
def key(n,ev=1):cmd(f'key {n} {ev}')
def select(n):
 for _ in range(8):
  if state()['fieldwork']['selected']==n:return
  key(1)
 raise AssertionError(('selection',n,state()['fieldwork']))
def shot(n):(out/(n+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def enter(i):
 global r
 if r:r.close()
 r=Renderer(exe);cmd('boot 1 25 60 74 3 81 0 0 0');cmd(f'fieldwork_fixture {i}')
 assert state()['fieldwork']['view']==14 and state()['fieldwork']['id']==i
try:
 for i in range(17):
  enter(i);before=state();shot(f'site-{i}')
  # Hints and real party management are free. Return to the same field notes.
  select(1);key(2);assert state()['fieldwork']['help']==1;shot(f'hint-{i}')
  if i==0:
   select(2);key(2);assert state()['page']==12;key(1,3);assert state()['page']==17 and state()['fieldwork']['view']==14
  select(0);key(2);select((paths[i]+1)%3);key(2)
  assert state()['fieldwork']['error']==6 and state()['nurture']==before['nurture'] and state()['johto']==before['johto']
  select(paths[i]);key(2);assert state()['fieldwork']['view']==16
  # Pika is intentionally unsuitable for non-electric sites; Sandlash for electric.
  wrong=1 if helpers[i]==0 else 0;select(wrong);key(2)
  assert state()['fieldwork']['error']==7 and state()['nurture']==before['nurture'];shot(f'prepare-{i}')
  select(helpers[i]);cmd('save_fail 1');key(2)
  assert state()['fieldwork']['error']==5 and state()['johto']==before['johto'] and state()['nurture']==before['nurture']
  key(2);after=state();assert after['fieldwork']['view']==17 and after['fieldwork']['evidence'][legends[i]]==before['fieldwork']['evidence'][legends[i]]+1
  assert after['nurture']['stamina']==before['nurture']['stamina']-5 and after['johto']['visits']==before['johto']['visits']+1
  for _ in range(26):cmd('tick 50')
  shot(f'result-{i}');assert state()['fieldwork']['ms']==1300
  key(2);assert state()['page']==20
 # Successful action motion uses real elapsed time, and sleep cannot fast-forward it.
 for quantum in [40,50,80,160]:
  enter(0);key(2);key(2);key(2)
  total=0
  while total<1200:cmd(f'tick {quantum}');total+=quantum
  # The last 50 ms display callback can precede the requested host wall time.
  assert 0<=total-state()['fieldwork']['ms']<50
  assert state()['fieldwork']['evidence'][0]==1 and state()['nurture']['stamina']==85
 enter(0);key(2);key(2);key(2);cmd('tick 300');elapsed=state()['fieldwork']['ms']
 key(2,3);assert state()['display']['off'];cmd('tick 1500');assert state()['fieldwork']['ms']==elapsed
 key(2);cmd('tick 100');assert not state()['display']['off'] and state()['fieldwork']['ms']<=elapsed+100
 # Ordinary exploration remains available, and does not secretly solve a story site.
 enter(0);key(1,3);assert state()['page']==20;key(1);key(2);assert state()['page']==17
 key(1);key(2)  # Investigation routes
 for _ in range(4):key(1)
 key(2);select(1);key(2);key(2)
 assert state()['fieldwork']['evidence'][0]==0 and state()['johto']['research'][4]==1
 result=dict(passed=True,native_build=version,pixel_checks=checks,sites=17,scope='production C pages + host world adapter; transactions separately tested; no hardware FPS claim')
 (out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:
 if r:r.close()
