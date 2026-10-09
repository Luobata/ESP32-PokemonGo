#!/usr/bin/env python3
"""Production checkpoint must succeed before any backup bytes are read."""
import verify_world_party as h
h.CASES=h.CASES[:h.CASES.index('static void seed_team')]+r'''
static unsigned reads;
static bool reader(void *out){reads++;return save_decode(out,disk,disk_len,0)==SAVE_READ_OK;}
static bool failed_reader(void *out){(void)out;reads++;return false;}
typedef struct {save_t blob;size_t length;bool fail;uint8_t encoded[sizeof(save_t)];} import_t;
static void encode_import(import_t *candidate){candidate->length=save_storage_encode(candidate->encoded,sizeof(candidate->encoded),&candidate->blob,sizeof(candidate->blob));assert(candidate->length);}
static bool import_reader(void *context,void *out,size_t *size,uint8_t *opening){
 import_t *candidate=context;assert(*size==sizeof(save_t));assert(s_save_lock);
 memcpy(out,candidate->encoded,sizeof(candidate->encoded));*size=candidate->length;*opening=1;
 return !candidate->fail;
}
static void validate_without_adopting(const save_t *saved){
 import_t candidate={.blob=*saved,.length=sizeof(save_t)};
 candidate.blob.pet.stamina=80*NURT_Q;candidate.blob.inventory.quantity[ITEM_BERRY]=20;candidate.blob.exploration_wins=1000;
 encode_import(&candidate);size_t encoded_length=candidate.length;
 world_t w=s_w;party_t party=s_party;inventory_t inventory=s_inventory;dex_t dex=s_dex;enc_queue_t queue=s_queue;
 uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));
 unsigned old_commits=commits;bool dirty=s_dirty;int64_t last_save=s_last_save_us;
 assert(world_backup_validate(import_reader,&candidate,SAVE_VERSION));
 assert(!world_backup_validate(import_reader,&candidate,SAVE_VERSION-1));
 candidate.length=1;assert(!world_backup_validate(import_reader,&candidate,SAVE_VERSION));
 candidate.length=sizeof(save_t)+1;assert(!world_backup_validate(import_reader,&candidate,SAVE_VERSION));
 candidate.length=encoded_length;candidate.fail=true;assert(!world_backup_validate(import_reader,&candidate,SAVE_VERSION));
 candidate.fail=false;save_put16(candidate.encoded,SAVE_VERSION+1);assert(!world_backup_validate(import_reader,&candidate,SAVE_VERSION+1));
 candidate.blob.party[0]=PARTY_MAX+1;encode_import(&candidate);assert(!world_backup_validate(import_reader,&candidate,SAVE_VERSION));
 assert(!world_backup_validate(NULL,&candidate,SAVE_VERSION));
 assert(!memcmp(&w,&s_w,sizeof(w))&&!memcmp(&party,&s_party,sizeof(party)));
 assert(!memcmp(&inventory,&s_inventory,sizeof(inventory))&&!memcmp(&dex,&s_dex,sizeof(dex))&&!memcmp(&queue,&s_queue,sizeof(queue)));
 assert(!memcmp(original,disk,sizeof(disk))&&commits==old_commits&&s_dirty==dirty&&s_last_save_us==last_save);
 // The next real checkpoint recollects live state, never the imported scratch.
 save_t next;assert(world_backup_snapshot(reader,&next));
 assert(next.pet.stamina==saved->pet.stamina&&next.inventory.quantity[ITEM_BERRY]==saved->inventory.quantity[ITEM_BERRY]&&next.exploration_wins==saved->exploration_wins);
}
int main(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 s_w.pet.stamina=37*NURT_Q;s_inventory.quantity[ITEM_BERRY]=7;s_exploration_wins=83;s_dirty=true;
 save_t copy;unsigned before=commits;
 assert(world_backup_snapshot(reader,&copy));assert(commits>before&&reads==1);
 assert(copy.pet.stamina==37*NURT_Q&&copy.inventory.quantity[ITEM_BERRY]==7&&copy.version==SAVE_VERSION&&copy.exploration_wins==83);
 assert(!s_dirty);failure=4;s_w.pet.stamina=12*NURT_Q;s_exploration_wins=84;
 assert(!world_backup_snapshot(reader,&copy)&&reads==1&&s_dirty);failure=0;
 assert(world_backup_snapshot(reader,&copy)&&copy.pet.stamina==12*NURT_Q&&copy.exploration_wins==84);
 assert(!world_backup_snapshot(failed_reader,&copy));
 assert(!world_backup_snapshot(NULL,&copy)&&!world_backup_snapshot(reader,NULL));
 validate_without_adopting(&copy);
 s_storage_ready=false;assert(!world_backup_snapshot(reader,&copy));
 puts("{\"passed\":true,\"checkpoint\":\"live state, failed save blocks export, retry, read failure, unavailable storage; borrowed import workspace never adopts progress or writes NVS\"}");return 0;
}
'''
if __name__=='__main__':
 try:print(h.run(h.ROOT))
 except Exception as e:
  print(getattr(e,'stderr',''));raise
