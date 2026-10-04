#!/usr/bin/env python3
"""Shared production save migration/validation and level-scaled milk recovery."""
import verify_trainer_campaign as harness

harness.CASES = r'''
static void compatibility(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 save_t original;assert(save_read_status(&original)==SAVE_READ_OK);
 const size_t sizes[]={sizeof(save_v5_t),sizeof(save_v6_t),sizeof(save_v7_t),sizeof(save_v8_t),
  sizeof(save_v9_t),sizeof(save_v10_t),sizeof(save_v14_t),sizeof(save_v14_t),sizeof(save_v14_t),
  sizeof(save_v14_t),sizeof(save_v15_t),sizeof(save_v16_t),sizeof(save_t)};
 for(unsigned version=5;version<=SAVE_VERSION;version++){
  save_t input=original,decoded;party_t party;input.version=version;
  // V7/8 trainer sessions used shorter mons. Empty legacy campaign is valid.
  if(version==7||version==8)memset((uint8_t*)&input+sizeof(save_v6_t),0,sizeof(input)-sizeof(save_v6_t));
  save_t untouched=input;size_t len=sizes[version-5];memset(&decoded,0xa5,sizeof(decoded));
  save_read_result_t r=save_decode(&decoded,&input,len,1);
  assert(r==(version==SAVE_VERSION?SAVE_READ_OK:SAVE_READ_MIGRATED));
  assert(decoded.version==SAVE_VERSION&&decoded.opening_seen);
  assert(save_validate_world(&decoded,&party)&&party.party_count==1&&party.party[0].species_id==25);
  assert(!memcmp(&input,&untouched,sizeof(input)));
  // In-place decode is the exact NVS scratch path used by USB import.
  decoded=input;r=save_decode(&decoded,&decoded,len,1);
  assert(r!=SAVE_READ_ERROR&&save_validate_world(&decoded,&party));
 }
 save_t bad=original,out;party_t party;
 bad.version=SAVE_VERSION+1;assert(save_decode(&out,&bad,sizeof(bad),0)==SAVE_READ_ERROR);
 assert(save_decode(&out,&original,sizeof(original)-1,0)==SAVE_READ_ERROR);
 assert(save_decode(&out,&original,sizeof(original)+1,0)==SAVE_READ_ERROR);
 assert(save_decode(&out,NULL,0,0)==SAVE_READ_ERROR);
 bad=original;((uint8_t*)&bad)[offsetof(save_t,opening_seen)]=2;
 assert(save_decode(&out,&bad,sizeof(bad),0)==SAVE_READ_ERROR);
 bad=original;bad.party[2]=255;assert(!save_validate_world(&bad,&party));
 bad=original;bad.party[0]=7;assert(!save_validate_world(&bad,&party));
 bad=original;bad.queue.count=ENC_QUEUE_CAP+1;assert(!save_validate_world(&bad,&party));
 bad=original;bad.inventory.quantity[ITEM_POKE]=65535;
 assert(save_decode(&out,&bad,sizeof(bad),0)==SAVE_READ_ERROR);
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
int main(void){assert(assets_init());compatibility();milk();puts("{\"passed\":true,\"schemas\":\"V5-V17, future/corrupt rejected\",\"milk\":\"low/high HP, cap, faint, status, turn cost, save failures and reboot\"}");return 0;}
'''
if __name__ == '__main__':
    harness.run()
