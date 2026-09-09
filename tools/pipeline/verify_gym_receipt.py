#!/usr/bin/env python3
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import build,Renderer,png
out=ROOT/'reports/evidence/progress-review-2026-09-09';out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0
def cmd(c):
 global checks
 f=r.command(c);assert r.command('check')['mismatch']==0;checks+=1;return f
def shot(name):
 f=cmd('tick 900');(out/(name+'.png')).write_bytes(png(f['pixels']))
try:
 cmd('boot 13 25 100 74 3 123 0 0 0');before=r.inspect()['inventory'];cmd('key 0 1')
 # Inspect actual initial sendout after reveal: the back picture must move.
 for _ in range(100):
  if r.inspect()['challenge']['mode']==2:break
  cmd('tick 90')
 cmd('tick 900');samples=[]
 for _ in range(8):
  f=cmd('tick 90');samples.append(b''.join(f['pixels'][((140+j)*240+8)*2:((140+j)*240+104)*2] for j in range(96)))
 assert len(set(samples))>=3
 for _ in range(3000):
  if r.inspect()['challenge']['mode']==5:break
  cmd('tick 360')
 assert r.inspect()['challenge']['won'];awarded=r.inspect()['inventory']
 assert awarded[0]-before[0]==5 and awarded[17]-before[17]==2 and awarded[12]-before[12]==1
 shot('leader-dialogue');cmd('key 0 1');shot('item-receipt');cmd('key 0 1');shot('badge-summary');cmd('key 2 1')
 assert r.inspect()['challenge']['mode']==0 and r.inspect()['inventory']==awarded
 result={'status':'PASS','renderer':version,'dirty_full_checks':checks,'player_back_motion':True,'dialogue_items_badge':True,'actual_inventory_deltas':True,'no_duplicate_reward':True}
 (out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:r.close()
