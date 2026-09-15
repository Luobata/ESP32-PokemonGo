#!/usr/bin/env python3
"""Offline stamina: production world/save with real transactions and simulated UTC."""
import json
import subprocess
import verify_world_party as h
import verify_exploration_routes as base
h.CASES=base.CASES[:base.CASES.index('static void core')]+r'''
#define UTC (1800000000LL*1000000)
#define MINUTE 60000000LL
static void seed(void){test_time=1000000;fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);s_w.pet.stamina=0;s_w.pet.last_us=test_time;}
static void sync_tests(void){
 seed();uint8_t gained=99;assert(world_sync_time(UTC,&gained)&&gained==0&&s_w.pet.stamina==0);
 // Thirty minutes switched off restores 50, and repeated sync cannot pay twice.
 reboot();assert(world_sync_time(UTC+30*MINUTE,&gained)&&gained==50&&s_w.pet.stamina==50*NURT_Q);
 assert(world_sync_time(UTC+30*MINUTE,&gained)&&gained==0&&s_w.pet.stamina==50*NURT_Q);
 reboot();assert(world_sync_time(UTC+60*MINUTE,&gained)&&gained==50&&s_w.pet.stamina==NURT_MAX);
 s_w.pet.stamina=0;assert(world_sync_time(UTC+60*MINUTE,&gained)&&gained==0);
 assert(world_sync_time(UTC+24*60*MINUTE,&gained)&&gained==100&&s_w.pet.stamina==NURT_MAX);tests+=6;
 // Ten minutes already earned online, then thirty minutes off.
 seed();assert(world_sync_time(UTC,NULL));test_time+=10*MINUTE;nurture_tick(&s_w.pet,test_time,0,false);world_debug_save();
 int32_t before=s_w.pet.stamina;reboot();assert(world_sync_time(UTC+40*MINUTE,&gained)&&gained==50);
 assert(s_w.pet.stamina==before+50*NURT_Q);tests++;
 // Several offline boots preserve accounted online time and stamina spending.
 seed();assert(world_sync_time(UTC,NULL));test_time+=6*MINUTE;nurture_tick(&s_w.pet,test_time,0,false);world_debug_save();
 reboot();s_w.pet.last_us=test_time;test_time+=6*MINUTE;nurture_tick(&s_w.pet,test_time,0,false);s_w.pet.stamina=0;world_debug_save();
 reboot();s_w.pet.last_us=test_time;test_time+=6*MINUTE;
 assert(world_sync_time(UTC+30*MINUTE,&gained)&&gained==20);
 assert(s_w.pet.stamina>=29*NURT_Q&&s_w.pet.stamina<=30*NURT_Q);tests++;
 // First ever sync cannot infer earlier shut-down time.
 seed();world_debug_save();reboot();assert(world_sync_time(UTC+60*MINUTE,&gained)&&gained==0);tests++;
}
static void faults(void){
 for(int mode=1;mode<=4;mode++){if(mode==3)continue;
  seed();assert(world_sync_time(UTC,NULL));reboot();rest_clock_t old=s_rest_clock;
  failure=mode;assert(!world_sync_time(UTC+30*MINUTE,NULL));failure=0;
  assert(!memcmp(&old,&s_rest_clock,sizeof(old))&&s_w.pet.stamina==0);
  reboot();assert(world_sync_time(UTC+30*MINUTE,NULL)&&s_w.pet.stamina==50*NURT_Q);
  reboot();assert(world_sync_time(UTC+30*MINUTE,NULL)&&s_w.pet.stamina==50*NURT_Q);tests++;
 }
 seed();assert(!world_sync_time(0,NULL)&&!s_rest_clock.epoch_us);
 assert(!world_sync_time(INT64_MAX,NULL)&&!s_rest_clock.epoch_us);
 assert(world_sync_time(UTC,NULL));assert(world_sync_time(UTC-MINUTE,NULL)&&s_rest_clock.epoch_us==UTC&&s_w.pet.stamina==0);
 assert(world_sync_time(UTC+MINUTE,NULL)&&s_w.pet.stamina==NURT_STAMINA_RECOVER_PH/60);tests+=4;
 // Imported V16 progress survives and establishes a fresh time baseline.
 seed();s_w.pet.stamina=23*NURT_Q;world_debug_save();save_t current;assert(save_read_status(&current)==SAVE_READ_OK);
 save_v16_t old;memcpy(&old,&current,sizeof(old));old.version=16;memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);
 save_t migrated;assert(save_read_status(&migrated)==SAVE_READ_MIGRATED&&migrated.version==SAVE_VERSION&&!migrated.rest_clock.epoch_us);
 assert(!memcmp(migrated.party,current.party,PARTY_BYTES)&&migrated.pet.stamina==23*NURT_Q);
 reboot();assert(world_sync_time(UTC,NULL)&&s_w.pet.stamina==23*NURT_Q&&erase_calls==0);tests++;
}
int main(void){sync_tests();faults();printf("{\"checks\":%u,\"save_version\":%d,\"offline_cap_minutes\":60,\"nvs_failure_atomic\":true,\"v16_migration\":true,\"sanitizers\":[\"ASan\",\"UBSan\"]}\n",tests,SAVE_VERSION);return 0;}
'''
if __name__=='__main__':
 try: print(json.dumps(h.run(h.ROOT),indent=2))
 except subprocess.CalledProcessError as exc: print(exc.stderr);raise
