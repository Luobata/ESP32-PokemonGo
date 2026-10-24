#!/usr/bin/env python3
"""V26 production migrations, exact-slot evolution and durable research rewards."""
import verify_trainer_campaign as h
from save_history_fixtures import c_cases
h.CASES=c_cases()+r'''
static void setup_evolution(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 johto_init(&s_johto);s_challenge.defeated=255;assert(johto_offer(&s_johto,255));assert(johto_depart(&s_johto));assert(johto_choose_starter(&s_johto,152));s_johto.badges=255;
 for(unsigned i=ITEM_SUN_STONE;i<ITEM_COUNT;i++)s_inventory.quantity[i]=9;
 world_debug_save();
}
static void historical(void){
 static save_t s,alias;
 for(unsigned i=0;i<sizeof(history)/sizeof(*history);i++){
  assert(save_decode(&s,history[i].data,history[i].size,0)!=SAVE_READ_ERROR);history_assert(&s,history[i].version);
  assert(!s.achievements.cross_gen_evolutions);
  for(unsigned j=19;j<ITEM_COUNT;j++)assert(!s.inventory.quantity[j]);
  for(unsigned j=0;j<5;j++)assert(!s.research_rewards[j]);
  memcpy(&alias,history[i].data,history[i].size);assert(save_decode(&alias,&alias,history[i].size,0)!=SAVE_READ_ERROR);
  assert(!memcmp(&alias,&s,sizeof(s)));
 }
}
static void branches(void){
 // Items, friendship, training and pre-existing alternative level branch.
 const unsigned cases[][4]={{44,182,19,0},{191,192,19,0},{95,208,20,0},{123,212,20,0},{61,186,21,0},{79,199,21,0},{117,230,22,0},{137,233,23,0},
 {42,169,255,80},{113,242,255,80},{172,25,255,80},{173,35,255,80},{174,39,255,80},{175,176,255,80},
 {133,196,255,80},{133,197,255,80},{236,106,255,0},{236,107,255,0},{236,237,255,0},{79,80,255,0}};
 for(unsigned c=0;c<sizeof(cases)/sizeof(*cases);c++){
  setup_evolution();unsigned slot=(unsigned[]){151,255,256,452}[c%4];
  mon_t m={.species_id=cases[c][0],.level=60,.exp=exp_for_level(60),.hp=73,.intimacy=cases[c][3],.flags=1,.explore_value=197,.nickname_idx=127};
  s_party.box[slot]=m;s_party.box[(slot+1)%453]=m;move_policy_set(&s_party.policies[6+slot],85,false);world_debug_save();
  inventory_t bag=s_inventory;party_t before=s_party;achievement_store_t ach=s_achievements;
  failure=4;assert(world_evolve_individual(6+slot,&m,cases[c][1])==ITEM_USE_SAVE_FAILED);failure=0;
  assert(!memcmp(&bag,&s_inventory,sizeof(bag))&&!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&ach,&s_achievements,sizeof(ach)));
  assert(world_evolve_individual(6+slot,&m,cases[c][1])==ITEM_USE_OK);
  mon_t result=m;result.species_id=cases[c][1];assert(!memcmp(&result,&s_party.box[slot],sizeof(result)));
  assert(!memcmp(&m,&s_party.box[(slot+1)%453],sizeof(m)));
  if(cases[c][2]!=255)assert(s_inventory.quantity[cases[c][2]]==bag.quantity[cases[c][2]]-1);
  assert(s_achievements.evolutions==1&&s_achievements.cross_gen_evolutions==(m.species_id<=151&&result.species_id>151));
  assert(dex_is_caught(&s_dex,result.species_id));assert(world_evolve_individual(6+slot,&m,result.species_id)==ITEM_USE_WRONG_TARGET);
  reboot();assert(!memcmp(&result,&s_party.box[slot],sizeof(result)));
 }
 setup_evolution();s_johto.badges=3;s_party.box[0]=(mon_t){.species_id=133,.level=60,.intimacy=80};mon_t m=s_party.box[0];
 assert(world_evolve_individual(6,&m,196)==ITEM_USE_NOT_APPLICABLE);s_johto.badges=7;
 m.intimacy=s_party.box[0].intimacy=79;assert(world_evolve_individual(6,&m,196)==ITEM_USE_NOT_APPLICABLE);
 s_inventory.quantity[ITEM_METAL_COAT]=0;m=s_party.box[0]=(mon_t){.species_id=95,.level=60};assert(world_evolve_individual(6,&m,208)==ITEM_USE_EMPTY);
 s_active.encounter.uid=42;assert(world_evolve_individual(6,&m,208)==ITEM_USE_BUSY);
}
static void rewards(void){
 setup_evolution();
 for(unsigned id=0;id<5;id++){
  unsigned item=ITEM_SUN_STONE+id,route=JOHTO_REWARDS[id].route;
  assert(world_johto_reward_claim(id)==WORLD_JOHTO_LOCKED);
  s_johto.research[route]=6;assert(world_johto_reward_claim(id)==WORLD_JOHTO_FULL&&!s_research_rewards[id]);
  s_inventory.quantity[item]=0;world_debug_save();failure=4;assert(world_johto_reward_claim(id)==WORLD_JOHTO_SAVE_FAILED&&!s_research_rewards[id]&&!s_inventory.quantity[item]);failure=0;
  assert(world_johto_reward_claim(id)==WORLD_JOHTO_OK&&s_inventory.quantity[item]==1&&s_research_rewards[id]==1);
  assert(world_johto_reward_claim(id)==WORLD_JOHTO_LOCKED);reboot();assert(s_research_rewards[id]==1);
  s_johto.research[route]=12;assert(world_johto_reward_claim(id)==WORLD_JOHTO_OK&&s_inventory.quantity[item]==2);
 }
 achievement_view_t view;world_achievements_snapshot(&view);assert(achievement_progress(&view,19)==2);
 s_inventory.quantity[ITEM_SUN_STONE]=9;assert(world_achievement_claim(19)==ACH_CLAIM_FULL&&!(s_achievements.claimed&(1u<<19)));
 s_inventory.quantity[ITEM_SUN_STONE]=8;failure=4;assert(world_achievement_claim(19)==ACH_CLAIM_FAILED&&!(s_achievements.claimed&(1u<<19)));failure=0;
 assert(world_achievement_claim(19)==ACH_CLAIM_OK);reboot();assert(s_achievements.claimed&(1u<<19));assert(world_achievement_claim(19)==ACH_CLAIM_ALREADY);
 s_johto.phase=JOHTO_COMPLETE;s_inventory.quantity[ITEM_MASTER]=0;assert(world_achievement_claim(31)==ACH_CLAIM_OK);reboot();assert(s_achievements.claimed&(1u<<31));
 assert(!erase_calls);
}
int main(void){assert(assets_init());historical();branches();rewards();puts("V26: V5-V26 alias migrations; 20 evolution branches; slots 151/255/256/452; identical siblings; 5 repeat reward sources; full/fail/stale/reboot and bit31 claims passed");}
'''
if __name__=='__main__':h.run()
