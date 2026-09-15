#!/usr/bin/env python3
"""V16 trails, badge activities and migration using production C + transactional NVS."""
import json
import subprocess
import verify_world_party as h
import verify_exploration_routes as base
h.CASES=base.CASES[:base.CASES.index('static void core')]+r'''
static void rotations(void){
 const unsigned masks[]={0,1,3,7,15,31,63,127,255,4095,8191,16383};
 unsigned distinct[152]={0},legend=0,total=0;
 for(unsigned m=0;m<12;m++){
  exploration_state_t x={0};exploration_updates_t u={0};enc_queue_t q={0};dex_t d={0};
  exploration_targets_sync(&x,&u,&d,&q,masks[m]);
  for(unsigned round=0;round<1000;round++)for(unsigned route=0;route<4;route++){
   x.route=route;unsigned old=exploration_current_target(&x,&u,masks[m]);
   assert(old&&exploration_species_open(old,masks[m])&&(exploration_habitat(old,NULL)==(int)route||(old==25&&route==3)));
   exploration_updates_t before=u;
   exploration_targets_sync(&x,&u,&d,&q,masks[m]);assert(!memcmp(&before,&u,sizeof(u)));
   exploration_target_completed(&x,&u,&d,&q,masks[m],route);
   assert(u.targets[route]!=old&&exploration_updates_valid(&u));
   distinct[old]++;if(old==150||old==151)legend++;total++;
  }
 }
 assert(legend>0&&legend<total/50);assert(distinct[150]&&distinct[151]);
 // Uncaught preference is statistical, and rare/legendary targets stay rarer.
 dex_t d={0};for(unsigned i=1;i<=151;i++)dex_mark_caught(&d,i,false);
 dex_t missing=d;missing.caught[(137-1)/8]&=~(1u<<((137-1)%8));
 unsigned caught_count=0,missing_count=0;
 for(unsigned seed=1;seed<=20000;seed++){
  exploration_state_t x={.route=3};exploration_updates_t a={0},b={0};enc_queue_t q={0};a.rounds[3]=b.rounds[3]=seed;
  exploration_targets_sync(&x,&a,&d,&q,16383);exploration_targets_sync(&x,&b,&missing,&q,16383);
  caught_count+=a.targets[3]==137;missing_count+=b.targets[3]==137;
 }
 assert(missing_count>caught_count*2);
 // Progression cannot replace an in-progress trail. Manual tracking stays pinned.
 exploration_state_t x={.route=0};exploration_updates_t u={0};enc_queue_t q={0};d=(dex_t){0};
 exploration_targets_sync(&x,&u,&d,&q,0);unsigned old=u.targets[0];x.clues[0]=2;
 exploration_targets_sync(&x,&u,&d,&q,16383);assert(u.targets[0]==old);
 x.tracked_species=25;assert(exploration_current_target(&x,&u,16383)==25);
 exploration_updates_t before=u;exploration_target_completed(&x,&u,&d,&q,16383,0);assert(!memcmp(&u,&before,sizeof(u)));
 tests+=8;
}
static void levels_and_trails(void){
 for(unsigned lv=1;lv<=100;lv++)for(unsigned rarity=1;rarity<=5;rarity++){
  unsigned v=battle_wild_level_for_pet(rarity,lv);assert(v>=2&&v<=100);assert(v<=lv+5||lv==1);
 }
 assert(battle_wild_level_for_pet(5,16)==16);
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);s_w.level=s_party.party[0].level=40;s_w.exp=s_party.party[0].exp=exp_for_level(40);s_w.pet.stamina=NURT_MAX;
 exploration_view_t before,after;world_exploration_snapshot(&before);
 for(int mode=1;mode<=4;mode++){if(mode==3)continue;failure=mode;assert(world_explore().kind==EXPLORE_SAVE_FAILED);failure=0;world_exploration_snapshot(&after);assert(!memcmp(&before,&after,sizeof(before)));}
 exploration_event_t event=world_explore();assert(event.kind==EXPLORE_ENCOUNTER&&event.level>=34&&event.level<=42);
 encounter_t enc;assert(world_get_encounter_uid(event.uid,&enc)&&enc.level==event.level);
 unsigned level=enc.level;world_exploration_snapshot(&before);world_debug_save();reboot();world_exploration_snapshot(&after);
 assert(!memcmp(before.updates.targets,after.updates.targets,4));assert(world_get_encounter_uid(event.uid,&enc)&&enc.level==level);
 s_w.level=80;assert(world_get_encounter_uid(event.uid,&enc)&&enc.level==level);
 s_exploration.clues[0]=3;s_exploration.pulse[0]=0;enc_queue_init(&s_queue);s_w.pet.stamina=NURT_MAX;
 world_exploration_snapshot(&before);event=world_explore();assert(event.kind==EXPLORE_TARGET&&event.species==before.updates.targets[0]);
 world_exploration_snapshot(&after);assert(after.updates.targets[0]!=event.species&&!after.state.clues[0]);
 world_debug_save();reboot();world_exploration_snapshot(&before);assert(!memcmp(&after.updates,&before.updates,sizeof(after.updates)));tests+=7;
}
static void activities(void){
 for(unsigned id=0;id<8;id++){
  fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_w.pet.stamina=NURT_MAX;
  assert(world_exploration_activity(id,false).kind==EXPLORE_RESEARCH_LOCKED);
  s_challenge.defeated=(1u<<(id+1))-1;
  assert(world_exploration_activity(id,true).kind==EXPLORE_RESEARCH_LOCKED);
  for(unsigned stage=0;stage<3;stage++){
   int32_t stamina=s_w.pet.stamina;exploration_updates_t before=s_exploration_updates;enc_queue_t queue=s_queue;
   failure=4;assert(world_exploration_activity(id,false).kind==EXPLORE_SAVE_FAILED);failure=0;
   assert(s_w.pet.stamina==stamina&&!memcmp(&before,&s_exploration_updates,sizeof(before))&&!memcmp(&queue,&s_queue,sizeof(queue)));
   exploration_event_t e=world_exploration_activity(id,false);assert(e.kind==EXPLORE_ENCOUNTER&&e.level==exploration_activity(id)->level+stage);
   assert(s_w.pet.stamina==stamina-NURT_EXPLORE_COST);
   assert(world_exploration_activity(id,false).kind==EXPLORE_BLOCKED&&s_w.pet.stamina==stamina-NURT_EXPLORE_COST);
   // Alternate real capture settlement and real battle reward settlement.
   if(stage!=1){
    mon_t mon={.species_id=e.species,.level=e.level,.hp=100,.exp=exp_for_level(e.level)};
    failure=4;assert(!world_capture_uid(e.uid,&mon));failure=0;assert(s_exploration_updates.activity_progress[id]==stage);
    assert(world_capture_uid(e.uid,&mon));assert(!world_capture_uid(e.uid,&mon));
   }else{
    battle_session_t session={.initialized=true,.started=true,.finished=true,.won=true,.wild_level=e.level,.wild_species=e.species,.pet_species=s_w.species,.pet_level=s_w.level};
    assert(world_battle_set_uid(e.uid,&session));uint16_t amount;
    failure=4;assert(!world_battle_reward_uid(e.uid,&amount));failure=0;assert(s_exploration_updates.activity_progress[id]==stage);
    assert(world_battle_reward_uid(e.uid,&amount));assert(world_battle_reward_uid(e.uid,&amount)&&!amount);
    assert(s_exploration_updates.activity_progress[id]==stage+1);
    mon_t mon={.species_id=e.species,.level=e.level,.hp=100,.exp=exp_for_level(e.level)};
    assert(world_capture_uid(e.uid,&mon)); // Win then capture counts once.
   }
   assert(s_exploration_updates.activity_progress[id]==stage+1);
   reboot();assert(s_exploration_updates.activity_progress[id]==stage+1);
  }
  unsigned reward=exploration_activity(id)->item,quantity=s_inventory.quantity[reward];
  failure=4;assert(world_exploration_activity(id,true).kind==EXPLORE_SAVE_FAILED);failure=0;
  assert(s_exploration_updates.activity_progress[id]==3&&s_inventory.quantity[reward]==quantity);
  s_inventory.quantity[reward]=items_capacity(reward);assert(world_exploration_activity(id,true).item_full&&s_exploration_updates.activity_progress[id]==3);s_inventory.quantity[reward]=quantity;
  exploration_event_t e=world_exploration_activity(id,true);assert(e.kind==EXPLORE_NONE&&e.item==reward&&e.quantity==1);
  assert(s_inventory.quantity[reward]==quantity+1&&!s_exploration_updates.activity_progress[id]);
  assert(world_exploration_activity(id,true).kind==EXPLORE_RESEARCH_LOCKED);
  reboot();assert(s_exploration_updates.activity_claimed&(1u<<id));assert(s_exploration_updates.activity_runs[id]==1);
  s_w.pet.stamina=4*NURT_Q;assert(world_exploration_activity(id,false).kind==EXPLORE_NO_STAMINA);
  tests+=9;
 }
 // The repeat reward always exists, and includes varied supplies plus rarer items.
 exploration_updates_t u={.activity_claimed=255};inventory_t bag={0};unsigned rewards=0;
 for(unsigned run=0;run<1000;run++){u.activity_progress[0]=3;bag=(inventory_t){0};exploration_event_t e={0};assert(exploration_activity_claim(0,&u,&bag,&e)==EXPLORE_NONE);rewards|=1u<<e.item;}
 assert((rewards&(1u<<ITEM_GREAT))&&(rewards&(1u<<ITEM_ULTRA))&&(rewards&(1u<<ITEM_MOON_STONE)));tests++;
}
static void migration(void){
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);s_challenge.defeated=31;s_exploration.clues[0]=2;s_exploration.research_flags=17;world_debug_save();
 save_t current;assert(save_read_status(&current)==SAVE_READ_OK);save_v15_t legacy;memcpy(&legacy,&current,sizeof(legacy));legacy.version=15;
 encounter_t e={.species_id=25,.rarity=2,.hp_ratio=100,.level=255,.activity=255};enc_queue_push(&legacy.queue,&e);
 memcpy(disk,&legacy,sizeof(legacy));disk_len=sizeof(legacy);save_t next;
 assert(save_read_status(&next)==SAVE_READ_MIGRATED&&next.version==SAVE_VERSION);
 assert(!next.queue.items[0].level&&!next.queue.items[0].activity&&next.exploration.clues[0]==2&&next.exploration.research_flags==17);
 assert(!memcmp(next.party,current.party,PARTY_BYTES)&&next.challenge.defeated==31);
 reboot();assert(s_queue.items[0].level>=2&&s_exploration.clues[0]==2);world_debug_save();assert(save_read_status(&next)==SAVE_READ_OK);
 next.queue.items[0].level=101;memcpy(disk,&next,sizeof(next));disk_len=sizeof(next);assert(save_read_status(&current)==SAVE_READ_ERROR);assert(erase_calls==0);tests+=4;
}
int main(void){rotations();levels_and_trails();activities();migration();printf("{\"checks\":%u,\"rotation_samples\":48000,\"bias_samples\":20000,\"badge_activities\":8,\"save_version\":%d,\"v15_migration\":true,\"sanitizers\":[\"ASan\",\"UBSan\"]}\n",tests,SAVE_VERSION);return 0;}
'''
if __name__=='__main__':
    try: result=h.run(h.ROOT)
    except subprocess.CalledProcessError as error: print(error.stderr);raise
    out=h.ROOT/'reports/evidence/exploration-updates-2026-09-15';out.mkdir(parents=True,exist_ok=True)
    (out/'core.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
