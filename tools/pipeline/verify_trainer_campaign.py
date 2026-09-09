#!/usr/bin/env python3
"""Production trainer/world/save tests with real assets and an in-memory NVS boundary."""
from pathlib import Path
import json, subprocess, sys, tempfile
import verify_encounter_lifecycle as lifecycle
ROOT=Path(__file__).resolve().parents[2]
CASES=r'''
static mon_t team[6];
static void seed(void){
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
 party_init(&s_party);
 for(unsigned i=0;i<6;i++){team[i]=(mon_t){.species_id=(uint8_t[]){3,6,9,65,143,149}[i],.level=90,.exp=exp_for_level(90),.hp=100};assert(party_receive(&s_party,&team[i]));}
 s_w.species=3;s_w.level=90;s_w.exp=exp_for_level(90);s_challenge.wild_wins=1;world_debug_save();
}
static void campaign(void){
 trainer_store_t st={.wild_wins=1};unsigned total=0,replacements=0;
 for(unsigned i=0;i<6;i++)team[i].level=100;
 assert(!trainer_unlocked(&(trainer_store_t){0},0));
 for(unsigned id=0;id<14;id++){
  assert(trainer_unlocked(&st,id));trainer_store_t checkpoint=st;
  // Random tactical battles may legitimately lose, even at level 100.
  // Exercise real wins for progression, validating every attempted loss too.
  for(unsigned attempt=0;attempt<32;attempt++){
  st=checkpoint;assert(trainer_begin(&st,id,team,6,1024,123+id+attempt*997));
  for(unsigned guard=0;!st.session.finished&&guard<600;guard++){
   trainer_event_t e;assert(trainer_step(&st,&e));assert(trainer_store_valid(&st));total++;
   if(e.kind==TRAINER_SWITCH_NEEDED){bool ok=false;for(unsigned j=0;j<6;j++)if(trainer_switch(&st,j,true)){ok=true;replacements++;break;}assert(ok);}
  }
  assert(st.session.finished);if(st.session.won)break;
  }
  assert(st.session.finished&&st.session.won);assert(trainer_reward(&st)>0);
  trainer_side_t before=st.session.sides[0];trainer_settle(&st);assert(st.defeated&(1u<<id));
  trainer_store_t once=st;trainer_settle(&st);assert(!memcmp(&once,&st,sizeof(st)));
  if(id>=8&&id<12){assert(st.league_stage==id+1);assert(!memcmp(&before,&st.session.sides[0],sizeof(before)));}
 }
 assert(st.defeated==16383&&!st.league_active);
 printf("\"campaign_actions\":%u,\"replacements\":%u,",total,replacements);tests++;
}
static void transactions(void){
 seed();trainer_store_t before=s_challenge;
 for(unsigned k=0;k<3;k++){failure=(int[]){1,2,4}[k];assert(!world_challenge_begin(0));assert(!memcmp(&before,&s_challenge,sizeof(before)));}failure=0;
 assert(world_challenge_begin(0));before=s_challenge;
 trainer_event_t e,untouched;memset(&e,0xa5,sizeof(e));untouched=e;
 failure=4;assert(!world_challenge_step(&e));assert(!memcmp(&e,&untouched,sizeof(e)));assert(!memcmp(&before,&s_challenge,sizeof(before)));failure=0;
 assert(world_challenge_step(&e));trainer_store_t after=s_challenge;reboot();assert(!memcmp(&after,&s_challenge,sizeof(after)));
 world_party_t view;world_party_snapshot(&view);assert(view.switch_locked);
 battle_session_t wild={.initialized=true};assert(!world_battle_set_uid(1,&wild));
 // Force a low-HP legitimate fixture, then verify failed healing doesn't spend milk.
 trainer_mon_t *m=&s_challenge.session.sides[0].mons[0];m->hp=1;s_inventory.quantity[ITEM_MILK]=2;world_debug_save();
 before=s_challenge;failure=4;assert(!world_challenge_recover(0));assert(!memcmp(&before,&s_challenge,sizeof(before))&&s_inventory.quantity[ITEM_MILK]==2);failure=0;
 assert(world_challenge_recover(0));assert(s_challenge.session.sides[0].mons[0].hp==51&&s_inventory.quantity[ITEM_MILK]==1);
 // Resume the real simulation and settle exactly once, including reboot/failure.
 while(!s_challenge.session.finished){assert(world_challenge_step(&e));if(e.kind==TRAINER_SWITCH_NEEDED){bool ok=false;for(unsigned i=0;i<6;i++)if(world_challenge_switch(i,true)){ok=true;break;}assert(ok);}}
 assert(s_challenge.session.won);party_t old=s_party;before=s_challenge;uint16_t milk=s_inventory.quantity[ITEM_MILK];
 failure=4;assert(!world_challenge_settle());assert(!memcmp(&old,&s_party,sizeof(old))&&!memcmp(&before,&s_challenge,sizeof(before))&&milk==s_inventory.quantity[ITEM_MILK]);failure=0;
 assert(world_challenge_settle());old=s_party;milk=s_inventory.quantity[ITEM_MILK];assert(s_challenge.defeated==1);
 reboot();assert(world_challenge_settle());assert(!memcmp(&old,&s_party,sizeof(old))&&milk==s_inventory.quantity[ITEM_MILK]);
 assert(erase_calls==0);tests++;
}
static void migration(void){
 for(unsigned version=5;version<=6;version++){
  seed();save_t saved;assert(save_read_status(&saved)==SAVE_READ_OK);
  saved.version=version;disk_len=version==5?sizeof(save_v5_t):version==6?sizeof(save_v6_t):sizeof(save_v7_t);memcpy(disk,&saved,disk_len);
  save_t migrated;assert(save_read_status(&migrated)==SAVE_READ_MIGRATED);assert(migrated.version==SAVE_VERSION&&migrated.challenge.wild_wins==1);
  assert(!memcmp(saved.party,migrated.party,PARTY_BYTES));reboot();assert(s_w.species==3&&s_w.level==90&&s_party.party_count==6);world_debug_save();assert(disk_len==sizeof(save_t));
 }
 seed();assert(world_challenge_begin(0));save_t bad;assert(save_read_status(&bad)==SAVE_READ_OK);bad.challenge.session.sides[0].mons[0].hp=65535;memcpy(disk,&bad,sizeof(bad));
 uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));reboot();assert(!s_storage_ready);world_debug_save();assert(!memcmp(original,disk,sizeof(disk))&&erase_calls==0);tests++;
}
static void edge_cases(void){
 trainer_store_t st={.wild_wins=1};assert(trainer_begin(&st,0,team,6,1024,7));
 trainer_mon_t *a=&st.session.sides[0].mons[0];a->hp=0;
 trainer_event_t e;assert(trainer_step(&st,&e)&&e.kind==TRAINER_SWITCH_NEEDED);
 trainer_side_t enemy=st.session.sides[1];assert(!trainer_switch(&st,0,true));assert(trainer_switch(&st,1,true));assert(!memcmp(&enemy,&st.session.sides[1],sizeof(enemy)));
 assert(!trainer_choose_move(&st,0));
 for(unsigned n=0;n<600&&!st.session.finished;n++){assert(trainer_step(&st,&e));if(e.kind==TRAINER_SWITCH_NEEDED){for(unsigned j=0;j<6;j++)if(trainer_switch(&st,j,true))break;}}
 assert(st.session.finished);tests++;
}
int main(void){assert(assets_init());seed();printf("{");campaign();transactions();migration();edge_cases();printf("\"cases\":%u,\"save_bytes\":%zu,\"sanitized\":true}\n",tests,sizeof(save_t));return 0;}
'''
def run():
 stubs,driver=lifecycle.harness();driver=driver[:driver.index('// Only species statistics')]+CASES
 with tempfile.TemporaryDirectory() as d:
  t=Path(d);(t/'device_stubs.h').write_text(stubs)
  for n in ('esp_event.h','esp_log.h','esp_timer.h','esp_wifi.h','nvs.h','nvs_flash.h','bsp_battery.h','freertos/FreeRTOS.h','freertos/semphr.h','freertos/task.h'):
   p=t/n;p.parent.mkdir(exist_ok=True,parents=True);p.write_text('#include "device_stubs.h"\n')
  (t/'driver.c').write_text(driver);asm=[]
  for n in ('gen1.bin','gen1_front.bin','gen1_back.bin','palettes.bin','font16.bin','moves.bin','ui.bin'):
   sy='_binary_'+n.replace('.','_');asm += ['.balign 4',f'.global {sy}_start',f'.global {sy}_end',f'{sy}_start:',f'.incbin "{ROOT/"assets"/n}"',f'{sy}_end:']
  (t/'assets.S').write_text('\n'.join(asm)+'\n')
  cmd=['cc','-std=gnu11','-DHOST_BUILD','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-variable','-Wno-unused-function','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I',str(t),'-I',str(ROOT/'firmware/main'),str(t/'driver.c'),str(t/'assets.S')]+[str(ROOT/'firmware/main'/n) for n in ('party.c','encounter.c','exploration.c','nurture.c','exp.c','items.c','evolution.c','trainer.c','combat.c','battle.c','assets.c','pokemon_names.c')]+['-lz','-Wl,-dead_strip','-o',str(t/'probe')]
  c=subprocess.run(cmd,capture_output=True,text=True);assert c.returncode==0,c.stderr
  c=subprocess.run([str(t/'probe')],capture_output=True,text=True,timeout=40);assert c.returncode==0,c.stdout+c.stderr
  print(c.stdout)
if __name__=='__main__':run()
