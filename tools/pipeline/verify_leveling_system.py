#!/usr/bin/env python3
"""Actual C experience economy, route trainers, research and save transactions."""
import verify_trainer_campaign as h
h.CASES=r'''
static void ready(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);party_init(&s_party);
 const unsigned ids[]={25,4,7},levels[]={50,20,49};
 for(unsigned i=0;i<3;i++){mon_t m={.species_id=ids[i],.level=levels[i],.exp=exp_for_level(levels[i]),.hp=100};assert(party_receive(&s_party,&m));}
 s_w.species=25;s_w.level=50;s_w.exp=exp_for_level(50);s_w.pet.satiety=s_w.pet.mood=50*NURT_Q;s_w.pet.intimacy=0;s_w.pet.stamina=90*NURT_Q;world_debug_save();
}
static void economy(void){
 assert(exp_battle_base(10)==100&&exp_battle_base(50)==1435&&exp_battle_base(80)==3646);
 for(unsigned lv=20;lv<100;lv++){unsigned need=exp_for_level(lv+1)-exp_for_level(lv);assert((need+exp_battle_base(lv)-1)/exp_battle_base(lv)<=8);}
 ready();party_t p=s_party;exp_award_party(&p,1,7,0);assert(!memcmp(&p,&s_party,sizeof(p)));exp_award_party(&p,1,7,1000);
 assert(p.party[0].exp-s_party.party[0].exp==1000);
 assert(p.party[1].exp-s_party.party[1].exp==1000); // 20 vs 50: 100% bench.
 assert(p.party[2].exp-s_party.party[2].exp==230); // 49 vs 50: tapers to 23%.
 p=s_party;exp_award_party(&p,3,7,1000);
 assert(p.party[0].exp-s_party.party[0].exp==500&&p.party[1].exp-s_party.party[1].exp==1000);
 assert(exp_party_percent(50,50,false)==20&&exp_party_percent(20,50,true)==200);
 tests++;
}
static void routes(void){
 trainer_store_t st={0};mon_t team[3];for(unsigned i=0;i<3;i++)team[i]=(mon_t){.species_id=(unsigned[]){25,9,6}[i],.level=100,.hp=100};
 for(unsigned id=14;id<26;id++)assert(trainer_unlocked(&st,id)==((id-14)%3==0));
 st.defeated=3;for(unsigned id=14;id<26;id++)assert(trainer_unlocked(&st,id)==((id-14)%3<2));
 st.defeated=31;
 for(unsigned id=14;id<26;id++){
  assert(trainer_unlocked(&st,id));assert(trainer_begin(&st,id,team,3,1024,123));
  assert(st.session.sides[1].count==(id-14)%3+1);
  for(unsigned i=0;i<st.session.sides[1].count;i++)assert(st.session.sides[1].mons[i].level==47);
  trainer_event_t e;
  for(unsigned n=0;n<500&&!st.session.finished;n++){
   assert(trainer_step(&st,&e)&&trainer_store_valid(&st));
   if(e.kind==TRAINER_SWITCH_NEEDED){bool switched=false;for(unsigned j=0;j<3;j++)if(trainer_switch(&st,j,true)){switched=true;break;}assert(switched);}
  }
  assert(st.session.finished&&st.session.won);
  inventory_t bag={0};trainer_grant_items(&st,&bag);assert(bag.quantity[ITEM_POKE]==1&&bag.quantity[ITEM_BERRY]==1&&!bag.quantity[ITEM_MILK]);
  trainer_settle(&st);assert(st.defeated==31&&!st.league_active&&trainer_store_valid(&st));
 }
 st.league_active=1;st.league_stage=9;assert(!trainer_unlocked(&st,14));tests++;
}
static void route_transactions(void){
 ready();trainer_store_t old=s_challenge;failure=4;assert(!world_challenge_begin(14)&&!memcmp(&old,&s_challenge,sizeof(old)));failure=0;
 assert(world_challenge_begin(14));old=s_challenge;reboot();assert(!memcmp(&old,&s_challenge,sizeof(old)));
 trainer_event_t e;while(!s_challenge.session.finished){assert(world_challenge_step(&e));if(e.kind==TRAINER_SWITCH_NEEDED){for(unsigned i=0;i<3;i++)if(world_challenge_switch(i,true))break;}}
 assert(s_challenge.session.won);party_t before=s_party;old=s_challenge;inventory_t bag=s_inventory;
 failure=4;assert(!world_challenge_settle()&&!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&bag,&s_inventory,sizeof(bag))&&!memcmp(&old,&s_challenge,sizeof(old)));failure=0;
 assert(world_challenge_settle()&&s_party.party[0].exp>before.party[0].exp&&!s_challenge.defeated);
 before=s_party;bag=s_inventory;assert(world_challenge_settle()&&!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&bag,&s_inventory,sizeof(bag)));reboot();assert(!memcmp(&before,&s_party,sizeof(before)));tests++;
}
static void research(void){
 ready();const unsigned species[4][5]={{10,13,16,43,46},{74,41,27,50,35},{129,72,60,98,54},{19,100,81,88,52}};
 for(unsigned route=0;route<4;route++){
  uint16_t gain=999;assert(world_research_claim(route,&gain)==EXPLORE_RESEARCH_LOCKED&&!gain);
  for(unsigned i=0;i<5;i++){dex_mark_seen(&s_dex,species[route][i],false);if(i<3)dex_mark_caught(&s_dex,species[route][i],false);}
  assert(world_research_claim(route,&gain)==EXPLORE_RESEARCH_LOCKED);
  s_exploration.research_flags|=16u<<route;world_debug_save();
  party_t before=s_party;exploration_state_t old=s_exploration;
  for(int f=1;f<=4;f++){if(f==3)continue;failure=f;assert(world_research_claim(route,&gain)==EXPLORE_SAVE_FAILED&&!gain&&!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&old,&s_exploration,sizeof(old)));failure=0;}
  assert(world_research_claim(route,&gain)==EXPLORE_NONE&&gain>0&&s_w.exp-before.party[0].exp==gain);
  before=s_party;reboot();assert(!memcmp(&before,&s_party,sizeof(before))&&(s_exploration.research_flags&(1u<<route)));
  assert(world_research_claim(route,&gain)==EXPLORE_RESEARCH_CLAIMED&&!gain&&!memcmp(&before,&s_party,sizeof(before)));
 }
 assert(s_exploration.research_flags==255);tests++;
}
static void discoveries(void){
 ready();party_t before=s_party;exploration_state_t start=s_exploration;enc_refresh_state_t refresh=s_refresh;
 failure=4;exploration_event_t e=world_explore();failure=0;assert(e.kind==EXPLORE_SAVE_FAILED&&!e.exp&&!memcmp(&before,&s_party,sizeof(before)));
 e=world_explore();assert(e.species&&e.exp&&s_w.exp-before.party[0].exp==e.exp);uint16_t species=e.species;
 before=s_party;reboot();assert(!memcmp(&before,&s_party,sizeof(before))&&dex_is_seen(&s_dex,species));
 s_exploration=start;s_refresh=refresh;enc_queue_init(&s_queue);world_debug_save();
 e=world_explore();assert(e.species==species&&!e.exp&&!memcmp(&before,&s_party,offsetof(party_t,box))); // exploration counter changes, compare XP below instead.
 tests++;
}
static uint16_t spawn(unsigned species){encounter_t e={.species_id=species,.rarity=1,.hp_ratio=100};enc_queue_push(&s_queue,&e);return s_queue.items[s_queue.count-1].uid;}
static void captures(void){
 ready();uint16_t uid=spawn(133);mon_t m={.species_id=133,.level=10,.exp=exp_for_level(10),.hp=100};uint32_t before=s_w.exp;
 failure=4;assert(!world_capture_uid(uid,&m)&&s_w.exp==before&&!dex_is_caught(&s_dex,133));failure=0;
 assert(world_capture_uid(uid,&m)&&s_w.exp-before==110);assert(s_party.party[3].exp==m.exp); // new catch does not train itself
 assert(!world_capture_uid(uid,&m));reboot();before=s_w.exp;uid=spawn(133);
 assert(world_capture_uid(uid,&m)&&s_w.exp-before==60);tests++;
}
static void migration(void){
 ready();assert(world_challenge_begin(0)==false);s_challenge.wild_wins=1;assert(world_challenge_begin(0));
 save_t old;assert(save_read(&old));old.version=13;combat_mon_t before=old.challenge.session.sides[0].mons[0];old.exploration.research_flags=0;
 memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);save_t next;
 assert(save_read_status(&next)==SAVE_READ_MIGRATED&&next.version==SAVE_VERSION);
 assert(!memcmp(&before,&next.challenge.session.sides[0].mons[0],sizeof(before))&&!memcmp(old.party,next.party,PARTY_BYTES));
 assert(save_write(&next));save_t after;assert(save_read_status(&after)==SAVE_READ_OK&&!memcmp(&after,&next,sizeof(next))&&sizeof(save_t)==3664&&erase_calls==0);tests++;
}
int main(void){assert(assets_init());economy();routes();route_transactions();research();discoveries();captures();migration();printf("{\"status\":\"PASS\",\"groups\":%u,\"route_trainers\":12,\"save_version\":%u,\"sanitized\":true}\n",tests,SAVE_VERSION);}
'''
# Ignore the exploration counter when asserting that a repeated species grants no XP.
h.CASES=h.CASES.replace('&&!memcmp(&before,&s_party,offsetof(party_t,box))','&&s_w.exp==before.party[0].exp')
if __name__=='__main__':h.run()
