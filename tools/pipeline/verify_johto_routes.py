#!/usr/bin/env python3
"""Shared Johto route generator and real world/save transactions, fatal ASan/UBSan."""
import verify_trainer_campaign as harness

CASES=r'''
static save_t base,candidate,before,after;
static void ready(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_challenge.defeated=255;
 assert(world_johto_visit()==WORLD_JOHTO_OK);assert(world_johto_depart()==WORLD_JOHTO_OK);assert(world_johto_starter(152)==WORLD_JOHTO_OK);
 s_johto.badges=255;assert(johto_receive_egg(&s_johto,123));s_w.pet.stamina=100*NURT_Q;world_debug_save();assert(save_read(&base));
}
static void pools(void){
 ready();unsigned stops=0,encounters=0;bool encountered[8][3][4]={0};
 for(unsigned route=0;route<8;route++){
  bool covered[252]={0};
  for(unsigned path=0;path<3;path++){
   const johto_path_t *p=johto_path(route,path);assert(p);
   for(unsigned i=0;i<4;i++){assert(p->species[i]>151&&p->species[i]<=248&&p->species[i]!=201);covered[p->species[i]]=true;}
   for(unsigned seed=0;seed<500;seed++){
    candidate=base;johto_search_t e;assert(johto_search_apply(&candidate,route,path,seed,&e));
    assert(candidate.johto.research[route]==1&&candidate.johto.explorations==1&&candidate.johto.egg_steps==1);
    assert(candidate.pet.stamina==base.pet.stamina-NURT_EXPLORE_COST&&e.clues==1&&e.route==route&&e.path==path);
    if(e.kind==JOHTO_SEARCH_CLUE){assert(e.quantity&&e.item<ITEM_COUNT);assert(candidate.inventory.quantity[e.item]==base.inventory.quantity[e.item]+e.quantity);stops++;}
    else {assert(e.kind==JOHTO_SEARCH_ENCOUNTER);bool match=false;for(unsigned i=0;i<4;i++)if(e.encounter.species_id==p->species[i]){match=true;encountered[route][path][i]=true;}assert(match);
     assert(e.encounter.level>=JOHTO_ROUTES[route].min_level&&e.encounter.level<=JOHTO_ROUTES[route].max_level);
     assert(dex_is_seen(&candidate.dex,e.encounter.species_id));encounters++;}
    assert(save_validate_world(&candidate,&candidate.members));
   }
   for(unsigned i=0;i<4;i++)assert(encountered[route][path][i]);
  }
  for(unsigned i=0;i<JOHTO_ROUTES[route].count;i++)assert(JOHTO_ROUTES[route].species[i]==201||covered[JOHTO_ROUTES[route].species[i]]);
  candidate=base;unsigned target=johto_track_target(&candidate.johto,route);
  for(unsigned step=0;step<8;step++){
   johto_search_t e;assert(johto_search_apply(&candidate,route,step%3,73+step,&e));
   if(step%4==3){assert(e.kind==JOHTO_SEARCH_TARGET&&e.encounter.species_id==target&&e.clues==0);assert(johto_track_target(&candidate.johto,route)!=target);target=johto_track_target(&candidate.johto,route);}
   else assert(e.kind!=JOHTO_SEARCH_TARGET&&johto_track_target(&candidate.johto,route)==target);
  }
 }
 assert(stops>4000&&stops<5500&&encounters>6500);
 printf("24 branch pools / 12000 seeded investigations: clues=%u encounters=%u; all 24 branches covered\n",stops,encounters);
}
static void boundaries(void){
 ready();johto_search_t e,unchanged;memset(&e,0xa5,sizeof(e));unchanged=e;
 candidate=base;assert(!johto_search_apply(&candidate,8,0,0,&e));assert(!johto_search_apply(&candidate,0,3,0,&e));assert(!memcmp(&candidate,&base,sizeof(base))&&!memcmp(&e,&unchanged,sizeof(e)));
 candidate.pet.stamina=NURT_EXPLORE_COST-1;before=candidate;assert(!johto_search_apply(&candidate,0,0,0,&e)&&!memcmp(&candidate,&before,sizeof(before)));
 candidate=base;candidate.johto.badges=0;before=candidate;assert(!johto_search_apply(&candidate,7,0,0,&e)&&!memcmp(&candidate,&before,sizeof(before)));
 candidate=base;candidate.johto.last_action=UINT32_MAX;before=candidate;assert(!johto_search_apply(&candidate,0,0,0,&e)&&!memcmp(&candidate,&before,sizeof(before)));
 candidate=base;candidate.johto.research[0]=UINT16_MAX;candidate.johto.explorations=UINT16_MAX;candidate.johto.last_action=UINT16_MAX;
 unsigned target=johto_track_target(&candidate.johto,0);assert(johto_search_apply(&candidate,0,0,0,&e));assert(e.kind==JOHTO_SEARCH_TARGET&&e.encounter.species_id==target&&e.clues==0);
 for(unsigned seed=0;seed<100;seed++){
  candidate=base;for(unsigned i=0;i<ITEM_COUNT;i++)candidate.inventory.quantity[i]=items_capacity(i);
  assert(johto_search_apply(&candidate,0,0,seed,&e));if(e.kind==JOHTO_SEARCH_CLUE){assert(!e.quantity&&e.item_full&&candidate.johto.research[0]==1);break;}assert(seed<99);
 }
 // Queue overflow remains five; a later discovery cannot alias an older UID.
 candidate=base;for(unsigned i=0;i<20;i++){candidate.pet.stamina=100*NURT_Q;assert(johto_search_apply(&candidate,0,0,i,&e));assert(candidate.queue.count<=5);for(unsigned j=1;j<candidate.queue.count;j++)assert(candidate.queue.items[j-1].uid!=candidate.queue.items[j].uid);}
}
static void transactions(void){
 for(unsigned fail=0;fail<3;fail++){
  ready();johto_search_t e,untouched;memset(&e,0xa5,sizeof(e));untouched=e;before=base;
  failure=(int[]){1,2,4}[fail];assert(world_johto_search(0,1,&e)==WORLD_JOHTO_SAVE_FAILED);failure=0;
  assert(!memcmp(&e,&untouched,sizeof(e)));assert(!memcmp(&s_johto,&before.johto,sizeof(s_johto)));assert(!memcmp(&s_inventory,&before.inventory,sizeof(s_inventory)));assert(!memcmp(&s_queue,&before.queue,sizeof(s_queue)));assert(!memcmp(&s_dex,&before.dex,sizeof(s_dex)));assert(s_w.pet.stamina==before.pet.stamina);
  // Re-collect after a rejected candidate; ordinary saving must never leak it.
  world_debug_save();assert(save_read(&after));assert(!memcmp(&after,&before,sizeof(before)));reboot();
  assert(world_johto_search(0,1,&e)==WORLD_JOHTO_OK);assert(save_read(&after));reboot();
  assert(after.johto.research[0]==1&&s_johto.research[0]==1&&s_w.pet.stamina==before.pet.stamina-NURT_EXPLORE_COST);
  assert(!memcmp(&s_inventory,&after.inventory,sizeof(s_inventory))&&!memcmp(&s_queue,&after.queue,sizeof(s_queue))&&!memcmp(&s_dex,&after.dex,sizeof(s_dex)));
 }
 ready();johto_search_t e;unsigned target=johto_track_target(&s_johto,6);
 for(unsigned i=0;i<4;i++){assert(world_johto_search(6,i%3,&e)==WORLD_JOHTO_OK);reboot();assert(s_johto.research[6]==i+1);if(i<3)assert(johto_track_target(&s_johto,6)==target);}
 assert(e.kind==JOHTO_SEARCH_TARGET&&e.encounter.species_id==target&&s_johto.egg_steps==4&&s_w.pet.stamina==80*NURT_Q);
 assert(s_story.version==1&&johto_track_target(&s_johto,6)!=target);
 s_w.pet.stamina=0;assert(world_johto_search(0,0,&e)==WORLD_JOHTO_NO_STAMINA);s_w.pet.stamina=100*NURT_Q;
 assert(world_challenge_start(TRAINER_JOHTO_FIRST)==WORLD_CHALLENGE_OK);assert(world_johto_search(0,0,&e)==WORLD_JOHTO_BUSY);assert(!erase_calls);
}
int main(void){assert(assets_init());pools();boundaries();transactions();puts("Johto routes: branch pools, clue/target rotation, egg/story, queue caps, atomic failures and reboot persistence passed");return 0;}
'''
if __name__=='__main__':
 harness.CASES=CASES
 harness.run()
