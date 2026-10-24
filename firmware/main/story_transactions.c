#include "story_transactions.h"
#include "exp.h"
#include <string.h>
static bool receive(save_t *s,const story_request_t *q,const mon_t *m){
 if(q->box_slot<BOX_CAPACITY){if(party_can_receive(&s->members,m->species_id)||!q->expected.species_id)return false;if(memcmp(&s->members.box[q->box_slot],&q->expected,sizeof(mon_t)))return false;s->members.box[q->box_slot]=*m;memset(&s->members.policies[PARTY_MAX+q->box_slot],0,sizeof(move_policy_t));}
 else if(!party_receive(&s->members,m))return false;
 dex_mark_caught(&s->dex,m->species_id,m->flags&1);return true;
}
activity_result_t story_apply(save_t *s,const story_request_t *q,story_result_t *out){
 if(!s||!q||!out)return ACT_LOCKED;
 memset(out,0,sizeof(*out));johto_story_t *story=&s->story;johto_state_t *j=&s->johto;
 if(j->phase<JOHTO_ACTIVE)return ACT_LOCKED;
 if(s->activities.run.kind)return ACT_BUSY;
 if(!story->version)johto_story_init(story);
 switch(q->op){
 case STORY_LAKE_BEGIN:
  if(johto_badges(j)<5||s->endgame.lake_stage)return ACT_LOCKED;
  if(s->pet.stamina<10*NURT_Q)return ACT_STAMINA;
  s->pet.stamina-=10*NURT_Q;s->endgame.version=1;s->endgame.lake_stage=LAKE_RUMOR;s->endgame.lake_level=trainer_champion(&s->challenge)?85:65;
  s->endgame.lake_partner=(mon_t){.species_id=130,.level=s->endgame.lake_level,.hp=100,.intimacy=70,.flags=1,.exp=exp_for_level(s->endgame.lake_level)};return ACT_OK;
 case STORY_LAKE_CLUE:
  if(s->endgame.lake_stage!=LAKE_RUMOR)return ACT_LOCKED;
  s->endgame.lake_stage=LAKE_FACILITY;return ACT_OK;
 case STORY_LAKE_SWITCH:
  if(s->endgame.lake_stage!=LAKE_GUARD_DONE||q->choice!=1)return ACT_LOCKED;
  s->endgame.lake_stage=LAKE_SIGNAL_OFF;return ACT_OK;
 case STORY_LAKE_CLAIM:
  if(s->endgame.lake_stage!=LAKE_CALM)return ACT_LOCKED;
  if(q->box_slot<BOX_CAPACITY&&memcmp(&s->members.box[q->box_slot],&q->expected,sizeof(mon_t)))return ACT_STALE;
  if(!receive(s,q,&s->endgame.lake_partner))return ACT_FULL;
  out->partner=s->endgame.lake_partner;out->received=1;s->endgame.lake_stage=LAKE_RECEIVED;
  for(unsigned i=0;i<5&&s->inventory.quantity[ITEM_BERRY]<items_capacity(ITEM_BERRY);i++)s->inventory.quantity[ITEM_BERRY]++;
  return ACT_OK;
 case STORY_TOWER:if(johto_badges(j)<4||story->tower_seen)return ACT_LOCKED;story->tower_seen=1;return ACT_OK;
 case STORY_RESCUE_BEGIN:return johto_rescue_begin(story,j,q->seed)?ACT_OK:ACT_LOCKED;
 case STORY_RESCUE_CHOOSE:return johto_rescue_choose(story,q->choice)?ACT_OK:ACT_LOCKED;
 case STORY_RESCUE_CLAIM:
  if(story->rescue_step!=3)return ACT_LOCKED;
  if(q->box_slot<BOX_CAPACITY&&memcmp(&s->members.box[q->box_slot],&q->expected,sizeof(mon_t)))return ACT_STALE;
  if(!receive(s,q,&story->rescue_partner))return ACT_FULL;
  out->received=1;out->partner=story->rescue_partner;
  if(!johto_rescue_claim(story,j))return ACT_LOCKED;
  for(unsigned i=0;i<3&&s->inventory.quantity[ITEM_BERRY]<items_capacity(ITEM_BERRY);i++)s->inventory.quantity[ITEM_BERRY]++;
  return ACT_OK;
 case STORY_RUIN_CHOOSE:return johto_ruin_choose(story,j,q->group,q->choice)?ACT_OK:ACT_LOCKED;
 case STORY_RUIN_BACK:if(story->ruin_step)story->ruin_step--;return ACT_OK;
 case STORY_RUIN_EXPLORE:{
  if(q->group>=4||!(story->ruins&(1u<<q->group)))return ACT_LOCKED;
  if(s->pet.stamina<NURT_EXPLORE_COST)return ACT_STAMINA;
  unsigned form=johto_ruin_form(story,q->group,q->seed);if(form>=26)return ACT_LOCKED;
  encounter_t e={.species_id=201,.level=johto_route_level(3,s->level,q->seed>>16),.rarity=3,.hp_ratio=100,.biome=form,.is_shiny=(q->seed>>8)%32==0,.ts=q->seed};
  enc_queue_push(&s->queue,&e);out->encounter=s->queue.items[s->queue.count-1];dex_mark_seen(&s->dex,201,e.is_shiny);s->pet.stamina-=NURT_EXPLORE_COST;return ACT_OK;
 }
 case STORY_PURIFY:
  if(!story->tower_seen||j->legend_clues[2]!=2)return ACT_LOCKED;
  // The three emblems describe a causal order; retry is free and reversible.
  if(q->choice!=1)return ACT_LOCKED;
  j->legend_clues[2]=3;return ACT_OK;
 case STORY_ENDING:if(j->phase!=JOHTO_COMPLETE)return ACT_LOCKED;story->ending_seen=1;return ACT_OK;
 case STORY_FINAL_PRIZE:
  if(j->phase!=JOHTO_COMPLETE||j->final_reward_claimed||q->choice>=JOHTO_REWARD_COUNT)return ACT_LOCKED;
  unsigned item=ITEM_SUN_STONE+q->choice;if(s->inventory.quantity[item]>=items_capacity(item))return ACT_FULL;
  s->inventory.quantity[item]++;j->final_reward_claimed=1;out->item=item;return ACT_OK;
 default:return ACT_LOCKED;
 }
}
