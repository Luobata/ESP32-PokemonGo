#!/usr/bin/env python3
"""Paid exploration stays usable with duplicate species; real C transactions."""
import verify_trainer_campaign as harness

harness.CASES = r'''
static unsigned cases;
static encounter_t existing(unsigned id) {
 return (encounter_t){.species_id=id,.rarity=2,.hp_ratio=37,.level=30,
  .is_shiny=true,.activity=ENC_ACTIVITY_EXPLORATION,.ts=123};
}
static void targets(void) {
 for(unsigned map=0;map<12;map++) {
  exploration_state_t x={.route=map<4?map:0};
  exploration_regions_t regions={.selected=map};regions.region[0].claimed=1;
  enc_refresh_state_t refresh={0};enc_queue_t q={0};dex_t dex={0};inventory_t bag={0};
  unsigned target;
  if(map<4){x.clues[map]=3;target=exploration_route(map)->target;}
  else {regions.region[map-4].clues=3;target=exploration_region_target(map,&regions,0x3fff,&dex);}
  assert(target);encounter_t old=existing(target);enc_queue_push(&q,&old);old=q.items[0];
  // Sequence wraps over an active ID and an already queued ID.
  q.next_uid=UINT16_MAX;
  exploration_event_t e=map<4?exploration_step_with_target(&x,&refresh,&q,&dex,UINT16_MAX,0x3fff,&bag,NULL,0,target)
   :exploration_region_step(&regions,&refresh,&q,&dex,UINT16_MAX,0x3fff,&bag,1);
  assert(e.kind==EXPLORE_TARGET&&e.species==target&&e.uid!=old.uid&&e.uid!=UINT16_MAX);
  assert(q.count==2&&!memcmp(&q.items[0],&old,sizeof(old))&&q.items[1].uid==e.uid);
  assert(map<4?x.clues[map]==0:regions.region[map-4].clues==0);cases++;
 }
}
static void continuous(void) {
 // Leave every discovery pending. Low-tier pools and pity must never stall.
 for(unsigned map=0;map<12;map++)for(unsigned trail=0;trail<(map<4?1u:3u);trail++) {
  exploration_state_t x={.route=map<4?map:0};
  exploration_regions_t regions={.selected=map};regions.region[0].claimed=1;
  enc_refresh_state_t refresh={0};enc_queue_t q={0};dex_t dex={0};inventory_t bag={0};
  for(unsigned step=0;step<500;step++) {
   unsigned before=q.count;uint16_t first=q.count?q.items[0].uid:0;
   exploration_event_t e=map<4?exploration_step_progress(&x,&refresh,&q,&dex,0,0x3fff,&bag)
    :exploration_region_step(&regions,&refresh,&q,&dex,0,0x3fff,&bag,trail+1);
   assert(e.kind==EXPLORE_CLUE||e.kind==EXPLORE_ENCOUNTER||e.kind==EXPLORE_TARGET);
   assert(q.count<=ENC_QUEUE_LIMIT);
   if(e.uid){
    assert(enc_queue_find(&q,e.uid)&&exploration_species_open(e.species,0x3fff));
    assert(q.items[q.count-1].uid==e.uid);
    if(before==ENC_QUEUE_LIMIT)assert(q.count==before&&!enc_queue_find(&q,first));
   }
   for(unsigned i=0;i<q.count;i++)for(unsigned j=i+1;j<q.count;j++)assert(q.items[i].uid!=q.items[j].uid);
   cases++;
  }
 }
}
static void transactions(void) {
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
 s_w.pet.stamina=NURT_MAX;s_exploration.clues[0]=3;s_exploration.tracked_species=25;
 enc_queue_init(&s_queue);
 for(unsigned i=0;i<ENC_QUEUE_LIMIT;i++){encounter_t e=existing(i==2?25:10+i);e.hp_ratio=100;enc_queue_push(&s_queue,&e);}
 world_debug_save();reboot();
 assert(s_queue.count==ENC_QUEUE_LIMIT);
 enc_queue_t before=s_queue;exploration_state_t trail=s_exploration;
 inventory_t bag=s_inventory;party_t party=s_party;dex_t dex=s_dex;int32_t stamina=s_w.pet.stamina;
 unsigned char saved[sizeof(disk)];
 for(unsigned i=0;i<3;i++) {
  size_t bytes=disk_len;memcpy(saved,disk,sizeof(disk));
  failure=(int[]){1,2,4}[i];exploration_event_t e=world_explore();failure=0;
  assert(e.kind==EXPLORE_SAVE_FAILED&&s_w.pet.stamina==stamina&&disk_len==bytes&&!memcmp(saved,disk,sizeof(disk)));
  assert(!memcmp(&s_queue,&before,sizeof(before))&&!memcmp(&s_exploration,&trail,sizeof(trail)));
  assert(!memcmp(&s_inventory,&bag,sizeof(bag))&&!memcmp(&s_party,&party,sizeof(party))&&!memcmp(&s_dex,&dex,sizeof(dex)));
  // A rejected candidate must not leak into the next ordinary checkpoint.
  world_debug_save();reboot();assert(!memcmp(&s_queue,&before,sizeof(before))&&s_exploration.clues[0]==3);cases++;
 }
 exploration_event_t e=world_explore();assert(e.kind==EXPLORE_TARGET&&e.species==25);
 assert(s_w.pet.stamina==stamina-NURT_EXPLORE_COST&&s_queue.count==ENC_QUEUE_LIMIT);
 assert(!enc_queue_find(&s_queue,before.items[0].uid));
 const encounter_t *retained=enc_queue_find(&s_queue,before.items[2].uid);
 assert(retained&&!memcmp(retained,&before.items[2],sizeof(*retained))&&e.uid!=retained->uid);
 before=s_queue;world_debug_save();reboot();
 assert(!memcmp(&before,&s_queue,sizeof(before))&&s_exploration.clues[0]==0&&s_exploration.tracked_species==25);
 assert(s_w.pet.stamina==stamina-NURT_EXPLORE_COST);cases++;
 // An unfinished badge activity remains one battle, with no repeat entry charge.
 s_challenge.defeated=1;s_w.pet.stamina=NURT_MAX;
 e=world_exploration_activity(0,false);assert(e.kind==EXPLORE_ENCOUNTER);stamina=s_w.pet.stamina;before=s_queue;
 assert(world_exploration_activity(0,false).kind==EXPLORE_BLOCKED);
 assert(s_w.pet.stamina==stamina&&!memcmp(&s_queue,&before,sizeof(before)));cases++;
}
int main(void) {
 assert(assets_init());targets();continuous();transactions();
 printf("{\"passed\":true,\"cases\":%u,\"save_version\":%u,\"save_bytes\":%zu,\"erase_calls\":%u}\n",cases,SAVE_VERSION,sizeof(save_t),erase_calls);
 return 0;
}
'''

if __name__ == '__main__':
    harness.run()
