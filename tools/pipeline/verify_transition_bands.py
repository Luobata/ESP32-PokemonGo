#!/usr/bin/env python3
"""Exercise the actual encounter mask against whole-screen tile decisions."""
from pathlib import Path
import subprocess,tempfile,json
ROOT=Path(__file__).resolve().parents[2]
source=(ROOT/'firmware/main/play_enc.c').read_text()
function=source.split('static void overlay_transition(int band_y)')[1].split('static void draw_band')[0]
function='static void overlay_transition(int band_y)'+function
prefix=r'''
#include <assert.h>
#include <stdlib.h>
#include <stdio.h>
#include "screen.h"
#include "transition.h"
#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define C_BLACK 0
static uint16_t *pixels;
uint16_t *screen_band(void){return pixels;}
static trans_id_t s_trans_id;
static unsigned s_trans_q;
'''
suffix=r'''
int main(void){
 pixels=malloc(SCREEN_W*SCREEN_BAND_H*sizeof(*pixels));assert(pixels);unsigned checks=0;
 for(s_trans_id=0;s_trans_id<TRANS_COUNT;s_trans_id++)for(unsigned frame=0;frame<=trans_frames(s_trans_id);frame++){
  s_trans_q=frame*1000/trans_frames(s_trans_id);
  for(unsigned band=0;band<SCREEN_H;band+=SCREEN_BAND_H){
   for(unsigned i=0;i<SCREEN_W*SCREEN_BAND_H;i++)pixels[i]=0xffff;
   overlay_transition(band);
   for(unsigned y=0;y<SCREEN_BAND_H;y++)for(unsigned x=0;x<SCREEN_W;x++)
    assert(pixels[y*SCREEN_W+x]==(trans_tile_covered(s_trans_id,s_trans_q,x/TRANS_TILE,(band+y)/TRANS_TILE)?0:0xffff));
   checks++;
  }
 }
 free(pixels);printf("{\"passed\":true,\"variants\":%u,\"band_checks\":%u,\"sanitizers\":\"ASan/UBSan fatal\"}\n",TRANS_COUNT,checks);
}
'''
with tempfile.TemporaryDirectory() as tmp:
 tmp=Path(tmp)
 for negative in [False,True]:
  impl=function
  if negative:
   impl=impl.replace('(band_y + BAND_H + TRANS_TILE - 1) / TRANS_TILE','(band_y + BAND_H) / TRANS_TILE').replace('if ((unsigned)(y0 + dy) >= BAND_H) continue;','')
  src=tmp/('negative.c' if negative else 'fixed.c');src.write_text(prefix+impl+(suffix.replace('assert(pixels[y*SCREEN_W+x]', 'if(0)assert(pixels[y*SCREEN_W+x]') if negative else suffix))
  exe=src.with_suffix('')
  subprocess.run(['cc','-std=c11','-O1','-g','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(ROOT/'firmware/main'),str(src),str(ROOT/'firmware/main/transition.c'),'-o',str(exe)],check=True)
  run=subprocess.run([str(exe)],capture_output=True,text=True)
  if negative:
   assert run.returncode!=0 and 'AddressSanitizer' in run.stderr and ('heap-buffer-overflow' in run.stderr or 'WRITE memory access' in run.stderr),run.stderr
   # Ignore pixel differences only in the negative control to reach the real out-of-bounds write.
   result['negative_control_detected']=True
  else:
   assert run.returncode==0,run.stderr;result=json.loads(run.stdout)
 print(json.dumps(result))
