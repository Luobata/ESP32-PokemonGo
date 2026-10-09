#!/usr/bin/env python3
"""Real C exploration/world/save balance and chain isolation, with NVS failures."""
import verify_dungeon_rewards as base
h=base.harness
h.CASES=h.CASES[:h.CASES.index('int main(')]+r'''
static void chain_battle(unsigned source,bool won,battle_session_t *b){
 enc_queue_init(&s_queue);
 encounter_t e={.species_id=19,.rarity=1,.level=12,.hp_ratio=100,.activity=source};enc_queue_push(&s_queue,&e);
 *b=(battle_session_t){.initialized=true,.started=true,.finished=true,.won=won,
 .pet_species=s_w.species,.pet_level=s_w.level,.wild_species=19,.wild_level=12,
 .pet_hp=won?30:0,.pet_hp_max=30,.wild_hp=won?0:20,.wild_hp_max=20};
 assert(world_battle_set_uid(s_queue.items[0].uid,b));
}
static void chain_transactions(void){
 setup();s_challenge.defeated=0x3fff;
 for(unsigned i=1;i<=3;i++){
  battle_session_t b;chain_battle(ENC_ACTIVITY_EXPLORATION,true,&b);unsigned uid=s_active.encounter.uid;uint16_t gain;
  unsigned char before[sizeof(disk)];memcpy(before,disk,sizeof(disk));
  for(unsigned j=0;j<3;j++){
   failure=(unsigned[]){1,2,4}[j];assert(!world_battle_reward_uid(uid,&gain));failure=0;
   assert(s_exploration_wins==i-1&&!s_active.session.reward_settled&&!memcmp(before,disk,sizeof(disk)));
  }
  assert(world_battle_reward_uid(uid,&gain)&&s_exploration_wins==i);
  assert(world_battle_set_uid(uid,&b)&&world_battle_reward_uid(uid,&gain)&&!gain&&s_exploration_wins==i);
  item_loot_t loot;assert(world_battle_loot_uid(uid,&loot)&&world_battle_loot_uid(uid,&loot)&&s_exploration_wins==i);
  restart();assert(s_exploration_wins==i&&!s_active.encounter.uid&&s_storage_ready);
 }
 assert(world_exploration_select(4)==EXPLORE_NONE&&s_exploration_wins==3);
 assert(world_exploration_select(2)==EXPLORE_NONE&&s_exploration_wins==3);restart();assert(s_exploration_wins==3);
 // Unrelated passive and dungeon reward partners use source zero, regardless of outcome.
 for(unsigned won=0;won<2;won++){
  battle_session_t b;chain_battle(0,won,&b);uint16_t gain;
  if(!won)assert(world_apply_defeat_uid(s_active.encounter.uid));
  assert(world_battle_reward_uid(s_active.encounter.uid,&gain)&&s_exploration_wins==3);
  restart();assert(s_exploration_wins==3);
 }
 // Trainer win/loss and a lost dungeon do not break or increase exploration wins.
 for(unsigned won=0;won<2;won++){
  s_w.pet.stamina=NURT_MAX;assert(world_challenge_start(0)==WORLD_CHALLENGE_OK);
  s_challenge.session.finished=1;s_challenge.session.won=won;
  assert(world_challenge_settle()&&s_exploration_wins==3);restart();assert(s_exploration_wins==3);
 }
 s_w.pet.stamina=NURT_MAX;assert(dungeon_new(chosen,3,127));
 run.battle.session.finished=1;run.battle.session.won=0;
 assert(dungeon_finish()&&s_exploration_wins==3);restart();assert(s_exploration_wins==3);
 // Passive capture and escaping an exploration encounter keep the chain.
 enc_queue_init(&s_queue);encounter_t e={.species_id=25,.rarity=2,.level=12,.hp_ratio=100};enc_queue_push(&s_queue,&e);world_debug_save();restart();
 unsigned uid=s_queue.items[0].uid;assert(s_queue.items[0].activity==0);
 mon_t mon={.species_id=25,.level=12,.exp=exp_for_level(12),.hp=100};assert(world_capture_uid(uid,&mon)&&s_exploration_wins==3);restart();
 battle_session_t b;chain_battle(ENC_ACTIVITY_EXPLORATION,true,&b);assert(world_take_uid(s_active.encounter.uid,NULL));assert(s_exploration_wins==3);
 chain_battle(ENC_ACTIVITY_EXPLORATION,false,&b);uid=s_active.encounter.uid;
 failure=4;assert(!world_apply_defeat_uid(uid)&&s_exploration_wins==3&&!s_active.session.defeat_applied);failure=0;
 assert(world_apply_defeat_uid(uid)&&s_exploration_wins==0);uint16_t gain;
 assert(world_battle_reward_uid(uid,&gain)&&world_apply_defeat_uid(uid)&&s_exploration_wins==0);
 restart();assert(s_exploration_wins==0);tests++;
}
static void chain_capture_confirmation(void){
 for(unsigned i=0;i<3;i++){
  setup();s_exploration_wins=50;enc_queue_init(&s_queue);
  unsigned source=(unsigned[]){0,1,ENC_ACTIVITY_EXPLORATION}[i];
  encounter_t e={.species_id=25,.rarity=2,.level=12,.hp_ratio=100,.activity=source};
  enc_queue_push(&s_queue,&e);world_debug_save();restart();unsigned uid=s_queue.items[0].uid;
  assert(s_queue.items[0].activity==source&&s_exploration_wins==50);
  battle_session_t b;assert(battle_session_init(&b,s_w.species,s_w.level,25,12,1024,812));
  assert(world_battle_set_uid(uid,&b));b.started=true;
  inventory_t inv=s_inventory;party_t party=s_party;enc_queue_t queue=s_queue;
  mon_t mon={.species_id=25,.level=12,.exp=exp_for_level(12),.hp=100};
  unsigned char before[sizeof(disk)];memcpy(before,disk,sizeof(disk));
  assert(!world_capture_break_chain_uid(0)&&!world_capture_break_chain_uid(65000));
  if(source){
   // Calling the throw/result API directly cannot bypass the confirmation.
   assert(!world_capture_ball_spend_uid(uid,ITEM_POKE,&b));
   assert(!world_capture_uid(uid,&mon));
   assert(s_exploration_wins==50&&!memcmp(&inv,&s_inventory,sizeof(inv))&&!memcmp(&party,&s_party,sizeof(party)));
   for(unsigned j=0;j<3;j++){
    failure=(unsigned[]){1,2,4}[j];assert(!world_capture_break_chain_uid(uid));failure=0;
    assert(s_exploration_wins==50&&!memcmp(before,disk,sizeof(disk))&&!memcmp(&queue,&s_queue,sizeof(queue)));
   }
  }
  assert(world_capture_break_chain_uid(uid)&&s_exploration_wins==(source?0:50));
  assert(!memcmp(&inv,&s_inventory,sizeof(inv))&&!memcmp(&queue,&s_queue,sizeof(queue)));
  // Confirmation is durable and idempotent, even without a thrown ball.
  failure=4;assert(world_capture_break_chain_uid(uid));failure=0;
  restart();assert(s_exploration_wins==(source?0:50)&&s_queue.items[0].activity==source);
  b.started=false;assert(world_battle_set_uid(uid,&b));b.started=true;
  assert(world_capture_ball_spend_uid(uid,ITEM_POKE,&b));
  assert(world_capture_uid(uid,&mon)&&s_exploration_wins==(source?0:50));
  restart();assert(s_exploration_wins==(source?0:50));
 }
 // The victory's extra chain point is also broken before the final capture.
 setup();s_exploration_wins=50;battle_session_t b;chain_battle(ENC_ACTIVITY_EXPLORATION,true,&b);
 unsigned uid=s_active.encounter.uid;uint16_t gain;item_loot_t loot;
 assert(!world_capture_break_chain_uid(uid)&&s_exploration_wins==50);
 assert(world_battle_reward_uid(uid,&gain)&&s_exploration_wins==51);
 assert(world_battle_loot_uid(uid,&loot)&&world_capture_break_chain_uid(uid)&&!s_exploration_wins);
 assert(world_battle_reward_uid(uid,&gain)&&!s_exploration_wins&&!gain);
 tests++;
}
static void chain_odds(void){
 const uint32_t streaks[]={0,10,50,100,200,1000,UINT32_MAX};unsigned previous=0;
 for(unsigned j=0;j<7;j++){
  unsigned bp=exploration_chain_shiny_bp(streaks[j],SHINY_EXPLORATION);assert(bp>previous&&bp<10000);previous=bp;
  unsigned shiny=0;
  for(unsigned seed=1;seed<=30000;seed++){
   exploration_regions_t rs={.selected=4};rs.region[0].steps=seed;
   enc_refresh_state_t refresh={0};enc_queue_t q={0};dex_t dex={0};inventory_t bag={0};
   exploration_event_t e=exploration_region_step(&rs,&refresh,&q,&dex,0,0x3fff,&bag,1);
   assert(e.kind==EXPLORE_ENCOUNTER&&q.items[0].activity==ENC_ACTIVITY_EXPLORATION);
   exploration_chain_discovery(&e,&q,&dex,streaks[j]);shiny+=e.shiny;
   assert(e.shiny==q.items[0].is_shiny);
  }
  unsigned actual=shiny/3;assert(actual+110>bp&&actual<bp+110);
  printf("chain[%lu]=%u/10000 ",(unsigned long)streaks[j],actual);
 }
 uint32_t maximum=UINT32_MAX;encounter_t enc={.activity=ENC_ACTIVITY_EXPLORATION};exploration_chain_settle(&maximum,&enc,true);assert(maximum==UINT32_MAX);
 // Badges use their own higher base, still independent of species rarity.
 assert(exploration_chain_shiny_bp(0,SHINY_BADGE)==312);
 tests++;
}
static void supply_distribution(void){
 unsigned last_poke=100000,last_quality=0,last_evolution=0,last_machine=0;
 for(unsigned rarity=1;rarity<=5;rarity++){
  unsigned kinds[4]={0},berries=0,ids[ITEM_COUNT]={0};
  for(unsigned seed=1;seed<=100000;seed++){
   item_loot_t loot=items_roll_loot(rarity,seed);assert(loot.item_id<ITEM_COUNT&&loot.quantity);
   kinds[items_info(loot.item_id)->kind]++;ids[loot.item_id]++;berries+=loot.item_id==ITEM_BERRY;
  }
  assert(kinds[ITEM_KIND_BALL]>69000&&kinds[ITEM_KIND_BALL]<71000);
  assert(kinds[ITEM_KIND_CARE]>19500&&berries>10000);
  unsigned quality=0;for(unsigned i=ITEM_ULTRA;i<ITEM_BALL_COUNT;i++)quality+=ids[i];
  unsigned evo=kinds[ITEM_KIND_STONE]+kinds[ITEM_KIND_MACHINE],machine=kinds[ITEM_KIND_MACHINE];
  assert(ids[ITEM_POKE]<last_poke&&quality>last_quality&&evo>last_evolution);
  assert(rarity==1?machine==0:machine>last_machine);
  assert(rarity==5?(ids[ITEM_MASTER]>0&&ids[ITEM_MASTER]<1000):ids[ITEM_MASTER]==0);
  if(rarity>=3)assert(kinds[0]-ids[ITEM_POKE]>ids[ITEM_POKE]);
  printf("loot[%u] balls=%u poke=%u great=%u ultra=%u specialty=%u master=%u food=%u evolution=%u machines=%u/100000 ",
   rarity,kinds[0],ids[ITEM_POKE],ids[ITEM_GREAT],ids[ITEM_ULTRA],quality-ids[ITEM_ULTRA]-ids[ITEM_MASTER],ids[ITEM_MASTER],kinds[3],evo,machine);
  last_poke=ids[ITEM_POKE];last_quality=quality;last_evolution=evo;last_machine=machine;
 }
 for(unsigned map=0;map<12;map++)for(unsigned deep=0;deep<2;deep++){
  unsigned food=0,berry=0;
  for(unsigned seed=1;seed<=2000;seed++){
   enc_queue_t q={0};dex_t d={0};inventory_t bag={0};enc_refresh_state_t r={0};exploration_event_t e;
   if(map<4){exploration_state_t x={.route=map,.steps=seed};x.pulse[map]=1;e=exploration_step_with_target(&x,&r,&q,&d,0,0x3fff,&bag,NULL,0,0);}
   else{exploration_regions_t x={.selected=map};x.region[0].claimed=1;x.region[map-4].steps=seed;x.region[map-4].pulse=1;x.region[map-4].deep=deep;e=exploration_region_step(&x,&r,&q,&d,0,0x3fff,&bag,1);}
   assert(e.kind==EXPLORE_CLUE&&e.item<ITEM_COUNT&&e.quantity>0&&bag.quantity[e.item]==e.quantity);
   food+=items_info(e.item)->kind==ITEM_KIND_CARE;berry+=e.item==ITEM_BERRY;
  }
  assert(food>1350&&berry>750);
 }
 inventory_t full;for(unsigned i=0;i<ITEM_COUNT;i++)full.quantity[i]=items_capacity(i);
 item_loot_t rolled={.item_id=ITEM_POKE,.quantity=2};
 item_loot_t result=items_fit_loot(rolled,&full,1);assert(result.full&&!result.quantity);
 full.quantity[ITEM_BERRY]=0;result=items_fit_loot(rolled,&full,1);assert(result.item_id==ITEM_BERRY&&result.quantity==2&&!result.full);
 full.quantity[ITEM_BERRY]=items_capacity(ITEM_BERRY)-1;rolled.item_id=ITEM_BERRY;result=items_fit_loot(rolled,&full,1);assert(result.item_id==ITEM_BERRY&&result.quantity==1&&result.full);
 tests++;
}
static void habitat_odds(void){
 for(unsigned map=4;map<12;map++)for(unsigned trail=1;trail<=3;trail++)for(unsigned deep=0;deep<2;deep++){
  unsigned rare=0;
  for(unsigned seed=1;seed<=10000;seed++){
   exploration_regions_t rs={.selected=map};rs.region[0].claimed=1;rs.region[map-4].steps=seed;rs.region[map-4].deep=deep;
   enc_refresh_state_t r={0};enc_queue_t q={0};dex_t d={0};inventory_t bag={0};
   exploration_event_t e=exploration_region_step(&rs,&r,&q,&d,0,0x3fff,&bag,trail);
   assert(e.kind==EXPLORE_ENCOUNTER);rare+=e.rarity>=4;
  }
  // Missing common tiers must not inflate four/five stars to 70-100%.
  assert(rare<=(deep?2900u:1700u));
 }
 tests++;
}
static void base_route_rules(void){
 for(unsigned map=0;map<4;map++){
  setup();assert(world_exploration_select(map)==EXPLORE_NONE);
  exploration_event_t e=world_explore();assert(e.kind==EXPLORE_ENCOUNTER&&e.level>=exploration_legacy_level_min(map));
 }
 for(unsigned seed=0;seed<100;seed++){
  exploration_state_t x={.route=0,.steps=seed};x.clues[0]=3;
  enc_refresh_state_t r={.since_rare=7,.since_elite=29};enc_queue_t q={0};dex_t d={0};inventory_t bag={0};
  exploration_event_t e=exploration_step_with_target(&x,&r,&q,&d,0,0x3fff,&bag,NULL,0,25);
  assert(e.kind==EXPLORE_TARGET&&e.species==25&&e.rarity==2&&enc_refresh_valid(&r));
 }
 tests++;
}
static void migration_v18(void){
 setup();save_t current;assert(save_read_status(&current)==SAVE_READ_OK);
 save_v18_t old=current.v18;old.version=18;save_t out;
 assert(save_decode(&out,&old,sizeof(old),0)==SAVE_READ_MIGRATED&&!out.exploration_wins);
 old.queue.items[0].activity=9;assert(save_decode(&out,&old,sizeof(old),0)==SAVE_READ_ERROR);
 old.queue.items[0].activity=0;old.regions.region[0].pity=6;assert(save_decode(&out,&old,sizeof(old),0)==SAVE_READ_ERROR);
 current.regions.region[0].pity=9;current.exploration_wins=UINT32_MAX;
 assert(test_decode_save(&out,&current)==SAVE_READ_OK&&out.exploration_wins==UINT32_MAX);
 current.regions.region[0].pity=10;assert(test_decode_save(&out,&current)==SAVE_READ_ERROR);tests++;
}
int main(void){assert(assets_init());chain_transactions();chain_capture_confirmation();chain_odds();supply_distribution();habitat_odds();base_route_rules();migration_v18();printf("\n{\"passed\":true,\"groups\":%u,\"save_version\":%u,\"save_bytes\":%zu,\"sanitized\":true}\n",tests,SAVE_VERSION,sizeof(save_t));return 0;}
'''
if __name__=='__main__':h.run()
