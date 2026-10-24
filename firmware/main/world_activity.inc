void world_activity_snapshot(activity_store_t *out){memset(out,0,sizeof(*out));if(s_lock&&xSemaphoreTake(s_lock,portMAX_DELAY)==pdTRUE){*out=s_activities;xSemaphoreGive(s_lock);}}
activity_result_t world_activity_action(const activity_request_t *q,activity_result_data_t *out){
 if(!q||!out||!lock_encounter_change())return ACT_SAVE_FAILED;
 if(!s_storage_ready||s_starter_pending){unlock_encounter_change();return ACT_SAVE_FAILED;}
 if(s_active.encounter.uid||s_challenge.session.active||s_challenge.league_active||dungeon_party_locked()){unlock_encounter_change();return ACT_BUSY;}
 collect_save_locked(&s_save_buf);activity_result_t result=activity_apply(&s_save_buf,q,out);
 if(result!=ACT_OK){unlock_encounter_change();return result;}
 int32_t debit=s_w.pet.stamina-s_save_buf.pet.stamina;
 xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
 if(ok){
  s_narrative=s_save_buf.narrative;s_activities=s_save_buf.activities;s_inventory=s_save_buf.inventory;record_growth_locked(&s_save_buf.members);s_party=s_save_buf.members;
  s_w.level=s_save_buf.level;s_w.exp=s_save_buf.exp;s_w.pet.stamina=s_w.pet.stamina>debit?s_w.pet.stamina-debit:0;
  s_queue=s_save_buf.queue;s_dex=s_save_buf.dex;s_w.pending=s_queue.count;s_last_save_us=esp_timer_get_time();
 }
 unlock_encounter_change();return ok?ACT_OK:ACT_SAVE_FAILED;
}
