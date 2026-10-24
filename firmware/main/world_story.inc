void world_story_snapshot(johto_story_t *out){memset(out,0,sizeof(*out));if(s_lock&&xSemaphoreTake(s_lock,portMAX_DELAY)==pdTRUE){*out=s_story;xSemaphoreGive(s_lock);}}
bool world_johto_final_available(void){
 if(!s_lock||xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE)return false;
 bool open=narrative_final_locked();
 xSemaphoreGive(s_lock);return open;
}
activity_result_t world_story_action(const story_request_t *q,story_result_t *out){
 if(!q||!out||!lock_encounter_change())return ACT_SAVE_FAILED;
 if(!s_storage_ready||s_starter_pending){unlock_encounter_change();return ACT_SAVE_FAILED;}
 if(s_active.encounter.uid||s_challenge.session.active||s_challenge.league_active||dungeon_party_locked()){unlock_encounter_change();return ACT_BUSY;}
 collect_save_locked(&s_save_buf);activity_result_t result=story_apply(&s_save_buf,q,out);
 if(result!=ACT_OK){unlock_encounter_change();return result;}
 int32_t debit=s_w.pet.stamina-s_save_buf.pet.stamina;
 xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
 if(ok){s_narrative=s_save_buf.narrative;s_story=s_save_buf.story;s_endgame=s_save_buf.endgame;s_johto=s_save_buf.johto;s_inventory=s_save_buf.inventory;s_party=s_save_buf.members;s_dex=s_save_buf.dex;s_queue=s_save_buf.queue;s_w.pending=s_queue.count;
  s_w.pet.stamina=s_w.pet.stamina>debit?s_w.pet.stamina-debit:0;s_last_save_us=esp_timer_get_time();}
 unlock_encounter_change();return ok?ACT_OK:ACT_SAVE_FAILED;
}

bool world_story_feather(void){if(!s_lock||xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE)return false;bool value=s_activities.silver_feather;xSemaphoreGive(s_lock);return value;}
const char *world_story_legend_hint(unsigned id){if(!s_lock||xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE)return "正在读取调查";const char *s=johto_story_legend_hint(&s_story,&s_johto,id,s_activities.silver_feather);xSemaphoreGive(s_lock);return s;}

bool world_story_kanto_ready(void){if(!s_lock||xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE)return false;bool value=(s_challenge.defeated&0x20ff)==0x20ff;xSemaphoreGive(s_lock);return value;}

void world_endgame_snapshot(endgame_t *out){memset(out,0,sizeof(*out));if(s_lock&&xSemaphoreTake(s_lock,portMAX_DELAY)==pdTRUE){*out=s_endgame;xSemaphoreGive(s_lock);}}
