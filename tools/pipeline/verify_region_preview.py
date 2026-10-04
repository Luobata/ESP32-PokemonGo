#!/usr/bin/env python3
"""Same C UI as LCD: twelve-map paging, themed admission, directional exploration."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build()
out=ROOT/'reports/evidence/gen1-regions-2026-10-05';out.mkdir(parents=True,exist_ok=True)
checks=0

def cmd(r,text):
 global checks
 frame=r.command(text)
 assert r.command('check')['mismatch']==0,text
 checks+=1
 return frame

def key(r,k):return cmd(r,f'key {k} 1')
def snap(r,name):
 frame=cmd(r,'check');(out/(name+'.png')).write_bytes(png(frame['pixels']))

for region in range(4,12):
 r=Renderer(exe)
 try:
  cmd(r,'boot 15 25 45 74 3 812 0 0 1');cmd(r,'challenge_unlock 16383');cmd(r,f'region_fixture {region} 1')
  assert r.inspect()['region']['map']==region;snap(r,f'map-{region}')
  key(r,2);snap(r,f'paths-{region}')
  key(r,2);cmd(r,'tick 720')
  for _ in range(8):
   if not r.inspect()['growth']:break
   cmd(r,'key 1 3');cmd(r,'tick 120')
  assert r.inspect()['region']['map']==region
  snap(r,f'discovery-{region}')
  # Enter the matching theme through its actual activity button.
  cmd(r,'key 1 3');key(r,1);key(r,1);key(r,2);snap(r,f'activities-{region}');key(r,2)
  assert r.inspect()['page']==16;snap(r,f'dungeon-{region}')
  key(r,1);key(r,2);key(r,2) # select own leader
  for _ in range(r.inspect()['party_count']):key(r,1)
  key(r,2);assert r.inspect()['page']==13 and r.inspect()['dungeon_theme']==region-3
 finally:r.close()
r=Renderer(exe)
try:
 cmd(r,'boot 15 25 45 74 3 812 0 0 1');key(r,1);key(r,2);snap(r,'locked-routes')
 for _ in range(4):key(r,1)
 key(r,2);assert r.inspect()['region']['map']==0
 cmd(r,'challenge_unlock 16383');cmd(r,'region_fixture 4 1');key(r,1);key(r,2)
 for _ in range(7):key(r,1)
 snap(r,'route-page-3');key(r,2);assert r.inspect()['region']['map']==11
finally:r.close()
# A complete production-C battle run, including the new exit-direction screen.
r=Renderer(exe)
try:
 cmd(r,'boot 16 150 100 74 3 812 0 0 0');cmd(r,'party_add 149 100 100 0 0');cmd(r,'party_add 143 100 100 0 0')
 cmd(r,'challenge_unlock 16383');cmd(r,'region_fixture 4 0')
 key(r,1);key(r,2)
 for _ in range(3):key(r,2);key(r,1)
 key(r,2)
 saw_trail=False
 for _ in range(700):
  st=r.inspect();d=st['dungeon']
  if st['growth']:
   cmd(r,'key 1 3');continue
  if st['page']==13:
   if d['mode'] in (0,1,5,7,10):key(r,2);cmd(r,'tick 3000')
   elif d['mode']==4:key(r,1);key(r,2)
   else:cmd(r,'tick 10000')
  elif st['page']==16:
   if d['phase']==9:snap(r,'exit-directions');saw_trail=True;key(r,2)
   elif d['phase']==7 and d['node']==7:
    cmd(r,'tick 1500');snap(r,'theme-clear');assert saw_trail and (st['queue'] or st['region']['pending_partner']),(saw_trail,st);break
   elif d['phase']==6:raise AssertionError('Unexpected defeat in overlevelled UI fixture')
   else:
    if d['phase']==3:key(r,1)
    key(r,2);cmd(r,'tick 1500')
  else:raise AssertionError(st['page'])
 else:raise AssertionError('Theme playthrough did not finish')
finally:r.close()
(out/'verification.json').write_text(json.dumps(dict(build=version,checks=checks,maps=8,pixel_band_mismatches=0),indent=2)+'\n')
print(json.dumps(dict(build=version,checks=checks,evidence=str(out))))
