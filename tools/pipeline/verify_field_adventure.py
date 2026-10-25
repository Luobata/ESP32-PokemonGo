#!/usr/bin/env python3
"""Production world/save/bank transactions for radar and walkable field circuits."""
import verify_trainer_campaign as h
from save_history_fixtures import c_cases
h.CASES=c_cases()+r'''
static save_t before,after,trial;
static void ready(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 s_w.pet.stamina=100*NURT_Q;s_w.level=60;s_w.exp=exp_for_level(60);s_queue.count=0;
 s_johto.phase=JOHTO_ACTIVE;s_johto.starter=152;s_johto.badges=255;
 assert(johto_receive_egg(&s_johto,15));s_w.last_ap_count=16;s_field_scan_us=esp_timer_get_time();world_debug_save();assert(save_read(&before));
}
static void same(void){world_debug_save();assert(save_read(&after));assert(!memcmp(&before,&after,sizeof(before)));}
static void transactions(void){
 encounter_t e,untouched;memset(&e,0xa5,sizeof(e));untouched=e;
 for(unsigned map=0;map<3;map++){
  e=untouched;ready();assert(world_field_search(map,&e)==FIELD_NEED_CLUES);same();
  for(unsigned p=0;p<3;p++){
   for(unsigned f=0;f<3;f++){failure=(unsigned[]){1,2,4}[f];assert(world_field_observe(map,p)==FIELD_SAVE_FAILED);failure=0;same();}
   assert(world_field_observe(map,p)==FIELD_OK);world_debug_save();assert(save_read(&before));reboot();assert(s_field.visited[map]==(1u<<(p+1))-1);
   assert(world_field_observe(map,p)==FIELD_OK);same();assert(s_johto.explorations==0&&s_johto.egg_steps==0);
  }
  for(unsigned f=0;f<3;f++){failure=(unsigned[]){1,2,4}[f];assert(world_field_search(map,&e)==FIELD_SAVE_FAILED);failure=0;same();assert(!memcmp(&e,&untouched,sizeof(e)));}
  assert(world_field_search(map,&e)==FIELD_OK);assert(s_field.serial==1&&s_field.map_claims==1&&!s_field.visited[map]);
  assert(s_queue.count==1&&s_w.pet.stamina==95*NURT_Q&&s_johto.explorations==1&&s_johto.egg_steps==1);
  assert(!memcmp(&s_queue.items[0],&e,sizeof(e)));for(unsigned k=0;k<6;k++)assert(!s_johto.legend_clues[k]);
  reboot();assert(world_field_search(map,&e)==FIELD_COOLDOWN);assert(s_queue.count==1&&s_w.pet.stamina==95*NURT_Q);
 }
 ready();for(unsigned f=0;f<3;f++){failure=(unsigned[]){1,2,4}[f];assert(world_field_search(FIELD_RADAR,&e)==FIELD_SAVE_FAILED);failure=0;same();}
 assert(world_field_search(FIELD_RADAR,&e)==FIELD_OK);assert(s_field.radar_claims==1&&s_w.pet.stamina==95*NURT_Q);reboot();
 assert(world_field_search(FIELD_RADAR,&e)==FIELD_NO_SIGNAL);s_w.last_ap_count=16;s_field_scan_us=esp_timer_get_time();assert(world_field_search(FIELD_RADAR,&e)==FIELD_COOLDOWN);
 s_refresh.online_s=120;assert(world_field_search(FIELD_RADAR,&e)==FIELD_OK);
}
static void gates(void){
 ready();encounter_t e;s_w.last_ap_count=0;assert(world_field_search(FIELD_RADAR,&e)==FIELD_NO_SIGNAL);s_w.last_ap_count=16;
 s_w.pet.stamina=NURT_EXPLORE_COST-1;assert(world_field_search(FIELD_RADAR,&e)==FIELD_NO_STAMINA);s_w.pet.stamina=NURT_EXPLORE_COST;
 assert(world_field_search(FIELD_RADAR,&e)==FIELD_OK&&s_w.pet.stamina==0);
 ready();s_johto.badges=1;assert(world_field_observe(1,0)==FIELD_LOCKED);s_johto.badges=3;assert(world_field_observe(1,0)==FIELD_OK&&world_field_observe(0,0)==FIELD_LOCKED);
 ready();s_queue.count=ENC_QUEUE_LIMIT;assert(world_field_search(FIELD_RADAR,&e)==FIELD_FULL&&s_w.pet.stamina==100*NURT_Q);
 ready();s_challenge.session.active=1;assert(world_field_search(FIELD_RADAR,&e)==FIELD_BUSY);assert(world_field_observe(0,0)==FIELD_BUSY);
 ready();before.field.version=2;assert(save_decode(&after,&before,sizeof(before),0)==SAVE_READ_ERROR);before.field.version=1;before.field.visited[0]=8;assert(save_decode(&after,&before,sizeof(before),0)==SAVE_READ_ERROR);
}
static void distribution(void){
 ready();assert(save_read(&before));
 for(unsigned mode=0;mode<4;mode++){
  unsigned shiny=0,count[6]={0},stars[6]={0};
  for(unsigned seed=1;seed<=30000;seed++){
   trial=before;trial.field.visited[0]=trial.field.visited[1]=trial.field.visited[2]=7;encounter_t e;
   assert(field_search_apply(&trial,mode,16,seed%4,seed,&e)==FIELD_OK);assert(e.level>=1&&e.level<=100);shiny+=e.is_shiny;count[e.rarity]++;stars[e.rarity]+=e.is_shiny;
   assert(trial.pet.stamina==95*NURT_Q&&trial.queue.count==1&&trial.field.serial==1);
  }
  unsigned expected=30000/field_shiny_denominator(mode);assert(shiny>expected*8/10&&shiny<expected*12/10);
  printf("mode %u: %u/30000 shiny; rarity counts",mode,shiny);for(unsigned i=1;i<6;i++)printf(" %u/%u",stars[i],count[i]);puts("");
 }
}
static void history_check(void){
 for(unsigned i=0;i<sizeof(history)/sizeof(*history);i++){assert(save_decode(&after,history[i].data,history[i].size,0)!=SAVE_READ_ERROR);history_assert(&after,history[i].version);}
 ready();s_field.version=1;s_field.map_due[2]=180;s_field.visited[2]=5;world_debug_save();reboot();assert(s_field.map_due[2]==180&&s_field.visited[2]==5);
}
int main(void){assert(assets_init());transactions();gates();distribution();history_check();assert(!erase_calls);puts("PASS: V5-V32, unchanged rejection, real world/save bank commits, reboot cooldown, circuit/egg/stamina atomic, independent shiny probability");}
'''
if __name__=='__main__':h.run()
