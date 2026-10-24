#!/usr/bin/env python3
"""Production V31 story transactions and historical migration (ASan/UBSan)."""
import verify_trainer_campaign as h
from save_history_fixtures import c_cases
h.CASES=c_cases()+r'''
static void ready(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_challenge.defeated=16383;
 s_johto.phase=JOHTO_ACTIVE;s_johto.starter=152;s_johto.badges=255;
 s_w.pet.stamina=100*NURT_Q;world_debug_save();
}
static void dialogue(void){
 ready();assert(world_narrative_update(N_BUG_REPORT,0,0,true)==N_LOCKED);
 failure=4;assert(world_narrative_update(N_WELCOME,0,0,true)==N_SAVE_FAILED&&!s_narrative.scene);failure=0;
 assert(world_narrative_update(N_WELCOME,0,0,true)==N_OK);reboot();assert(s_narrative.scene==N_WELCOME+1&&!s_narrative.page);
 assert(world_narrative_update(N_WELCOME,0,0,false)==N_OK);reboot();assert(s_narrative.page==1);
 assert(world_narrative_update(N_WELCOME,0,0,false)==N_LOCKED);narrative_t before=s_narrative;
 failure=4;assert(world_narrative_update(N_WELCOME,1,0,false)==N_SAVE_FAILED&&!memcmp(&before,&s_narrative,sizeof(before)));failure=0;
 inventory_t bag=s_inventory;int32_t stamina=s_w.pet.stamina;
 assert(world_narrative_update(N_WELCOME,1,0,false)==N_OK);assert(!s_narrative.scene&&narrative_seen(&s_narrative,N_WELCOME));
 assert(world_narrative_update(N_WELCOME,1,0,false)==N_LOCKED);assert(!memcmp(&bag,&s_inventory,sizeof(bag))&&s_w.pet.stamina==stamina);
 s_narrative.bug_evidence=1;world_debug_save();assert(world_narrative_update(N_BUG_REPORT,0,0,true)==N_OK);
 for(unsigned i=0;i<2;i++)assert(world_narrative_update(N_BUG_REPORT,i,0,false)==N_OK);
 before=s_narrative;assert(world_narrative_update(N_BUG_REPORT,2,0,false)==N_WRONG&&!memcmp(&before,&s_narrative,sizeof(before)));
 reboot();assert(s_narrative.page==2);assert(world_narrative_update(N_BUG_REPORT,2,1,false)==N_OK);
 assert(!memcmp(&bag,&s_inventory,sizeof(bag))&&s_w.pet.stamina==stamina);
}
static void bug_evidence(void){
 ready();activity_result_data_t event;activity_request_t q={.op=ACTION_BEGIN,.choice=ACT_BUG,.slots={0},.count=1,.seed=7};
 assert(world_activity_action(&q,&event)==ACT_OK);assert(world_narrative_update(N_WELCOME,0,0,true)==N_BUSY);
 q=(activity_request_t){.op=ACTION_END_SURVEY};assert(world_activity_action(&q,&event)==ACT_OK);q.op=ACTION_SETTLE;q.box_slot=BOX_CAPACITY;
 assert(world_activity_action(&q,&event)==ACT_OK&&!s_narrative.bug_evidence);
 q=(activity_request_t){.op=ACTION_BEGIN,.choice=ACT_BUG,.slots={0},.count=1,.seed=7};assert(world_activity_action(&q,&event)==ACT_OK);
 for(unsigned i=0;i<6;i++){q=(activity_request_t){.op=ACTION_SURVEY,.choice=0};assert(world_activity_action(&q,&event)==ACT_OK);q.op=ACTION_SKIP;assert(world_activity_action(&q,&event)==ACT_OK);reboot();}
 // Even a low-diversity survey, without throwing any ball, advances the story.
 s_activities.run.observed=1;q=(activity_request_t){.op=ACTION_SETTLE,.box_slot=BOX_CAPACITY};
 failure=4;assert(world_activity_action(&q,&event)==ACT_SAVE_FAILED&&!s_narrative.bug_evidence&&s_activities.run.kind);failure=0;
 assert(world_activity_action(&q,&event)==ACT_OK&&s_narrative.bug_evidence&&!s_activities.bug_completed);reboot();assert(s_narrative.bug_evidence&&!s_activities.run.kind);
 assert(world_activity_action(&q,&event)==ACT_LOCKED);
}
static void locked_encounter(void){
 ready();s_story.version=1;s_story.tower_seen=1;s_johto.legend_clues[0]=3;world_debug_save();encounter_t first,again;
 failure=4;assert(world_johto_legend(0,&first)==WORLD_JOHTO_SAVE_FAILED&&!s_narrative.legend);failure=0;
 assert(world_johto_legend(0,&first)==WORLD_JOHTO_OK&&s_narrative.legend==1);int32_t spent=s_w.pet.stamina;
 narrative_t locked=s_narrative;encounter_t collision=first;collision.species_id=25;narrative_consume(&s_narrative,&collision);assert(!memcmp(&locked,&s_narrative,sizeof(locked)));
 assert(world_johto_legend(0,&again)==WORLD_JOHTO_OK&&!memcmp(&first,&again,sizeof(first))&&s_w.pet.stamina==spent);
 assert(world_johto_legend(1,&again)==WORLD_JOHTO_BUSY);reboot();assert(!memcmp(&s_narrative.pending,&first,sizeof(first)));
 for(unsigned i=0;i<6;i++){encounter_t e={.species_id=25,.level=10,.hp_ratio=100,.rarity=1};enc_queue_push(&s_queue,&e);}world_debug_save();
 assert(!enc_queue_find(&s_queue,first.uid));failure=4;assert(world_johto_legend(0,&again)==WORLD_JOHTO_SAVE_FAILED&&!memcmp(&first,&s_narrative.pending,sizeof(first)));failure=0;
 assert(world_johto_legend(0,&again)==WORLD_JOHTO_OK&&again.uid!=first.uid);uint16_t new_uid=again.uid;again.uid=first.uid;assert(!memcmp(&first,&again,sizeof(first))&&s_w.pet.stamina==spent);
 // Actual first attack consumes the reservation in the same world save.
 battle_session_t b={.initialized=true,.started=true,.pet_species=25,.wild_species=243,.rng=123,.pet_hp=20,.pet_hp_max=20,.wild_hp=30,.wild_hp_max=30};
 failure=4;assert(!world_battle_set_uid(new_uid,&b)&&s_narrative.legend);failure=0;
 assert(world_battle_set_uid(new_uid,&b)&&!s_narrative.legend);reboot();assert(!s_narrative.legend);
}
static void goals(void){
 narrative_context_t c={0};narrative_init(&c.state);johto_init(&c.chapter);johto_story_init(&c.story);c.defeated=16383;c.chapter.phase=JOHTO_ACTIVE;c.chapter.starter=152;
 unsigned visits=0;bool complete=false;
 for(unsigned guard=0;guard<100;guard++){
  narrative_goal_t g=narrative_goal(&c);
  switch(g.action){
  case N_GO_ROUTE:assert(johto_route_open(&c.chapter,g.index));c.chapter.research[g.index]++;johto_story_explore(&c.story,&c.chapter,g.index);{unsigned id=johto_probe_next(&c.chapter,&c.story,c.feather,g.index,c.state.focus);if(id<JOHTO_PROBE_COUNT)c.chapter.legend_clues[johto_probe(id)->legend]++;}break;
  case N_GO_GYM:if(g.index==8){assert(narrative_final(&c));complete=true;}else{assert(g.index==johto_badges(&c.chapter));c.chapter.badges|=1u<<g.index;}break;
  case N_GO_BUG:c.state.bug_evidence=1;break;
  case N_GO_RUIN:c.story.ruins=1;break;
  case N_GO_RESCUE:c.story.rescues=1;break;
  case N_GO_TOWER:c.story.tower_seen=1;break;
  case N_GO_LAKE:c.lake=LAKE_RECEIVED;break;
  case N_GO_SEA:c.feather=1;break;
  case N_GO_PURIFY:assert(c.chapter.legend_clues[2]==2);c.chapter.legend_clues[2]=3;break;
  case N_GO_LEGEND:assert(johto_story_legend_ready(&c.story,&c.chapter,g.index,c.feather));c.story.legend_visits|=1u<<g.index;visits++;break;
  default:assert(!"unexpected or blocked goal");
  }
  if(complete)break;
 }
 assert(complete&&visits==5&&c.lake==LAKE_RECEIVED&&c.story.rescues==1&&c.story.ruins==1);
 c.chapter.phase=JOHTO_COMPLETE;assert(narrative_goal(&c).action==N_GO_KANTO_ROUTE);c.story.forest_visits|=1;
 for(unsigned i=0;i<3;i++){unsigned id=johto_probe_next(&c.chapter,&c.story,c.feather,1,0);assert(id<JOHTO_PROBE_COUNT&&johto_probe(id)->legend==5);johto_story_explore(&c.story,&c.chapter,1);c.chapter.legend_clues[5]++;}
 assert(narrative_goal(&c).action==N_GO_LEGEND&&narrative_goal(&c).index==5);c.story.legend_visits|=1u<<5;assert(narrative_goal(&c).action==N_GO_FREE);
 c.chapter.phase=JOHTO_ACTIVE;c.state.legacy_final=1;c.state.bug_evidence=0;c.story.ruins=0;assert(narrative_final(&c)&&narrative_goal(&c).index==8);
}
static void migration(void){
 static save_t s;for(unsigned i=0;i<sizeof(history)/sizeof(*history);i++){
  assert(save_decode(&s,history[i].data,history[i].size,0)!=SAVE_READ_ERROR);history_assert(&s,history[i].version);
 }
 ready();s_story.version=1;s_story.tower_seen=1;s_story.ruins=15;s_story.rescues=2;s_activities.silver_feather=1;
 for(unsigned i=0;i<5;i++)s_johto.legend_clues[i]=3;collect_save_locked(&s);
 static save_v30_t old;memcpy(&old,&s,sizeof(old));old.prefix.version=30;
 assert(save_decode(&s,&old,sizeof(old),0)==SAVE_READ_MIGRATED&&s.narrative.legacy_final&&!s.narrative.bug_evidence);
 assert(!memcmp(&s.story,&s_story,sizeof(s_story))&&!memcmp(&s.members,&s_party,sizeof(s_party)));
 narrative_t bad=s.narrative;bad.seen=UINT64_MAX;assert(!narrative_valid(&bad));bad=s.narrative;bad.scene=N_LETTER+1;bad.page=3;assert(!narrative_valid(&bad));
 bad=s.narrative;bad.legend=1;bad.pending=(encounter_t){.uid=1,.species_id=243,.level=50,.rarity=5,.hp_ratio=100};assert(narrative_valid(&bad));
 ((uint8_t*)&bad.pending.exp_granted)[0]=2;assert(!narrative_valid(&bad));((uint8_t*)&bad.pending.exp_granted)[0]=0;((uint8_t*)&bad.pending.is_shiny)[0]=2;assert(!narrative_valid(&bad));
}
int main(void){assert(assets_init());dialogue();bug_evidence();locked_encounter();goals();migration();puts("V31 passed: checkpoint/retry, observation evidence, protected FIFO encounter, guided whole-chapter goals, V5-V31 migrations and malformed bytes");}
'''
if __name__=='__main__':h.run()
