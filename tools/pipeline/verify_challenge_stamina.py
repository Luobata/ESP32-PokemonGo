#!/usr/bin/env python3
"""Actual world/save/trainer C: entry fees, prepaid league, recovery and rollback."""
import json
import subprocess
import verify_world_party as h

h.CASES = r'''
bool assets_species(uint16_t id,species_t *out){
 if(id<1||id>151)return false;
 memset(out,0,sizeof(*out));out->id=id;out->type2=255;
 out->hp=out->attack=out->defense=out->special=out->speed=40;return true;
}
uint32_t assets_species_count(void){return 151;}
#include "trainer.c"

static void ready(unsigned stamina){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 s_w.level=30;s_w.exp=exp_for_level(30);
 s_w.pet.satiety=s_w.pet.mood=70*NURT_Q;s_w.pet.stamina=stamina*NURT_Q;
 s_challenge.wild_wins=1;s_challenge.defeated=0x1fff;
 assert(save_now("fixture"));
}
static void boundary(void){
 const uint8_t ids[]={14,0,8,13},costs[]={5,10,20,10};
 for(unsigned i=0;i<4;i++){
  ready(costs[i]);s_w.pet.stamina--;assert(save_now("fraction"));
  trainer_store_t before=s_challenge;unsigned n=writes;
  assert(world_challenge_start(ids[i])==WORLD_CHALLENGE_NO_STAMINA);
  assert(s_w.pet.stamina==costs[i]*NURT_Q-1&&!memcmp(&before,&s_challenge,sizeof(before))&&writes==n);
  assert(nurture_wait_minutes(&s_w.pet,costs[i])==1);
  assert(nurture_stamina_points(&s_w.pet)==costs[i]-1);tests++;
  s_w.pet.stamina++;assert(world_challenge_start(ids[i])==WORLD_CHALLENGE_OK);
  assert(s_w.pet.stamina==0&&s_challenge.session.ability==1024);
  assert(world_challenge_start(ids[i])==WORLD_CHALLENGE_BUSY&&s_w.pet.stamina==0);
  reboot();assert(s_storage_ready&&!s_starter_pending&&s_w.pet.stamina==0&&s_challenge.session.active);
  assert(world_challenge_start(ids[i])==WORLD_CHALLENGE_BUSY&&s_w.pet.stamina==0);tests+=6;
 }
}
static void rollback(void){
 const unsigned failures[]={1,2,4};
 for(unsigned id=0;id<4;id++)for(unsigned f=0;f<3;f++){
  const uint8_t ids[]={14,0,8,13};ready(30);
  trainer_store_t before=s_challenge;uint8_t saved[sizeof(disk)];memcpy(saved,disk,sizeof(saved));
  failure=failures[f];assert(world_challenge_start(ids[id])==WORLD_CHALLENGE_SAVE_FAILED);failure=0;
  assert(s_w.pet.stamina==30*NURT_Q&&!memcmp(&before,&s_challenge,sizeof(before))&&!memcmp(saved,disk,sizeof(saved)));
  unsigned cost=trainer_stamina_cost(&before,ids[id]);
  assert(world_challenge_start(ids[id])==WORLD_CHALLENGE_OK&&s_w.pet.stamina==(int32_t)((30-cost)*NURT_Q));tests+=2;
 }
 ready(30);s_challenge.defeated=0;s_challenge.wild_wins=0;
 unsigned n=writes;assert(world_challenge_start(0)==WORLD_CHALLENGE_LOCKED);
 assert(world_challenge_start(255)==WORLD_CHALLENGE_LOCKED);
 assert(writes==n&&s_w.pet.stamina==30*NURT_Q);tests+=2;
}
static void league(void){
 ready(20);
 for(unsigned id=8;id<=12;id++){
  assert(trainer_stamina_cost(&s_challenge,id)==(id==8?20:0));
  assert(world_challenge_start(id)==WORLD_CHALLENGE_OK&&s_w.pet.stamina==0);
  s_challenge.session.finished=1;s_challenge.session.won=1;
  assert(world_challenge_settle()&&s_w.pet.stamina==0);
  assert(world_challenge_settle()&&s_w.pet.stamina==0);
  reboot();assert(s_storage_ready&&s_w.pet.stamina==0);
  assert(s_challenge.league_active==(id<12));tests+=5;
 }
 assert(world_challenge_start(8)==WORLD_CHALLENGE_NO_STAMINA);
 assert(world_challenge_start(13)==WORLD_CHALLENGE_NO_STAMINA);tests+=2;
 // Quitting the league discards its prepayment; a fresh run costs 20 again.
 ready(40);assert(world_challenge_begin(8));assert(world_challenge_retire());
 assert(world_challenge_settle()&&!s_challenge.league_active&&s_w.pet.stamina==20*NURT_Q);
 assert(world_challenge_begin(8)&&s_w.pet.stamina==0);tests+=2;
}
static void outcomes(void){
 for(unsigned outcome=0;outcome<3;outcome++){
  ready(10);assert(world_challenge_begin(14));
  uint32_t exp=s_w.exp;
  if(outcome==2)assert(world_challenge_retire());
  else{s_challenge.session.finished=1;s_challenge.session.won=outcome;}
  failure=4;assert(!world_challenge_settle());failure=0;
  assert(s_w.pet.stamina==5*NURT_Q&&s_w.pet.mood==70*NURT_Q&&s_w.exp==exp);
  assert(world_challenge_settle());
  int mood=(outcome?70:65)*NURT_Q;
  assert(s_w.pet.stamina==5*NURT_Q&&s_w.pet.mood==mood);
  uint32_t after=s_w.exp;assert(outcome==2?after==exp:after>exp);
  assert(world_challenge_settle()&&s_w.exp==after&&s_w.pet.mood==mood);
  reboot();assert(s_storage_ready&&s_w.pet.stamina==5*NURT_Q&&s_w.pet.mood==mood);tests+=5;
 }
}
static void recover_during_write(void){
 xSemaphoreTake(s_lock,portMAX_DELAY);s_w.pet.stamina+=NURT_Q;s_dirty=true;xSemaphoreGive(s_lock);
}
static void recovery(void){
 ready(0);assert(nurture_ability_factor(&s_w.pet)==1024);
 assert(nurture_wait_minutes(&s_w.pet,5)==6);
 assert(nurture_wait_minutes(&s_w.pet,10)==12);
 assert(nurture_wait_minutes(&s_w.pet,20)==24);
 nurture_tick(&s_w.pet,0,0,false);nurture_tick(&s_w.pet,7*60*1000000LL,0,false);
 assert(!nurture_wait_minutes(&s_w.pet,5)&&world_challenge_begin(14));
 nurture_t n=s_w.pet;n.stamina=0;n.satiety=n.mood=70*NURT_Q;
 assert(nurture_ability_factor(&n)==1024);n.satiety=24*NURT_Q;assert(nurture_ability_factor(&n)==614);
 n.satiety=70*NURT_Q;n.mood=24*NURT_Q;assert(nurture_ability_factor(&n)==614);
 n.satiety=n.mood=70*NURT_Q;n.last_us=0;nurture_tick(&n,9*3600*1000000LL,0,false);assert(n.stamina==NURT_MAX);
 tests+=8;
 for(unsigned fail=0;fail<2;fail++){
  ready(10);extra_commit_hook=recover_during_write;failure=fail?4:0;
  assert(world_challenge_begin(14)==!fail);failure=0;extra_commit_hook=NULL;
  assert(s_w.pet.stamina==(fail?11:6)*NURT_Q&&s_dirty);tests+=2;
 }
}
int main(void){boundary();rollback();league();outcomes();recovery();
 printf("{\"cases\":%u,\"save_version\":%d,\"save_bytes\":%zu}\n",tests,SAVE_VERSION,sizeof(save_t));return 0;}
'''

if __name__ == '__main__':
    try:
        result = h.run(h.ROOT)
    except subprocess.CalledProcessError as e:
        print(e.stdout or ''); print(e.stderr or ''); raise
    result.update(sanitized=True, scope='Production world/save/trainer/nurture, simulated NVS faults/reboots and recovery during commits')
    out = h.ROOT / 'reports/evidence/challenge-stamina-2026-09-10'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'transactions.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
