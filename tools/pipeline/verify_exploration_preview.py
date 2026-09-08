#!/usr/bin/env python3
"""Native shared-C route UI, save failures, animation and encounter return."""
import sys,json,struct
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();out=ROOT/'reports/evidence/routes-v11-2026-09-08';out.mkdir(parents=True,exist_ok=True)
checks=0
screens=[]
def cmd(r,line):
 global checks
 f=r.command(line);assert r.command('check')['mismatch']==0,line;checks+=1;return f
def snap(r,name):
 f=cmd(r,'check');p=out/(name+'.png');p.write_bytes(png(f['pixels']));screens.append(p)
def key(r,k):return cmd(r,f'key {k} 1')
def until(r,condition):
 for _ in range(400):
  if condition(r.inspect()):return
  cmd(r,'tick 40')
 raise AssertionError(r.inspect())
r=Renderer(exe)
try:
 cmd(r,'boot 11 25 30 74 3 123 0 0 0')
 for _ in range(7):key(r,1)
 snap(r,'menu');key(r,0);assert r.inspect()['page']==15
 snap(r,'forest');key(r,1);snap(r,'route-list')
 cmd(r,'key 1 3');key(r,0);assert r.inspect()['exploration']['route']==3;snap(r,'power-plant')
 for route in (1,2):
  key(r,1)
  while r.inspect()['exploration']['route']==3: # selection isn't global until commit
   # From selected route 3: next 0,1 or 0,1,2.
   for _ in range(route+1):key(r,1)
   key(r,0);break
  assert r.inspect()['exploration']['route']==route;snap(r,('cave' if route==1 else 'coast'))
  cmd(r,'exploration_fixture 3 3 0 0')
 # Persistence failure never charges, and route selection remains unchanged.
 cmd(r,'exploration_fixture 0 10 0 0');before=r.inspect()['exploration'];cmd(r,'save_fail 1');key(r,0)
 assert r.inspect()['exploration']==before;snap(r,'save-failed')
 # First action is a monster, animation blocks gameplay keys; manual sleep remains available.
 key(r,0);after=r.inspect()['exploration'];assert after['energy']==9
 frames=set()
 for _ in range(4):
  frames.add(cmd(r,'tick 120')['pixels'])
  for k in range(3):key(r,k)
  s=r.inspect();assert s['page']==15 and s['display']['busy'] and not s['can_leave'] and s['exploration']==after
 assert len(frames)>=3
 cmd(r,'key 2 3');assert r.inspect()['display']['off']
 cmd(r,'tick 120');key(r,2);assert not r.inspect()['display']['off'];snap(r,'discovery');key(r,1);assert r.inspect()['exploration']==after
 # Three clues are route-specific; seventh action guarantees the target.
 key(r,0);cmd(r,'tick 600');assert r.inspect()['exploration']['clues'][0]==1;snap(r,'clue-one')
 key(r,1);key(r,1);key(r,0);assert r.inspect()['exploration']['route']==1
 key(r,1);cmd(r,'key 1 3');key(r,0);assert r.inspect()['exploration']['clues'][0]==1
 # Force the last step only inside the isolated host fixture.
 cmd(r,'exploration_fixture 2 2 3 0');key(r,0);cmd(r,'tick 600');s=r.inspect();assert s['exploration']['clues'][2]==0 and s['exploration']['energy']==1;snap(r,'target-lapras')
 key(r,0);assert r.inspect()['page']==3
 until(r,lambda s:not s['display']['busy']);key(r,0);assert r.inspect()['page']==4
 # Throw exactly when the rendered timing pointer is inside the blue window.
 f=cmd(r,'check');blue=struct.unpack_from('>H',f['pixels'],2*(217*240+120))[0]
 window=[x for x in range(20,221) if struct.unpack_from('>H',f['pixels'],2*(217*240+x))[0]==blue];left,right=min(window),max(window)
 for _ in range(60):
  f=cmd(r,'tick 20');pixels=f['pixels'];color=lambda x:struct.unpack_from('>H',pixels,2*(217*240+x))[0]
  if any(color(x)==0 and left<=x<=right for x in range(20,221)):break
 before=r.inspect();key(r,0);assert r.inspect()['party_count']==before['party_count']+1
 until(r,lambda s:s['page']==15);assert r.inspect()['exploration']['energy']==1;snap(r,'returned-after-capture')
 # Other pages use their original list return path; empty credits have no mutation.
 cmd(r,'exploration_fixture 1 0 0 0');before=r.inspect()['exploration'];key(r,0);assert r.inspect()['exploration']==before;snap(r,'no-energy')
finally:r.close()
r=Renderer(exe)
try:
 cmd(r,'boot 15 25 30 74 3 123 0 0 0');cmd(r,'exploration_fixture 0 2 3 0')
 key(r,0);cmd(r,'tick 600');key(r,0);until(r,lambda s:s['presentation']['phase']=='choice')
 key(r,0);key(r,0);cmd(r,'tick 3480');key(r,0)
 until(r,lambda s:s['page']==3);until(r,lambda s:s['presentation']['phase']=='choice')
 assert r.inspect()['active']['attacks']==1 and r.inspect()['exploration']['energy']==1
 cmd(r,'tick 3000');assert r.inspect()['active']['attacks']==1
 # It remains a choice after a failed direct catch, not an automatic battle.
 for _ in range(10):
  key(r,2);until(r,lambda s:not s['display']['busy'])
  if r.inspect()['page']==15:break
  if r.inspect()['presentation']['phase']=='result':key(r,2);break
 assert r.inspect()['page']==15 and r.inspect()['exploration']['energy']==1
finally:r.close()
report=dict(build=version,checks=checks,screens=[p.name for p in screens],capture_returns_to=15,failed_capture_retaliations=1,escape_returns_to=15)
(out/'preview-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
