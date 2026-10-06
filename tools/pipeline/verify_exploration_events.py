#!/usr/bin/env python3
"""Production migration visitors, care bonuses, durable events and failed saves."""
import verify_dungeon_rewards as base
h=base.harness
h.CASES=h.CASES[:h.CASES.index('int main(')]+r'''
static void visitors(void){
 for(unsigned map=4;map<12;map++){
  bool found[152]={0};uint8_t all[12];unsigned total=exploration_guest_candidates(map,all);assert(total>=5);
  for(unsigned step=0;step<240;step+=12)for(unsigned direction=0;direction<3;direction++){
   uint8_t a[2],b[2];assert(exploration_visitors(map,direction,step,0x3fff,a)==2);
   assert(exploration_visitors(map,direction,step+11,0x3fff,b)==2&&!memcmp(a,b,2));
   assert(a[0]!=a[1]);for(unsigned i=0;i<2;i++){unsigned rarity=0;assert(exploration_species_open(a[i],0x3fff));assert(exploration_habitat(a[i],&rarity)>=0&&rarity>=2&&rarity<=4);found[a[i]]=true;}
   assert(exploration_visitors(map,direction,step+12,0x3fff,b)==2&&memcmp(a,b,2));
  }
  for(unsigned i=0;i<total;i++)assert(found[all[i]]);
 }
 // Concrete ecology anchors, not only self-consistency against the same table.
 uint8_t a[12];unsigned n=exploration_guest_candidates(4,a);bool squirtle=false;for(unsigned i=0;i<n;i++)squirtle|=a[i]==7;assert(squirtle);
 n=exploration_guest_candidates(5,a);bool golbat=false;for(unsigned i=0;i<n;i++)golbat|=a[i]==42;assert(golbat);
}
static void care(void){
 nurture_t n={0};assert(nurture_exp_percent(&n)==100&&nurture_event_percent(&n)==12&&nurture_capture_percent(&n)==100);
 n.satiety=NURT_MAX;assert(nurture_exp_percent(&n)==125);
 n.mood=NURT_MAX;assert(nurture_exp_percent(&n)==135&&nurture_event_percent(&n)==32);
 n.intimacy=NURT_MAX;assert(nurture_exp_percent(&n)==155&&nurture_capture_percent(&n)==150);
 unsigned last=0;for(unsigned i=0;i<=100;i++){n.intimacy=i*NURT_Q;unsigned v=nurture_capture_percent(&n);assert(v>=last);last=v;}
}
static void event_odds(void){
 unsigned low=0,high=0,kind[4]={0},sparkle_shiny=0;
 for(unsigned i=1;i<=40000;i++)for(unsigned mood=0;mood<2;mood++){
  enc_queue_t q={0};dex_t dex={0};inventory_t bag={0};nurture_t pet={.mood=mood?NURT_MAX:0};
  encounter_t enc={.species_id=25,.rarity=2,.hp_ratio=100,.activity=9,.is_shiny=enc_shiny_from_roll(i,SHINY_EXPLORATION)};enc_queue_push(&q,&enc);
  exploration_event_t e={.kind=EXPLORE_ENCOUNTER,.species=25,.uid=q.items[0].uid,.route=i%12};
  exploration_special_apply(&e,&q,&dex,&bag,&pet,i);
  if(mood){high+=!!e.special;kind[e.special]++;if(e.special==EXPLORE_SPECIAL_SPARKLE)sparkle_shiny+=e.shiny;}else low+=!!e.special;
 }
 assert(low>4000&&low<5600&&high>12000&&high<13600&&high>low*2);
 assert(kind[EXPLORE_SPECIAL_TRAINING]>5500&&kind[EXPLORE_SPECIAL_SPARKLE]>5500);
 assert(sparkle_shiny>kind[EXPLORE_SPECIAL_SPARKLE]/30&&sparkle_shiny<kind[EXPLORE_SPECIAL_SPARKLE]/18);
 printf("events low=%u high=%u sparkle=%u/%u\n",low,high,sparkle_shiny,kind[EXPLORE_SPECIAL_SPARKLE]);
}
static void transactions(void){
 unsigned observed[4]={0};
 for(unsigned step=0;step<120;step++){
  setup();s_challenge.defeated=0x3fff;assert(world_exploration_select(4)==EXPLORE_NONE);
  s_regions.region[0].steps=step;s_regions.region[0].pulse=step%2;world_debug_save();
  unsigned char original[sizeof(disk)];memcpy(original,disk,sizeof(disk));inventory_t bag=s_inventory;party_t party=s_party;exploration_regions_t regions=s_regions;
  failure=4;exploration_event_t e=world_explore_path(1);failure=0;
  assert(e.kind==EXPLORE_SAVE_FAILED&&!memcmp(original,disk,sizeof(disk))&&!memcmp(&bag,&s_inventory,sizeof(bag))&&!memcmp(&party,&s_party,sizeof(party))&&!memcmp(&regions,&s_regions,sizeof(regions)));
  e=world_explore_path(1);assert(e.kind==EXPLORE_CLUE||e.kind==EXPLORE_ENCOUNTER);observed[e.special]++;
  bag=s_inventory;party=s_party;regions=s_regions;enc_queue_t queue=s_queue;restart();
  assert(!memcmp(&bag,&s_inventory,sizeof(bag))&&!memcmp(&party,&s_party,sizeof(party))&&!memcmp(&regions,&s_regions,sizeof(regions))&&!memcmp(&queue,&s_queue,sizeof(queue)));
  uint8_t a[2],b[2];exploration_visitors(4,0,regions.region[0].steps,0x3fff,a);assert(world_exploration_select(0)==EXPLORE_NONE&&world_exploration_select(4)==EXPLORE_NONE);exploration_visitors(4,0,s_regions.region[0].steps,0x3fff,b);assert(!memcmp(a,b,2));
 }
 for(unsigned i=0;i<4;i++)assert(observed[i]>0);
 // Full food stacks are capped; no underflow or implicit reward reset.
 for(unsigned i=0;i<100;i++){exploration_event_t e={.kind=EXPLORE_CLUE};enc_queue_t q={0};dex_t d={0};inventory_t bag={0};bag.quantity[ITEM_BERRY]=items_capacity(ITEM_BERRY);nurture_t pet={.mood=NURT_MAX};exploration_special_apply(&e,&q,&d,&bag,&pet,i);assert(bag.quantity[ITEM_BERRY]==items_capacity(ITEM_BERRY)&&!e.extra_quantity);}
}
int main(void){assert(assets_init());visitors();care();event_odds();transactions();printf("{\"passed\":true,\"visitors\":true,\"events\":true,\"care\":true,\"rollback_reboot\":true,\"save_version\":%u}\n",SAVE_VERSION);}
'''
if __name__=='__main__':h.run()
