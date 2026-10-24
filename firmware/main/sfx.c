#include "sfx.h"
#include "sdkconfig.h"

#if CONFIG_POKEWALK_SILENT_BOOT

// Keep every gameplay, background and debug caller safe without creating a
// queue/task or touching the codec. Rebuilding with the option off restores SFX.
void sfx_start(void) {}
void sfx_notify_state(void) {}
void sfx_cry(uint16_t species) {(void)species;}
void sfx_encounter(uint8_t rarity, bool shiny) {(void)rarity;(void)shiny;}
void sfx_music_play(music_id_t id) { (void)id; }
void sfx_move(uint16_t id, uint8_t type, bool missed) { (void)id; (void)type; (void)missed; }
void sfx_play(sfx_id_t id) { (void)id; }
void sfx_profile_reset(void) {}
sfx_profile_t sfx_profile_read(void) { return (sfx_profile_t){0}; }

#else

#include <stdatomic.h>
#include "sound_mixer.h"
#include "audio_settings.h"
#include "screen_idle.h"
#include "bsp_audio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#define SFX_CHUNK_SAMPLES 480
#define SFX_SILENCE_GRACE_MS 8000u
static QueueHandle_t s_queue;
static atomic_uint s_music;
static atomic_uint s_alert;
static int16_t s_pcm[SFX_CHUNK_SAMPLES];
static sound_mixer_t s_mixer;
static sfx_profile_t s_profile;
static atomic_bool s_profile_reset;
static portMUX_TYPE s_profile_lock = portMUX_INITIALIZER_UNLOCKED;
void sfx_profile_reset(void) { atomic_store(&s_profile_reset, true); }
sfx_profile_t sfx_profile_read(void) {
 portENTER_CRITICAL(&s_profile_lock);
 sfx_profile_t result=s_profile;
 portEXIT_CRITICAL(&s_profile_lock);
 return result;
}
typedef struct { uint16_t id; uint8_t type, kind; bool missed; } request_t;

static void sfx_task(void *arg) {
 (void)arg;
 bool opened=false, notifying=false;
 int volume=-1;
 uint32_t previous_write=0, switch_chunks=0;
 uint32_t last_sound_ms=0;
 sound_mixer_init(&s_mixer);
 for(;;) {
  if(atomic_exchange(&s_profile_reset,false)) {
   portENTER_CRITICAL(&s_profile_lock);
   s_profile=(sfx_profile_t){0};
   portEXIT_CRITICAL(&s_profile_lock);
   previous_write=0;switch_chunks=0;
  }
  request_t request={0}, next;
  // Latest effect takes priority over stale menu clicks; queue cannot build an audio backlog.
  bool pending=false;
  while(xQueueReceive(s_queue,&next,0)==pdTRUE) {
   if(next.kind!=3) {request=next;pending=true;}
  }
  bool off=screen_idle_is_off();
  music_id_t requested=off?MUSIC_NONE:(music_id_t)atomic_load(&s_music);
  unsigned alert=0;
  if(notifying&&!s_mixer.active)notifying=false;
  if(!audio_settings_muted() && off && !notifying) {
   // Sleeping music is suspended, but an encounter may briefly open the codec.
   alert=atomic_exchange(&s_alert,0);
   s_mixer.active=false;
  }
  if(audio_settings_muted() || (off&&!notifying&&!alert)) {
   s_mixer.active=false;notifying=false;
   if(audio_settings_muted())atomic_store(&s_alert,0);
   if(opened) {
    if(bsp_audio_suspend()!=ESP_OK) {vTaskDelay(pdMS_TO_TICKS(250));continue;}
    opened=false;
   }
   // Peek preserves the event for the next loop and cannot lose an event
   // delivered between checking mute/sleep and blocking here.
   xQueuePeek(s_queue,&next,portMAX_DELAY);continue;
  }
  if(!alert && !pending && !s_mixer.active)alert=atomic_exchange(&s_alert,0);
  if(!opened) {
   // A short gap between throw/shake/result cues must not cycle the ES8311.
   // When already asleep, a NONE request alone must not open it either.
   if(requested==MUSIC_NONE&&!pending&&!alert&&!s_mixer.active) {
    xQueuePeek(s_queue,&next,portMAX_DELAY);continue;
   }
   if(bsp_audio_init()!=ESP_OK || bsp_audio_set_format(AUDIO_SAMPLE_RATE,16,1)!=ESP_OK) {
    vTaskDelay(pdMS_TO_TICKS(250));continue;
   }
   volume=-1;opened=true;previous_write=0;
   portENTER_CRITICAL(&s_profile_lock);s_profile.opens++;portEXIT_CRITICAL(&s_profile_lock);
  }
  if(volume!=audio_settings_volume()) {
   int desired=audio_settings_volume();
   bsp_audio_set_volume(desired);volume=desired;
  }
  if(pending && !off) {
   if(request.kind==2)sound_mixer_cry(&s_mixer,request.id);
   else if(request.kind==1)sound_mixer_move(&s_mixer,request.id,request.type,request.missed);
   else sound_mixer_effect(&s_mixer,(sfx_id_t)request.id);
  }
  if(alert){sound_mixer_effect(&s_mixer,audio_encounter_alert(alert==2?4:1,alert==3));notifying=true;}
  if(s_mixer.music.id!=requested) {
   switch_chunks=10;
   portENTER_CRITICAL(&s_profile_lock);s_profile.switches++;portEXIT_CRITICAL(&s_profile_lock);
  }
  sound_mixer_music(&s_mixer,requested);
  uint32_t now_ms=(uint32_t)(esp_timer_get_time()/1000);
  bool sounding=s_mixer.music.id!=MUSIC_NONE||s_mixer.active;
  if(sounding)last_sound_ms=now_ms;
  // The original capture script waits about 4.8 s before its first shake.
  // Keep that deliberate silence within one codec session; do not reopen it
  // between throw and shake. No additional audio buffer is allocated.
  // Feed silence through the existing DMA buffers during short scene pauses.
  // Mute/screen-off are handled above and bypass this grace period entirely.
  if(opened && (sounding||(!off&&now_ms-last_sound_ms<SFX_SILENCE_GRACE_MS))) {
   uint32_t start=(uint32_t)esp_timer_get_time();
   sound_mixer_render(&s_mixer,SFX_CHUNK_SAMPLES,s_pcm);
   uint32_t rendered=(uint32_t)esp_timer_get_time()-start;
   esp_err_t error=bsp_audio_write(s_pcm,sizeof(s_pcm));
   uint32_t now=(uint32_t)esp_timer_get_time(),gap=previous_write?now-previous_write:0;
   previous_write=now;
   portENTER_CRITICAL(&s_profile_lock);
   s_profile.chunks++;s_profile.render_us+=rendered;
   if(rendered>s_profile.render_max_us)s_profile.render_max_us=rendered;
   if(gap>s_profile.gap_max_us)s_profile.gap_max_us=gap;
   if(gap>2u*SFX_CHUNK_SAMPLES*1000000u/AUDIO_SAMPLE_RATE)s_profile.late_chunks++;
   if(switch_chunks&&rendered>s_profile.switch_render_max_us)s_profile.switch_render_max_us=rendered;
   if(error!=ESP_OK)s_profile.errors++;
   portEXIT_CRITICAL(&s_profile_lock);
   if(switch_chunks)switch_chunks--;
   if(error!=ESP_OK)vTaskDelay(pdMS_TO_TICKS(25));
  } else {
   if(bsp_audio_suspend()!=ESP_OK) {vTaskDelay(pdMS_TO_TICKS(250));continue;}
   opened=false;
   xQueuePeek(s_queue,&next,portMAX_DELAY);
  }
 }
}
void sfx_start(void) {
 if(s_queue)return;
 s_queue=xQueueCreate(8,sizeof(request_t));
 if(s_queue && xTaskCreate(sfx_task,"sound",4096,NULL,5,NULL)!=pdPASS) {vQueueDelete(s_queue);s_queue=NULL;}
}
void sfx_notify_state(void) {
 if(!s_queue)return;
 request_t request={.kind=3};
 xQueueSend(s_queue,&request,0); // A full queue already guarantees a wake.
}
void sfx_play(sfx_id_t id) {
 if((unsigned)id>=SFX_COUNT||!s_queue||audio_settings_muted()||screen_idle_is_off())return;
 request_t request={.id=id};xQueueSend(s_queue,&request,0);
}
void sfx_music_play(music_id_t id) { if((unsigned)id<MUSIC_COUNT){atomic_store(&s_music,id);sfx_notify_state();} }
void sfx_move(uint16_t id,uint8_t type,bool missed) {
 if(!s_queue||audio_settings_muted()||screen_idle_is_off())return;
 request_t request={.id=id,.type=type,.kind=1,.missed=missed};xQueueSend(s_queue,&request,0);
}
void sfx_cry(uint16_t species) {
 if(species>251||!s_queue||audio_settings_muted()||screen_idle_is_off())return;
 request_t request={.id=species,.kind=2};xQueueSend(s_queue,&request,0);
}
void sfx_encounter(uint8_t rarity,bool shiny) {
 if(!s_queue||audio_settings_muted())return;
 unsigned desired=shiny?3:rarity>=4?2:1,previous=atomic_load(&s_alert);
 while(previous<desired&&!atomic_compare_exchange_weak(&s_alert,&previous,desired)){}
 sfx_notify_state();
}
#endif
