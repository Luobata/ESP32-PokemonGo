#include "johto_activity.h"
#include "assets.h"
#include "exp.h"
#include "encounter.h"
#include <string.h>
static uint32_t roll(activity_run_t *r){uint32_t x=r->seed?r->seed:1;x^=x<<13;x^=x>>17;x^=x<<5;return r->seed=x;}
void activity_init(activity_store_t *s){memset(s,0,sizeof(*s));s->version=ACTIVITY_VERSION;}
static const uint8_t bugs[15]={10,11,12,13,14,15,46,48,123,127,165,167,193,204,214};
static bool bug_species(unsigned id){if(!id)return true;for(unsigned i=0;i<15;i++)if(bugs[i]==id)return true;return false;}
static bool zero_bytes(const void *data,size_t size){const uint8_t *p=data;for(size_t i=0;i<size;i++)if(p[i])return false;return true;}
static bool mon_valid(const mon_t *m,bool empty){return !m->species_id?(empty&&zero_bytes(m,sizeof(*m))):(m->species_id<=251&&m->level&&m->level<=100&&m->hp<=100&&m->intimacy<=100&&!(m->flags&~1u)&&combat_individual_valid(m));}
bool activity_valid(const activity_store_t *s){
 if(!s->version)return zero_bytes(s,sizeof(*s));
 const activity_run_t *r=&s->run;
 if(s->version!=ACTIVITY_VERSION||s->reserved||s->bug_first_silver>1||s->silver_feather>1||s->bug_choices>s->bug_completed/3)return false;
 if(!r->kind)return zero_bytes(r,sizeof(*r));
 if(!s->runs||r->kind>ACT_TOWER||r->phase>ACT_DEEP_PATH||r->node>6||r->attempts>3||r->hard>1||r->path>1||r->banked>1||r->won>1||r->observed>32767||r->xp>60000||r->banked_xp>60000)return false;
 if(r->count!=(r->kind==ACT_BUG?1:3))return false;
 unsigned lo=activity_min_level(r->kind,r->hard),hi=activity_max_level(r->kind,r->hard)-(r->kind==ACT_BUG?0:5);
 if(r->base_level<lo||r->base_level>hi)return false;
 for(unsigned i=0;i<3;i++){
  if(i>=r->count){if(r->slots[i]||!zero_bytes(&r->members[i],sizeof(mon_t))||!zero_bytes(&r->policies[i],sizeof(move_policy_t)))return false;continue;}
  if(r->slots[i]>=6||!mon_valid(&r->members[i],false)||!move_policy_valid(&r->policies[i]))return false;
  for(unsigned j=0;j<i;j++)if(r->slots[j]==r->slots[i])return false;
 }
 if(!mon_valid(&r->found,true)||!mon_valid(&r->candidate,true))return false;
 if(r->kind==ACT_BUG){
  if(!bug_species(r->candidate.species_id)||!bug_species(r->found.species_id))return false;
  if(r->phase>ACT_SETTLE||r->hard||r->path||r->banked||r->won||r->xp||r->banked_xp||!zero_bytes(&r->battle,sizeof(r->battle))||!zero_bytes(&r->earned,sizeof(r->earned)))return false;
  if(activity_observations(r)>r->node||(!r->node&&(r->attempts||r->candidate.species_id||r->found.species_id)))return false;
  if(r->phase==ACT_PATH&&(r->node>=6||r->found.species_id))return false;
  if((r->phase==ACT_FIND||r->phase==ACT_COMPARE)&&(!r->node||!r->found.species_id))return false;
  if((r->candidate.species_id||r->phase==ACT_COMPARE)&&!r->attempts)return false;
 }else{
  const trainer_session_t *b=&r->battle.session;
  if(!r->node||r->attempts||r->observed||r->candidate.species_id||!trainer_store_valid(&r->battle)||!b->active||b->sides[0].count!=3)return false;
  if(r->phase!=ACT_SETTLE&&r->phase<ACT_BATTLE)return false;
  if(r->phase==ACT_BATTLE&&(r->node==3||r->node==5))return false;
  if(r->phase==ACT_CAMP&&(r->node!=3&&r->node!=5))return false;
  if((r->phase==ACT_RELAY||r->phase==ACT_DEEP_PATH)&&r->node!=3)return false;
  if(r->phase==ACT_DEEP_PATH&&!r->banked)return false;
  if(r->node>3&&!r->banked)return false;
  if(!r->banked&&r->banked_xp)return false;
  if(r->won&&(r->node!=6||r->phase!=ACT_SETTLE||!b->finished||!b->won||!r->found.species_id))return false;
  if(!r->won&&r->found.species_id)return false;
  for(unsigned i=0;i<3;i++)if(b->sides[0].mons[i].species!=r->members[i].species_id||b->sides[0].mons[i].level!=r->members[i].level)return false;
 }
 return true;
}
bool activity_expedition(unsigned k){return k>=ACT_SEA&&k<=ACT_TOWER;}
const char *activity_name(unsigned k){return k==ACT_BUG?"捕虫调查":k==ACT_ICE?"冰雪救援":k==ACT_TOWER?"铃铛塔试炼":"漩涡远征";}
unsigned activity_min_level(unsigned k,bool hard){return k==ACT_BUG?35:k==ACT_ICE?(hard?72:58):k==ACT_TOWER?(hard?82:70):hard?70:55;}
unsigned activity_max_level(unsigned k,bool hard){return k==ACT_BUG?50:k==ACT_ICE?(hard?92:78):k==ACT_TOWER?(hard?100:92):hard?90:75;}
bool activity_open(unsigned k,const johto_state_t *j){return j&&j->phase>=JOHTO_ACTIVE&&k>=1&&k<=4&&johto_badges(j)>=(unsigned[]){0,2,6,5,7}[k];}
unsigned activity_rarity(unsigned id){species_t sp;if(!assets_species(id,&sp))return 1;unsigned n=sp.hp+sp.attack+sp.defense+sp.special+sp.speed;return n<250?1:n<330?2:n<400?3:n<470?4:5;}
unsigned activity_observations(const activity_run_t *r){unsigned n=0;for(unsigned i=0;i<15;i++)n+=!!(r->observed&(1u<<i));return n;}
unsigned activity_score(const activity_run_t *r){return activity_observations(r)*10+(r->candidate.species_id?20+activity_rarity(r->candidate.species_id)*10:0);}
const char *activity_habitat(unsigned i){return (const char*[]){"草丛足迹","树干抓痕","花丛飞影"}[i%3];}
const char *activity_habitat_hint(unsigned i){return (const char*[]){"幼虫与圆丝蛛的足迹","螳螂与甲虫留下的抓痕","蝴蝶与蜻蜓在花间飞舞"}[i%3];}
static bool sea_battle(activity_run_t *r,bool fresh){
 uint16_t hp[3],max[3];uint8_t status[3];
 for(unsigned i=0;i<3;i++){const combat_mon_t *m=&r->battle.session.sides[0].mons[i];hp[i]=m->hp;max[i]=m->max_hp;status[i]=m->status;}
 memset(&r->battle,0,sizeof(r->battle));r->battle.defeated=255;
 if(!trainer_begin_filtered(&r->battle,20,r->members,3,1024,roll(r),r->policies))return false;
 trainer_session_t *s=&r->battle.session;
 const uint8_t water[4][3]={{170,90,72},{171,117,73},{226,211,121},{230,131,160}};
 const uint8_t steel[2][3]={{82,205,211},{208,212,230}};
 unsigned index=r->node==1?0:r->node==2?1:r->node==4?2:3;
 unsigned n=index<2?1:index==2?2:3;
 unsigned level=r->base_level+(index<2?index*2: index==2?3:5)+(r->path?2:0);
 unsigned cap=activity_max_level(r->kind,r->hard);if(level>cap)level=cap;
 s->sides[1].count=n;s->sides[1].active=0;
 for(unsigned i=0;i<n;i++){
  static const uint8_t ice[4][3]={{220,215,86},{221,225,87},{124,221,215},{131,221,215}};
  static const uint8_t tower[4][3]={{164,198,200},{196,197,203},{227,212,208},{248,149,230}};
  unsigned id=r->kind==ACT_ICE?ice[index][(i+r->path)%3]:r->kind==ACT_TOWER?tower[index][(i+r->path)%3]:r->path&&index>=2?steel[index-2][i]:water[index][i];combat_init(&s->sides[1].mons[i],id,level,combat_max_hp(id,level));
 }
 for(unsigned i=0;i<3;i++)if(!fresh){combat_mon_t *m=&s->sides[0].mons[i];m->hp=max[i]?(uint32_t)hp[i]*m->max_hp/max[i]:0;if(hp[i]&&!m->hp)m->hp=1;m->status=status[i];if(m->status==4)m->sleep=2;}
 unsigned active=0;while(active<3&&!s->sides[0].mons[active].hp)active++;if(active==3)return false;
 s->sides[0].active=active;s->participated=1u<<active;s->acted=3;r->phase=ACT_BATTLE;return true;
}
bool activity_begin(activity_store_t *s,unsigned kind,const mon_t *m,const move_policy_t *p,const uint8_t *slots,unsigned count,unsigned seed,bool hard){
 if(s->run.kind||s->runs==UINT32_MAX||count!=(kind==ACT_BUG?1:3)||(kind!=ACT_BUG&&!activity_expedition(kind)))return false;
 activity_run_t *r=&s->run;memset(r,0,sizeof(*r));r->kind=kind;r->seed=seed;r->count=count;r->hard=activity_expedition(kind)&&hard;
 for(unsigned i=0;i<count;i++){if(slots[i]>=6||!mon_valid(&m[i],false))return false;for(unsigned j=0;j<i;j++)if(slots[i]==slots[j])return false;r->slots[i]=slots[i];r->members[i]=m[i];r->policies[i]=p[i];if(m[i].level>r->base_level)r->base_level=m[i].level;}
 unsigned lo=activity_min_level(kind,hard),hi=activity_max_level(kind,hard)-(kind==ACT_BUG?0:5);
 if(r->base_level<lo)r->base_level=lo;
 if(r->base_level>hi)r->base_level=hi;
 if(activity_expedition(kind)){r->node=1;if(!sea_battle(r,true))return false;}
 else r->phase=ACT_PATH;
 s->runs++;return true;
}
bool activity_investigate(activity_run_t *r,unsigned habitat){
 if(r->kind!=ACT_BUG||r->phase!=ACT_PATH||r->node>=6||habitat>2)return false;
 static const uint8_t pools[3][8]={{0,0,1,3,4,6,10,11},{6,7,8,8,9,13,14,14},{2,2,5,7,10,11,12,12}};
 unsigned index=pools[habitat][roll(r)%8];r->observed|=1u<<index;r->node++;
 unsigned level=r->base_level+roll(r)%3;if(level>50)level=50;
 r->found=(mon_t){.species_id=bugs[index],.level=level,.hp=100,.exp=exp_for_level(level),.nickname_idx=255,.flags=enc_shiny_from_roll(roll(r),SHINY_EXPLORATION)?1:0};
 r->phase=ACT_FIND;return true;
}
bool activity_throw(activity_run_t *r,unsigned ball,uint32_t elapsed,unsigned bonus,cap_result_t *out){
 if(r->kind!=ACT_BUG||r->phase!=ACT_FIND||r->attempts>=3||ball>=CAP_BALL_COUNT)return false;
 species_t sp;if(!assets_species(r->found.species_id,&sp))return false;
 cap_context_t ctx={.pet_level=r->members[0].level,.wild_level=r->found.level,.wild_speed=sp.speed,.wild_weight_hg=sp.weight_hg};
 cap_attempt_context(sp.catch_rate,bonus,ball,100,activity_rarity(r->found.species_id),elapsed,roll(r),&ctx,out);
 r->attempts++;if(out->caught){r->found.intimacy=ball==CAP_BALL_FRIEND?80:10;r->phase=ACT_COMPARE;}
 return true;
}
static void bug_next(activity_run_t *r){memset(&r->found,0,sizeof(r->found));r->phase=r->node==6?ACT_SETTLE:ACT_PATH;}
bool activity_skip(activity_run_t *r){if(r->kind!=ACT_BUG||r->phase!=ACT_FIND)return false;bug_next(r);return true;}
bool activity_keep(activity_run_t *r,bool replace){if(r->kind!=ACT_BUG||r->phase!=ACT_COMPARE)return false;if(replace)r->candidate=r->found;bug_next(r);return true;}
bool activity_finish_battle(activity_run_t *r){
 if(!activity_expedition(r->kind)||r->phase!=ACT_BATTLE||!r->battle.session.finished)return false;
 if(!r->battle.session.won){r->xp=0;memset(&r->earned,0,sizeof(r->earned));r->phase=ACT_SETTLE;return true;}
 r->xp+=exp_battle_base(r->base_level)*(r->node==6?3:2);r->earned.quantity[ITEM_BERRY]+=2;r->earned.quantity[ITEM_MILK]++;
 if(r->node==6){r->won=1;r->earned.quantity[r->kind==ACT_ICE?ITEM_METAL_COAT:r->kind==ACT_TOWER?ITEM_KINGS_ROCK:ITEM_DRAGON_SCALE]++;if(r->path)r->earned.quantity[ITEM_METAL_COAT]++;r->phase=ACT_SETTLE;
  unsigned id=r->kind==ACT_ICE?(uint8_t[]){215,220,225,124,238,236}[roll(r)%6]:r->kind==ACT_TOWER?(uint8_t[]){198,200,227,235,246,203}[roll(r)%6]:(uint8_t[]){170,171,211,226,222,117}[roll(r)%6];r->found=(mon_t){.species_id=id,.level=r->base_level,.hp=100,.exp=exp_for_level(r->base_level),.nickname_idx=255,.flags=enc_shiny_from_roll(roll(r),SHINY_DUNGEON)?1:0};
 }else if(r->node==1){r->node=2;return sea_battle(r,false);}else {r->node++;r->phase=ACT_CAMP;}
 return true;
}
bool activity_sea_next(activity_run_t *r,unsigned choice){
 if(!activity_expedition(r->kind))return false;
 if(r->phase==ACT_CAMP&&choice<2){
  for(unsigned i=0;i<3;i++){combat_mon_t *m=&r->battle.session.sides[0].mons[i];unsigned pct=choice?25:60;if(!m->hp&&choice)m->hp=m->max_hp/2;if(m->hp){unsigned hp=m->hp+m->max_hp*pct/100;m->hp=hp>m->max_hp?m->max_hp:hp;m->status=m->sleep=0;}}
  if(r->node==3)r->phase=ACT_RELAY;else{r->node=6;return sea_battle(r,false);}return true;
 }
 if(r->phase==ACT_RELAY&&r->banked&&choice<2){r->phase=choice?ACT_DEEP_PATH:ACT_SETTLE;return true;}
 if(r->phase==ACT_DEEP_PATH&&choice<2){r->path=choice;r->node=4;return sea_battle(r,false);}
 return false;
}
static bool pending_add(activity_store_t *s,unsigned item,unsigned n){if(n>UINT16_MAX-s->pending.quantity[item])return false;s->pending.quantity[item]+=n;return true;}
bool activity_bank(activity_store_t *s){
 activity_run_t *r=&s->run;if(!activity_expedition(r->kind)||r->phase!=ACT_RELAY||r->banked)return false;
 for(unsigned i=0;i<ITEM_COUNT;i++)if(!pending_add(s,i,r->earned.quantity[i]))return false;
 memset(&r->earned,0,sizeof(r->earned));r->banked=1;r->banked_xp=r->xp;return true;
}
bool activity_settle(activity_store_t *s){
 activity_run_t *r=&s->run;if(!r->kind||r->phase!=ACT_SETTLE)return false;
 if(r->kind==ACT_BUG){
  unsigned score=activity_score(r);if(!pending_add(s,ITEM_BERRY,r->node)||!pending_add(s,ITEM_MILK,r->node>=4)||!pending_add(s,ITEM_GREAT,score>=90?3:score>=50?1:0))return false;
  if(score>=50&&!s->bug_first_silver){if(!pending_add(s,ITEM_SUN_STONE,1))return false;s->bug_first_silver=1;}
  if(r->node==6&&activity_observations(r)>=3&&s->bug_completed<UINT16_MAX){s->bug_completed++;if(s->bug_completed%3==0)s->bug_choices++;}
 }else{
  for(unsigned i=0;i<ITEM_COUNT;i++)if(!pending_add(s,i,r->earned.quantity[i]))return false;
  if(r->won&&r->kind==ACT_SEA){if(s->sea_clears<UINT16_MAX)s->sea_clears++;s->silver_feather=1;}
 }
 return true;
}
