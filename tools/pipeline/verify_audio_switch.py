#!/usr/bin/env python3
"""Run the real sound worker through capture gaps, mute, sleep and quiet expiry."""
from pathlib import Path
import subprocess, tempfile
import verify_silent_boot as base
ROOT=base.ROOT
assert 'CONFIG_I2S_ISR_IRAM_SAFE=y' in (ROOT/'firmware/sdkconfig.defaults').read_text()
# ISR latency through real flash erases is verified on hardware, not this stub.
C=r'''
#include "platform.h"
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
#include "sfx.c"
static jmp_buf done;
static uint64_t clock_us;
static unsigned event, opens, closes, blocks, writes, pending_count;
static bool muted, sleeping, codec_open;
static request_t pending[8];
static unsigned open_at[8], close_at[8];
static const unsigned times[]={0,200,6268,7285,8301,9317,11500,12500,13000,13500,14500,23500,33000};
static void dispatch(void) {
 while(event<sizeof(times)/sizeof(times[0])&&clock_us/1000>=times[event]) {
  unsigned n=event++;
  switch(n) {
   case 0:sfx_music_play(MUSIC_WILD);break;
   case 1:sfx_music_play(MUSIC_NONE);sfx_play(SFX_BALL_THROW);break;
   case 2:case 3:case 4:sfx_play(SFX_MENU);break;
   case 5:sfx_music_play(MUSIC_CAUGHT);break;
   case 6:muted=true;sfx_notify_state();break;
   case 7:muted=false;sfx_notify_state();break;
   case 8:sleeping=true;sfx_notify_state();break;
   case 9:sleeping=false;sfx_notify_state();break;
   case 10:sfx_music_play(MUSIC_NONE);break;
   case 11:sfx_encounter(1,false);break;
   case 12:longjmp(done,1);
  }
 }
}
int64_t esp_timer_get_time(void){return clock_us;}
void *xQueueCreate(unsigned n,unsigned size){assert(n==8&&size==sizeof(request_t));return (void*)1;}
int xQueueSend(void *q,const void *p,unsigned wait){(void)q;(void)wait;assert(pending_count<8);pending[pending_count++]=*(const request_t*)p;return pdTRUE;}
int xQueueReceive(void *q,void *p,unsigned wait){(void)q;(void)wait;dispatch();if(!pending_count)return 0;*(request_t*)p=pending[0];memmove(pending,pending+1,--pending_count*sizeof(*pending));return pdTRUE;}
int xQueuePeek(void *q,void *p,unsigned wait){(void)q;(void)p;assert(wait==portMAX_DELAY);blocks++;if(!pending_count){clock_us=(uint64_t)times[event]*1000;dispatch();}return pdTRUE;}
void vQueueDelete(void *q){(void)q;}
int xTaskCreate(void (*f)(void*),const char*n,unsigned stack,void*a,unsigned prio,void*h){(void)f;(void)n;(void)a;(void)h;assert(stack==4096&&prio==5);return pdPASS;}
void vTaskDelay(unsigned ticks){clock_us+=ticks*1000;dispatch();}
bool audio_settings_muted(void){return muted;}
uint8_t audio_settings_volume(void){return 55;}
bool screen_idle_is_off(void){return sleeping;}
esp_err_t bsp_audio_init(void){return ESP_OK;}
esp_err_t bsp_audio_set_format(uint32_t hz,uint8_t bits,uint8_t channels){assert(!codec_open&&hz==22050&&bits==16&&channels==1);assert(opens<8);open_at[opens++]=clock_us/1000;codec_open=true;return ESP_OK;}
void bsp_audio_set_volume(uint8_t v){assert(v==55);}
esp_err_t bsp_audio_suspend(void){assert(codec_open&&closes<8);close_at[closes++]=clock_us/1000;codec_open=false;return ESP_OK;}
esp_err_t bsp_audio_write(const void *p,size_t n){assert(codec_open&&p&&n==960);writes++;clock_us+=21769;return ESP_OK;}
int main(void){
 sfx_start();sfx_profile_reset();
 if(!setjmp(done))sfx_task(NULL);
 // One opening for the entire throw/shake/result sequence, then one per wake.
 assert(opens==4&&closes==4&&writes>300&&blocks>=3);
 assert(open_at[0]==0&&open_at[1]==12500&&open_at[2]==13500);
 assert(close_at[0]>=11500&&close_at[0]<11530);
 assert(close_at[1]>=13000&&close_at[1]<13030);
 assert(close_at[2]>=22450&&close_at[2]<22550);
 // A new encounter can wake an idle, music-free channel without a menu click.
 assert(open_at[3]==23500&&close_at[3]>31700&&close_at[3]<32500);
 sfx_profile_t stats=sfx_profile_read();assert(stats.opens==4&&stats.errors==0);
 printf("PASS: capture has no reopen; mute/sleep immediate; full 9.9s capture stays open; idle silence expires after 8s; %u chunks\n",writes);
}
'''
def main():
 with tempfile.TemporaryDirectory() as name:
  p=Path(name);(p/'platform.h').write_text(base.PLATFORM)
  for h in ('sdkconfig.h','esp_err.h','esp_log.h','esp_timer.h','freertos/FreeRTOS.h','freertos/queue.h','freertos/task.h'):
   f=p/h;f.parent.mkdir(exist_ok=True,parents=True);f.write_text('#include "platform.h"\n')
  (p/'test.c').write_text(C)
  subprocess.run(['cc','-std=c11','-O2','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DCONFIG_POKEWALK_SILENT_BOOT=0','-I',str(p),'-I',str(base.MAIN),'-I',str(base.BSP/'include'),str(p/'test.c'),*[str(base.MAIN/x) for x in ('audio.c','music.c','cry.c','sound_mixer.c')],'-o',str(p/'test')],check=True)
  subprocess.run([str(p/'test')],check=True,timeout=30)
  # The previous 2 s keepalive must fail this same full-length capture case.
  (p/'sfx.c').write_text((base.MAIN/'sfx.c').read_text().replace(
      '#define SFX_SILENCE_GRACE_MS 8000u', '#define SFX_SILENCE_GRACE_MS 2000u'))
  subprocess.run(['cc','-std=c11','-O2','-DCONFIG_POKEWALK_SILENT_BOOT=0',
      '-I',str(p),'-I',str(base.MAIN),'-I',str(base.BSP/'include'),str(p/'test.c'),
      *[str(base.MAIN/x) for x in ('audio.c','music.c','cry.c','sound_mixer.c')],
      '-o',str(p/'old-test')],check=True)
  old=subprocess.run([str(p/'old-test')],capture_output=True,text=True,timeout=30)
  assert old.returncode!=0 and 'opens==4' in old.stderr, old
  print('PASS: negative control rejects the old 2 s capture keepalive')
if __name__=='__main__':main()
