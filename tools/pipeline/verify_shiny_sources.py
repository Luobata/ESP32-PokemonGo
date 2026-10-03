#!/usr/bin/env python3
"""Source-specific shiny odds and durable, capturable dungeon completion encounters."""
import verify_dungeon_rewards as base
h=base.harness
prefix=h.CASES[:h.CASES.index('static void admission')]
h.CASES=prefix+r'''
static void odds(void){
 const unsigned denom[]={64,48,32,16};
 for(unsigned source=0;source<SHINY_SOURCE_COUNT;source++){
  unsigned shiny=0;assert(enc_shiny_denominator(source)==denom[source]);
  for(unsigned roll=0;roll<6144;roll++)shiny+=enc_shiny_from_roll(roll,source);
  assert(shiny==6144/denom[source]);
 }
 assert(!enc_shiny_denominator(SHINY_SOURCE_COUNT));
 assert(!enc_shiny_from_roll(0,(shiny_source_t)-1));tests++;
 // A single dungeon channel includes common and rare species, all at the same odds.
 unsigned total[6]={0},shiny[6]={0};enc_queue_t q={0};
 for(unsigned seed=0;seed<10000;seed++){
  encounter_t e,again;assert(exploration_dungeon_partner(seed,1,16383,&q,&e));
  assert(exploration_dungeon_partner(seed,1,16383,&q,&again)&&!memcmp(&e,&again,sizeof(e)));
  assert(exploration_habitat(e.species_id,NULL)==0&&exploration_species_open(e.species_id,16383));
  total[e.rarity]++;shiny[e.rarity]+=e.is_shiny;
 }
 for(unsigned rarity=1;rarity<=5;rarity++){
  assert(total[rarity]>100);
  // Broad deterministic sample bound: no rare-species shiny multiplier.
  assert(shiny[rarity]*100>total[rarity]*3&&shiny[rarity]*100<total[rarity]*10);
 }
 tests++;
}
static void clear_partner(void){
 setup();assert(dungeon_new(chosen,3,41));
 for(unsigned i=0;i<5;i++){encounter_t e={.species_id=60+i,.level=5,.rarity=1,.hp_ratio=100};enc_queue_push(&s_queue,&e);}
 world_debug_save();enc_queue_t before=s_queue;dex_t dex_before=s_dex;uint16_t oldest=s_queue.items[0].uid;
 win(7);failure=4;assert(!dungeon_finish());
 assert(!memcmp(&before,&s_queue,sizeof(before))&&!memcmp(&dex_before,&s_dex,sizeof(dex_before))&&!s_dungeon.clears);
 failure=0;assert(dungeon_resume());
 assert(s_queue.count==5&&!enc_queue_find(&s_queue,oldest));
 encounter_t found=s_queue.items[4];
 assert(found.species_id==run.receipt.partner_species&&found.is_shiny==run.receipt.partner_shiny);
 assert(found.level>=1&&found.level<=100&&!found.activity);
 assert(dex_is_seen(&s_dex,found.species_id)&&s_w.pending==5);
 before=s_queue;restart();assert(dungeon_resume());
 assert(!memcmp(&before,&s_queue,sizeof(before))&&s_dungeon.clears==1);
 mon_t m={.species_id=found.species_id,.level=found.level,.exp=exp_for_level(found.level),.hp=100,.flags=found.is_shiny?1:0};
 assert(world_capture_uid(found.uid,&m));assert(dex_is_caught(&s_dex,found.species_id));
 if(found.is_shiny)assert(dex_is_shiny_caught(&s_dex,found.species_id));
 assert(!world_capture_uid(found.uid,&m));tests++;
 // World reward committed, dungeon acknowledgement failed: replay returns same receipt.
 setup();assert(dungeon_new(chosen,3,43));win(7);run_fail_after=1;
 assert(!dungeon_finish());assert(run.pending&&s_queue.count==1&&s_dungeon.clears==1);
 before=s_queue;dungeon_receipt_t receipt=s_dungeon.receipt;
 restart();assert(dungeon_resume());assert(!memcmp(&before,&s_queue,sizeof(before)));
 assert(run.receipt.partner_species==receipt.partner_species&&run.receipt.partner_shiny==receipt.partner_shiny);tests++;
 // Non-clear reward and defeat never generate a partner.
 setup();assert(dungeon_new(chosen,3,44));win(0);assert(dungeon_finish());
 assert(!s_queue.count&&!run.receipt.partner_species);tests++;
}
static void legacy_layout(void){
 struct old_receipt {uint32_t xp;inventory_t items;uint8_t first_clear,first_elite,full;};
 _Static_assert(sizeof(struct old_receipt)==sizeof(dungeon_receipt_t),"receipt size unchanged");
 struct old_receipt old;memset(&old,0,sizeof(old));old.xp=100;old.first_clear=1;
 dungeon_receipt_t migrated;memcpy(&migrated,&old,sizeof(old));
 assert(migrated.xp==100&&migrated.first_clear&&!migrated.partner_species&&!migrated.partner_shiny);
 dungeon_progress_t p={.receipt=migrated};assert(dungeon_progress_valid(&p));
 p.receipt.partner_species=152;assert(!dungeon_progress_valid(&p));tests++;
}
int main(void){assert(assets_init());odds();clear_partner();legacy_layout();printf("{\"checks\":%u,\"source_denominators\":[64,48,32,16],\"dungeon_candidate_samples\":10000,\"single_durable_encounter_per_clear\":true,\"capture_verified\":true,\"receipt_layout_unchanged\":true}\n",tests);}
'''
if __name__=='__main__':h.run()
