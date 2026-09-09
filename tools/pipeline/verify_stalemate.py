#!/usr/bin/env python3
"""Shared-core anti-stall semantics, actual wild/trainer completion and save ABI."""
import verify_trainer_campaign as h
h.CASES=r'''
static combat_mon_t a,d;static battle_round_t r;static uint32_t rng=123;
static void pair(void){combat_init(&a,25,60,500);combat_init(&d,143,60,500);memset(&r,0,sizeof(r));}
static void use(unsigned id){memset(&r,0,sizeof(r));combat_turn(&a,&d,1024,&rng,50,id,&r);}
static void selection(void){
 combat_init(&a,129,5,100);combat_init(&d,92,5,100);
 assert(combat_choose(&a,&d,&rng)==165);use(165);assert(r.damage&&a.hp<100&&d.hp<100);
 combat_init(&a,132,5,100);assert(combat_choose(&a,&d,&rng)==144);
 pair();unsigned attacks=0;
 for(unsigned seed=1;seed<=2000;seed++){uint32_t random=seed;move_t m;assert(combat_move(combat_choose(&a,&d,&random),&m));attacks+=m.power>0;}
 assert(attacks>=1400);printf("attack choices: %u/2000\n",attacks);
 pair();use(14);use(104);
 for(unsigned seed=1;seed<=200;seed++){uint32_t random=seed;move_t m;assert(combat_move(combat_choose(&a,&d,&random),&m));assert(m.power>0);}
 // The only normally damaging move of low-level Rattata is immune against Gastly.
 combat_init(&a,19,1,100);combat_init(&d,92,1,100);assert(combat_choose(&a,&d,&rng)==165);
 // Archived move IDs are not confused with initialized safety state.
 a.moves[0]=33;a.moves[1]=98;use(165);assert(combat_valid(&a));tests++;
}
static void fatigue_rules(void){
 pair();a.hp=d.hp=250;
 for(unsigned round=1;round<=8;round++){
  use(105);battle_round_t other={0};combat_turn(&d,&a,1024,&rng,50,105,&other);
  combat_finish_round(&a,&d,&r);assert((r.fatigue>0)==(round==8));
 }
 assert(a.hp==475&&d.hp==475&&strstr(combat_feedback(&r),"苦战"));
 a.hp=100;use(105);assert(r.healed==225); // 10% reduced recovery, including Rest/drain via shared heal.
 a.hp=100;use(156);assert(r.healed==400||a.hp==500); // capped missing HP still applies.
 for(unsigned round=0;round<15&&a.hp&&d.hp;round++){
  a.status=d.status=0;use(105);battle_round_t other={0};combat_turn(&d,&a,1024,&rng,50,105,&other);combat_finish_round(&a,&d,&r);
 }
 assert(!a.hp||!d.hp);
 pair();for(unsigned i=0;i<7;i++){use(150);combat_finish_round(&a,&d,&r);assert(!r.fatigue);}
 d.hp--;use(150);combat_finish_round(&a,&d,&r);assert(!r.fatigue);
 for(unsigned i=0;i<7;i++){use(150);combat_finish_round(&a,&d,&r);assert(!r.fatigue);}
 use(150);combat_finish_round(&a,&d,&r);assert(r.fatigue==1);
 d.hp=0;a.hp=1;r.fatigue=0;combat_finish_round(&a,&d,&r);assert(a.hp==1&&!r.fatigue);
 tests++;
}
static void integration(void){
 for(unsigned seed=1;seed<=100;seed++){
  battle_session_t wild;assert(battle_session_init(&wild,129,5,129,5,1024,seed));
  for(unsigned n=0;n<BATTLE_MAX_ROUNDS&&!wild.finished;n++)assert(battle_session_step(&wild,&r));
  assert(wild.finished&&(!wild.pet_hp||!wild.wild_hp));
 }
 trainer_store_t st={.wild_wins=1};mon_t mon={.species_id=129,.level=5,.hp=100};assert(trainer_begin(&st,0,&mon,1,1024,123));
 combat_init(&st.session.sides[0].mons[0],129,5,100);combat_init(&st.session.sides[1].mons[0],129,5,100);
 st.session.sides[1].count=1;st.session.planned[0]=st.session.planned[1]=165;
 trainer_event_t e;for(unsigned i=0;i<30&&!st.session.finished;i++){assert(trainer_step(&st,&e));assert(trainer_store_valid(&st));}
 assert(st.session.finished&&st.session.turns<30);
 // Persistence keeps exact binary compatibility and safety state across resume.
 assert(sizeof(save_t)==3664);pair();use(104);combat_mon_t restored;memcpy(&restored,&a,sizeof(a));
 uint32_t x=1,y=1;assert(combat_choose(&a,&d,&x)==combat_choose(&restored,&d,&y));
 tests++;
}
int main(void){assert(assets_init());selection();fatigue_rules();integration();printf("{\"status\":\"PASS\",\"groups\":%u,\"wild_seeds\":100,\"save_bytes\":%zu,\"sanitized\":true}\n",tests,sizeof(save_t));}
'''
if __name__=='__main__':h.run()
