#!/usr/bin/env python3
"""Per-individual move exclusions: production AI, world/save transactions and party."""
import verify_trainer_campaign as h
h.CASES=r'''
static void setup(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);party_init(&s_party);
 for(unsigned i=0;i<6;i++){mon_t m={.species_id=25,.level=60,.exp=exp_for_level(60)+i,.hp=100,.flags=i&1};assert(party_receive(&s_party,&m));}
 mon_t m={.species_id=76,.level=60,.exp=exp_for_level(60),.hp=100};assert(party_receive(&s_party,&m));
 s_w.species=25;s_w.level=60;s_w.exp=exp_for_level(60);s_challenge.wild_wins=1;world_debug_save();
}
static void selection(void){
 move_policy_t empty={0};unsigned checks=0;
 for(unsigned species=1;species<=151;species++){
  combat_mon_t a,d;combat_init(&a,species,100,500);combat_init(&d,143,50,500);
  uint16_t ids[COMBAT_MOVE_CAP];int n=combat_known_moves(species,100,ids,COMBAT_MOVE_CAP);assert(n>0);
  move_policy_t policy={0};for(int i=0;i<n;i++)if(i%2)move_policy_set(&policy,ids[i],false);
  for(uint32_t seed=1;seed<80;seed++){
   uint32_t r=seed,q=seed;assert(combat_choose(&a,&d,&r)==combat_choose_filtered(&a,&d,&q,&empty)&&r==q);
   r=seed;unsigned id=combat_choose_filtered(&a,&d,&r,&policy);assert(move_policy_allows(&policy,id));checks++;
  }
 }
 // Direct, charged, copied and random moves all obey the same exclusions.
 combat_mon_t a,d;combat_init(&a,76,60,500);combat_init(&d,143,50,500);
 move_policy_t p={0};move_policy_set(&p,120,false);move_policy_set(&p,153,false);move_policy_set(&p,91,false);
 for(unsigned i=0;i<200;i++){uint32_t rng=i+1;combat_mon_t aa=a,dd=d;battle_round_t r={0};
  aa.charge=1;aa.charge_move=91;combat_turn_filtered(&aa,&dd,1024,&rng,50,153,&r,&p);
  assert(r.move_id!=120&&r.move_id!=153&&r.move_id!=91);
 }
 move_policy_set(&p,53,false);a.mimic_move=53;a.species=151;
 for(uint32_t i=1;i<100;i++){uint32_t rng=i;assert(combat_choose_filtered(&a,&d,&rng,&p)!=53);}
 for(unsigned move=1;move<=250;move++)move_policy_set(&p,move,false);
 assert(move_policy_allows(&p,165));uint32_t rng=5;assert(combat_choose_filtered(&a,&d,&rng,&p)==165);
 move_policy_set(&p,118,true);battle_round_t r={0};combat_turn_filtered(&a,&d,1024,&rng,50,118,&r,&p);assert(r.move_id==165);
 printf("\"ai_choices\":%u,",checks);tests++;
}
static void transactions(void){
 setup();world_party_t view;world_party_snapshot(&view);mon_t m=view.members[1];
 assert(world_move_set(1,&m,85,false)==WORLD_SWITCH_OK);move_policy_t p;
 assert(world_move_policy(1,&m,&p)&&!move_policy_allows(&p,85));
 assert(move_policy_allows(&s_party.policies[0],85));reboot();assert(!move_policy_allows(&s_party.policies[1],85));
 world_party_snapshot(&view);m=view.members[1];
 failure=4;assert(world_move_set(1,&m,85,true)==WORLD_SWITCH_SAVE_FAILED);failure=0;
 assert(!move_policy_allows(&s_party.policies[1],85));reboot();assert(!move_policy_allows(&s_party.policies[1],85));
 world_party_snapshot(&view);m=view.members[1];mon_t stale=m;stale.level--;assert(world_move_set(1,&stale,85,true)==WORLD_SWITCH_STALE);
 assert(world_move_set(1,&m,250,false)==WORLD_SWITCH_INVALID);
 uint16_t ids[COMBAT_MOVE_CAP];int n=combat_known_moves(m.species_id,m.level,ids,COMBAT_MOVE_CAP);
 for(int i=1;i<n;i++)assert(world_move_set(1,&m,ids[i],false)==WORLD_SWITCH_OK);
 assert(world_move_set(1,&m,ids[0],false)==WORLD_SWITCH_LAST_MOVE);
 assert(world_move_set(1,&m,0,true)==WORLD_SWITCH_OK);
 assert(combat_enabled_moves(m.species_id,m.level,&s_party.policies[1])==n);
 assert(world_move_set(1,&m,85,false)==WORLD_SWITCH_OK);
 assert(world_set_leader(1,&m,NULL)==WORLD_SWITCH_OK);assert(!move_policy_allows(&s_party.policies[0],85)&&move_policy_allows(&s_party.policies[1],85));
 reboot();world_party_snapshot(&view);unsigned box_slot=party_box_find(&s_party,76);mon_t box=s_party.box[box_slot];assert(box.species_id==76);
 assert(world_box_exchange(0,&view.members[0],&box)==WORLD_SWITCH_OK);
 assert(!move_policy_allows(&s_party.policies[PARTY_MAX+box_slot],85)&&move_policy_allows(&s_party.policies[0],85));
 reboot();assert(!move_policy_allows(&s_party.policies[PARTY_MAX+box_slot],85));
 assert(world_move_set(PARTY_MAX+box_slot,&s_party.box[box_slot],85,true)==WORLD_SWITCH_OK);
 assert(world_challenge_begin(0));world_party_snapshot(&view);
 assert(world_move_set(0,&view.members[0],33,false)==WORLD_SWITCH_BUSY);tests++;
}
static void growth_and_identity(void){
 party_t p;party_init(&p);mon_t m={.species_id=1,.level=16,.exp=4096,.hp=100};assert(party_receive(&p,&m));
 move_policy_set(&p.policies[0],45,false);p.party[0].species_id=2;
 assert(!move_policy_allows(&p.policies[0],45));
 uint16_t ids[COMBAT_MOVE_CAP];int n=combat_known_moves(2,100,ids,COMBAT_MOVE_CAP);
 for(int i=0;i<n;i++)if(combat_learn_level(2,ids[i])>16)assert(move_policy_allows(&p.policies[0],ids[i]));
 for(unsigned i=1;i<6;i++)assert(party_receive(&p,&m));assert(party_receive(&p,&m));
 assert(move_policy_allows(&p.policies[PARTY_MAX],45));assert(party_exchange_at(&p,0,0));
 assert(!move_policy_allows(&p.policies[PARTY_MAX],45)&&move_policy_allows(&p.policies[0],45));
 save_t saved={.version=SAVE_VERSION},out;save_store_party(&saved,&p);
 assert(!memcmp(saved.move_policies,p.policies,sizeof(p.policies)));
 saved.move_policies[0].disabled[23]|=128;assert(save_decode(&out,&saved,sizeof(saved),0)==SAVE_READ_ERROR);tests++;
}
static void filtered_battles(void){
 setup();move_policy_t policy[PARTY_MAX]={0};uint16_t ids[COMBAT_MOVE_CAP];int n=combat_known_moves(25,60,ids,COMBAT_MOVE_CAP);
 for(unsigned slot=0;slot<6;slot++)for(int i=0;i<n;i++)if(ids[i]!=85)move_policy_set(&policy[slot],ids[i],false);
 trainer_store_t st={.wild_wins=1};assert(trainer_begin_filtered(&st,0,s_party.party,6,1024,123,policy));
 assert(st.session.planned[0]==85||st.session.planned[0]==165);
 st.session.sides[0].mons[0].hp=0;trainer_event_t e;assert(trainer_step_filtered(&st,&e,policy)&&e.kind==TRAINER_SWITCH_NEEDED);
 assert(trainer_switch_filtered(&st,1,true,policy));assert(st.session.planned[0]==85||st.session.planned[0]==165);
 for(unsigned i=0;i<500&&!st.session.finished;i++){
  assert(trainer_step_filtered(&st,&e,policy));if(e.kind==TRAINER_SWITCH_NEEDED){for(unsigned j=0;j<6;j++)if(trainer_switch_filtered(&st,j,true,policy))break;}
  if(e.kind==TRAINER_ATTACK&&e.side==0)assert(e.attack.move_id==85||e.attack.move_id==165||!e.attack.move_id);
 }
 assert(st.session.finished);battle_session_t b;assert(battle_session_init(&b,25,60,143,60,1024,19));b.move_policy=policy[0];
 b.auto_battle=true;for(unsigned i=0;i<500&&!b.finished;i++){battle_round_t r={0};if(!battle_session_step(&b,&r))break;if(r.by_pet)assert(r.move_id==85||r.move_id==165||!r.move_id);}
 assert(b.finished);tests++;
}
int main(void){assert(assets_init());printf("{");selection();transactions();growth_and_identity();filtered_battles();printf("\"cases\":%u,\"save_version\":%u,\"passed\":true}\n",tests,SAVE_VERSION);return 0;}
'''
if __name__=='__main__':h.run()
