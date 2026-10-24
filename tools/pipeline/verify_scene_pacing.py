#!/usr/bin/env python3
"""Check full capture orchestration, not just the move clip's resampling rate.
Optional --gold-src independently checks the pinned upstream script/VM inputs.
"""
import argparse,hashlib,json,re,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
COMMIT='656583c939d30f920a316177311a502dd222b57c'
p=argparse.ArgumentParser();p.add_argument('--gold-src',type=Path);a=p.parse_args()
# Each wait is dispatched once; CheckTimer then returns for N decrement ticks.
# The 4 checks produce 3 wobble cycles before the success/breakout result.
waits=[36,16,16,8,16,32,32,32,32,8,48,48,48,48]
clock=0;edges=[]
for duration in waits:
 clock+=1
 for _ in range(duration):clock+=1
 edges.append(clock)
assert edges==[37,54,71,80,97,130,163,196,229,238,287,336,385,434]
assert clock+3+33==470
s=(ROOT/'firmware/main/play_capture.c').read_text()
assert int(re.search(r'#define CAPTURE_REVEAL_FRAME (\d+)u',s)[1])==clock
assert int(re.search(r'#define CAPTURE_END_FRAME (\d+)u',s)[1])==clock+36
assert 's_anim_ms=ms' in s and 'presentation_clock_sample' in s
assert 'start_clock();' in s
assert 'capture_frame_ms(287+shake*49)' in s
# Execute the production phase map at every millisecond. This oracle keeps
# source timing separate from the explicit absorption/readability adaptation.
with tempfile.TemporaryDirectory() as d:
 test=Path(d)/'test.c';exe=Path(d)/'test'
 test.write_text(r'''#include <stdio.h>
#include "capture_presentation.h"
#include "battle_presentation.h"
int main(void){
 for(unsigned ms=0;ms<12000;ms++)printf("%u\n",capture_source_frame(ms));
 for(unsigned p=0;p<49;p++)printf("%d\n",capture_rock_tilt(p));
 for(unsigned p=0;p<500;p++)printf("%u\n",capture_frame_ms(p));
 printf("%u %u\n",BATTLE_PRESENTATION_SENDOUT_MOTION_MS,BATTLE_PRESENTATION_TURN_PAUSE_MS);
}''')
 subprocess.run(['cc','-std=c11','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(ROOT/'firmware/main'),str(test),'-o',str(exe)],check=True)
 lines=subprocess.check_output([str(exe)],text=True).splitlines()
 # Fixed source-motion boundaries, with independent per-source-frame arrival
 # times. Check the inverse at every ms using a search, not production's loop.
 from bisect import bisect_right
 def base(f):
  display=f if f<=71 else 71+((f-71)*22+8)//9 if f<80 else f+13
  return (display*70224000+4194303)//4194304
 def arrive(f):
  value=base(f)
  for a,b in ((0,37),(71,80),(97,225),(287,322),(336,371),(385,420),(434,470)):
   part=max(0,min(base(f),base(b))-base(a))
   value+=(part+2)//3
  return value
 arrivals=[arrive(f) for f in range(900)]
 assert [arrivals[f] for f in (37,71,80,97,225,287,322,336,385,434,470)]==[827,1396,1888,2172,5030,6068,6850,7085,8101,9117,9921]
 expected=[bisect_right(arrivals,ms)-1 for ms in range(12000)]
 assert list(map(int,lines[:12000]))==expected
 poses=[0,-2,-4,-2,0,2,4,2,0]
 actual=list(map(int,lines[12000:12049]))
 assert actual==[poses[p*8//35] if p<35 else 0 for p in range(49)]
 assert max(abs(a-b) for a,b in zip(actual,actual[1:]))==2
 for source,ms in enumerate(map(int,lines[12049:12549])):
  assert ms==arrivals[source]
 assert lines[-1]=='1980 900'
hashes={}
if a.gold_src:
 for f in ['data/moves/animations.asm','engine/battle_anims/anim_commands.asm']:
  t=(a.gold_src/f).read_bytes();hashes[f]=hashlib.sha256(t).hexdigest()
 script=(a.gold_src/'data/moves/animations.asm').read_text()
 ball=script.split('BattleAnim_ThrowPokeBall:\n',1)[1].split('BattleAnim_SendOutMon:',1)[0]
 normal=ball.split('.TheTrainerBlockedTheBall:',1)[0]
 shake=ball.split('.Shake:\n',1)[1].split('.Loop:',1)[0]
 loop=ball.split('.Loop:\n',1)[1].split('.Click:',1)[0]
 actual=lambda t:list(map(int,re.findall(r'anim_wait (\d+)',t)))
 assert actual(normal)+actual(shake)+actual(loop)*4==waits
 assert actual(ball.split('.BreakFree:\n',1)[1])==[2,32]
 vm=(a.gold_src/'engine/battle_anims/anim_commands.asm').read_text()
 assert re.search(r'RunBattleAnimCommand:\s+call \.CheckTimer\s+ret nc',vm)
 assert re.search(r'dec a\s+ld \[wBattleAnimDelay\], a\s+and a\s+ret',vm)
print(json.dumps(dict(commit=COMMIT,source_verified=bool(a.gold_src),source_hashes=hashes,
 capture_result_frames=434,capture_end_frames=470,source_result_ms=7267,source_end_ms=7870,result_ms=9117,end_ms=9921,absorption_ms=492,trainer_sendout_min_ms=3180,turn_pause_ms=900,display_quantum_ms=40)))
