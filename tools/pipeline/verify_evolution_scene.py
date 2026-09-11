#!/usr/bin/env python3
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
exe,version=build();out=ROOT/'reports/evidence/evolution-scene-2026-09-11';out.mkdir(parents=True,exist_ok=True)
r=None;checks=0
def cmd(s):
 global checks
 f=r.command(s);assert r.command('check')['mismatch']==0,s;checks+=1;return f
def key(k):
 for e in [0,4,1,5]:cmd(f'key {k} {e}')
def back():
 for e in [0,3,4,5]:cmd(f'key 1 {e}')
def shot(name):(out/(name+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def boot(species=1,page=5):
 global r
 if r:r.close()
 r=Renderer(exe);cmd(f'boot {page} {species} 16 74 3 123 1 0 0');cmd('care_progress 0 0')
def start():key(0);key(2);assert r.inspect()['evolution_ui']['active']
try:
 boot();start();shot('intro');cmd('tick 1600');shot('silhouette');key(2);assert r.inspect()['party'][0]['species']==1
 back();assert not r.inspect()['evolution_ui']['active'] and r.inspect()['party'][0]['species']==1
 key(2);cmd('save_fail_after 0');cmd('tick 9000');assert r.inspect()['party'][0]['species']==1 and r.inspect()['evolutions']==0;shot('save-failed')
 key(2);assert r.inspect()['party'][0]['species']==2 and r.inspect()['evolutions']==1
 cmd('tick 150');shot('light-burst');cmd('tick 3500');shot('success');cmd('tick 5000');assert r.inspect()['evolution_ui']['active']
 key(2);assert not r.inspect()['evolution_ui']['active'];assert r.inspect()['page']==5;shot('care-after')
 # Thunder Stone (index 10) through actual bag input; no debit before reveal.
 boot(25,10);cmd('inventory 10 1');cmd('tick 300')
 for _ in range(10):key(1)
 key(2);assert r.inspect()['evolution_ui']['active'],r.inspect()
 cmd('tick 1500');assert r.inspect()['party'][0]['species']==25 and r.inspect()['inventory'][10]==1;back();assert r.inspect()['party'][0]['species']==25 and r.inspect()['inventory'][10]==1
 key(2);assert r.inspect()['evolution_ui']['active'];cmd('save_fail_after 0');cmd('tick 9000');assert r.inspect()['party'][0]['species']==25 and r.inspect()['inventory'][10]==1;key(2);cmd('tick 4500');assert r.inspect()['party'][0]['species']==26 and r.inspect()['evolutions']==1 and r.inspect()['inventory'][10]==0
 shot('stone-success');key(2);cmd('tick 300');shot('bag-after')
 result=dict(build=version,checks=checks,passed=True);(out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:
 if r:r.close()
