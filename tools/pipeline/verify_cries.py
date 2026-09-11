#!/usr/bin/env python3
"""All species: bounded PCM, duration, chunk invariance, cancellation; no speaker output."""
from pathlib import Path
import subprocess,tempfile,json
ROOT=Path(__file__).resolve().parents[2]
C=r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sound_mixer.h"
static int16_t a[220500],b[220500];
int main(void){
 unsigned shortest=99999,longest=0;unsigned long long hashes[152]={0};
 for(unsigned id=1;id<=151;id++){
  cry_player_t p;cry_start(&p,id);unsigned n=0,nonzero=0;int16_t x;
  while(cry_sample(&p,&x)){assert(++n<220500);assert(abs(x)<=8100);nonzero+=x!=0;hashes[id]=hashes[id]*31+(uint16_t)x;}
  unsigned ms=cry_duration_ms(id);assert(abs((int)(n*1000/22050)-(int)ms)<=3);assert(nonzero>100);
  if(ms<shortest)shortest=ms;if(ms>longest)longest=ms;
  sound_mixer_t m,k;sound_mixer_init(&m);sound_mixer_music(&m,MUSIC_EVOLUTION);sound_mixer_cry(&m,id);k=m;
  sound_mixer_render(&m,n+100,a);
  for(unsigned off=0;off<n+100;){unsigned size=n+100-off;if(size>113)size=113;sound_mixer_render(&k,size,b+off);off+=size;}
  assert(!memcmp(a,b,(n+100)*2));assert(!m.active&&!k.active);
  sound_mixer_cry(&m,id);sound_mixer_cry(&m,0);assert(!m.active);
 }
 assert(hashes[1]!=hashes[2]&&hashes[2]!=hashes[3]&&hashes[25]!=hashes[26]);
 assert(!cry_duration_ms(0)&&!cry_duration_ms(152));
 printf("{\"species\":151,\"shortest_ms\":%u,\"longest_ms\":%u,\"chunk_invariant\":true,\"sanitized\":true}\n",shortest,longest);
}
'''
with tempfile.TemporaryDirectory() as d:
 t=Path(d);(t/'test.c').write_text(C)
 subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'firmware/main'),str(t/'test.c')]+[str(ROOT/'firmware/main'/x) for x in ('cry.c','sound_mixer.c','music.c','audio.c')]+['-o',str(t/'test')],check=True)
 r=subprocess.run([str(t/'test')],capture_output=True,text=True,check=True);print(r.stdout,end='')
 out=ROOT/'reports/evidence/evolution-scene-2026-09-11/cry-audio.json';out.write_text(r.stdout)
