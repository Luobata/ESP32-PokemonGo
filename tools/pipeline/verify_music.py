#!/usr/bin/env python3
"""Offline PCM verification: no speaker, browser AudioContext, or hardware access."""
from pathlib import Path
import subprocess,tempfile,json
ROOT=Path(__file__).resolve().parents[2]
C=r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sound_mixer.h"
static int16_t whole[22050],pieces[22050];
int main(void){
 unsigned peak=0;unsigned long long energy=0;
 assert(audio_note_hz_q8(69)>=439*256&&audio_note_hz_q8(69)<=441*256);
 for(unsigned id=1;id<MUSIC_COUNT;id++){
  sound_mixer_t a,b;sound_mixer_init(&a);sound_mixer_music(&a,id);b=a;
  for(unsigned second=0;second<130;second++){
   if(second==5){sound_mixer_move(&a,85,3,false);sound_mixer_move(&b,85,3,false);}
   if(second==8){sound_mixer_effect(&a,SFX_CAUGHT);sound_mixer_effect(&b,SFX_CAUGHT);}
   sound_mixer_render(&a,22050,whole);
   unsigned offset=0;
   while(offset<22050){unsigned n=113;if(offset+n>22050)n=22050-offset;sound_mixer_render(&b,n,pieces+offset);offset+=n;}
   assert(!memcmp(whole,pieces,sizeof(whole))&&!memcmp(&a,&b,sizeof(a)));
   for(unsigned i=0;i<22050;i++){unsigned x=abs(whole[i]);assert(x<24000);if(x>peak)peak=x;energy+=x;}
   if(second==0){music_player_t before=a.music;sound_mixer_music(&a,id);assert(!memcmp(&before,&a.music,sizeof(before)));}
  }
 }
 sound_mixer_t m;sound_mixer_init(&m);sound_mixer_render(&m,22050,whole);for(unsigned i=0;i<22050;i++)assert(!whole[i]);
 for(unsigned type=0;type<15;type++){sound_mixer_move(&m,85,type,false);sound_mixer_render(&m,22050,whole);unsigned nonzero=0;for(unsigned i=0;i<22050;i++)nonzero+=whole[i]!=0;assert(nonzero>1000&&!m.active);}
 assert(energy);printf("{\"tracks\":%u,\"seconds_per_track\":130,\"peak\":%u,\"energy\":%llu,\"chunk_invariant\":true,\"sanitized\":true}\n",MUSIC_COUNT-1,peak,energy);
}
'''
def main():
 with tempfile.TemporaryDirectory() as folder:
  t=Path(folder);(t/'probe.c').write_text(C)
  command=['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'firmware/main'),str(t/'probe.c')]+[str(ROOT/'firmware/main'/n) for n in ('music.c','sound_mixer.c','cry.c','audio.c')]+['-o',str(t/'probe')]
  r=subprocess.run(command,capture_output=True,text=True);assert not r.returncode,r.stderr
  r=subprocess.run([str(t/'probe')],capture_output=True,text=True,timeout=60);assert not r.returncode,r.stdout+r.stderr;print(r.stdout)
if __name__=='__main__':main()
