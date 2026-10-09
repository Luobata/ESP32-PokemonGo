#!/usr/bin/env python3
"""Shared production save migration/validation and level-scaled milk recovery."""
import verify_trainer_campaign as harness
from save_history_fixtures import c_cases

harness.CASES = r'''
static void historical_compatibility(void){
 for(unsigned i=0;i<sizeof(history)/sizeof(history[0]);i++){
  fprintf(stderr,"Historical save: %s\n",history[i].name);
  save_t decoded;save_read_result_t result=save_decode(&decoded,history[i].data,history[i].size,0);
  assert(result==SAVE_READ_OK||result==SAVE_READ_MIGRATED);
  history_assert(&decoded,history[i].version);
  save_t again;assert(test_decode_save(&again,&decoded)==SAVE_READ_OK);
  assert(!memcmp(&again,&decoded,sizeof(again))); // migration is not repeated
  fresh();memcpy(disk,history[i].data,history[i].size);disk_len=history[i].size;
  have_disk=namespace_exists=true;reboot();assert(world_save_loaded()&&s_storage_ready);
  assert(s_w.species==25&&s_w.level==32&&party_total(&s_party)==3);
  assert(s_party.box[history[i].version<12?148:3].flags==1);
  assert(s_w.exp>=32768&&s_w.pet.stamina==45*NURT_Q); // old EXP curve may be reconciled upwards
  assert(s_achievements.claimed==(history[i].version<8?0:5));
  world_debug_save();assert(save_read_status(&again)==SAVE_READ_OK);
  inventory_t bag=s_inventory;achievement_store_t claims=s_achievements;
  reboot();assert(!memcmp(&bag,&s_inventory,sizeof(bag))&&!memcmp(&claims,&s_achievements,sizeof(claims)));
 assert(erase_calls==0);
 }
}
static void migration_boundaries(void){
 // V11 also shipped with valid tracking IDs: preserve those; only its old
 // reserved values outside the species range acquire the default zero.
 save_v14_t early;memcpy(&early,history[6].data,sizeof(early));
 save_t out;early.exploration.tracked_species=133;
 assert(save_decode(&out,&early,sizeof(early),0)==SAVE_READ_MIGRATED);
 assert(out.exploration.tracked_species==133);
 early.version=12;early.exploration.tracked_species=255;
 assert(save_decode(&out,&early,sizeof(early),0)==SAVE_READ_ERROR);
 // Pre-partner formats must never turn even plausible padding into rewards.
 for(unsigned i=10;i<=11;i++){
  save_t input={0};memcpy(&input,history[i].data,history[i].size);
  input.dungeon.receipt.partner_species=149;input.dungeon.receipt.partner_shiny=1;
  assert(save_decode(&out,&input,history[i].size,0)==SAVE_READ_MIGRATED);
  assert(!out.dungeon.receipt.partner_species&&!out.dungeon.receipt.partner_shiny);
 }
 // Actual modern reward fields are preserved and still validated strictly.
 save_v17_t modern;memcpy(&modern,history[16].data,sizeof(modern));
 modern.dungeon.receipt.partner_species=149;modern.dungeon.receipt.partner_shiny=1;
 assert(save_decode(&out,&modern,sizeof(modern),0)==SAVE_READ_MIGRATED);
 assert(out.dungeon.receipt.partner_species==149&&out.dungeon.receipt.partner_shiny==1);
 modern.dungeon.receipt.partner_shiny=2;
 assert(save_decode(&out,&modern,sizeof(modern),0)==SAVE_READ_ERROR);
 modern.dungeon.receipt.partner_shiny=1;modern.dungeon.receipt.partner_species=0;
 assert(save_decode(&out,&modern,sizeof(modern),0)==SAVE_READ_ERROR);
}
static void compatibility(void){
 fresh();assert(!world_save_loaded());assert(world_choose_starter(25)==WORLD_STARTER_OK);
 reboot();assert(world_save_loaded());
 save_t original;assert(save_read_status(&original)==SAVE_READ_OK);
 const size_t sizes[]={sizeof(save_v5_t),sizeof(save_v6_t),sizeof(save_v7_t),sizeof(save_v8_t),
  sizeof(save_v9_t),sizeof(save_v10_t),sizeof(save_v14_t),sizeof(save_v14_t),sizeof(save_v14_t),
  sizeof(save_v14_t),sizeof(save_v15_t),sizeof(save_v16_t),sizeof(save_v17_t),sizeof(save_v18_t),sizeof(save_v19_t),sizeof(save_v20_t),sizeof(save_t)};
 for(unsigned version=5;version<=21;version++){
  save_t input=original,decoded;party_t party;input.version=version;
  // V7/8 trainer sessions used shorter mons. Empty legacy campaign is valid.
  if(version==7||version==8)memset((uint8_t*)&input+sizeof(save_v6_t),0,sizeof(input)-sizeof(save_v6_t));
  save_t untouched=input;size_t len=sizes[version-5];memset(&decoded,0xa5,sizeof(decoded));
  save_read_result_t r=save_decode(&decoded,&input,len,1);
  assert(r==SAVE_READ_MIGRATED);
  assert(decoded.version==SAVE_VERSION&&decoded.opening_seen);
  assert(save_validate_world(&decoded,&party)&&party.party_count==1&&party.party[0].species_id==25);
  assert(!memcmp(&input,&untouched,sizeof(input)));
  // In-place decode is the exact NVS scratch path used by USB import.
  decoded=input;r=save_decode(&decoded,&decoded,len,1);
  assert(r!=SAVE_READ_ERROR&&save_validate_world(&decoded,&party));
 }
 // V22 has only the checksummed envelope on disk; test the aliased USB path.
 uint8_t encoded[sizeof(save_t)];size_t stored=save_storage_encode(encoded,sizeof(encoded),&original,sizeof(original));assert(stored);
 save_t aliased;memcpy(&aliased,encoded,stored);
 assert(save_decode(&aliased,&aliased,stored,0)==SAVE_READ_OK&&!memcmp(&aliased,&original,sizeof(original)));
 assert(save_decode(&aliased,&original,sizeof(original),0)==SAVE_READ_ERROR);
 save_t bad=original,out;party_t party;
 bad.version=SAVE_VERSION+1;assert(save_decode(&out,&bad,sizeof(bad),0)==SAVE_READ_ERROR);
 assert(save_decode(&out,&original,sizeof(original)-1,0)==SAVE_READ_ERROR);
 assert(save_decode(&out,&original,sizeof(original)+1,0)==SAVE_READ_ERROR);
 assert(save_decode(&out,NULL,0,0)==SAVE_READ_ERROR);
 bad=original;((uint8_t*)&bad)[offsetof(save_t,opening_seen)]=2;
 assert(test_decode_save(&out,&bad)==SAVE_READ_ERROR);
 bad=original;bad.party[2]=255;assert(!save_validate_world(&bad,&party));
 bad=original;bad.party[0]=7;assert(!save_validate_world(&bad,&party));
 bad=original;bad.queue.count=ENC_QUEUE_CAP+1;assert(!save_validate_world(&bad,&party));
 bad=original;bad.version=SAVE_VERSION+1;memcpy(disk,&bad,sizeof(bad));reboot();assert(!world_save_loaded()&&!s_storage_ready);
 bad=original;bad.inventory.quantity[ITEM_POKE]=65535;
 assert(test_decode_save(&out,&bad)==SAVE_READ_ERROR);
}
static void milk(void){
 const uint16_t maximum[]={30,80,200,301,500};
 const uint16_t healing[]={30,50,100,151,250};
 for(unsigned i=0;i<5;i++){
  fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_challenge.wild_wins=1;
  assert(world_challenge_begin(0));trainer_mon_t *m=&s_challenge.session.sides[0].mons[0];
  m->max_hp=maximum[i];m->hp=1;m->status=1 /* poison */;m->sleep=0;s_inventory.quantity[ITEM_MILK]=2;world_debug_save();
  assert(items_milk_heal(m->max_hp)==healing[i]);
  for(unsigned k=0;k<3;k++){
   trainer_store_t before=s_challenge;failure=(int[]){1,2,4}[k];
   assert(!world_challenge_recover(0));assert(!memcmp(&before,&s_challenge,sizeof(before))&&s_inventory.quantity[ITEM_MILK]==2);
  }failure=0;
  assert(world_challenge_recover(0));unsigned hp=1+healing[i];if(hp>maximum[i])hp=maximum[i];
  assert(m->hp==hp&&!m->status&&!m->sleep&&s_inventory.quantity[ITEM_MILK]==1);
  assert(s_challenge.session.next==1&&s_challenge.session.acted==1);
  reboot();m=&s_challenge.session.sides[0].mons[0];assert(m->hp==hp&&s_inventory.quantity[ITEM_MILK]==1);
  m->hp=m->max_hp;assert(!world_challenge_recover(0)&&s_inventory.quantity[ITEM_MILK]==1);
  m->hp=0;assert(!world_challenge_recover(0)&&s_inventory.quantity[ITEM_MILK]==1);
  m->hp=m->max_hp-1;assert(world_challenge_recover(0)&&m->hp==m->max_hp&&!s_inventory.quantity[ITEM_MILK]);
  m->hp=1;assert(!world_challenge_recover(0));
 }
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_challenge.wild_wins=1;assert(world_challenge_begin(0));
 trainer_mon_t *m=&s_challenge.session.sides[0].mons[0];m->hp=m->max_hp;m->status=1 /* poison */;
 assert(world_challenge_recover(0)&&!m->status&&m->hp==m->max_hp); // status-only recovery
}
int main(void){assert(assets_init());historical_compatibility();migration_boundaries();compatibility();milk();puts("{\"passed\":true,\"schemas\":\"V5-V22 historical fixtures, future/corrupt rejected\",\"milk\":\"low/high HP, cap, faint, status, turn cost, save failures and reboot\"}");return 0;}
'''
if __name__ == '__main__':
    harness.CASES = c_cases() + harness.CASES
    harness.run()
