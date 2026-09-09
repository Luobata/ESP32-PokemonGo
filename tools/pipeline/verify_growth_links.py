#!/usr/bin/env python3
"""Real C save transactions: encounter XP, nurture factors, stamina and box swap."""
import json,subprocess
import verify_world_party as h
import verify_exploration_routes as base
h.CASES=base.CASES[:base.CASES.index('static void core')]+r'''
static void ready(void){fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_w.level=10;s_w.exp=exp_for_level(10);s_w.pet.satiety=s_w.pet.mood=50*NURT_Q;s_w.pet.intimacy=0;s_w.pet.stamina=90*NURT_Q;world_debug_save();}
static uint16_t encounter(void){encounter_t e={.species_id=133,.rarity=3,.hp_ratio=100};enc_queue_push(&s_queue,&e);return s_queue.items[s_queue.count-1].uid;}
static void capture(void){
 ready();uint16_t uid=encounter();uint32_t before=s_w.exp;mon_t m={.species_id=133,.level=10,.hp=100,.exp=exp_for_level(10)};
 for(int f=1;f<=4;f++){if(f==3)continue;party_t old=s_party;failure=f;assert(!world_capture_uid(uid,&m));failure=0;assert(s_w.exp==before&&!memcmp(&old,&s_party,sizeof(old))&&enc_queue_find(&s_queue,uid));}
 assert(world_capture_uid(uid,&m));assert(s_w.exp==before+110);assert(!world_capture_uid(uid,&m)&&s_w.exp==before+110);
 reboot();assert(s_w.exp==before+110&&s_party.party_count==2);tests+=5;
}
static void rewards(void){
 for(unsigned won=0;won<2;won++){
  ready();uint16_t uid=encounter();battle_session_t b={.initialized=true,.started=true,.finished=true,.won=won,.pet_species=25,.wild_species=133,.pet_level=10,.wild_level=10};
  assert(world_battle_set_uid(uid,&b));uint32_t before=s_w.exp;uint16_t gain;
  for(int f=1;f<=4;f++){if(f==3)continue;failure=f;assert(!world_battle_reward_uid(uid,&gain));failure=0;assert(s_w.exp==before&&!s_active.session.reward_settled);}
  assert(world_battle_reward_uid(uid,&gain)&&gain==(won?100:30));assert(s_w.exp==before+gain);
  assert(world_battle_reward_uid(uid,&gain)&&gain==0);uint32_t kept=s_w.exp;
  reboot();assert(s_w.exp==kept&&!s_active.encounter.uid);tests+=5;
 }
}
static void stamina(void){
 ready();exploration_state_t old=s_exploration;s_w.pet.stamina=4*NURT_Q;assert(world_explore().kind==EXPLORE_NO_STAMINA&&!memcmp(&old,&s_exploration,sizeof(old)));
 s_w.pet.stamina=5*NURT_Q;failure=4;assert(world_explore().kind==EXPLORE_SAVE_FAILED);failure=0;assert(s_w.pet.stamina==5*NURT_Q&&s_exploration.energy==3);
 assert(world_explore().kind==EXPLORE_ENCOUNTER&&s_w.pet.stamina==0&&s_exploration.energy==2);
 world_debug_save();reboot();assert(s_w.pet.stamina==0&&s_exploration.energy==2);
 nurture_t n={.satiety=20*NURT_Q,.mood=20*NURT_Q,.stamina=10*NURT_Q,.last_us=0};nurture_rest(&n);assert(n.stamina==10*NURT_Q);
 for(unsigned i=0;i<ITEM_COUNT;i++){item_use_result_t out;items_apply(i,25,10,&n,&out);assert(out.after.stamina<=n.stamina);}
 nurture_tick(&n,3600000000LL,100,false);assert(n.stamina==22*NURT_Q);
 nurture_t low={0},high={.satiety=NURT_MAX,.mood=NURT_MAX,.intimacy=NURT_MAX};assert(nurture_exp_percent(&low)==80&&nurture_exp_percent(&high)==130);assert(nurture_rare_bonus(&low)==0&&nurture_rare_bonus(&high)==50);
 // Paired deterministic streams: care may improve tiers but cannot bypass story locks.
 enc_refresh_state_t r={0};enc_queue_t q;dex_t d;dex_init(&d);inventory_t inv={0};unsigned improves=0;
 for(unsigned i=0;i<3000;i++){
  exploration_state_t a={.energy=1,.steps=i,.route=i%4},b=a;enc_refresh_state_t ra=r,rb=r;enc_queue_init(&q);
  exploration_event_t ea=exploration_step_nurtured(&a,&ra,&q,&d,0,0,&inv,&low);enc_queue_init(&q);
  exploration_event_t eb=exploration_step_nurtured(&b,&rb,&q,&d,0,0,&inv,&high);assert(eb.rarity>=ea.rarity&&exploration_species_open(eb.species,0));improves+=eb.rarity>ea.rarity;
 }assert(improves>0);tests+=8;
}
static void boxes(void){
 ready();s_party.box[132]=(mon_t){.species_id=133,.level=12,.hp=70,.flags=1,.intimacy=61,.exp=exp_for_level(12)};world_debug_save();world_party_t v;world_party_snapshot(&v);mon_t old=v.members[0],in=s_party.box[132];
 failure=4;assert(world_box_exchange(0,&old,&in)==WORLD_SWITCH_SAVE_FAILED);failure=0;assert(s_w.species==25&&s_party.box[132].species_id==133);
 assert(world_box_exchange(0,&old,&in)==WORLD_SWITCH_OK);assert(s_w.species==133&&s_w.pet.intimacy==61*NURT_Q&&s_party.box[132].species_id==25&&s_party.party[0].flags==1);
 int32_t energy=s_w.pet.stamina;reboot();assert(s_w.species==133&&s_party.box[132].species_id==25&&s_w.pet.stamina==energy);
 assert(world_box_exchange(0,&old,&in)==WORLD_SWITCH_STALE);
 party_t p=s_party;p.box[24]=(mon_t){.species_id=133,.level=3};party_t before=p;assert(party_exchange(&p,0,25)&&p.party[0].species_id==25&&!memcmp(&p.box[24],&before.box[24],sizeof(mon_t))&&p.box[132].species_id==133);
 uint16_t uid=encounter();battle_session_t battle={.initialized=true,.started=true,.pet_species=133,.wild_species=133};assert(world_battle_set_uid(uid,&battle));world_party_snapshot(&v);in=s_party.box[132];assert(world_box_exchange(0,&v.members[0],&in)==WORLD_SWITCH_BUSY);tests+=5;
}
int main(void){capture();rewards();stamina();boxes();printf("{\"cases\":%u,\"paired_rarity_steps\":3000,\"save_version\":%d,\"save_bytes\":%zu}\n",tests,SAVE_VERSION,sizeof(save_t));return 0;}
'''
try:r=h.run(h.ROOT)
except subprocess.CalledProcessError as e:print(e.stderr);raise
p=h.ROOT/'reports/evidence/growth-links-2026-09-08';p.mkdir(parents=True,exist_ok=True);(p/'world.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
