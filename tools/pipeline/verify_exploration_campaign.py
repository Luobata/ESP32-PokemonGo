#!/usr/bin/env python3
"""Campaign gates and item transactions in actual exploration/world/save C."""
import json,subprocess
import verify_world_party as h
import verify_exploration_routes as base
prefix=base.CASES[:base.CASES.index('static void core')]
h.CASES=prefix+r'''
static void campaign(void){
 unsigned masks[]={0,1,3,15,63,255,4095,8191,16383};
 unsigned targets[][4]={{25,95,131,125},{123,95,131,125},{123,95,138,125},{123,142,138,125},{123,142,138,135},{123,146,138,135},{149,146,144,145},{149,150,144,145},{151,150,144,145}};
 for(unsigned c=0;c<9;c++){
  assert(exploration_chapter_current(masks[c])==c);
  if(c<8)assert(!exploration_chapter_open(c+1,masks[c]));
  bool found_item=false;unsigned seen_items=0;
  exploration_state_t x;exploration_init(&x);enc_refresh_state_t r={0};enc_queue_t q;dex_t d;dex_init(&d);inventory_t bag={0};
  for(unsigned i=0;i<4000;i++){
   enc_queue_init(&q);x.route=i%4;x.energy=24;
   exploration_event_t e=exploration_step_progress(&x,&r,&q,&d,0,masks[c],&bag);
   if(e.species)assert(exploration_species_open(e.species,masks[c]));
   assert(items_inventory_valid(&bag));if(e.item_full)assert(!e.quantity&&bag.quantity[e.item]==items_capacity(e.item));
   if(e.item!=ITEM_NONE){seen_items|=1u<<e.item;found_item=true;bool allowed=false;for(unsigned k=0;k<=c;k++)allowed|=exploration_chapter(k)->item==e.item;assert(allowed);}
  }
  assert(found_item&&(seen_items&(1u<<exploration_chapter(c)->item)));
  for(unsigned route=0;route<4;route++){
   enc_queue_init(&q);x.route=route;x.clues[route]=3;x.energy=1;
   exploration_event_t e=exploration_step_progress(&x,&r,&q,&d,0,masks[c],&bag);assert(e.kind==EXPLORE_TARGET&&e.species==targets[c][route]);
  }
 }
 // Four elites are required together; unlocking access to the league is insufficient.
 assert(exploration_chapter_current(255)==5);assert(exploration_chapter_current(2047)==5);
 // Obtained progress survives reboot; failed item commits publish nothing.
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_challenge.defeated=16383;
 bool tested=false;
 for(unsigned i=0;i<200;i++){
  s_exploration.energy=24;s_exploration.pulse[0]=1;s_exploration.clues[0]=0;s_exploration.steps=i;
  exploration_state_t x=s_exploration;enc_refresh_state_t r=s_refresh;enc_queue_t q=s_queue;dex_t d=s_dex;inventory_t bag=s_inventory;
  exploration_event_t e=exploration_step_progress(&x,&r,&q,&d,0,s_challenge.defeated,&bag);
  if(!e.quantity)continue;
  inventory_t prior=s_inventory;exploration_state_t previous=s_exploration;
  failure=4;assert(world_explore().kind==EXPLORE_SAVE_FAILED);failure=0;
  assert(!memcmp(&prior,&s_inventory,sizeof(prior))&&!memcmp(&previous,&s_exploration,sizeof(previous)));
  e=world_explore();assert(e.quantity==1&&s_inventory.quantity[e.item]==prior.quantity[e.item]+1);
  world_debug_save();reboot();assert(s_challenge.defeated==16383&&s_exploration.energy==23&&s_inventory.quantity[e.item]==prior.quantity[e.item]+1);
  tested=true;break;
 }
 assert(tested);
}
int main(void){campaign();printf("{\"chapters\":9,\"sequence_steps\":36000,\"targets\":36,\"atomic_item_save\":true,\"save_version\":%d}\n",SAVE_VERSION);return 0;}
'''
try:r=h.run(h.ROOT)
except subprocess.CalledProcessError as e:print(e.stderr);raise
p=h.ROOT/'reports/evidence/routes-story-2026-09-08';p.mkdir(parents=True,exist_ok=True);(p/'campaign.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
