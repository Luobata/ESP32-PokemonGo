static void narrative_context_locked(narrative_context_t *c){
 *c=(narrative_context_t){.state=s_narrative,.chapter=s_johto,.story=s_story,
  .defeated=s_challenge.defeated,.bug_completed=s_activities.bug_completed,
  .feather=s_activities.silver_feather,.lake=s_endgame.lake_stage,
  .activity=s_activities.run.kind,.battle=s_challenge.session.active||s_active.encounter.uid,
  .dungeon=dungeon_party_locked()};
}
static bool narrative_final_locked(void){narrative_context_t c;narrative_context_locked(&c);return narrative_final(&c);}
void world_narrative_snapshot(narrative_context_t *c){
 memset(c,0,sizeof(*c));if(!s_lock||xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE)return;
 narrative_context_locked(c);xSemaphoreGive(s_lock);
}
unsigned world_narrative_update(unsigned scene,unsigned page,unsigned answer,bool begin){
 world_johto_result_t r=johto_transaction();if(r)return r==WORLD_JOHTO_BUSY?N_BUSY:N_SAVE_FAILED;
 narrative_context_t c;narrative_context_locked(&c);
 unsigned result=begin?narrative_begin(&c,scene):narrative_advance(&c,scene,page,answer);
 if(result){unlock_encounter_change();return result;}
 if(!memcmp(&s_narrative,&c.state,sizeof(c.state))){unlock_encounter_change();return N_OK;}
 s_save_buf.narrative=c.state;
 return johto_commit(false,false,0)==WORLD_JOHTO_OK?N_OK:N_SAVE_FAILED;
}
