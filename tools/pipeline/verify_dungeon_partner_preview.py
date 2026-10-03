#!/usr/bin/env python3
"""Native eight-node playthrough: settlement discovery and band rendering parity."""
import sys,json
from pathlib import Path
root=Path(__file__).resolve().parents[2];sys.path.insert(0,str(root/'tools/inspector'))
from native import Renderer,build,png
r=Renderer(build()[0]);out=root/'reports/evidence/battery-bag-shiny-2026-10-03'
def key(n):return r.command(f'key {n} 1')
try:
 r.command('boot 16 150 100 74 3 41 0 0 0');r.command('party_add 149 100 100 0 0');r.command('party_add 143 100 100 0 0')
 key(1);key(2)
 for i in range(3):key(2);key(1)
 key(2)
 previous=None
 for i in range(500):
  st=r.inspect();d=st['dungeon'];phase=(st['page'],d['node'],d['phase'],d['mode'])
  if phase!=previous:print(i,phase,flush=True);previous=phase
  if st['page']==13:
   if d['mode'] in [0,1,5,7,10]:
    key(2);r.command('tick 3000')
   elif d['mode']==4:key(1);key(2)
   else:r.command('tick 10000')
  elif st['page']==16:
   if d['phase']==7 and d['node']==7:
    r.command('tick 1500');f=r.command('check');assert not f['mismatch'];out.joinpath('dungeon-clear-partner.png').write_bytes(png(f['pixels']));print('CLEAR',json.dumps(r.inspect()['queue']),flush=True);break
   if d['phase']==6:raise AssertionError('Dungeon defeat')
   if d['phase']==3:key(1) # Choose safe path/supplies.
   key(2);r.command('tick 1500')
  else:raise AssertionError(st['page'])
 else:raise AssertionError('Playthrough timeout')
finally:r.close()
