#!/usr/bin/env python3
"""Warehouse release: exact individual, atomic persistence, history and move policy."""
import verify_trainer_campaign as h
h.CASES=r'''
static void setup(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);party_init(&s_party);
 for(unsigned i=0;i<6;i++){mon_t m={.species_id=25,.level=60,.exp=exp_for_level(60),.hp=100};assert(party_receive(&s_party,&m));}
 mon_t a={.species_id=76,.level=60,.exp=exp_for_level(60),.hp=100,.flags=1},b=a;b.flags=0;
 s_party.box[3]=a;s_party.box[80]=b;
 move_policy_set(&s_party.policies[PARTY_MAX+3],153,false);
 move_policy_set(&s_party.policies[PARTY_MAX+80],120,false);
 s_w.species=25;s_w.level=60;s_w.exp=exp_for_level(60);s_challenge.wild_wins=1;
 dex_mark_caught(&s_dex,76,true);world_debug_save();
}
static void release(void){
 setup();mon_t wanted=s_party.box[3];party_t before=s_party;
 dex_t dex=s_dex;achievement_store_t achievements=s_achievements;
 uint8_t bytes[sizeof(disk)];memcpy(bytes,disk,sizeof(bytes));
 assert(world_box_release(BOX_SPECIES,&wanted)==WORLD_SWITCH_INVALID);
 assert(world_box_release(3,NULL)==WORLD_SWITCH_INVALID);
 mon_t stale=wanted;stale.exp++;
 assert(world_box_release(3,&stale)==WORLD_SWITCH_STALE);
 assert(world_box_release(80,&wanted)==WORLD_SWITCH_STALE);
 for(unsigned k=0;k<3;k++){
  failure=(int[]){1,2,4}[k];assert(world_box_release(3,&wanted)==WORLD_SWITCH_SAVE_FAILED);failure=0;
  assert(!memcmp(&before,&s_party,sizeof(before))&&!memcmp(bytes,disk,sizeof(bytes)));
  reboot();assert(!memcmp(&before,&s_party,sizeof(before)));
 }
 assert(world_box_release(3,&wanted)==WORLD_SWITCH_OK);
 assert(!s_party.box[3].species_id&&move_policy_allows(&s_party.policies[PARTY_MAX+3],153));
 assert(!memcmp(&before.box[80],&s_party.box[80],sizeof(mon_t)));
 assert(!move_policy_allows(&s_party.policies[PARTY_MAX+80],120));
 assert(!memcmp(before.party,s_party.party,sizeof(before.party)));
 assert(!memcmp(&dex,&s_dex,sizeof(dex))&&!memcmp(&achievements,&s_achievements,sizeof(achievements)));
 reboot();assert(!s_party.box[3].species_id&&move_policy_allows(&s_party.policies[PARTY_MAX+3],153));
 assert(world_box_release(3,&wanted)==WORLD_SWITCH_STALE);
 wanted=s_party.box[80];assert(world_box_release(80,&wanted)==WORLD_SWITCH_OK);reboot();
 for(unsigned i=0;i<BOX_SPECIES;i++)assert(!s_party.box[i].species_id);
 assert(!memcmp(&dex,&s_dex,sizeof(dex)));tests++;
}
static void locks(void){
 setup();mon_t m=s_party.box[3];assert(world_challenge_begin(0));party_t before=s_party;
 assert(world_box_release(3,&m)==WORLD_SWITCH_BUSY);assert(!memcmp(&before,&s_party,sizeof(before)));
 s_challenge.session.active=false;s_challenge.league_active=true;
 assert(world_box_release(3,&m)==WORLD_SWITCH_BUSY);s_challenge.league_active=false;s_active.encounter.uid=5;
 assert(world_box_release(3,&m)==WORLD_SWITCH_BUSY);s_active.encounter.uid=0;s_storage_ready=false;
 assert(world_box_release(3,&m)==WORLD_SWITCH_STORAGE_UNAVAILABLE);tests++;
}
int main(void){assert(assets_init());release();locks();printf("{\"passed\":true,\"cases\":%u,\"save_version\":%u}\n",tests,SAVE_VERSION);return 0;}
'''
if __name__=='__main__':h.run()
