#!/usr/bin/env python3
"""Actual page frames: readable move holds, failed settlement retry, menu links."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=ROOT/'reports/evidence/system-review-2026-09-08';out.mkdir(parents=True,exist_ok=True)
exe,version=build();checks=0;frames=[];moves=set();r=Renderer(exe)
def cmd(line):
 global checks
 f=r.command(line);assert r.command('check')['mismatch']==0,line;checks+=1;return f
def capture(name): (out/(name+'.png')).write_bytes(png(cmd('check')['pixels']))
try:
 cmd('boot 3 25 60 130 3 123 0 0 0');cmd('tick 6000');cmd('key 1 1')
 injected=False;before=0;held={}
 for n in range(5000):
  st=r.inspect();assert st['page']==3
  p=st['presentation'];a=st['active']
  if p['phase']=='attack':
   mid=p['move_id'];moves.add(mid);held[mid]=held.get(mid,0)+1
   if len(frames)<100:frames.append(cmd('check')['pixels'])
   if held[mid]==12:capture('move-'+str(mid))
  if a and a['finished'] and not injected:
   cmd('save_fail 1');before=st['exp'];injected=True
  if injected and p['phase']=='result':
   assert st['exp']==before;capture('settlement-retry');cmd('tick 2000');assert r.inspect()['exp']==before
   cmd('key 2 1');assert r.inspect()['page']==3
   cmd('key 0 1');cmd('tick 2500');assert r.inspect()['exp']>before
   gain=r.inspect()['exp']-before;cmd('tick 3000');assert r.inspect()['exp']==before+gain;break
  cmd('tick 90')
 else:raise AssertionError('battle did not finish')
 cmd('party_add 1 12 60 0 0');assert r.inspect()['caught']>=2
 cmd('page 11');capture('menu-rewards')
 for i in range(6):cmd('key 1 1')
 capture('menu-rewards-selected')
finally:r.close()
# Optional presentation artifact; validation above has no image-library dependency.
try:
 from PIL import Image
 import io
 ims=[Image.open(io.BytesIO(png(f))) for f in frames]
 if ims:ims[0].save(out/'battle-preview.gif',save_all=True,append_images=ims[1:],duration=90,loop=0)
except ImportError:pass
report={'checks':checks,'version':version,'moves':sorted(moves),'settlement_retry_exactly_once':True,'reward_gain':gain}
(out/'preview.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
