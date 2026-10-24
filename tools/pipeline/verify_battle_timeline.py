#!/usr/bin/env python3
"""Whole-turn timing contract, source ordering, cadence independence and mutations."""
import argparse, hashlib, json, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
MAIN=ROOT/'firmware/main'
p=argparse.ArgumentParser();p.add_argument('--gold-src',type=Path);args=p.parse_args()
C=r'''
#include <assert.h>
#include <stdio.h>
#include "presentation_clock.h"
#include "battle_timing.h"
static unsigned frames;
bool gold_fx_enabled(const battle_round_t *r){(void)r;return true;}
uint8_t battle_fx_hit_frame(const battle_round_t *r){(void)r;return frames;}
uint8_t battle_fx_frames(const battle_round_t *r){(void)r;return frames+14;}
int main(void){
 for(unsigned cadence=1;cadence<=240;cadence++){
  presentation_clock_t c;presentation_clock_start(&c,0xfffffff0u);
  for(unsigned ms=cadence;ms<=12000;ms+=cadence)
   assert(presentation_clock_sample(&c,0xfffffff0u+ms,false)==ms);
  unsigned old=c.elapsed_ms,last=c.last_ms;
  assert(presentation_clock_sample(&c,last+1000,true)==old);
  assert(presentation_clock_sample(&c,last+6000,true)==old);
  assert(presentation_clock_sample(&c,last+6045,false)==old);
  assert(presentation_clock_sample(&c,last+6090,false)==old+45);
  presentation_clock_start(&c,last+9000);assert(c.elapsed_ms==0);
 }
 unsigned side,miss,a,b,max,other;
 while(scanf("%u %u %u %u %u %u %u",&frames,&side,&miss,&a,&b,&max,&other)==7){
  battle_round_t r={.move_id=33,.by_pet=side,.damage=a-b,.missed=miss};
  uint16_t before[2]={a,a},after[2]={a,a},maximum[2]={max,max};
  after[side?1:0]=b;after[side?0:1]=other;
  battle_timing_t p=battle_timing_plan(&r,before,after,maximum);
  printf("%lu %lu %lu %lu %lu %lu %lu %lu\n",(unsigned long)p.track_end,
   (unsigned long)p.hit_start,(unsigned long)p.hit_end,(unsigned long)p.hp_start[p.target],
   (unsigned long)p.hp_ms[p.target],(unsigned long)p.feedback_start,
   (unsigned long)p.faint_start,(unsigned long)p.end);
  for(unsigned ms=0;ms<=p.end;ms++){
   unsigned h=battle_timing_hp_frame(&p,ms,p.target);
   if(ms<=p.hp_start[p.target])assert(h==0);
   if(ms>=p.feedback_start && p.hp_ms[p.target])assert(h==12);
   if(ms<p.track_end)assert(battle_timing_visible(&p,ms,p.target));
   if(ms<p.faint_start)assert(battle_timing_phase(&p,ms)!=BATTLE_TIME_DONE);
  }
 }
}
'''
def motion(n):return (n*4+2)//3
def gb(n):return (n*70224000+4194303)//4194304
cases=json.loads((ROOT/'assets/gold_fx_sources.json').read_text())['cases']
commands=[];expected=[]
for case in cases:
 for side in (0,1):
  # Full loss, small chip, and sequential drain/recoil, all on real clip lengths.
  for before,after,maximum,other,miss in ((200,0,200,200,0),(200,170,400,200,0),(100,40,200,80,0),(100,100,200,100,1)):
   count=case['display_frames'];commands.append(f'{count} {side} {miss} {before} {after} {maximum} {other}\n')
   def hp(a,b):return 0 if a==b else motion(max(540,gb(2*abs(a*48//maximum-b*48//maximum))))
   track=801+count*60;hit=track+gb(5)
   hit_end=hit+(motion(gb(38 if side else 43)) if before!=after and not miss else 0)
   start=hit_end+gb(4);duration=hp(before,after);feedback=start+duration+hp(before,other)
   faint=feedback+900;end=faint+(motion(gb(14))+gb(60) if after==0 else 0)
   expected.append((track,hit,hit_end,start,duration,feedback,faint,end))
with tempfile.TemporaryDirectory() as td:
 d=Path(td);(d/'test.c').write_text(C)
 def run(clock=None,timing=None):
  (d/'presentation_clock.h').write_text(clock or (MAIN/'presentation_clock.h').read_text())
  (d/'battle_timing.h').write_text(timing or (MAIN/'battle_timing.h').read_text())
  subprocess.run(['cc','-std=c11','-O2','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(d),'-I',str(MAIN),str(d/'test.c'),'-o',str(d/'test')],check=True,capture_output=True)
  return subprocess.run([str(d/'test')],input=''.join(commands),text=True,capture_output=True)
 good=run();assert good.returncode==0,good.stderr
 assert [tuple(map(int,l.split())) for l in good.stdout.splitlines()]==expected
 # Executable negative controls: callback counting and HP concurrent with hit.
 clock=(MAIN/'presentation_clock.h').read_text().replace('c->elapsed_ms += delta','c->elapsed_ms += 45')
 assert run(clock=clock).returncode!=0
 timing=(MAIN/'battle_timing.h').read_text().replace('uint32_t cursor = p.hit_end + gb_frames_to_ms(4);','uint32_t cursor = p.hit_start;')
 bad=run(timing=timing)
 assert bad.returncode!=0 or [tuple(map(int,l.split())) for l in bad.stdout.splitlines()]!=expected
sources={}
if args.gold_src:
 for name in ('data/moves/effects.asm','data/moves/animations.asm','engine/battle/anim_hp_bar.asm','engine/battle/core.asm','engine/battle_anims/anim_commands.asm'):
  data=(args.gold_src/name).read_bytes();sources[name]=hashlib.sha256(data).hexdigest()
 effects=(args.gold_src/'data/moves/effects.asm').read_text().split('NormalHit:',1)[1].split('DoSleep:',1)[0]
 assert effects.index('moveanim')<effects.index('applydamage')<effects.index('criticaltext')<effects.index('checkfaint')
 anim=(args.gold_src/'data/moves/animations.asm').read_text()
 enemy=anim.split('BattleAnim_EnemyDamage:',1)[1].split('BattleAnim_EnemyStatDown:',1)[0]
 assert enemy.count('anim_wait 5')==2 and 'anim_loop 3' in enemy
 hp=(args.gold_src/'engine/battle/anim_hp_bar.asm').read_text().split('.finish\n',1)[1].split('ShortHPBar_CalcPixelFrame:',1)[0]
 assert hp.count('call DelayFrame')==2
print(json.dumps(dict(cases=len(expected),cadences=240,negative_controls=2,source_hashes=sources,passed=True)))
