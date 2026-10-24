#pragma once
#include "gym_rules.h"
#include "party.h"
#include "trainer.h"
#include "exp.h"
#include <string.h>
enum { LAKE_NONE,LAKE_RUMOR,LAKE_FACILITY,LAKE_GUARD_DONE,LAKE_SIGNAL_OFF,LAKE_CALM,LAKE_RECEIVED };
// V30 append-only progress. V29 story/trainer/achievement bytes remain frozen.
typedef struct {
 gym_rules_t battle;
 mon_t lake_partner;
 uint16_t claimed;
 uint8_t version,champion_gyms,champion_elm,lake_stage,lake_level;
} endgame_t;
static inline bool endgame_valid(const endgame_t *s){
 if(!s->version){endgame_t zero={0};return !memcmp(s,&zero,sizeof(zero));}
 if(s->version!=1||s->champion_elm>1||s->claimed>=2048||s->lake_stage>LAKE_RECEIVED||!gym_rules_valid(&s->battle))return false;
 if((s->claimed&255u)&~s->champion_gyms)return false;
 if((s->claimed&256u)&&s->champion_gyms!=255)return false;
 if((s->claimed&512u)&&!s->champion_elm)return false;
 if((s->claimed&1024u)&&s->lake_stage!=LAKE_RECEIVED)return false;
 if(!s->lake_stage){mon_t zero={0};return !s->lake_level&&!memcmp(&s->lake_partner,&zero,sizeof(zero));}
 return (s->lake_level==65||s->lake_level==85)&&s->lake_partner.species_id==130&&s->lake_partner.level==s->lake_level&&s->lake_partner.flags==1&&s->lake_partner.hp<=100&&s->lake_partner.intimacy<=100&&s->lake_partner.exp==exp_for_level(s->lake_level)&&combat_individual_valid(&s->lake_partner);
}

static inline bool endgame_battle_valid(const endgame_t *e,const trainer_store_t *t){
 unsigned k=e->battle.kind,id=t->session.trainer;
 if(!k)return true;
 if(k<=GYM_DRAGON)return id==TRAINER_JOHTO_FIRST+k-1&&trainer_champion(t);
 if(k==GYM_ELM)return id>=TRAINER_JOHTO_FIRST+8&&id<TRAINER_LAKE_GUARD&&trainer_champion(t);
 return k==GYM_LAKE&&id==TRAINER_LAKE_BOSS&&e->lake_stage>=LAKE_SIGNAL_OFF;
}
