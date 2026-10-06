#!/usr/bin/env python3
"""Navigate production LCD screens in the native renderer, including real battles."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
OUT=ROOT/'reports/evidence/exploration-balance-2026-10-06'

def run():
 OUT.mkdir(parents=True,exist_ok=True);exe,version=build();checks=0
 def cmd(r,s):
  nonlocal checks
  f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f
 def key(r,b):return cmd(r,f'key {b} 1')
 def snap(r,name):
  f=cmd(r,'check');(OUT/f'{name}.png').write_bytes(png(f['pixels']))
 def dismiss_growth(r):
  for _ in range(30):
   cmd(r,"tick 500")
   if not r.inspect()["growth"]:return
   cmd(r,"key 1 3")
  raise AssertionError("Growth notices did not finish")
 def boot(r,level=100,species=150,wins=50):
  cmd(r,f'boot 15 {species} {level} 74 3 812 0 0 1');cmd(r,'challenge_unlock 16383');cmd(r,'region_fixture 4 1');cmd(r,f'chain_fixture {wins}');cmd(r,'page 15')
 r=Renderer(exe)
 try:
  boot(r);snap(r,'chain-50-map');key(r,1);key(r,2);snap(r,'map-minimum-levels');cmd(r,'key 1 3')
  key(r,1);key(r,2) # Root selection resumes at route, so next is activities.
  for _ in range(6):key(r,1)
  snap(r,'chain-help-menu');key(r,2);snap(r,'chain-rules');cmd(r,'key 1 3');cmd(r,'key 1 3')
  assert r.inspect()['exploration_chain']['wins']==50
  cmd(r,'page 15');cmd(r,'chain_fixture 4294967295');cmd(r,'page 15');snap(r,'chain-counter-maximum')
 finally:r.close()
 results=[]
 for won in (True,False):
  r=Renderer(exe)
  try:
   boot(r,100 if won else 1,150 if won else 129)
   before=r.inspect();key(r,2);key(r,2);cmd(r,'tick 1000');found=r.inspect()
   new=[e for e in found['queue'] if e['uid'] not in {e['uid'] for e in before['queue']}];assert len(new)==1
   level=new[0]['level'];assert 35<=level<=45
   dismiss_growth(r)
   key(r,2);assert r.inspect()['page']==3;cmd(r,'tick 6000')
   # Check the battle initializer preserves the discovered map level.
   st=r.inspect();entries=st['queue']+[st['active']] if st['active'] else st['queue'];entry=next(e for e in entries if e['uid']==new[0]['uid']);assert entry['wild_level']==level
   if won:
    snap(r,'battle-map-level')
    balls=r.inspect()['inventory']
    key(r,2);assert r.inspect()['page']==4
    snap(r,'chain-capture-confirm')
    cmd(r,'tick 2000');assert r.inspect()['exploration_chain']['wins']==50
    cmd(r,'key 2 0');assert r.inspect()['page']==4 # PRESS alone cannot cancel or throw.
    key(r,2) # Default is cancel; the release cannot re-enter capture.
    assert r.inspect()['page']==3 and r.inspect()['exploration_chain']['wins']==50
    key(r,2);cmd(r,'key 1 3') # Holding B cancels too.
    assert r.inspect()['page']==3 and r.inspect()['inventory']==balls

   key(r,1);key(r,2)
   for _ in range(150):
    cmd(r,'tick 3000');st=r.inspect()
    if st['active'] and st['active']['finished'] and st['active']['reward_settled']:
     assert st['active']['won']==won
     assert st['exploration_chain']['wins']==(51 if won else 0)
     dismiss_growth(r);cmd(r,'tick 3000');st=r.inspect()
     if st['can_leave'] and not st['growth']:break
   else:raise AssertionError(st)
   snap(r,'chain-win' if won else 'chain-loss');results.append(dict(won=won,discovered_level=level,battle_level=st['active']['wild_level'],wins=st['exploration_chain']['wins']))
   if won:
    balls=r.inspect()['inventory'];key(r,2);assert r.inspect()['page']==4
    key(r,1);cmd(r,'save_fail 1');key(r,2)
    assert r.inspect()['exploration_chain']['wins']==51 and r.inspect()['inventory']==balls
    snap(r,'chain-capture-save-failed');key(r,2)
    assert r.inspect()['exploration_chain']['wins']==0 and r.inspect()['inventory']==balls
    snap(r,'chain-capture-ready')
    # Confirmation waits for CLICK and cannot also throw on the same gesture.
    cmd(r,'key 1 3');cmd(r,'chain_fixture 51');key(r,2);key(r,1)
    cmd(r,'key 2 0');assert r.inspect()['exploration_chain']['wins']==51
    cmd(r,'key 2 1')
    assert r.inspect()['exploration_chain']['wins']==0 and r.inspect()['inventory']==balls
    # Re-entering after confirmation needs no second confirmation; C now throws.
    cmd(r,'key 1 3');key(r,2);key(r,2)
    assert sum(r.inspect()['inventory'])==sum(balls)-1

  finally:r.close()
 r=Renderer(exe)
 try:
  cmd(r,'boot 3 150 100 74 3 812 0 0 1');cmd(r,'chain_fixture 50');cmd(r,'tick 6000')
  balls=r.inspect()['inventory'];key(r,2);key(r,2)
  assert r.inspect()['exploration_chain']['wins']==50 and sum(r.inspect()['inventory'])==sum(balls)-1
 finally:r.close()
 r=Renderer(exe)
 try:
  boot(r);key(r,2);key(r,2);cmd(r,'tick 1000');dismiss_growth(r);key(r,2);cmd(r,'tick 6000')
  balls=r.inspect()['inventory'];key(r,2);key(r,1);key(r,2)
  assert r.inspect()['page']==4 and r.inspect()['exploration_chain']['wins']==0 and r.inspect()['inventory']==balls
  cmd(r,'key 1 3');assert r.inspect()['page']==3 and r.inspect()['exploration_chain']['wins']==0
 finally:r.close()
 result=dict(build=version,checks=checks,pixel_band_mismatches=0,battles=results)
 (OUT/'chain-preview.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':run()
