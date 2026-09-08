#!/usr/bin/env python3
"""Real NVS preference implementation: defaults, restart, invalid data and failed commits."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
STUB='''#include <stdint.h>
typedef int esp_err_t;typedef int nvs_handle_t;
#define ESP_OK 0
#define NVS_READONLY 0
#define NVS_READWRITE 1
int nvs_open(const char*,int,int*);int nvs_get_u8(int,const char*,uint8_t*);int nvs_set_u8(int,const char*,uint8_t);int nvs_commit(int);void nvs_close(int);
'''
C=r'''
#include "nvs.h"
#include "audio_settings.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int disk[2]={-1,-1},stage[2],fail,writes;
static unsigned key(const char *k){assert(!strcmp(k,"mute")||!strcmp(k,"volume"));return !strcmp(k,"volume");}
int nvs_open(const char*n,int m,int*h){assert(!strcmp(n,"pokewalk"));(void)m;*h=1;memcpy(stage,disk,sizeof(stage));return fail==1?-1:0;}
int nvs_get_u8(int h,const char*k,uint8_t*v){(void)h;int value=disk[key(k)];if(value<0||fail==4)return -1;*v=value;return 0;}
int nvs_set_u8(int h,const char*k,uint8_t v){(void)h;writes++;if(fail==2)return -1;stage[key(k)]=v;return 0;}
int nvs_commit(int h){(void)h;if(fail==3)return -1;memcpy(disk,stage,sizeof(disk));return 0;}
void nvs_close(int h){(void)h;}
int main(void){
 audio_settings_init();assert(audio_settings_muted()&&audio_settings_volume()==55);
 assert(audio_settings_set_muted(true)&&audio_settings_set_volume(55)&&writes==0);
 for(fail=1;fail<=3;fail++){
  assert(!audio_settings_set_muted(false)&&!audio_settings_set_volume(100));
  assert(audio_settings_muted()&&audio_settings_volume()==55&&disk[0]==-1&&disk[1]==-1);
 }
 fail=0;assert(audio_settings_set_muted(false));assert(audio_settings_set_volume(100));
 audio_settings_init();assert(!audio_settings_muted()&&audio_settings_volume()==100);
 for(fail=1;fail<=3;fail++){assert(!audio_settings_set_volume(0)&&audio_settings_volume()==100);assert(!audio_settings_set_muted(true)&&!audio_settings_muted());}
 fail=0;assert(audio_settings_set_volume(0));audio_settings_init();assert(audio_settings_volume()==0&&!audio_settings_muted());
 assert(!audio_settings_set_volume(101)&&audio_settings_volume()==0);
 disk[0]=2;disk[1]=255;audio_settings_init();assert(audio_settings_muted()&&audio_settings_volume()==55);
 disk[0]=0;disk[1]=90;fail=4;audio_settings_init();assert(audio_settings_muted()&&audio_settings_volume()==55);
 puts("PASS: independent mute/volume persistence, 0-100 bounds, invalid defaults, every NVS failure preserves state");
}
'''
with tempfile.TemporaryDirectory() as d:
 t=Path(d);(t/'nvs.h').write_text(STUB);(t/'probe.c').write_text(C)
 c=subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(t),'-I',str(ROOT/'firmware/main'),str(ROOT/'firmware/main/audio_settings.c'),str(t/'probe.c'),'-o',str(t/'probe')],capture_output=True,text=True);assert not c.returncode,c.stderr
 c=subprocess.run([str(t/'probe')],capture_output=True,text=True);assert not c.returncode,c.stderr;print(c.stdout)
