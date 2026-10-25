#include "field_adventure_core.h"
static unsigned field_signals_locked(void){return s_field_scan_us>=0&&esp_timer_get_time()-s_field_scan_us<90000000?s_w.last_ap_count:0;}
void world_field_snapshot(field_view_t *out){
 if(!out)return;
 memset(out,0,sizeof(*out));
 if(!s_lock)return;
 xSemaphoreTake(s_lock,portMAX_DELAY);refresh_clock_locked();
 out->state=s_field;out->online_s=s_refresh.online_s;out->scans=s_w.scans;out->place=s_field_place;
 out->signals=field_signals_locked();out->stamina=nurture_stamina_points(&s_w.pet);
 for(unsigned i=0;i<FIELD_MAP_COUNT;i++)if(field_map_open(&s_johto,i))out->open_maps|=1u<<i;
 xSemaphoreGive(s_lock);
}
static unsigned field_transaction(void){
 world_johto_result_t r=johto_transaction();
 return r==WORLD_JOHTO_OK?FIELD_OK:r==WORLD_JOHTO_BUSY?FIELD_BUSY:FIELD_SAVE_FAILED;
}
unsigned world_field_observe(unsigned map,unsigned point){
 unsigned r=field_transaction();if(r)return r;
 r=field_observe_apply(&s_save_buf,map,point);
 if(r||!memcmp(&s_field,&s_save_buf.field,sizeof(s_field))){unlock_encounter_change();return r;}
 return johto_commit(false,false,0)==WORLD_JOHTO_OK?FIELD_OK:FIELD_SAVE_FAILED;
}
unsigned world_field_search(unsigned mode,encounter_t *out){
 if(!out)return FIELD_LOCKED;
 unsigned r=field_transaction();if(r)return r;encounter_t e;
 r=field_search_apply(&s_save_buf,mode,field_signals_locked(),s_field_place,(uint32_t)esp_timer_get_time(),&e);
 if(r){unlock_encounter_change();return r;}
 if(johto_commit(false,true,FIELD_COST*NURT_Q)!=WORLD_JOHTO_OK)return FIELD_SAVE_FAILED;
 *out=e;sfx_encounter(e.rarity,e.is_shiny);return FIELD_OK;
}
