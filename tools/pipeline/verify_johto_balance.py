#!/usr/bin/env python3
"""Deterministic unmodified endgame battles; reports balance rather than faking wins."""
import verify_trainer_campaign as h
h.CASES=r'''
int main(void){assert(assets_init());
 for(unsigned type=0;type<3;type++)for(unsigned id=TRAINER_JOHTO_FIRST+8;id<TRAINER_JOHTO_FIRST+11;id++){
  unsigned wins=0,total=0,max_round=0;
  for(unsigned seed=1;seed<=80;seed++){
   mon_t team[6]={0};for(unsigned i=0;i<6;i++){team[i]=(mon_t){.species_id=type==1?(unsigned[]){25,26,135,145,181,171}[i]:(unsigned[]){154,160,157,181,197,248}[i],.level=type==2?70:90,.hp=100};}
   trainer_store_t t={.defeated=0x3fff};assert(trainer_begin(&t,id,team,6,1024,seed));trainer_event_t ev;unsigned steps=0;
   while(!t.session.finished&&steps++<2000){assert(trainer_step(&t,&ev));if(ev.kind==TRAINER_SWITCH_NEEDED){bool found=false;for(unsigned i=0;i<6;i++)if(trainer_switch(&t,i,true)){found=true;break;}assert(found);}}
   assert(t.session.finished&&steps<2000);wins+=t.session.won;total+=steps;if(steps>max_round)max_round=steps;
  }
  printf("profile=%u trainer=%u wins=%u/80 mean_steps=%u max_steps=%u\n",type,id,wins,total/80,max_round);
 }
 return 0;
}
'''
if __name__=='__main__':h.run()
