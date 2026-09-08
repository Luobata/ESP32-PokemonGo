#!/usr/bin/env python3
"""Real C page motion, wake gestures and transition masks; no physical device claim."""
import hashlib,json,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
from verify_menu_party_layout import crop
OUT=ROOT/'reports/evidence/comfort-2026-09-08'
OUT.mkdir(parents=True,exist_ok=True)
exe,build_id=build(); checks=0

def command(r,s):
 global checks
 f=r.command(s); assert r.command('check')['mismatch']==0,s;checks+=1
 return f['pixels']

def game(s):return {k:v for k,v in s.items() if k!='display'}

# All species fit their original boxes, frame motion changes real page pixels.
animated=[]
for sid in range(1,152):
 r=Renderer(exe)
 try:
  base=command(r,f'boot 5 {sid} 30 19 1 7 0')
  roi=crop(base,120,64,112,112); varied=False
  for _ in range(24):
   frame=command(r,'tick 80')
   varied |= crop(frame,120,64,112,112)!=roi
   # Everything outside the sprite rectangle stays exactly still.
   assert crop(frame,0,0,240,64)==crop(base,0,0,240,64)
   assert crop(frame,0,64,120,112)==crop(base,0,64,120,112)
   assert crop(frame,232,64,8,112)==crop(base,232,64,8,112)
   assert crop(frame,0,176,240,144)==crop(base,0,176,240,144)
   if sid==25 and _ in (0,3,7,11,15): (OUT/f'care-{_}.png').write_bytes(png(frame))
  if varied:animated.append(sid)
 finally:r.close()
assert len(animated)==151,('missing original idle motions',set(range(1,152))-set(animated))

r=Renderer(exe)
try:
 command(r,'boot 12 25 30 19 1 7 0')
 for sid in (1,4,7,133,149):command(r,f'party_add {sid} 30 85 500 0')
 command(r,'tick 80')
 for selected in range(6):
  base=command(r,'tick 0');moving=False
  for i in range(12):
   frame=command(r,'tick 80')
   for row in range(6):
    region=(22,36+row*36,36,36)
    if row==selected:moving |= crop(base,*region)!=crop(frame,*region)
    else:assert crop(base,*region)==crop(frame,*region),('unselected member moved',selected,row)
   if selected==0 and i in (0,3,7,11):(OUT/f'party-{i}.png').write_bytes(png(frame))
  assert moving,('selected member did not sway',selected)
  command(r,'key 1 1')
 # Entire C wake hold is swallowed, including its classified LONG.
 before=game(r.inspect()); command(r,'key 2 3');assert r.inspect()['display']['off']
 command(r,'key 2 0');command(r,'tick 1600');command(r,'key 2 3');command(r,'key 2 4');command(r,'key 2 5')
 assert not r.inspect()['display']['off'] and game(r.inspect())==before
 command(r,'key 2 3');assert r.inspect()['display']['off']
 command(r,'tick 60000');assert r.inspect()['display']['off']
 command(r,'key 0 1');assert game(r.inspect())==before
 # Repeated exits must release timers instead of exhausting the timer pool.
 for _ in range(24):command(r,'page 5');command(r,'tick 80');command(r,'page 12');command(r,'tick 80')
 command(r,'key 1 2');command(r,'tick 59900');assert not r.inspect()['display']['off']
 command(r,'tick 200');assert r.inspect()['display']['off'],'idle motion must not inhibit 60s timeout'
finally:r.close()

r=Renderer(exe)
try:
 command(r,'boot 3 25 30 19 1 7 0')
 for _ in range(100):
  if r.inspect()['presentation']['phase']=='choice':break
  command(r,'tick 60')
 before=game(r.inspect());command(r,'key 2 3')
 assert r.inspect()['display']['off'] and game(r.inspect())==before,'C-long escaped battle'
 command(r,'key 2 3');assert game(r.inspect())==before,'semantic wake must only wake'
finally:r.close()

# Independent properties for new masks, and consecutive encounters vary without RNG.
probe=r'''
#include <assert.h>
#include "transition.h"
int main(void) {
 unsigned seen=0;
 for(unsigned uid=0;uid<256;uid++) {
  trans_id_t a=trans_pick_encounter(uid,0,0),b=trans_pick_encounter(uid+1,0,0);
  assert(a!=b && a==trans_pick_encounter(uid,0,0));seen|=1u<<a;
 }
 assert(__builtin_popcount(seen)==8);
 for(int id=TRANS_WAVE;id<=TRANS_SPECKLE;id++) {
  assert(trans_frames(id)>0 && !trans_has_flash(id));
  for(unsigned y=0;y<40;y++)for(unsigned x=0;x<30;x++) {
   assert(!trans_tile_covered(id,0,x,y));assert(trans_tile_covered(id,1000,x,y));
   int covered=0;
   for(unsigned q=0;q<=1000;q+=10) {int next=trans_tile_covered(id,q,x,y);assert(next>=covered);covered=next;}
  }
 }
 unsigned count=0,different=0;
 for(unsigned y=0;y<40;y++)for(unsigned x=0;x<30;x++) {
  count+=trans_tile_covered(TRANS_SPECKLE,500,x,y);
  different+=trans_tile_covered(TRANS_SPECKLE,500,x,y)!=trans_tile_covered(TRANS_WAVE,500,x,y);
 }
 assert(count==600 && different>300);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'probe.c').write_text(probe)
 subprocess.run(['cc','-std=c11','-fsanitize=address,undefined','-I',str(ROOT/'firmware/main'),str(p/'probe.c'),str(ROOT/'firmware/main/transition.c'),'-o',str(p/'probe')],check=True)
 subprocess.run([str(p/'probe')],check=True)
report={'build':exe.parent.name,'care_species_animated':len(animated),'selected_party_slots':6,'dirty_full_checks':checks,'C_long_battle_no_escape':True,'wake_hold_consumed':True,'idle_animation_allows_sleep':True,'transition_variants':8,'new_masks_monotonic_complete':True}
(OUT/'motion.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(report,ensure_ascii=False))
