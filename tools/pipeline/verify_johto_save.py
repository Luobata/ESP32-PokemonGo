#!/usr/bin/env python3
"""V5-V26 full-warehouse migration, policy identity, chapter persistence.

Uses production world/save/bank code with host NVS/RTOS adapters; real NVS
restore and fault injection are separately exercised by the release checks.
"""
import verify_trainer_campaign as harness
from save_history_fixtures import c_cases

CASES = r'''
static void policies(void) {
 bool occupied[251]={0};
 for(unsigned id=1;id<=251;id++){
  int bit=move_policy_bit(id);assert(bit>=0&&bit<251&&!occupied[bit]);occupied[bit]=true;
  move_policy_t p={0};move_policy_set(&p,id,false);assert(move_policy_valid(&p));
  for(unsigned j=1;j<=251;j++)assert(move_policy_allows(&p,j)==(j!=id||j==165));
  move_policy_set(&p,id,true);move_policy_t empty={0};assert(!memcmp(&p,&empty,sizeof(p)));
 }
 assert(move_policy_bit(0)<0&&move_policy_bit(252)<0);
 for(unsigned bit=251;bit<256;bit++){
  move_policy_t bad={0};bad.disabled[bit/8]=1u<<(bit%8);assert(!move_policy_valid(&bad));
 }
}
static void full_migration(void) {
 static save_v23_t old,unchanged;static save_t out,alias,reloaded;
 const void *fixture=NULL;for(unsigned i=0;i<sizeof(history)/sizeof(history[0]);i++)if(history[i].version==23)fixture=history[i].data;
 assert(fixture);memcpy(&old,fixture,sizeof(old));old.members.party_count=6;
 for(unsigned i=0;i<459;i++){
  mon_v27_t *m=i<6?&old.members.party[i]:&old.members.box[i-6];
  *m=(mon_v27_t){.species_id=1+i%151,.level=1+i%100,.exp=12345+i,.hp=i%101,
             .intimacy=i%101,.explore_value=i,.nickname_idx=i%251,.flags=i%2};
  for(unsigned b=0;b<24;b++)old.members.policies[i].disabled[b]=(i*73+b*31+19)&255;
  old.members.policies[i].disabled[23]&=0x7f;
 }
 unchanged=old;assert(save_decode(&out,&old,sizeof(old),0)==SAVE_READ_MIGRATED);
 assert(!memcmp(&old,&unchanged,sizeof(old)));assert(out.johto.version==1&&out.johto.phase==JOHTO_HIDDEN);
 for(unsigned i=0;i<459;i++){
  const mon_v27_t *a=i<6?&old.members.party[i]:&old.members.box[i-6];
  const mon_t *b=i<6?&out.members.party[i]:&out.members.box[i-6];
  assert(!memcmp(a,b,sizeof(*a)));assert(!memcmp(old.members.policies[i].disabled,out.members.policies[i].disabled,24));
  for(unsigned byte=24;byte<32;byte++)assert(out.members.policies[i].disabled[byte]==0);
 }
 memcpy(&alias,&old,sizeof(old));assert(save_decode(&alias,&alias,sizeof(old),0)==SAVE_READ_MIGRATED);
 assert(!memcmp(&alias,&out,sizeof(out)));assert(save_validate_world(&out,&out.members));
 // Reject malformed old reserved bits before repurposing them for new move 166.
 old.members.policies[458].disabled[23]|=0x80;
 assert(save_decode(&alias,&old,sizeof(old),0)==SAVE_READ_ERROR);old=unchanged;
 fresh();save_bank_ref_t old_ref;
 assert(save_bank_prepare(save_bank_platform(),NULL,&old,sizeof(old),&old_ref));
 memcpy(disk,&old_ref,sizeof(old_ref));disk_len=sizeof(old_ref);have_disk=namespace_exists=true;
 assert(save_read_status(&reloaded)==SAVE_READ_MIGRATED&&!memcmp(&reloaded,&out,sizeof(out)));
 // Every new bit, even for currently unopened moves, survives normal saving.
 for(unsigned i=0;i<459;i++)for(unsigned b=24;b<32;b++)out.members.policies[i].disabled[b]=(i*17+b*53)&255;
 for(unsigned i=0;i<459;i++)out.members.policies[i].disabled[31]&=7;
 assert(save_write(&out));assert(save_read_status(&reloaded)==SAVE_READ_OK&&!memcmp(&reloaded,&out,sizeof(out)));
 for(unsigned f=0;f<3;f++){
  save_t prior=reloaded;failure=(int[]){1,2,4}[f];out.playtime_s++;
  assert(!save_write(&out));failure=0;
  assert(save_read_status(&reloaded)==SAVE_READ_OK&&!memcmp(&prior,&reloaded,sizeof(prior)));
  assert(save_write(&out));assert(save_read_status(&reloaded)==SAVE_READ_OK&&!memcmp(&reloaded,&out,sizeof(out)));
 }
}
static void chapter_roundtrip(void) {
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);save_t s,reloaded;
 assert(save_read(&s));s.challenge.defeated=255;
 assert(johto_offer(&s.johto,s.challenge.defeated));assert(!johto_offer(&s.johto,s.challenge.defeated));
 assert(save_write(&s));reboot();assert(s_johto.phase==JOHTO_INVITED&&!s_johto.badges);
 assert(save_read(&s));assert(johto_depart(&s.johto));assert(johto_choose_starter(&s.johto,152));
 assert(johto_gym_win(&s.johto,0));assert(johto_receive_egg(&s.johto,256));
 for(unsigned i=1;i<=12;i++)assert(johto_explore(&s.johto,0,i,true));
 assert(s.johto.egg_status==JOHTO_EGG_READY&&johto_egg_shiny(&s.johto));
 assert(save_write(&s));reboot();assert(!memcmp(&s_johto,&s.johto,sizeof(s_johto)));
 assert(save_read(&reloaded));assert(!johto_hatch(&reloaded.johto,false));
 assert(save_write(&reloaded));assert(save_read(&s));assert(s.johto.egg_status==JOHTO_EGG_READY);
 // Corrupt/unknown chapter schemas never fall back to a new game.
 reloaded=s;reloaded.johto.version=2;assert(test_decode_save(&s,&reloaded)==SAVE_READ_ERROR);
 reloaded.johto.version=1;reloaded.johto.egg_steps=0;assert(test_decode_save(&s,&reloaded)==SAVE_READ_ERROR);
 assert(!erase_calls);
}
static void gameplay(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 assert(!world_johto_available());assert(world_johto_visit()==WORLD_JOHTO_LOCKED);
 s_challenge.defeated=15;assert(world_johto_available());world_debug_save();
 failure=4;assert(world_johto_visit()==WORLD_JOHTO_SAVE_FAILED&&s_johto.phase==JOHTO_HIDDEN);failure=0;
 assert(world_johto_visit()==WORLD_JOHTO_OK);assert(world_johto_depart()==WORLD_JOHTO_OK);
 unsigned old=party_total(&s_party);failure=4;assert(world_johto_starter(152)==WORLD_JOHTO_SAVE_FAILED&&party_total(&s_party)==old);failure=0;
 assert(world_johto_starter(152)==WORLD_JOHTO_OK);assert(party_total(&s_party)==old+1&&dex_is_caught(&s_dex,152));
 assert(world_johto_starter(155)==WORLD_JOHTO_LOCKED);reboot();assert(s_johto.phase==JOHTO_ACTIVE&&s_party.party[1].species_id==152);
 assert(world_challenge_start(TRAINER_JOHTO_FIRST+1)==WORLD_CHALLENGE_LOCKED);
 for(unsigned gym=0;gym<8;gym++){
  s_w.pet.stamina=100*NURT_Q;assert(world_challenge_start(TRAINER_JOHTO_FIRST+gym)==WORLD_CHALLENGE_OK);
  assert(s_challenge.defeated==15);assert(trainer_store_valid(&s_challenge));
  // Result fixture: the transaction, first-reward idempotency and restart are
  // under test here. Battle simulation is independently exercised below.
  s_challenge.session.finished=1;s_challenge.session.won=1;world_debug_save();
  failure=4;assert(!world_challenge_settle()&&johto_badges(&s_johto)==gym);failure=0;
  assert(world_challenge_settle()&&johto_badges(&s_johto)==gym+1);johto_state_t copy=s_johto;
  assert(world_challenge_settle()&&!memcmp(&copy,&s_johto,sizeof(copy)));reboot();assert(!memcmp(&copy,&s_johto,sizeof(copy))&&s_challenge.defeated==15);
 }
 assert(s_johto.egg_status==JOHTO_EGG_INCUBATING);
 assert(world_johto_egg(true)==WORLD_JOHTO_LOCKED);
 encounter_t e={0};s_w.pet.stamina=0;assert(world_johto_explore(0,&e)==WORLD_JOHTO_NO_STAMINA&&!s_johto.explorations);
 s_w.pet.stamina=100*NURT_Q;failure=4;assert(world_johto_explore(0,&e)==WORLD_JOHTO_SAVE_FAILED&&!s_johto.explorations&&s_w.pet.stamina==100*NURT_Q);failure=0;
 for(unsigned i=0;i<64;i++){
  unsigned route=i%8;s_w.pet.stamina=100*NURT_Q;
  assert(world_johto_explore(route,&e)==WORLD_JOHTO_OK);
  assert(e.species_id>151&&e.species_id<=251&&e.species_id!=175&&e.species_id!=176&&e.species_id!=201);
  assert(e.level>=JOHTO_ROUTES[route].min_level&&e.level<=JOHTO_ROUTES[route].max_level&&s_queue.count<=5&&s_w.pet.stamina==100*NURT_Q-NURT_EXPLORE_COST);
 }
 assert(s_johto.egg_status==JOHTO_EGG_READY);bool shiny=johto_egg_shiny(&s_johto);old=party_total(&s_party);
 failure=4;assert(world_johto_egg(true)==WORLD_JOHTO_SAVE_FAILED&&party_total(&s_party)==old);failure=0;
 assert(world_johto_egg(true)==WORLD_JOHTO_OK&&party_total(&s_party)==old+1&&dex_is_caught(&s_dex,175));
 assert((s_party.party[2].flags&1)==shiny);assert(world_johto_egg(true)==WORLD_JOHTO_LOCKED);reboot();assert(s_johto.eggs_hatched==1);
 assert(world_challenge_start(TRAINER_JOHTO_FIRST+8)==WORLD_CHALLENGE_LOCKED);
 s_challenge.defeated=0x3fff;s_story.version=1;s_story.rescues=2;s_story.ruins=15;s_story.tower_seen=1;s_activities.silver_feather=1;for(unsigned k=0;k<5;k++)s_johto.legend_clues[k]=3;s_w.pet.stamina=100*NURT_Q;assert(world_challenge_start(TRAINER_JOHTO_FIRST+8)==WORLD_CHALLENGE_OK);
 s_challenge.session.finished=1;s_challenge.session.won=1;assert(world_challenge_settle());assert(s_johto.phase==JOHTO_COMPLETE);
 s_story.forest_visits=3;for(unsigned i=0;i<3;i++){s_w.pet.stamina=100*NURT_Q;assert(world_johto_explore(1,&e)==WORLD_JOHTO_OK);}
 assert(!s_johto.legend_clues[5]);
 unsigned psychic_slot=s_party.party_count;mon_t psychic={.species_id=63,.level=20,.hp=100,.exp=exp_for_level(20)};assert(party_receive(&s_party,&psychic));s_party.party[1].hp=100;world_debug_save();
 for(unsigned i=14;i<17;i++){unsigned slot=i==15?psychic_slot:1;const johto_probe_t *p=johto_probe(i);s_w.pet.stamina=100*NURT_Q;assert(world_johto_investigate(i,p->path,slot,&s_party.party[slot])==WORLD_JOHTO_OK);reboot();}
 for(unsigned i=0;i<6;i++){s_w.pet.stamina=100*NURT_Q;assert(world_johto_legend(i,&e)==WORLD_JOHTO_OK);assert((e.species_id==(unsigned[]){243,244,245,249,250,251}[i]));assert(world_take_uid(e.uid,NULL)&&!s_narrative.legend);}
 // A ready egg survives full party+warehouse and reboot, without rerolling.
 s_johto.egg_status=JOHTO_EGG_READY;s_johto.egg_steps=12;s_johto.egg_seed=256;
 while(s_party.party_count<6){mon_t m={.species_id=152,.level=35,.exp=exp_for_level(35),.hp=100};assert(party_receive(&s_party,&m));}
 for(unsigned i=0;i<BOX_CAPACITY;i++)s_party.box[i]=(mon_t){.species_id=1+i%251,.level=35,.exp=exp_for_level(35),.hp=100};
 world_debug_save();assert(world_johto_egg(true)==WORLD_JOHTO_FULL);reboot();assert(s_johto.egg_seed==256&&s_johto.egg_status==JOHTO_EGG_READY);
 assert(!erase_calls);
}
static void johto_battles(void){
 mon_t team[6];for(unsigned i=0;i<6;i++)team[i]=(mon_t){.species_id=(unsigned[]){154,157,160,196,212,248}[i],.level=95,.hp=100};
 for(unsigned id=26;id<35;id++){
  const trainer_info_t *actual=trainer_info(id);const johto_trainer_t *expected=&JOHTO_TRAINERS[id-26];
  assert(actual&&actual->count==expected->count&&!strcmp(actual->name,expected->name));
  for(unsigned i=0;i<actual->count;i++)assert(actual->species[i]==expected->species[i]&&actual->levels[i]==expected->levels[i]);
  assert((trainer_badge_art(id)!=NULL)==(id<34));
  trainer_store_t st={.defeated=255};assert(trainer_begin(&st,id,team,6,1024,83+id));
  for(unsigned guard=0;!st.session.finished&&guard<1000;guard++){
   trainer_event_t e;assert(trainer_step(&st,&e));assert(trainer_store_valid(&st));
   if(e.kind==TRAINER_SWITCH_NEEDED){bool switched=false;for(unsigned i=0;i<6;i++)if(trainer_switch(&st,i,true)){switched=true;break;}assert(switched);}
  }
  assert(st.session.finished);trainer_settle(&st);assert(st.defeated==255);
 }
}

int main(void){assert(assets_init());policies();full_migration();chapter_roundtrip();gameplay();johto_battles();puts("V26: 251 unique policy bits, 459 dense V23 individuals, alias/reference migration, failures, reboot and chapter/egg persistence, real world transactions, 8 gyms/final, paid discoveries and full-box eggs passed");return 0;}
'''
if __name__=='__main__':
 harness.CASES=c_cases()+CASES
 harness.run()
