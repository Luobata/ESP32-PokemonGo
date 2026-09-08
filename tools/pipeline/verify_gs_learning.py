#!/usr/bin/env python3
"""Exhaustive supported Gold/Silver eligibility, monotonic learning and HM mechanics."""
import verify_trainer_campaign as h
h.CASES=r'''
static bool known(unsigned sp,unsigned lv,unsigned id){uint16_t m[COMBAT_MOVE_CAP];int n=combat_known_moves(sp,lv,m,COMBAT_MOVE_CAP);for(int i=0;i<n;i++)if(m[i]==id)return true;return false;}
static void learn(void){
 unsigned checks=0;
 for(unsigned sp=1;sp<=151;sp++){
  bool prev[251]={0};
  for(unsigned lv=1;lv<=100;lv++){
   uint16_t ids[COMBAT_MOVE_CAP];int n=combat_known_moves(sp,lv,ids,COMBAT_MOVE_CAP);bool now[251]={0};
   for(int i=0;i<n;i++){move_t m;assert(combat_move(ids[i],&m));assert(ids[i]<=250&&!now[ids[i]]);now[ids[i]]=true;assert(combat_learn_level(sp,ids[i])<=lv);}
   for(unsigned id=1;id<=250;id++)assert(!prev[id]||now[id]);memcpy(prev,now,sizeof(now));checks++;
  }
 }
 assert(!known(7,24,57)&&known(7,25,57));assert(known(9,25,57));
 assert(known(7,35,127)&&known(7,20,250));assert(!known(25,100,57));
 assert(known(25,100,84)&&known(26,100,84));assert(known(1,100,76));
 combat_mon_t a,d;combat_init(&a,7,40,200);combat_init(&d,74,40,200);uint32_t rng=1;battle_round_t r={.by_pet=true};
 for(unsigned seed=1;seed<100;seed++){combat_init(&d,74,40,200);rng=seed;memset(&r,0,sizeof(r));combat_turn(&a,&d,1024,&rng,50,250,&r);if(!r.missed)break;}
 assert(r.move_id==250&&r.damage>0&&d.trap>0&&combat_valid(&a)&&combat_valid(&d));
 printf("{\"species_level_checks\":%u,\"hm_compatibility\":true,\"never_forgets\":true,\"whirlpool_damage_and_trap\":true}\n",checks);
}
int main(void){assert(assets_init());learn();}
'''
h.run()
