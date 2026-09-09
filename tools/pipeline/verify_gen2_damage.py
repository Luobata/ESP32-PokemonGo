#!/usr/bin/env python3
"""Golden Gen-II stat/damage vectors plus V12->V13 live battle migration."""
import verify_trainer_campaign as h
h.CASES=r'''
static void stats(void){
 // Crystal base stats, DV=15 and stat EXP=0: HP/Atk/Def/Speed/SpAtk/SpDef.
 const unsigned golden[][8]={
 {25,5,20,12,9,15,11,10},{25,50,110,75,50,110,70,60},
 {25,100,210,145,95,215,135,115},{65,50,130,70,65,140,155,105},
 {113,50,325,25,25,70,55,125},{143,50,235,130,85,50,85,130},
 {68,50,165,150,100,75,85,105},{9,50,154,103,120,98,105,125}};
 for(unsigned i=0;i<sizeof(golden)/sizeof(golden[0]);i++)for(unsigned stat=0;stat<6;stat++)assert(combat_stat(golden[i][0],golden[i][1],stat)==golden[i][stat+2]);
 for(unsigned id=1;id<=151;id++)for(unsigned lv=1;lv<=100;lv++){
  battle_session_t s;assert(battle_session_init(&s,id,lv,id,lv,1024,1));
  assert(s.pet_hp==combat_stat(id,lv,COMBAT_HP)&&s.wild_hp==s.pet_hp&&combat_valid(&s.fighters[0]));
 }
 tests++;
}
static void damage(void){
 // Golden pre-random normal/critical damage, calculated from the original
 // floor sequence using the literal stats above, not generated game tables.
 const unsigned vectors[][5]={
 {25,9,85,74,144}, {65,68,94,180,354}, {25,143,33,15,28},
 {113,143,57,19,36}, {25,113,85,37,72}
 };
 for(unsigned i=0;i<sizeof(vectors)/sizeof(vectors[0]);i++){
  unsigned normal=0,crit=0;
  for(unsigned seed=1;seed<=1000;seed++){
   combat_mon_t a,d;combat_init(&a,vectors[i][0],50,10000);combat_init(&d,vectors[i][1],50,10000);
   uint32_t rng=seed;battle_round_t r={0};combat_turn(&a,&d,1024,&rng,50,vectors[i][2],&r);
   if(r.missed)continue;
   unsigned base=vectors[i][r.critical?4:3];bool matches=false;
   for(unsigned random=217;random<=255;random++)matches|=r.damage==base*random/255;
   assert(matches);if(r.critical)crit++;else normal++;
  }
  assert(normal&&crit);
 }
 // Level 100 and the repeated byte reduction with boosted screens.
 for(unsigned seed=1;seed<=1000;seed++)for(unsigned boosted=0;boosted<2;boosted++){
  combat_mon_t a,d;combat_init(&a,150,100,10000);combat_init(&d,68,100,10000);
  if(boosted){a.special=6;d.safety.special_defense=6;d.light_screen=5;}
  uint32_t rng=seed;battle_round_t r={0};combat_turn(&a,&d,1024,&rng,50,94,&r);
  if(r.missed)continue;
  unsigned base=r.critical?762:boosted?140:384;
  assert(r.damage>=base*217/255&&r.damage<=base);
 }
 // Screens, burn, and separate SpDef boosts: critical ignores nonpositive
 // attacker-vs-defender stage differences; Amnesia cannot raise offense.
 for(unsigned seed=1;seed<=400;seed++){
  combat_mon_t a,d;combat_init(&a,25,50,10000);combat_init(&d,113,50,10000);
  d.light_screen=5;uint32_t rng=seed;battle_round_t r={0};
  combat_turn(&a,&d,1024,&rng,50,85,&r);
  if(!r.missed){unsigned base=r.critical?72:19;assert(r.damage>=base*217/255&&r.damage<=base);}
  combat_init(&a,25,50,10000);combat_init(&d,113,50,10000);d.safety.special_defense=2;rng=seed;memset(&r,0,sizeof(r));
  combat_turn(&a,&d,1024,&rng,50,85,&r);
  if(!r.missed){unsigned base=r.critical?72:19;assert(r.damage>=base*217/255&&r.damage<=base);}
 }
 combat_mon_t a,d;combat_init(&a,25,50,1000);combat_init(&d,113,50,1000);uint32_t rng=3;battle_round_t r={0};
 combat_turn(&a,&d,1024,&rng,50,133,&r);assert(combat_sp_def_stage(&a)==2&&a.special==0);
 combat_turn(&a,&d,1024,&rng,50,114,&r);assert(!combat_sp_def_stage(&a)&&!a.special);
 tests++;
}
static void migration(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);save_t current;assert(save_read(&current));
 current.version=12;trainer_store_t *st=&current.challenge;
 st->wild_wins=17;st->defeated=255;st->league_active=1;st->league_stage=9;
 trainer_session_t *s=&st->session;s->active=1;s->trainer=9;s->rng=123;s->ability=1024;
 for(unsigned side=0;side<2;side++){
  s->sides[side].count=3;
  for(unsigned i=0;i<3;i++){
   combat_mon_t *m=&s->sides[side].mons[i];combat_init(m,25,50,190);m->hp=(unsigned[]){95,1,0}[i];
   m->substitute=i?0:47;m->special=2;m->safety.marker=0x5347;m->safety.special_defense=0;
   m->safety.stalled=3;m->safety.fatigue=2;m->safety.low_hp=m->hp;m->status=1;
  }
 }
 assert(trainer_store_valid(st));memcpy(disk,&current,sizeof(current));disk_len=sizeof(current);
 save_t next;assert(save_read_status(&next)==SAVE_READ_MIGRATED&&next.version==13);
 assert(!memcmp(next.party,current.party,PARTY_BYTES));assert(next.challenge.defeated==255&&next.challenge.league_stage==9&&next.challenge.session.rng==123);
 for(unsigned side=0;side<2;side++)for(unsigned i=0;i<3;i++){
  const combat_mon_t *m=&next.challenge.session.sides[side].mons[i];assert(m->max_hp==110&&m->hp==((unsigned[]){55,1,0})[i]);
  assert(m->special==2&&combat_sp_def_stage(m)==2&&m->status==1&&m->safety.stalled==3&&m->safety.fatigue==2);
  assert(m->substitute==(i?0:27));
 }
 assert(trainer_store_valid(&next.challenge)&&save_write(&next));save_t twice;assert(save_read_status(&twice)==SAVE_READ_OK&&!memcmp(&next,&twice,sizeof(next)));
 // Reject malformed old saves before rescaling, and leave bytes on disk intact.
 current.challenge.session.sides[0].mons[0].hp=65535;memcpy(disk,&current,sizeof(current));
 assert(save_read_status(&next)==SAVE_READ_ERROR&&!memcmp(disk,&current,sizeof(current)));
 assert(sizeof(save_t)==3664&&erase_calls==0);tests++;
}
int main(void){assert(assets_init());stats();damage();migration();printf("{\"status\":\"PASS\",\"groups\":%u,\"stat_cases\":15100,\"damage_seeds\":7800,\"save_bytes\":%zu,\"sanitized\":true}\n",tests,sizeof(save_t));}
'''
if __name__=='__main__':h.run()
