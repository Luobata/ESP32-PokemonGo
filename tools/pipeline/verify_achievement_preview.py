#!/usr/bin/env python3
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import build,Renderer,png
out=ROOT/'reports/evidence/achievements-volume-2026-09-08';out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0
def cmd(c):
 global checks
 f=r.command(c);assert r.command('check')['mismatch']==0,c;checks+=1;return f
def shot(name): (out/f'{name}.png').write_bytes(png(cmd('check')['pixels']))
try:
 cmd('boot 11 25 12 74 3 123 0 0 1');shot('menu')
 for _ in range(5):cmd('key 1 1')
 cmd('key 0 1')
 for _ in range(3):cmd('key 1 1')
 cmd('key 0 1');assert r.inspect()['volume']==55
 for _ in range(12):cmd('key 0 1')
 assert r.inspect()['volume']==100 and r.inspect()['muted'];shot('volume-100-muted')
 cmd('save_fail 1');cmd('key 1 1');assert r.inspect()['volume']==100;shot('volume-failed')
 for _ in range(22):cmd('key 1 1')
 assert r.inspect()['volume']==0;shot('volume-zero')
 for _ in range(11):cmd('key 0 1')
 cmd('key 2 1');cmd('key 1 3');cmd('key 0 1');assert not r.inspect()['muted']
 cmd('spawn 19 1 10');assert r.inspect()['encounter_alert']==1
 cmd('spawn 149 4 11');assert r.inspect()['encounter_alert']==2
 cmd('spawn 25 1 12 1');assert r.inspect()['encounter_alert']==3
 cmd('spawn 19 1 13');assert r.inspect()['encounter_alert']==3
 assert any(r.audio(11025));assert r.inspect()['encounter_alert']==0
 cmd('key 2 3');assert r.inspect()['display']['off'];cmd('spawn 149 4 14');assert any(r.audio(11025));assert r.inspect()['display']['off'];assert not any(r.audio(11025));cmd('key 2 1');
 cmd('key 0 1');cmd('spawn 149 5 14');assert r.inspect()['encounter_alert']==0;assert not any(r.audio(3528))
 cmd('page 14');shot('achievements-ready');before=r.inspect()['inventory']
 cmd('save_fail 1');cmd('key 0 1');assert not r.inspect()['achievement_claimed'] and r.inspect()['inventory']==before;shot('achievement-save-failed')
 cmd('key 0 1');assert r.inspect()['achievement_claimed']==1;after=r.inspect()['inventory'];shot('achievement-claimed')
 cmd('key 0 1');assert r.inspect()['inventory']==after
 for i in range(1,16):cmd('key 1 1');shot(f'achievement-{i}')
 cmd('page 13');shot('only-first-gym');before=cmd('check')['pixels']
 cmd('key 1 1');assert before==cmd('check')['pixels'];cmd('key 1 3');assert before==cmd('check')['pixels']
 cmd('key 0 1');cmd('tick 2000');shot('opponent-team-balls')
 print(json.dumps({'build':version,'render_checks':checks,'volume_bounds':True,'claims':True,'alert_priority':True,'locked_challenges_hidden':True}))
finally:r.close()
