#!/usr/bin/env python3
"""Use real LCD renderer and A/B/C events, including persistence and failures."""
import json,sys,re,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
OUT=ROOT/'reports/evidence/move-settings-2026-10-07'
OUT.mkdir(parents=True,exist_ok=True)
r=Renderer(build()[0]);checks=0

def cmd(s):
 global checks
 frame=r.command(s);check=r.command('check');assert check['mismatch']==0
 checks+=1
 return frame

def key(k,hold=False):return cmd(f'key {"ABC".index(k)} {3 if hold else 1}')
def v():return r.inspect()['party_view']
def open_moves():
 key('C');key('B');key('B');key('C');assert v()['skills']
def move_to(id):
 for _ in range(v()['skill_count']+1):
  if v()['skill_id']==id:return
  key('B')
 raise AssertionError(id)
def shot(name):
 frame=cmd('check');(OUT/f'{name}.png').write_bytes(png(frame['pixels']))
try:
 cmd('boot 12 76 60 143 3 1 0 0 1');open_moves();n=v()['skill_count'];assert v()['skill_enabled_count']==n
 move_to(153);shot('explosion-enabled');key('C');assert not v()['skill_enabled'] and v()['skill_enabled_count']==n-1
 shot('explosion-disabled');key('B',True);assert not v()['skills'];key('C');assert v()['skills'];move_to(153);assert not v()['skill_enabled']
 cmd('save_fail 1');key('C');assert not v()['skill_enabled'] and v()['feedback']=='保存失败 请重试';shot('save-error')
 key('C');assert v()['skill_enabled'];move_to(0);key('C');assert v()['skill_enabled_count']==n
 # Leave just one learned move. C cannot uncheck the final one.
 move_to(5)
 for _ in range(n-1):key('C');key('B')
 assert v()['skill_enabled_count']==1;key('C');assert v()['feedback']=='至少保留一招';assert v()['skill_enabled_count']==1;shot('last-move')
 move_to(0);key('C');assert v()['skill_enabled_count']==n;shot('all-enabled')
 key('B',True);key('B',True);assert not v()['details']
 # A second individual starts with its own default policy.
 key('B');open_moves();assert v()['skill_enabled_count']==v()['skill_count'];key('C');disabled=v()['skill_id'];assert not v()['skill_enabled']
 key('B',True);key('B',True);key('A');open_moves();move_to(5);assert v()['skill_enabled']
 # Shared page strings must have real, nonempty firmware glyphs.
 b=(ROOT/'assets/font16.bin').read_bytes();_,_,_,stride,nchars=struct.unpack_from('<4sHHHI',b);codes=struct.unpack_from(f'<{nchars}H',b,14)
 for name in ('game_ui.c','play_party.c'):
  s=(ROOT/'firmware/main'/name).read_text();s=re.sub(r'//[^\n]*|/\*.*?\*/','',s,flags=re.S)
  for literal in re.findall(r'"((?:[^"\\]|\\.)*)"',s):
   for c in literal:
    if ord(c)>127:assert ord(c) in codes,c
 print(json.dumps({'passed':True,'render_band_checks':checks,'toggle_and_reentry':True,'save_failure':True,'last_move_guard':True,'per_individual':True}))
finally:r.close()
