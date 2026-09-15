#!/usr/bin/env python3
"""Production checkpoint must succeed before any backup bytes are read."""
import verify_world_party as h
h.CASES=h.CASES[:h.CASES.index('static void seed_team')]+r'''
static unsigned reads;
static bool reader(void *out){reads++;assert(disk_len==sizeof(save_t));memcpy(out,disk,disk_len);return true;}
static bool failed_reader(void *out){(void)out;reads++;return false;}
int main(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 s_w.pet.stamina=37*NURT_Q;s_inventory.quantity[ITEM_BERRY]=7;s_dirty=true;
 save_t copy;unsigned before=commits;
 assert(world_backup_snapshot(reader,&copy));assert(commits>before&&reads==1);
 assert(copy.pet.stamina==37*NURT_Q&&copy.inventory.quantity[ITEM_BERRY]==7&&copy.version==SAVE_VERSION);
 assert(!s_dirty);failure=4;s_w.pet.stamina=12*NURT_Q;
 assert(!world_backup_snapshot(reader,&copy)&&reads==1&&s_dirty);failure=0;
 assert(world_backup_snapshot(reader,&copy)&&copy.pet.stamina==12*NURT_Q);
 assert(!world_backup_snapshot(failed_reader,&copy));
 assert(!world_backup_snapshot(NULL,&copy)&&!world_backup_snapshot(reader,NULL));
 s_storage_ready=false;assert(!world_backup_snapshot(reader,&copy));
 puts("{\"passed\":true,\"checkpoint\":\"live state, failed save blocks export, retry, read failure, unavailable storage\"}");return 0;
}
'''
if __name__=='__main__':
 try:print(h.run(h.ROOT))
 except Exception as e:
  print(getattr(e,'stderr',''));raise
