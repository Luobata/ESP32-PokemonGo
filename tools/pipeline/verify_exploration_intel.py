#!/usr/bin/env python3
"""Optional intel, save rollback, legacy balance, recovery and rarity distribution."""
import json
import verify_world_party as h
import verify_exploration_routes as base
h.CASES=base.CASES[:base.CASES.index('static void core')]+r'''
int main(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 s_exploration.energy=0;s_exploration.pulse[0]=1;s_w.pet.stamina=5*NURT_Q;
 exploration_event_t e=world_explore();assert(e.kind==EXPLORE_CLUE&&s_exploration.energy==0&&s_w.pet.stamina==0);
 assert(world_explore().kind==EXPLORE_NO_STAMINA);
 s_exploration.energy=17;s_w.pet.stamina=10*NURT_Q;world_debug_save();reboot();
 assert(s_exploration.energy==17);s_exploration.pulse[0]=1;s_exploration.clues[0]=0;
 failure=4;e=world_explore();assert(e.kind==EXPLORE_SAVE_FAILED&&s_exploration.energy==17&&s_w.pet.stamina==10*NURT_Q);
 failure=0;e=world_explore();assert(e.kind==EXPLORE_CLUE&&s_exploration.energy==16&&s_w.pet.stamina==5*NURT_Q);
 reboot();assert(s_exploration.energy==16&&s_w.pet.stamina==5*NURT_Q);
 nurture_t pet;nurture_init(&pet);pet.stamina=0;nurture_tick(&pet,0,0,false);
 for(unsigned second=1;second<=7200;second++)nurture_tick(&pet,(int64_t)second*1000000,0,false);
 assert(pet.stamina==NURT_MAX);assert(nurture_wait_minutes(&pet,100)==0);
 unsigned rare[2]={0},items[2]={0};
 for(unsigned n=0;n<10000;n++)for(unsigned intel=0;intel<2;intel++){
  exploration_state_t x={.route=n%4,.energy=intel,.steps=n};enc_refresh_state_t r={0};enc_queue_t q;enc_queue_init(&q);dex_t d;dex_init(&d);inventory_t bag={0};
  e=exploration_step_team(&x,&r,&q,&d,0,16383,&bag,&pet,0);
  assert(e.kind==EXPLORE_ENCOUNTER&&x.energy==0);rare[intel]+=e.rarity>=4;
  x=(exploration_state_t){.route=n%4,.energy=intel,.steps=n};x.pulse[x.route]=1;
  e=exploration_step_team(&x,&r,&q,&d,0,16383,&bag,&pet,0);
  assert(e.kind==EXPLORE_CLUE&&x.energy==0);items[intel]+=e.quantity>0;
 }
 assert(rare[1]>rare[0]&&items[1]>items[0]);
 printf("{\"passed\":true,\"rare_without\":%u,\"rare_with\":%u,\"items_without\":%u,\"items_with\":%u,\"samples_each\":10000,\"recovery_seconds\":7200}\n",rare[0],rare[1],items[0],items[1]);return 0;
}
'''
if __name__=='__main__':print(json.dumps(h.run(h.ROOT)))
