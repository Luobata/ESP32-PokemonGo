#!/usr/bin/env python3
"""First-generation regions: real world/NVS/dungeon rules, ASan and UBSan."""
import verify_dungeon_rewards as base
from dungeon_history_fixtures import c_dungeon_history
h = base.harness
h.CASES = c_dungeon_history() + h.CASES[:h.CASES.index('int main(')] + r'''
static void unlock_all(void){s_challenge.defeated=0x3fff;for(unsigned i=0;i<8;i++)s_regions.region[i].claimed=1;}
static void habitats(void){
 exploration_regions_t rs={0};assert(exploration_map_open(0,0,&rs));
 for(unsigned map=4;map<12;map++){
  const exploration_region_t *r=exploration_region(map);assert(r&&r->min_level<=r->max_level);
  assert(!exploration_map_open(map,0,&rs));assert(!exploration_map_open(map,0x3fff&~r->gate,&rs));
  rs.region[0].claimed=1;assert(exploration_map_open(map,0x3fff,&rs));
  for(unsigned i=0;i<24&&r->pool[i];i++){assert(exploration_habitat(r->pool[i],NULL)>=0);for(unsigned j=0;j<i;j++)assert(r->pool[i]!=r->pool[j]);}
  for(unsigned dir=0;dir<3;dir++){
   unsigned n4=0,n5=0;
   for(unsigned seed=1;seed<=3000;seed++){
    encounter_t e={0};rs.dungeon_pity=0;assert(exploration_region_partner(map,dir,false,seed,0x3fff,&rs,&e));
    unsigned rarity=0;assert(exploration_habitat(e.species_id,&rarity)>=0&&e.rarity==rarity&&rarity>=4);
    n4+=rarity==4;n5+=rarity==5;
   }
   assert(n4&&n5);assert(n5>400&&n5<850);
   rs.dungeon_pity=4;encounter_t e;assert(exploration_region_partner(map,dir,false,7,0x3fff,&rs,&e)&&e.rarity==5&&!rs.dungeon_pity);
  }
 }
 // No high level map bypasses a species' original progression gate.
 for(unsigned map=4;map<12;map++)for(unsigned seed=1;seed<=1000;seed++){
  rs=(exploration_regions_t){.selected=map};rs.region[0].claimed=1;rs.region[map-4].steps=seed;
  enc_refresh_state_t r={0};enc_queue_t q={0};dex_t d={0};inventory_t bag={0};
  uint16_t wins=exploration_region(map)->gate;
  exploration_event_t e=exploration_region_step(&rs,&r,&q,&d,0,wins,&bag,0);
  assert(e.kind==EXPLORE_ENCOUNTER&&exploration_species_open(e.species,wins));
 }
 tests++;
}
static void odds(void){
 unsigned total=0,shiny=0;
 for(unsigned map=4;map<12;map++)for(unsigned depth=0;depth<2;depth++){
  unsigned rare=0;
  for(unsigned seed=1;seed<=10000;seed++){
   exploration_regions_t rs={.selected=map};rs.region[0].claimed=1;rs.region[map-4].steps=seed;rs.region[map-4].deep=depth;
   enc_refresh_state_t r={0};enc_queue_t q={0};dex_t d={0};inventory_t bag={0};
   exploration_event_t e=exploration_region_step(&rs,&r,&q,&d,0,0x3fff,&bag,0);
   assert(e.kind==EXPLORE_ENCOUNTER);rare+=e.rarity>=4;shiny+=e.shiny;total++;
  }
  assert(rare>(depth?6000:3700)&&rare<(depth?7000:4800));
 }
 assert(shiny>total/60&&shiny<total/38);
 for(unsigned map=4;map<12;map++)for(unsigned dir=0;dir<=3;dir++){
  exploration_regions_t rs={.selected=map};rs.region[0].claimed=1;enc_refresh_state_t r={0};dex_t d={0};inventory_t bag={0};
  for(unsigned n=0;n<200;n++){
   enc_queue_t q={0};bool guaranteed=rs.region[map-4].pity==5;
   exploration_event_t e=exploration_region_step(&rs,&r,&q,&d,0,0x3fff,&bag,dir);
   assert(e.kind==EXPLORE_ENCOUNTER||e.kind==EXPLORE_TARGET||e.kind==EXPLORE_CLUE);
   if(guaranteed&&e.kind==EXPLORE_ENCOUNTER)assert(e.rarity>=4);
   assert(exploration_regions_valid(&rs));
  }
 }
 tests++;
}
static void region_transactions(void){
 setup();assert(world_exploration_select(4)==EXPLORE_RESEARCH_LOCKED);
 unlock_all();s_challenge.session.active=0;assert(world_exploration_select(4)==EXPLORE_NONE);
 exploration_regions_t before=s_regions;int32_t stamina=s_w.pet.stamina;
 failure=4;assert(world_explore_path(1).kind==EXPLORE_SAVE_FAILED);assert(!memcmp(&before,&s_regions,sizeof(before))&&stamina==s_w.pet.stamina);failure=0;
 exploration_event_t e=world_explore_path(1);assert(e.kind==EXPLORE_ENCOUNTER&&e.level>=35&&e.level<=45);
 assert(s_w.pet.stamina==stamina-NURT_EXPLORE_COST);before=s_regions;restart();assert(!memcmp(&before,&s_regions,sizeof(before)));
 assert(world_exploration_depth()==EXPLORE_RESEARCH_LOCKED);
 const exploration_region_t *r=exploration_region(4);for(unsigned i=0;i<5;i++)dex_mark_caught(&s_dex,r->pool[i],false);
 assert(world_exploration_depth()==EXPLORE_NONE);assert(s_regions.region[0].deep);
 s_regions.region[0].claimed=0;s_regions.region[0].traced=1;s_regions.region[0].clears=0;
 uint16_t gain;assert(world_research_claim(4,&gain)==EXPLORE_RESEARCH_LOCKED);s_regions.region[0].clears=1;
 assert(world_research_claim(4,&gain)==EXPLORE_NONE&&gain);assert(world_research_claim(4,&gain)==EXPLORE_RESEARCH_CLAIMED);
 save_t saved,out;assert(save_read_status(&saved)==SAVE_READ_OK);saved.regions.selected=12;assert(save_decode(&out,&saved,sizeof(saved),0)==SAVE_READ_ERROR);
 tests++;
}
static void theme_rewards(void){
 for(unsigned theme=1;theme<=9;theme++){
  setup();unlock_all();assert(dungeon_theme_open(theme));assert(dungeon_new_theme(chosen,3,theme,theme,false));
  unsigned max=theme==9?100:exploration_region(theme+3)->max_level,min=theme==9?70:exploration_region(theme+3)->min_level;
  for(unsigned i=0;i<run.battle.session.sides[1].count;i++)assert(run.battle.session.sides[1].mons[i].level>=min&&run.battle.session.sides[1].mons[i].level<=max);
  win(0);assert(dungeon_finish()&&run.receipt.xp>150);assert(dungeon_choose(0));
  win(7);assert(dungeon_finish()&&run.phase==DUNGEON_TRAIL&&!run.pending);
  int32_t stamina=s_w.pet.stamina;party_t before=s_party;failure=4;
  assert(!dungeon_choose(1)&&run.pending);assert(!memcmp(&before,&s_party,sizeof(before)));failure=0;
  assert(dungeon_resume()&&run.receipt.partner_species&&run.receipt.first_clear);
  before=s_party;exploration_regions_t regions=s_regions;restart();assert(dungeon_resume()&&!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&regions,&s_regions,sizeof(regions)));
  assert(s_w.pet.stamina==stamina);
  if(theme<9){assert(s_regions.region[theme-1].clears==1);assert(dungeon_new_theme(chosen,3,theme,theme,true));}
 }
 tests++;
}
static void overflow(void){
 setup();unlock_all();assert(dungeon_new_theme(chosen,3,811,1,false));
 for(unsigned i=0;i<ITEM_COUNT;i++)s_inventory.quantity[i]=items_capacity(i);
 enc_queue_init(&s_queue);for(unsigned i=0;i<ENC_QUEUE_LIMIT;i++){encounter_t e={.species_id=i+1,.rarity=1,.hp_ratio=100,.is_shiny=i==0};enc_queue_push(&s_queue,&e);}
 enc_queue_t before=s_queue;win(7);assert(dungeon_finish());assert(dungeon_choose(2));
 assert(run.receipt.full&&s_regions.pending_partner.species_id&&!memcmp(&before,&s_queue,sizeof(before)));
 assert(s_regions.pending_items.quantity[ITEM_WATER_STONE]==1&&!world_dungeon_ready());
 restart();assert(s_regions.pending_partner.species_id&&s_queue.items[0].is_shiny);
 assert(!world_region_collect());s_inventory.quantity[ITEM_WATER_STONE]--;s_inventory.quantity[ITEM_ULTRA]-=2;
 enc_queue_take_uid(&s_queue,s_queue.items[1].uid,NULL);assert(world_region_collect());assert(!s_regions.pending_partner.species_id&&s_queue.items[0].is_shiny);
 assert(!s_regions.pending_items.quantity[ITEM_WATER_STONE]);tests++;
}
static void run_migration(void){
 setup();assert(sizeof(dungeon_history)==sizeof(dungeon_v3_t));
 memcpy(run_disk,dungeon_history,sizeof(dungeon_history));run_len=sizeof(dungeon_history);loaded=false;dungeon_load();
 assert(run.version==4&&!run.theme&&run.phase==DUNGEON_FORK&&run.seed==91273&&run.run_id==23);
 assert(run.node==1&&run.cards==(1u<<3)&&run.count==2&&run.members[0].species_id==6&&run.members[1].species_id==9&&run.members[1].flags==1);
 assert(run.battle.session.sides[0].mons[0].hp==72&&dungeon_resume());tests++;
}
int main(void){assert(assets_init());habitats();odds();region_transactions();theme_rewards();overflow();run_migration();printf("{\"passed\":true,\"maps\":8,\"themes\":9,\"samples\":246424,\"checks\":%u,\"save_bytes\":%zu,\"sanitizers\":true}\n",tests,sizeof(save_t));return 0;}
'''
if __name__ == '__main__':h.run()
