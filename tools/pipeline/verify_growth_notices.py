#!/usr/bin/env python3
"""Committed XP notices across actual world/save paths, including failed writes."""
import json
import verify_world_party as h
import verify_exploration_routes as base

h.CASES=base.CASES[:base.CASES.index('static void core')]+r'''
static void ready(void) {
 fresh();memset(&s_growth,0,sizeof(s_growth));assert(world_choose_starter(25)==WORLD_STARTER_OK);
 s_w.level=9;s_w.exp=exp_for_level(10)-1;
 s_w.pet.satiety=s_w.pet.mood=50*NURT_Q;s_w.pet.intimacy=0;
 mon_t second={.species_id=7,.level=4,.exp=exp_for_level(5)-1,.hp=100,.flags=1};
 assert(party_receive(&s_party,&second));world_debug_save();
}
static uint16_t encounter(void) {
 encounter_t e={.species_id=133,.rarity=3,.hp_ratio=100};enc_queue_push(&s_queue,&e);
 return s_queue.items[s_queue.count-1].uid;
}
static void notices(void) {
 exp_growth_t e;assert(world_growth_pop(&e)&&e.species==25&&e.before==9&&e.after>=10);
 assert(world_growth_pop(&e)&&e.species==7&&e.before==4&&e.after>=5&&e.flags==1);
 assert(!world_growth_pop(&e));tests+=3;
}
static void battle_rewards(void) {
 for(unsigned won=0;won<2;won++) {
  ready();uint16_t uid=encounter();battle_session_t b={.initialized=true,.started=true,.finished=true,.won=won,.pet_species=25,.wild_species=133,.pet_level=9,.wild_level=20};
  assert(world_battle_set_uid(uid,&b));uint16_t gain;exp_growth_t e;
  for(unsigned f=1;f<=4;f++){if(f==3)continue;failure=f;assert(!world_battle_reward_uid(uid,&gain));failure=0;assert(!world_growth_pop(&e));tests++;}
  assert(world_battle_reward_uid(uid,&gain)&&gain);notices();
  assert(world_battle_reward_uid(uid,&gain)&&!gain&&!world_growth_pop(&e));tests++;
 }
}
static void capture_reward(void) {
 ready();uint16_t uid=encounter();mon_t m={.species_id=133,.level=20,.hp=100,.exp=exp_for_level(20)};exp_growth_t e;
 failure=4;assert(!world_capture_uid(uid,&m));failure=0;assert(!world_growth_pop(&e));
 assert(world_capture_uid(uid,&m));notices();assert(!world_capture_uid(uid,&m)&&!world_growth_pop(&e));tests+=2;
}
static void research_reward(void) {
 ready();for(unsigned i=0;i<5;i++){uint8_t ids[]={10,13,16,43,46};dex_mark_caught(&s_dex,ids[i],false);}
 s_exploration.research_flags=16;uint16_t gain;exp_growth_t e;
 failure=4;assert(world_research_claim(0,&gain)==EXPLORE_SAVE_FAILED);failure=0;assert(!world_growth_pop(&e));
 assert(world_research_claim(0,&gain)==EXPLORE_NONE&&gain);notices();
 assert(world_research_claim(0,&gain)==EXPLORE_RESEARCH_CLAIMED&&!world_growth_pop(&e));tests+=2;
}
static void merged_and_swapped(void) {
 ready();exp_growth_t e;world_grant_exp(100);world_grant_exp(700);
 assert(world_growth_pop(&e)&&e.species==25&&e.before==9&&e.after>=11&&!world_growth_pop(&e));
 world_party_t v;world_party_snapshot(&v);assert(world_set_leader(1,&v.members[1],NULL)==WORLD_SWITCH_OK);
 assert(!world_growth_pop(&e));tests+=2;
}
int main(void){battle_rewards();capture_reward();research_reward();merged_and_swapped();printf("{\"cases\":%u,\"save_version\":%d,\"save_bytes\":%zu}\n",tests,SAVE_VERSION,sizeof(save_t));return 0;}
'''
result=h.run(h.ROOT)
result.update(scope='Actual world/XP/save C, ASan and UBSan; failed commits, victory/defeat/capture/research, party sharing, retries and swaps')
out=h.ROOT/'reports/evidence/controls-growth-2026-09-10';out.mkdir(parents=True,exist_ok=True)
(out/'growth-save.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
