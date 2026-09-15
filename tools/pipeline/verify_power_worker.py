#!/usr/bin/env python3
"""Run the real sound task on a pthread queue: blocking, alerts and state changes."""
import json,subprocess,tempfile
from pathlib import Path
import verify_silent_boot as base
C=r'''
#include "platform.h"
#include "sfx.h"
#include "sound_mixer.h"
#include "scan_pacing.h"
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
static pthread_mutex_t mu=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cond=PTHREAD_COND_INITIALIZER;
static unsigned char queue[8][32];static unsigned qn,qbytes;
static atomic_bool muted=true,off,opened,waiting;
static atomic_uint opens,closes,writes,effects,cries,moves;
static void (*worker)(void*);
static void *entry(void*x){(void)x;worker(NULL);return NULL;}
static void pause_ms(unsigned n){struct timespec t={n/1000,(n%1000)*1000000};nanosleep(&t,NULL);}
void *xQueueCreate(unsigned n,unsigned bytes){assert(n==8&&bytes<=32);qbytes=bytes;return queue;}
int xQueueSend(void*q,const void*x,unsigned t){(void)q;(void)t;pthread_mutex_lock(&mu);int ok=qn<8;if(ok)memcpy(queue[qn++],x,qbytes);pthread_cond_signal(&cond);pthread_mutex_unlock(&mu);return ok;}
int xQueueReceive(void*q,void*x,unsigned t){(void)q;(void)t;pthread_mutex_lock(&mu);int ok=qn>0;if(ok){memcpy(x,queue[0],qbytes);memmove(queue,queue+1,--qn*32);}pthread_mutex_unlock(&mu);return ok;}
int xQueuePeek(void*q,void*x,unsigned t){(void)q;assert(t==portMAX_DELAY);pthread_mutex_lock(&mu);while(!qn){waiting=true;pthread_cond_wait(&cond,&mu);}waiting=false;memcpy(x,queue[0],qbytes);pthread_mutex_unlock(&mu);return 1;}
void vQueueDelete(void*q){(void)q;}
int xTaskCreate(void(*f)(void*),const char*n,unsigned st,void*a,unsigned pr,void*h){(void)n;(void)st;(void)a;(void)pr;(void)h;pthread_t t;worker=f;assert(!pthread_create(&t,NULL,entry,NULL));pthread_detach(t);return pdPASS;}
void vTaskDelay(unsigned n){pause_ms(n);}
bool audio_settings_muted(void){return muted;}
uint8_t audio_settings_volume(void){return 55;}
bool screen_idle_is_off(void){return off;}
int bsp_audio_init(void){return 0;}
int bsp_audio_set_format(uint32_t hz,uint8_t b,uint8_t c){(void)hz;(void)b;(void)c;opened=true;opens++;return 0;}
int bsp_audio_suspend(void){opened=false;closes++;return 0;}
void bsp_audio_set_volume(uint8_t p){(void)p;}
int bsp_audio_write(const void*p,size_t n){(void)p;(void)n;assert(opened);writes++;pause_ms(1);return 0;}
void sound_mixer_init(sound_mixer_t*m){memset(m,0,sizeof(*m));}
void sound_mixer_effect(sound_mixer_t*m,sfx_id_t id){(void)id;effects++;m->active=true;}
void sound_mixer_cry(sound_mixer_t*m,uint16_t id){(void)id;cries++;m->active=true;}
void sound_mixer_move(sound_mixer_t*m,uint16_t id,uint8_t t,bool miss){(void)id;(void)t;(void)miss;moves++;m->active=true;}
void sound_mixer_music(sound_mixer_t*m,music_id_t id){m->music.id=id;}
void sound_mixer_render(sound_mixer_t*m,uint32_t n,int16_t*out){memset(out,0,n*2);m->active=false;}
sfx_id_t audio_encounter_alert(uint8_t r,bool s){return s?SFX_SHINY:r>=4?SFX_RARE:SFX_ENCOUNTER;}
static void wait_idle(void){for(int i=0;i<1000;i++){if(waiting&&!opened)return;pause_ms(1);}assert(!"sound worker did not block");}
static void wait_writes(unsigned n){for(int i=0;i<1000;i++){if(writes>n)return;pause_ms(1);}assert(!"lost wake event");}
int main(void){
 sfx_start();wait_idle();assert(!opens);unsigned n=writes;pause_ms(50);assert(writes==n);
 muted=false;sfx_music_play((music_id_t)1);wait_writes(n);
 for(int i=0;i<10;i++){
  off=true;sfx_notify_state();wait_idle();n=writes;pause_ms(5);assert(writes==n);
  unsigned prior=effects;sfx_encounter(5,true);wait_writes(n);wait_idle();assert(effects>prior);
  off=false;sfx_notify_state();wait_writes(writes);
  muted=true;sfx_notify_state();wait_idle();n=writes;sfx_encounter(5,true);pause_ms(5);assert(writes==n);
  muted=false;sfx_notify_state();wait_writes(n);
 }
 sfx_music_play(MUSIC_NONE);wait_idle();n=writes;sfx_cry(25);wait_writes(n);wait_idle();assert(cries==1);
 n=writes;sfx_move(57,2,false);wait_writes(n);wait_idle();assert(moves==1);
 scan_pacing_t p={0};assert(scan_pacing_next(&p,true,true)==30000);assert(scan_pacing_next(&p,true,true)==30000);assert(scan_pacing_next(&p,true,true)==60000);
 for(int i=0;i<500;i++)assert(scan_pacing_next(&p,true,true)==60000);
 assert(scan_pacing_next(&p,true,false)==30000&&!p.stable);p.stable=3;assert(scan_pacing_next(&p,false,true)==30000&&!p.stable);
 puts("{\"sound_cycles\":10,\"blocks_while_idle\":true,\"screen_off_alert_resleeps\":true,\"mute_wake\":true,\"move_cry_wake\":true,\"scan_backoff_cap_ms\":60000}");
}
'''
with tempfile.TemporaryDirectory(prefix='pw-worker-') as d:
 p=Path(d);(p/'platform.h').write_text(base.PLATFORM)
 for n in ['sdkconfig.h','esp_log.h','esp_err.h','freertos/FreeRTOS.h','freertos/queue.h','freertos/task.h']:
  f=p/n;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('#include "platform.h"\n')
 (p/'probe.c').write_text(C)
 r=subprocess.run(['cc','-std=c11','-D_POSIX_C_SOURCE=200809L','-pthread','-fsanitize=address,undefined','-I',str(p),'-I',str(base.BSP/'include'),'-I',str(base.MAIN),str(base.MAIN/'sfx.c'),str(p/'probe.c'),'-o',str(p/'probe')],capture_output=True,text=True);assert r.returncode==0,r.stderr
 r=subprocess.run([str(p/'probe')],capture_output=True,text=True,timeout=15);assert r.returncode==0,r.stderr;print(json.dumps(json.loads(r.stdout),indent=2))
