#!/usr/bin/env python3
"""Production clock/world/save: sleep, restart, checkpoint and failed writes."""
import verify_world_party as h
h.CASES=h.CASES[:h.CASES.index('static void seed_team')]+r'''
#include "evolution.c"
static bool reader(void *out){return save_decode(out,disk,disk_len,0)==SAVE_READ_OK;}
static unsigned persisted_playtime(void){save_t saved;assert(save_read(&saved));return saved.playtime_s;}
int main(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 assert(!world_playtime_seconds());test_time+=3600000000LL;assert(!world_playtime_seconds());
 world_playtime_set_paused(false);test_time+=4800000;assert(world_playtime_seconds()==4);
 test_time+=400000;assert(world_playtime_seconds()==5);
 world_playtime_set_paused(true);assert(persisted_playtime()==5);
 unsigned saved=commits;world_playtime_set_paused(true);assert(commits==saved);
 test_time+=86400000000LL;assert(world_playtime_seconds()==5); // display asleep, CPU running
 world_playtime_set_paused(false);test_time+=800000;assert(world_playtime_seconds()==6);
 s_w.pet.satiety=20*NURT_Q;assert(world_item_use(25,ITEM_BERRY,NULL)==ITEM_USE_OK);
 assert(persisted_playtime()==6);reboot();assert(world_playtime_seconds()==6);
 test_time+=3600000000LL;assert(world_playtime_seconds()==6); // no saved uptime or wall-clock accrual
 world_playtime_set_paused(false);test_time+=60500000;save_t copy;
 assert(world_backup_snapshot(reader,&copy)&&copy.playtime_s==66);
 test_time+=5500000;assert(world_playtime_seconds()==72);
 failure=4;world_playtime_set_paused(true);assert(s_dirty&&world_playtime_seconds()==72);
 assert(persisted_playtime()==66);assert(!world_backup_snapshot(reader,&copy));failure=0;
 assert(world_backup_snapshot(reader,&copy)&&copy.playtime_s==72);reboot();assert(world_playtime_seconds()==72);
 // All old V19 fields and even its undefined tail remain in the frozen prefix.
 save_v19_t old=copy.v19;old.version=19;old.exploration_wins=91;
 memset((uint8_t*)&old+offsetof(save_v19_t,exploration_wins)+sizeof(uint32_t),0xa5,
        sizeof(old)-offsetof(save_v19_t,exploration_wins)-sizeof(uint32_t));
 save_t next;assert(save_decode(&next,&old,sizeof(old),0)==SAVE_READ_MIGRATED);
 assert(!next.playtime_s&&next.exploration_wins==91&&next.inventory.quantity[ITEM_BERRY]==copy.inventory.quantity[ITEM_BERRY]);
 assert(!memcmp(next.party,old.party,PARTY_BYTES));
 next.playtime_s=UINT32_MAX;assert(save_write(&next));reboot();world_playtime_set_paused(false);
 test_time+=100000000000LL;assert(world_playtime_seconds()==UINT32_MAX);world_debug_save();reboot();assert(world_playtime_seconds()==UINT32_MAX);
 playtime_clock_t clock;playtime_init(&clock,0,1000000);playtime_pause(&clock,1000000,false);
 for(unsigned i=0;i<10;i++){playtime_pause(&clock,clock.last_us+100000,true);playtime_pause(&clock,clock.last_us+1000000000,false);}
 assert(clock.seconds==1&&!clock.fraction_us);
 playtime_advance(&clock,1);assert(clock.seconds==1);playtime_advance(&clock,1000001);assert(clock.seconds==2);
 puts("{\"passed\":true,\"save_version\":20,\"running_sleep_reboot\":true,\"fractional_resume\":true,\"backup_and_retry\":true,\"old_padding_ignored\":true,\"saturation\":true,\"sanitized\":true}");return 0;
}
'''
if __name__=='__main__':
 try:print(h.run(h.ROOT))
 except Exception as e:print(getattr(e,'stderr',''));raise
