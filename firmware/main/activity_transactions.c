#include "activity_transactions.h"
#include "exp.h"
#include <limits.h>
static void flush(activity_store_t *a,inventory_t *bag){for(unsigned i=0;i<ITEM_COUNT;i++){unsigned n=a->pending.quantity[i],room=items_capacity(i)-bag->quantity[i];if(n>room)n=room;bag->quantity[i]+=n;a->pending.quantity[i]-=n;}}
static uint32_t award(save_t *s,unsigned xp){uint32_t before=0;for(unsigned i=0;i<s->members.party_count;i++)before+=s->members.party[i].exp;activity_run_t *r=&s->activities.run;unsigned mask=0;for(unsigned i=0;i<r->count;i++)mask|=1u<<r->slots[i];exp_award_party(&s->members,mask,mask,exp_scaled(xp,nurture_exp_percent(&s->pet)));s->exp=s->members.party[0].exp;s->level=s->members.party[0].level;uint32_t after=0;for(unsigned i=0;i<s->members.party_count;i++)after+=s->members.party[i].exp;return after-before;}
activity_result_t activity_apply(save_t *s,const activity_request_t *q,activity_result_data_t *out){
 activity_store_t *a=&s->activities;activity_run_t *r=&a->run;memset(out,0,sizeof(*out));
 if(!a->version)activity_init(a);
 if(q->op==ACTION_BEGIN){
  if(r->kind)return ACT_BUSY;
  if(!activity_open(q->choice,&s->johto))return ACT_LOCKED;
  unsigned cost=q->choice==ACT_BUG?10:20;if(s->pet.stamina<(int32_t)(cost*NURT_Q))return ACT_STAMINA;
  if(q->count!=(q->choice==ACT_BUG?1:3))return ACT_LOCKED;
  mon_t m[3];move_policy_t policies[3];
  for(unsigned i=0;i<q->count;i++){if(q->slots[i]>=s->members.party_count)return ACT_STALE;m[i]=s->members.party[q->slots[i]];policies[i]=s->members.policies[q->slots[i]];}
  if(!activity_begin(a,q->choice,m,policies,q->slots,q->count,q->seed,q->hard))return ACT_LOCKED;
  s->pet.stamina-=cost*NURT_Q;return ACT_OK;
 }
 if(q->op==ACTION_CLAIM){flush(a,&s->inventory);return ACT_OK;}
 if(q->op==ACTION_PRIZE){if(!a->bug_choices||q->choice>1)return ACT_LOCKED;unsigned id=q->choice?ITEM_KINGS_ROCK:ITEM_SUN_STONE;if(a->pending.quantity[id]==UINT16_MAX)return ACT_FULL;a->pending.quantity[id]++;a->bug_choices--;flush(a,&s->inventory);return ACT_OK;}
 if(!r->kind)return ACT_LOCKED;
 for(unsigned i=0;i<r->count;i++)if(r->slots[i]>=s->members.party_count||s->members.party[r->slots[i]].species_id!=r->members[i].species_id)return ACT_STALE;
 bool ok=false;
 switch(q->op){
 case ACTION_SURVEY:ok=activity_investigate(r,q->choice);if(ok)dex_mark_seen(&s->dex,r->found.species_id,r->found.flags&1);break;
 case ACTION_THROW:if(r->kind!=ACT_BUG||r->phase!=ACT_FIND||r->attempts>=3)return ACT_LOCKED;
  if(q->choice>=CAP_BALL_COUNT||!s->inventory.quantity[q->choice])return ACT_FULL;
  ok=activity_throw(r,q->choice,q->elapsed,1024+r->members[0].intimacy*3,&out->capture);if(ok)s->inventory.quantity[q->choice]--;break;
 case ACTION_KEEP:ok=activity_keep(r,q->choice!=0);break;
 case ACTION_SKIP:ok=activity_skip(r);break;
 case ACTION_END_SURVEY:if(r->kind==ACT_BUG&&(r->phase==ACT_PATH||r->phase==ACT_FIND)){r->phase=ACT_SETTLE;ok=true;}break;
 case ACTION_CAMP:case ACTION_CONTINUE:case ACTION_PATH:ok=activity_sea_next(r,q->choice);break;
 case ACTION_BANK:ok=activity_bank(a);if(ok){out->exp_gained=award(s,r->xp);r->banked_xp=out->exp_gained;r->xp=0;flush(a,&s->inventory);}break;
 case ACTION_STEP:if(activity_expedition(r->kind)&&r->phase==ACT_BATTLE)ok=trainer_step_filtered(&r->battle,&out->event,r->policies);break;
 case ACTION_SWITCH:if(activity_expedition(r->kind)&&r->phase==ACT_BATTLE)ok=trainer_switch_filtered(&r->battle,q->choice,q->hard,r->policies);break;
 case ACTION_BATTLE_END:
  for(unsigned i=0;i<r->count;i++){combat_record_sketch(&r->members[i],&r->battle.session.sides[0].mons[i]);combat_record_sketch(&s->members.party[r->slots[i]],&r->battle.session.sides[0].mons[i]);}
  ok=activity_finish_battle(r);break;
 case ACTION_RETIRE:if(activity_expedition(r->kind)&&r->phase==ACT_BATTLE){trainer_retire(&r->battle);r->xp=0;memset(&r->earned,0,sizeof(r->earned));r->phase=ACT_SETTLE;ok=true;}break;
 case ACTION_SETTLE:
  if(r->phase!=ACT_SETTLE)return ACT_LOCKED;
  // The story needs observation, not a lucky species, catch or medal. This
  // evidence commits with the real settlement, including a full-box retry.
  if(r->kind==ACT_BUG&&r->node==ACTIVITY_BUG_NODES){s->narrative.version=1;s->narrative.bug_evidence=1;}
  if(r->kind==ACT_BUG&&r->candidate.species_id){
   if(!party_receive(&s->members,&r->candidate)){
    if(q->box_slot>=BOX_CAPACITY)return ACT_FULL;
    mon_t *old=&s->members.box[q->box_slot];if(!old->species_id||memcmp(old,&q->expected,sizeof(*old)))return ACT_STALE;
    *old=r->candidate;memset(&s->members.policies[PARTY_MAX+q->box_slot],0,sizeof(move_policy_t));
   }
   dex_mark_caught(&s->dex,r->candidate.species_id,r->candidate.flags&1);
  }
  out->rewards=a->pending;
  if(!activity_settle(a))return ACT_FULL;
  for(unsigned i=0;i<ITEM_COUNT;i++)out->rewards.quantity[i]=a->pending.quantity[i]-out->rewards.quantity[i];
  if(activity_expedition(r->kind)){
   out->exp_gained=award(s,r->xp);
   if(r->won&&r->found.species_id){encounter_t e={.species_id=r->found.species_id,.level=r->found.level,.is_shiny=r->found.flags&1,.rarity=activity_rarity(r->found.species_id),.hp_ratio=100,.ts=a->runs};enc_queue_push(&s->queue,&e);dex_mark_seen(&s->dex,e.species_id,e.is_shiny);}
  }
  flush(a,&s->inventory);memset(r,0,sizeof(*r));ok=true;break;
 default:break;
 }
 return ok?ACT_OK:ACT_LOCKED;
}
