// Included by world.c. Uses the existing locked transaction workspace, never
// allocates a second world/party blob. Background saves share the save lock.
void world_johto_snapshot(johto_state_t *out) {
 if(!out)return;
 johto_init(out);
 if(s_lock&&xSemaphoreTake(s_lock,portMAX_DELAY)==pdTRUE){*out=s_johto;xSemaphoreGive(s_lock);}
}
bool world_johto_available(void) {
 if(!s_lock||xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE)return false;
 johto_state_t j=s_johto;uint16_t defeated=s_challenge.defeated;xSemaphoreGive(s_lock);
 return j.phase!=JOHTO_HIDDEN||johto_offer(&j,defeated);
}
static world_johto_result_t johto_transaction(void) {
 if(!lock_encounter_change())return WORLD_JOHTO_SAVE_FAILED;
 if(!s_storage_ready||s_starter_pending){unlock_encounter_change();return WORLD_JOHTO_SAVE_FAILED;}
 if(s_active.encounter.uid||s_challenge.session.active||s_challenge.league_active||dungeon_party_locked()||s_activities.run.kind){
  unlock_encounter_change();return WORLD_JOHTO_BUSY;
 }
 collect_save_locked(&s_save_buf);return WORLD_JOHTO_OK;
}
static world_johto_result_t johto_commit(bool received,bool discovery,unsigned debit) {
 xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
 if(ok){
  s_field=s_save_buf.field;s_narrative=s_save_buf.narrative;s_story=s_save_buf.story;s_johto=s_save_buf.johto;s_inventory=s_save_buf.inventory;
  s_w.pet.stamina=s_w.pet.stamina>(int32_t)debit?s_w.pet.stamina-debit:0;
  if(received)s_party=s_save_buf.members;
  if(received||discovery)s_dex=s_save_buf.dex;
  if(discovery){s_queue=s_save_buf.queue;s_w.pending=s_queue.count;prune_battles_locked();}
  s_last_save_us=esp_timer_get_time();
 }
 unlock_encounter_change();return ok?WORLD_JOHTO_OK:WORLD_JOHTO_SAVE_FAILED;
}
world_johto_result_t world_johto_visit(void) {
 world_johto_result_t r=johto_transaction();if(r)return r;
 if(s_johto.phase!=JOHTO_HIDDEN){unlock_encounter_change();return WORLD_JOHTO_OK;}
 if(!johto_offer(&s_save_buf.johto,s_challenge.defeated)){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
 return johto_commit(false,false,0);
}
world_johto_result_t world_johto_depart(void) {
 world_johto_result_t r=johto_transaction();if(r)return r;
 if(!johto_depart(&s_save_buf.johto)){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
 return johto_commit(false,false,0);
}
world_johto_result_t world_johto_starter(unsigned species) {
 world_johto_result_t r=johto_transaction();if(r)return r;
 if(!johto_choose_starter(&s_save_buf.johto,species)){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
 mon_t mon={.species_id=species,.level=35,.exp=exp_for_level(35),.hp=100,.nickname_idx=255};
 if(!party_receive(&s_save_buf.members,&mon)){unlock_encounter_change();return WORLD_JOHTO_FULL;}
 dex_mark_caught(&s_save_buf.dex,species,false);
 return johto_commit(true,false,0);
}
world_johto_result_t world_johto_egg(bool hatch) {
 world_johto_result_t r=johto_transaction();if(r)return r;
 if(hatch){
  if(s_save_buf.johto.egg_status!=JOHTO_EGG_READY){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
  bool shiny=johto_egg_shiny(&s_save_buf.johto);
  mon_t mon={.species_id=175,.level=5,.exp=exp_for_level(5),.hp=100,.nickname_idx=255,.flags=shiny?1:0};
  if(!party_receive(&s_save_buf.members,&mon)){unlock_encounter_change();return WORLD_JOHTO_FULL;}
  if(!johto_hatch(&s_save_buf.johto,true)){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
  dex_mark_caught(&s_save_buf.dex,175,shiny);
 }else if(!johto_receive_egg(&s_save_buf.johto,(uint32_t)esp_timer_get_time()^s_johto.explorations)){
  unlock_encounter_change();return WORLD_JOHTO_LOCKED;
 }
 return johto_commit(hatch,false,0);
}
static uint32_t johto_roll(uint32_t x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);}
static unsigned johto_rarity(unsigned species) {
 species_t sp;if(!assets_species(species,&sp))return 1;
 unsigned total=sp.hp+sp.attack+sp.defense+sp.special+sp.speed;
 return total<250?1:total<330?2:total<400?3:total<470?4:5;
}
static bool johto_wild_supported(unsigned species){return species!=201;}
static world_johto_result_t johto_discover(unsigned route,unsigned legendary,encounter_t *out) {
 if(!out)return WORLD_JOHTO_LOCKED;
 world_johto_result_t r=johto_transaction();if(r)return r;
 if(legendary<6&&s_narrative.legend){unlock_encounter_change();return WORLD_JOHTO_BUSY;}
 if(route>=JOHTO_ROUTE_COUNT||!johto_route_open(&s_johto,route)||(legendary<6&&!johto_story_legend_ready(&s_story,&s_johto,legendary,s_activities.silver_feather))){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
 unsigned cost=NURT_EXPLORE_COST*(legendary<6?2:1);
 if(s_w.pet.stamina<(int32_t)cost){unlock_encounter_change();return WORLD_JOHTO_NO_STAMINA;}
 if(legendary>=6&&(s_johto.last_action==UINT32_MAX||!johto_explore(&s_save_buf.johto,route,s_johto.last_action+1,true))){
  unlock_encounter_change();return WORLD_JOHTO_LOCKED;
 }
 if(legendary>=6)johto_story_explore(&s_save_buf.story,&s_save_buf.johto,route);
 else{s_save_buf.story.version=1;s_save_buf.story.legend_visits|=1u<<legendary;s_save_buf.story.legend_at[legendary]=s_johto.explorations;}
 uint32_t roll=johto_roll((uint32_t)esp_timer_get_time()^s_save_buf.johto.explorations*0x9e3779b9u);
 unsigned species=0;
 if(legendary<6)species=(unsigned[]){243,244,245,249,250,251}[legendary];
 else {
  const johto_route_t *map=&JOHTO_ROUTES[route];unsigned total=0;
  for(unsigned i=0;i<map->count;i++)if(johto_wild_supported(map->species[i]))total+=(unsigned[]){0,40,28,16,7,2}[johto_rarity(map->species[i])];
  unsigned choice=roll%total;
  for(unsigned i=0;i<map->count;i++)if(johto_wild_supported(map->species[i])){
   unsigned weight=(unsigned[]){0,40,28,16,7,2}[johto_rarity(map->species[i])];
   if(choice<weight){species=map->species[i];break;}choice-=weight;
  }
 }
 encounter_t e={.species_id=species,.rarity=legendary<6?5:johto_rarity(species),.hp_ratio=100,
  .level=johto_route_level(route,s_w.level,roll>>16),.activity=legendary<6?0:ENC_ACTIVITY_EXPLORATION,
  .ts=s_save_buf.johto.explorations,.is_shiny=enc_shiny_from_roll(johto_roll(roll^0x619ab3e5),legendary<6?SHINY_BADGE:SHINY_EXPLORATION)};
 enc_queue_push(&s_save_buf.queue,&e);e=s_save_buf.queue.items[s_save_buf.queue.count-1];
 if(legendary<6){s_save_buf.narrative.version=1;s_save_buf.narrative.legend=legendary+1;s_save_buf.narrative.pending=e;}
 dex_mark_seen(&s_save_buf.dex,e.species_id,e.is_shiny);
 exploration_event_t chain={.kind=EXPLORE_ENCOUNTER,.uid=e.uid,.species=e.species_id,.rarity=e.rarity,.shiny=e.is_shiny,.chain_roll=johto_roll(roll^0xab31e059)};
 if(legendary>=6)exploration_chain_discovery(&chain,&s_save_buf.queue,&s_save_buf.dex,s_save_buf.exploration_wins);
 e.is_shiny=chain.shiny;s_save_buf.pet.stamina-=cost;
 r=johto_commit(false,true,cost);if(r==WORLD_JOHTO_OK){*out=e;sfx_encounter(e.rarity,e.is_shiny);}return r;
}
world_johto_result_t world_johto_explore(unsigned route,encounter_t *out){return johto_discover(route,6,out);}
world_johto_result_t world_johto_legend(unsigned legend,encounter_t *out){
 if(legend>=6||!out)return WORLD_JOHTO_LOCKED;
 world_johto_result_t r=johto_transaction();if(r)return r;
 if(s_narrative.legend){
  if(s_narrative.legend!=legend+1){unlock_encounter_change();return WORLD_JOHTO_BUSY;}
  encounter_t e=s_narrative.pending;encounter_t *entry=enc_queue_find(&s_queue,e.uid);
  if(entry&&!memcmp(entry,&e,sizeof(e))){*out=e;unlock_encounter_change();return WORLD_JOHTO_OK;}
  // Restore the exact locked individual, never a reroll. push assigns a fresh
  // UID if the ordinary five-entry FIFO has since displaced the old one.
  enc_queue_push(&s_save_buf.queue,&e);e=s_save_buf.queue.items[s_save_buf.queue.count-1];s_save_buf.narrative.pending=e;
  r=johto_commit(false,true,0);if(!r)*out=e;return r;
 }
 unlock_encounter_change();
 return johto_discover((unsigned[]){4,4,6,6,7,1}[legend],legend,out);
}

void world_johto_reward_progress(uint16_t claimed[JOHTO_REWARD_COUNT]) {
 memset(claimed,0,sizeof(s_research_rewards));if(!s_lock)return;
 xSemaphoreTake(s_lock,portMAX_DELAY);memcpy(claimed,s_research_rewards,sizeof(s_research_rewards));xSemaphoreGive(s_lock);
}
world_johto_result_t world_johto_reward_claim(unsigned id) {
 if(id>=JOHTO_REWARD_COUNT)return WORLD_JOHTO_LOCKED;
 world_johto_result_t r=johto_transaction();if(r)return r;
 if(s_research_rewards[id]>=johto_reward_entitled(&s_johto,id)){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
 unsigned item=ITEM_SUN_STONE+id;
 if(s_inventory.quantity[item]>=items_capacity(item)){unlock_encounter_change();return WORLD_JOHTO_FULL;}
 s_save_buf.inventory.quantity[item]++;s_save_buf.research_rewards[id]++;
 xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
 if(ok){s_inventory=s_save_buf.inventory;memcpy(s_research_rewards,s_save_buf.research_rewards,sizeof(s_research_rewards));s_last_save_us=esp_timer_get_time();}
 unlock_encounter_change();return ok?WORLD_JOHTO_OK:WORLD_JOHTO_SAVE_FAILED;
}

world_johto_result_t world_johto_search(unsigned route,unsigned path,johto_search_t *out){
 if(!out)return WORLD_JOHTO_LOCKED;
 world_johto_result_t r=johto_transaction();if(r)return r;
 if(!johto_path(route,path)||!johto_route_open(&s_johto,route)){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
 if(s_w.pet.stamina<NURT_EXPLORE_COST){unlock_encounter_change();return WORLD_JOHTO_NO_STAMINA;}
 johto_search_t event;
 if(!johto_search_apply(&s_save_buf,route,path,(uint32_t)esp_timer_get_time(),&event)){unlock_encounter_change();return WORLD_JOHTO_LOCKED;}
 r=johto_commit(false,event.kind!=JOHTO_SEARCH_CLUE,NURT_EXPLORE_COST);
 if(!r){*out=event;if(event.kind!=JOHTO_SEARCH_CLUE)sfx_encounter(event.encounter.rarity,event.encounter.is_shiny);}
 return r;
}

world_johto_result_t world_johto_investigate(unsigned id,unsigned path,unsigned slot,const mon_t *expected){
 world_johto_result_t r=johto_transaction();if(r)return r;
 unsigned result=johto_probe_apply(&s_save_buf,id,path,slot,expected);
 if(result){unlock_encounter_change();return result==PROBE_WRONG_PATH?WORLD_JOHTO_WRONG_PATH:result==PROBE_WRONG_PARTNER?WORLD_JOHTO_WRONG_PARTNER:result==PROBE_NO_STAMINA?WORLD_JOHTO_NO_STAMINA:WORLD_JOHTO_LOCKED;}
 return johto_commit(false,false,NURT_EXPLORE_COST);
}
