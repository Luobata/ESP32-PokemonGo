#!/usr/bin/env python3
"""Check the shared GBC clock and source timelines, independent of LCD speed."""
import argparse,hashlib,json,subprocess,tempfile
from pathlib import Path
from fractions import Fraction
from pokemon_animation_oracle import original_ticks
ROOT=Path(__file__).resolve().parents[2]
C=r'''
#include <stdio.h>
#include <assert.h>
#include "pokemon_animation.h"
#include "gb_clock.h"
#include "battle_fx.h"
#include "battle_presentation.h"
const uint8_t *assets_front_sprite(uint16_t s,uint8_t *n){(void)s;(void)n;return NULL;}
int main(void){
 assert(BATTLE_PRESENTATION_HP_FRAMES*BATTLE_FX_TICK_MS==540);
 assert(BATTLE_FX_LEAD_MS==600+gb_frames_to_ms(12));
 assert(!battle_fx_elapsed_frame(0)&&!battle_fx_elapsed_frame(800)&&!battle_fx_elapsed_frame(860));
 assert(battle_fx_elapsed_frame(861)==1);
 assert(battle_fx_elapsed_frame(801+60*200)==200);
 unsigned sid,ms,slow;
 while(scanf("%u %u %u",&sid,&ms,&slow)==3){
  pokemon_anim_sample_t s=pokemon_anim_sample_mode(sid,ms,slow);
  printf("%u %u\n",s.frame,s.finished);
 }
}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--src',type=Path);args=p.parse_args()
 manifest=json.loads((ROOT/'assets/pokemon_animation_sources.json').read_text())
 commands=[];expected=[]
 for spec in manifest['species']:
  folder="unown_a" if spec["id"]==201 else spec["name"]
  path=f"gfx/pokemon/{folder}/anim.asm"
  if args.src:
   data=(args.src/path).read_bytes();assert hashlib.sha256(data).hexdigest()==manifest['inputs'][path]['sha256'];script=data.decode()
  else:script='\n'.join(' '.join(map(str,c)) for c in spec['commands'])
  for slow in (0,1):
   ticks=original_ticks(script,spec['frame_count'],4 if slow else 0)
   # Both sides of every original frame boundary, plus full-duration endpoints.
   samples={0,0xffffffff}
   for frame in range(len(ticks)+2):
    ms=-(-(frame*70224*1000)//4194304);samples.update((ms,max(ms-1,0)))
   for ms in sorted(samples):
    frame=int(Fraction(ms*4194304,70224*1000));finished=frame>=len(ticks)
    commands.append(f"{spec['id']} {ms} {slow}\n");expected.append((0 if finished else ticks[frame],int(finished)))
 with tempfile.TemporaryDirectory() as name:
  d=Path(name);(d/'test.c').write_text(C)
  subprocess.run(['cc','-O2','-std=c11','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(ROOT/'firmware/main'),str(d/'test.c'),str(ROOT/'firmware/main/pokemon_animation.c'),'-o',str(d/'test')],check=True)
  result=subprocess.run([str(d/'test')],input=''.join(commands),text=True,capture_output=True,check=True)
  actual=[tuple(map(int,line.split())) for line in result.stdout.splitlines()];assert actual==expected
 clips=json.loads((ROOT/'assets/gold_fx_sources.json').read_text());errors=[]
 for case in clips['cases']:
  error=case['display_frames']*45-Fraction(case['source_frames']*70224*1000,4194304)
  assert 0<=error<45,(case,float(error));errors.append(float(error))
 print(json.dumps(dict(species=len(manifest['species']),clock_samples=len(expected),original_scripts_verified=bool(args.src),move_clips=len(errors),max_resample_error_ms=max(errors),hp_ms=540,move_lead_ms=801,trainer_slow_mode=True)))
if __name__=='__main__':main()
