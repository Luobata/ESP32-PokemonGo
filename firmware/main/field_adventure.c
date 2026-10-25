#include "field_adventure_core.h"
#include "assets.h"
#include <limits.h>
static uint32_t field_mix(uint32_t x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);}
static uint32_t deadline(uint32_t now,unsigned delay){return now>UINT32_MAX-delay?UINT32_MAX:now+delay;}
static unsigned field_rarity(unsigned id){species_t p;if(!assets_species(id,&p))return 1;unsigned n=p.hp+p.attack+p.defense+p.special+p.speed;return n<250?1:n<330?2:n<400?3:n<470?4:5;}
unsigned field_observe_apply(save_t *s,unsigned map,unsigned point){
 if(!s||point>=3||!field_map_open(&s->johto,map))return FIELD_LOCKED;
 s->field.version=1;s->field.visited[map]|=1u<<point;return FIELD_OK;
}
unsigned field_search_apply(save_t *s,unsigned mode,unsigned signals,unsigned place,uint32_t seed,encounter_t *out){
 if(!s||!out||mode>FIELD_RADAR)return FIELD_LOCKED;
 if(s->challenge.session.active||s->challenge.league_active||s->activities.run.kind)return FIELD_BUSY;
 if(mode==FIELD_RADAR){if(!signals)return FIELD_NO_SIGNAL;}
 else if(!field_map_open(&s->johto,mode))return FIELD_LOCKED;
 if(field_remaining(&s->field,mode,s->refresh.online_s))return FIELD_COOLDOWN;
 if(mode<FIELD_MAP_COUNT&&s->field.visited[mode]!=7)return FIELD_NEED_CLUES;
 if(s->queue.count>=ENC_QUEUE_LIMIT)return FIELD_FULL;
 if(s->pet.stamina<FIELD_COST*NURT_Q)return FIELD_NO_STAMINA;
 if(s->field.serial==UINT32_MAX)return FIELD_LOCKED;
 // Separate habitat and shiny rolls; rarity never changes the shiny denominator.
 static const uint8_t pools[7][8]={
  {177,178,198,200,202,203,207,213}, {10,13,123,127,165,167,193,214}, {37,58,92,93,109,200,228,229},
  {16,19,43,46,69,102,114,123},{10,13,21,29,32,48,83,127},
  {41,50,74,81,92,95,100,104},{54,60,72,79,98,118,120,129}
 };
 unsigned habitat=mode==FIELD_RADAR?3+place%4:mode;
 const uint8_t *pool=pools[habitat];unsigned weights[8],total=0;
 for(unsigned i=0;i<8;i++){weights[i]=(unsigned[]){0,40,28,16,7,2}[field_rarity(pool[i])];total+=weights[i];}
 uint32_t roll=field_mix(seed^((s->field.serial+1)*0x9e3779b9u));unsigned pick=roll%total,species=pool[0];
 for(unsigned i=0;i<8;i++){if(pick<weights[i]){species=pool[i];break;}pick-=weights[i];}
 unsigned level=s->level>3?s->level-3:2;level+=(roll>>16)%6;if(level>100)level=100;
 if(mode<FIELD_MAP_COUNT)level=johto_route_level((unsigned[]){3,2,4}[mode],s->level,roll>>16);
 encounter_t e={.species_id=species,.rarity=field_rarity(species),.hp_ratio=100,.level=level,.activity=ENC_ACTIVITY_EXPLORATION,.ts=s->refresh.online_s,
  .is_shiny=field_mix(roll^0x619ab3e5)%field_shiny_denominator(mode)==0};
 // A map circuit is real route progress; signs alone never hatch eggs or add clues.
 if(mode<FIELD_MAP_COUNT){unsigned route=(unsigned[]){3,2,4}[mode];if(s->johto.last_action==UINT32_MAX||!johto_explore(&s->johto,route,s->johto.last_action+1,true))return FIELD_LOCKED;johto_story_explore(&s->story,&s->johto,route);}
 enc_queue_push(&s->queue,&e);e=s->queue.items[s->queue.count-1];
 exploration_event_t chain={.kind=EXPLORE_ENCOUNTER,.uid=e.uid,.species=e.species_id,.rarity=e.rarity,.shiny=e.is_shiny,.chain_roll=field_mix(roll^0xab31e059)};
 exploration_chain_discovery(&chain,&s->queue,&s->dex,s->exploration_wins);e=*enc_queue_find(&s->queue,e.uid);dex_mark_seen(&s->dex,e.species_id,e.is_shiny);
 s->field.version=1;s->field.serial++;s->pet.stamina-=FIELD_COST*NURT_Q;
 if(mode==FIELD_RADAR){s->field.radar_due=deadline(s->refresh.online_s,FIELD_RADAR_COOLDOWN);if(s->field.radar_claims<UINT32_MAX)s->field.radar_claims++;}
 else{s->field.map_due[mode]=deadline(s->refresh.online_s,FIELD_MAP_COOLDOWN);s->field.visited[mode]=0;if(s->field.map_claims<UINT32_MAX)s->field.map_claims++;}
 *out=e;return FIELD_OK;
}
