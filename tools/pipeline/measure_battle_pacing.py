#!/usr/bin/env python3
"""Measure real combat actions over deterministic wild matchups, without rendering."""
import verify_trainer_campaign as h
h.CASES=r'''
int main(void){assert(assets_init());
 const unsigned cases[][4]={{25,5,19,5},{4,10,10,10},{25,20,19,20},{1,20,74,20},{6,50,9,50},{25,50,143,50},{65,50,68,50},{149,80,149,80}};
 printf("{\"cases\":[");
 for(unsigned k=0;k<8;k++){
  unsigned total=0,cap=0,wins=0,min=999,max=0,hp=0,ehp=0;
  for(unsigned seed=1;seed<=100;seed++){
   battle_session_t s;assert(battle_session_init(&s,cases[k][0],cases[k][1],cases[k][2],cases[k][3],1024,seed));hp=s.pet_hp;ehp=s.wild_hp;
   battle_round_t r;while(!s.finished)assert(battle_session_step(&s,&r));
   total+=s.attack_count;cap+=s.pet_hp&&s.wild_hp;wins+=s.won;if(s.attack_count<min)min=s.attack_count;if(s.attack_count>max)max=s.attack_count;
  }
  printf("%s{\"pet\":%u,\"level\":%u,\"wild\":%u,\"wild_level\":%u,\"pet_hp\":%u,\"wild_hp\":%u,\"mean_actions\":%.2f,\"min\":%u,\"max\":%u,\"timeouts\":%u,\"wins\":%u}",k?",":"",cases[k][0],cases[k][1],cases[k][2],cases[k][3],hp,ehp,total/100.0,min,max,cap,wins);
 }
 printf("]}\n");}
'''
if __name__=='__main__':h.run()
