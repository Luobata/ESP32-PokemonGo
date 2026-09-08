#!/usr/bin/env python3
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();p=ROOT/'reports/evidence/growth-links-2026-09-08';p.mkdir(parents=True,exist_ok=True);checks=0
r=Renderer(exe)
def cmd(line):
 global checks
 f=r.command(line);assert r.command('check')['mismatch']==0,line;checks+=1;return f
def snap(name): (p/(name+'.png')).write_bytes(png(cmd('check')['pixels']))
try:
 cmd('boot 12 25 12 74 3 123 0 0 1');cmd('party_add 150 30 70 10 1');old=r.inspect();cmd('key 0 3');snap('warehouse')
 cmd('save_fail 1');cmd('key 0 1');assert r.inspect()['party']==old['party'] and r.inspect()['box_count']==old['box_count'];snap('swap-failed')
 cmd('key 0 1');assert r.inspect()['party'][0]['species']==150 and r.inspect()['party'][0]['flags']&1 and r.inspect()['box_count']==1;snap('new-party')
 cmd('key 0 3');cmd('key 0 1');assert r.inspect()['party'][0]['species']==25
 cmd('page 5');cmd('nurture_fixture 100 100 50 100');cmd('tick 80');snap('care-bonuses')
 for i in range(2):cmd('key 1 1')
 before=r.inspect()['nurture']['stamina'];cmd('key 0 1');assert r.inspect()['nurture']['stamina']==before;snap('time-only')
 cmd('page 15');cmd('nurture_fixture 80 70 4 0');cmd('tick 120');prior=r.inspect()['exploration'];cmd('key 0 1');assert r.inspect()['exploration']==prior;snap('no-stamina')
 # Real time tick in the host boundary: gain one point in ~5 minutes, without actions.
 for i in range(6):cmd('tick 60000')
 assert r.inspect()['nurture']['stamina']>=5
 cmd('key 0 1') # Wake only when automatic sleep has engaged.
 cmd('key 0 1');cmd('tick 600');assert r.inspect()['exploration']['energy']==prior['energy']-1
 assert r.inspect()['nurture']['stamina']<2
finally:r.close()
report={'checks':checks,'version':version,'warehouse_roundtrip':True,'time_only_regen':True};(p/'preview.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
