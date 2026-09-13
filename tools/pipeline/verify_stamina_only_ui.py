#!/usr/bin/env python3
"""Legacy balances no longer affect rewards/UI; verify real input and dirty redraw."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();out=ROOT/'reports/evidence/stamina-only-2026-09-13';out.mkdir(parents=True,exist_ok=True)
results=[];frames=[]
for legacy in (0,24):
 r=Renderer(exe)
 try:
  r.command('boot 15 25 16 74 3 123 0 0 0');r.command(f'exploration_fixture 0 {legacy} 0 1');r.command('nurture_fixture 80 80 100 50');f=r.command('tick 180');assert r.command('check')['mismatch']==0
  frames.append(f['pixels']);(out/f'explore-legacy-{legacy}.png').write_bytes(png(f['pixels']))
  for e in (0,4,1,5):r.command(f'key 2 {e}')
  r.command('tick 1500');assert r.command('check')['mismatch']==0
  s=r.inspect();assert s['exploration']['energy']==legacy and s['nurture']['stamina']==95
  results.append(s['exploration']);(out/f'discovery-legacy-{legacy}.png').write_bytes(png(r.command('tick 0')['pixels']))
 finally:r.close()
assert frames[0]==frames[1], 'retired balance visible in UI'
for x in results:x.pop('energy')
assert results[0]==results[1]
r=Renderer(exe)
try:
 r.command('boot 1 25 16 74 3 123 0 0 0');r.command('nurture_fixture 80 80 50 50');f=r.command('tick 300');assert r.command('check')['mismatch']==0;(out/'home.png').write_bytes(png(f['pixels']))
finally:r.close()
print(json.dumps(dict(build=version,legacy_balance_invisible=True,stamina_cost=5,passed=True)))
