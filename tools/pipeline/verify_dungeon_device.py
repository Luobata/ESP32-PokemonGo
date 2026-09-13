#!/usr/bin/env python3
"""Drive the exact device pages and C dungeon model through the three buttons."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'inspector'))
from native import Renderer,build,png
r=Renderer(build()[0]);out=Path('reports/evidence/dungeon-owned-2026-09-13');out.mkdir(parents=True,exist_ok=True)
try:
 frame=r.command('boot 16 25 40 74 3 1 0 0 0')
 for species in (6,9,143):r.command(f'party_add {species} 40 30 0 0')
 initial=r.inspect()
 (out/'lobby.png').write_bytes(png(frame['pixels']))
 def key(n):return r.command(f'key {n} 1')
 key(1);key(2) # new run
 (out/'owned-selection.png').write_bytes(png(r.command('check')['pixels']))
 key(1);key(2);key(1);key(2);key(1);key(2);key(1);key(2) # own Charizard, Blastoise, Snorlax, then depart
 assert [m['species'] for m in r.inspect()['dungeon_team']]==[6,9,143]
 assert all(m['level']==40 for m in r.inspect()['dungeon_team'])
 visited=set();saved=set()
 for i in range(1400):
  state=r.inspect();d=state['dungeon'];phase=d['phase'];visited.add(phase)
  if phase not in saved:
   frame=r.command('check');assert frame['mismatch']==0,frame['mismatch']
   (out/f'phase-{phase}.png').write_bytes(png(frame['pixels']));saved.add(phase)
  if state.get('growth'):
   key(2);r.command('tick 90');continue
  if phase==7:
   f=r.command('tick 1300');(out/'settled-rewards.png').write_bytes(png(f['pixels']));key(2)
  elif phase==1:
   r.command('tick 1500')
   if r.inspect()['dungeon']['mode']==4:key(1);key(2)
  elif phase==2:key(2)
  elif phase==3:key(1);key(2) # thorns / supplies
  elif phase==4:key(2) # heal
  elif phase in (5,6):break
  else:raise AssertionError(d)
  if i%40==0:print(i,d,flush=True)
 assert phase in (5,6),d
 after=r.inspect();assert initial['party']!=after['party'],'no real experience granted'
 assert after['inventory']!=initial['inventory'],'no real supplies granted'
 assert initial['party'][0]==after['party'][0], 'unselected leader received XP'
 assert initial['challenge']['defeated']==after['challenge']['defeated']
 print('PASS',d,'phases',sorted(visited),'real party experience and supplies granted')
finally:r.close()
