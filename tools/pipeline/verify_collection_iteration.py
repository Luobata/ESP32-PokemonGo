#!/usr/bin/env python3
"""Real assets and production transactions for tracking, reserves and rematches."""
import verify_trainer_campaign as h
h.CASES=r'''
#include "exploration.c"
static void tracking(void){
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
 assert(world_exploration_track(151)==EXPLORE_BLOCKED);
 exploration_state_t before=s_exploration;
 failure=4;assert(world_exploration_track(25)==EXPLORE_SAVE_FAILED);failure=0;
 assert(!memcmp(&before,&s_exploration,sizeof(before)));
 assert(world_exploration_track(25)==EXPLORE_NONE);world_debug_save();reboot();assert(s_exploration.tracked_species==25);
 s_exploration.energy=24;unsigned found=0;
 for(unsigned i=0;i<7;i++){
  s_w.pet.stamina=NURT_MAX;
  exploration_event_t e=world_explore();assert(e.kind==EXPLORE_ENCOUNTER||e.kind==EXPLORE_CLUE||e.kind==EXPLORE_TARGET);
  if(e.kind==EXPLORE_TARGET){assert(e.species==25);found++;}
  enc_queue_init(&s_queue);
 }
 assert(found==1);
 s_exploration.clues[0]=3;assert(world_exploration_track(4)==EXPLORE_NONE);
 assert(!s_exploration.clues[0]&&!s_exploration.clues[1]&&s_exploration.route==1);
 assert(world_exploration_track(0)==EXPLORE_NONE&&!s_exploration.tracked_species);
 // Every unlocked species can be targeted at its real rarity, including legends.
 for(unsigned id=1;id<=151;id++){
  unsigned rarity;int route=exploration_habitat(id,&rarity);assert(route>=0);
  exploration_state_t x={.energy=1,.route=route,.tracked_species=id};x.clues[route]=3;
  enc_refresh_state_t r={0};enc_queue_t q;enc_queue_init(&q);dex_t d;dex_init(&d);inventory_t bag={0};
  exploration_event_t e=exploration_step_progress(&x,&r,&q,&d,0,16383,&bag);
  assert(e.kind==EXPLORE_TARGET&&e.species==id&&e.rarity>=rarity);
  x.energy=1;x.clues[route]=3;exploration_state_t old=x;
  e=exploration_step_progress(&x,&r,&q,&d,0,16383,&bag);assert(e.kind==EXPLORE_BLOCKED&&!memcmp(&old,&x,sizeof(x)));
 }
}
static void catch_sharing(void){
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
 mon_t reserve={.species_id=7,.level=10,.exp=exp_for_level(10),.hp=100};assert(party_receive(&s_party,&reserve));
 encounter_t e={.species_id=4,.rarity=2,.hp_ratio=100};enc_queue_push(&s_queue,&e);uint16_t uid=s_queue.items[0].uid;
 mon_t caught={.species_id=4,.level=10,.hp=100};unsigned gain=exp_scaled(exp_scaled(100,60),nurture_exp_percent(&s_w.pet));
 failure=4;assert(!world_capture_uid(uid,&caught));failure=0;assert(s_party.party_count==2&&s_party.party[1].exp==reserve.exp);
 assert(world_capture_uid(uid,&caught));assert(s_party.party_count==3&&s_party.party[1].exp==reserve.exp+gain/5);
 assert(s_party.party[2].exp==exp_for_level(10)); // New catch does not award itself reserve EXP.
 uint32_t xp=s_party.party[1].exp;assert(!world_capture_uid(uid,&caught)&&s_party.party[1].exp==xp);
}
static void team_and_rematch(void){
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
 mon_t mon={.species_id=7,.level=10,.exp=exp_for_level(10),.hp=100};assert(party_receive(&s_party,&mon));
 mon.species_id=25;assert(party_receive(&s_party,&mon));
 assert(exploration_team_bonus(&s_party,0)==10&&exploration_team_bonus(&s_party,2)==10&&exploration_team_bonus(&s_party,3)==20);
 mon.species_id=25;assert(party_receive(&s_party,&mon));assert(exploration_team_bonus(&s_party,3)==20);
 uint32_t xp=s_party.party[1].exp;exp_share_party(&s_party,2,100);assert(s_party.party[1].exp==xp+20);
 s_challenge.defeated=8191;s_challenge.wild_wins=1;
 for(unsigned id=0;id<8;id++){
  trainer_store_t st=s_challenge;assert(trainer_begin(&st,id,s_party.party,s_party.party_count,1024,42));
  assert(st.session.sides[1].count==6&&trainer_store_valid(&st));
  for(unsigned i=0;i<6;i++)assert(st.session.sides[1].mons[i].level>=65);
  assert(trainer_rematch_prize(&st)==ITEM_NONE);
 }
 assert(world_challenge_begin(0));s_challenge.session.finished=1;s_challenge.session.won=1;
 unsigned amount=exp_scaled(trainer_reward(&s_challenge),nurture_exp_percent(&s_w.pet));
 uint32_t prior=s_party.party[1].exp;unsigned qty=s_inventory.quantity[ITEM_MOON_STONE];
 failure=4;assert(!world_challenge_settle());failure=0;assert(s_party.party[1].exp==prior&&s_inventory.quantity[ITEM_MOON_STONE]==qty);
 assert(world_challenge_settle());assert(s_party.party[1].exp==prior+amount/5);assert(s_inventory.quantity[ITEM_MOON_STONE]==qty+1);
 uint32_t settled=s_party.party[1].exp;assert(world_challenge_settle()&&s_party.party[1].exp==settled&&s_inventory.quantity[ITEM_MOON_STONE]==qty+1);
 world_debug_save();reboot();assert(s_party.party[1].exp==settled&&s_inventory.quantity[ITEM_MOON_STONE]==qty+1);
}
int main(void){assert(assets_init());tracking();catch_sharing();team_and_rematch();puts("{\"tracked_species\":151,\"pending_protected\":true,\"save_rollback\":true,\"restart\":true,\"reserve_xp\":true,\"gym_rematches\":8,\"prize_idempotent\":true}");}
'''
h.run()
