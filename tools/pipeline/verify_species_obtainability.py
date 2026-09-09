#!/usr/bin/env python3
"""Audit actual species assets, campaign route generation and capture windows."""
import verify_trainer_campaign as h
h.CASES=r'''
#include "exploration.c"
#define reboot posix_reboot
#include "capture.c"
#undef reboot
int main(void){
 assert(assets_init());unsigned masks[]={0,1,3,15,63,255,4095,8191,16383};
 printf("{\"chapters\":[");
 for(unsigned chapter=0;chapter<9;chapter++){
  exploration_state_t x;exploration_init(&x);enc_refresh_state_t r={0};enc_queue_t q;dex_t d;dex_init(&d);inventory_t bag={0};unsigned seen[152]={0};
  for(unsigned i=0;i<20000;i++){
   x.energy=24;x.route=(i/100)%4;enc_queue_init(&q);
   exploration_event_t e=exploration_step_progress(&x,&r,&q,&d,0,masks[chapter],&bag);
   if(e.species){assert(exploration_species_open(e.species,masks[chapter]));seen[e.species]++;}
  }
  unsigned count=0;
  for(unsigned id=1;id<=151;id++){if(exploration_species_open(id,masks[chapter]))assert(seen[id]);count+=!!seen[id];}
  printf("%s{\"chapter\":%u,\"directly_encountered_species\":%u}",chapter?",":"",chapter,count);
 }
 unsigned min_window=65535;
 for(unsigned id=1;id<=151;id++){
  species_t sp;assert(assets_species(id,&sp)&&sp.catch_rate>0);
  unsigned w=cap_window_width(sp.catch_rate,1024,CAP_BALL_POKE,100);assert(w>0);if(w<min_window)min_window=w;
  bool caught=false;for(unsigned ms=0;ms<10000&&!caught;ms++){
   cap_result_t result;cap_attempt(sp.catch_rate,1024,CAP_BALL_POKE,100,5,ms,123,&result);caught=result.caught;
  }assert(caught);
 }
 printf("],\"species\":151,\"campaign_steps\":180000,\"catchable_with_basic_ball\":151,\"minimum_window_px\":%u}\n",min_window);
}
'''
h.run()
