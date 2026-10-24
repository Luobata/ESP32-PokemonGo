#pragma once
#include "johto_story.h"
#include "endgame.h"

// V31: append-only scene IDs. Reading a scene never grants an activity reward.
enum {
 N_LETTER,N_ARRIVAL,N_WELCOME,N_FIELD,N_EGG,N_BUG_INVITE,N_BUG_REPORT,
 N_RUIN_INVITE,N_RUIN_REPORT,N_TOWER_INVITE,N_TOWER_REPORT,N_LAKE_INVITE,
 N_LAKE_REPORT,N_SEA_INVITE,N_SEA_REPORT,N_ROOF,N_ELM,N_ENDING,N_FOREST,
 N_LEGEND_RAI,N_LEGEND_ENTEI,N_LEGEND_SUICUNE,N_LEGEND_LUGIA,
 N_LEGEND_HOOH,N_LEGEND_CELEBI,N_SCENE_COUNT
};
typedef struct {
 uint64_t seen;
 encounter_t pending; // Locked until an actual battle/throw starts, even if FIFO evicts it.
 uint16_t scene;       // 0 = no interrupted dialogue, otherwise scene ID + 1.
 uint8_t page,version,bug_evidence,legacy_final,focus,legend;
} narrative_t;
_Static_assert(sizeof(narrative_t)==32,"Freeze V31 narrative record");
typedef struct {
 narrative_t state;
 johto_state_t chapter;
 johto_story_t story;
 uint16_t defeated,bug_completed;
 uint8_t feather,lake,activity,battle,dungeon;
} narrative_context_t;
enum { N_OK,N_LOCKED,N_BUSY,N_SAVE_FAILED,N_WRONG,N_NO_STAMINA };
enum { N_GO_ROUTE,N_GO_GYM,N_GO_STARTER,N_GO_EGG,N_GO_BUG,N_GO_RUIN,
 N_GO_TOWER,N_GO_LAKE,N_GO_SEA,N_GO_RESCUE,N_GO_PURIFY,N_GO_LEGEND,
 N_GO_KANTO,N_GO_KANTO_ROUTE,N_GO_ACTIVITY,N_GO_BATTLE,N_GO_DUNGEON,N_GO_FREE };
typedef struct { const char *title,*place,*task; uint8_t action,index; } narrative_goal_t;
static inline unsigned narrative_pages(unsigned s){
 static const uint8_t n[N_SCENE_COUNT]={3,3,2,2,2,2,3,2,3,2,3,2,2,2,2,2,2,3,2,2,2,2,2,2,2};
 return s<N_SCENE_COUNT?n[s]:0;
}
static inline bool narrative_seen(const narrative_t *n,unsigned s){return s<N_SCENE_COUNT&&(n->seen&(UINT64_C(1)<<s));}
static inline bool narrative_valid(const narrative_t *n){
 if(!n->version){narrative_t zero={0};return !memcmp(n,&zero,sizeof(zero));}
 if(n->version!=1||n->seen>>N_SCENE_COUNT||n->scene>N_SCENE_COUNT||n->bug_evidence>1||n->legacy_final>1||n->focus>2||n->legend>6)return false;
 if(n->scene?(n->page>=narrative_pages(n->scene-1)):n->page!=0)return false;
 if(!n->legend){encounter_t zero={0};return !memcmp(&n->pending,&zero,sizeof(zero));}
 const encounter_t *e=&n->pending;
 return e->uid&&e->species_id==(uint16_t[]){243,244,245,249,250,251}[n->legend-1]&&e->level>=1&&e->level<=100&&e->rarity==5&&e->hp_ratio==100&&!e->activity&&!e->biome&&((const uint8_t*)&e->exp_granted)[0]==0&&((const uint8_t*)&e->is_transient)[0]==0&&((const uint8_t*)&e->is_shiny)[0]<=1;
}
static inline void narrative_init(narrative_t *n){memset(n,0,sizeof(*n));n->version=1;}
static inline void narrative_consume(narrative_t *n,const encounter_t *e){if(e&&n->legend&&n->pending.uid==e->uid&&n->pending.ts==e->ts&&n->pending.species_id==e->species_id&&n->pending.level==e->level&&n->pending.is_shiny==e->is_shiny){if(n->scene==N_LEGEND_RAI+n->legend){n->seen|=UINT64_C(1)<<(n->scene-1);n->scene=0;n->page=0;}memset(&n->pending,0,sizeof(n->pending));n->legend=0;}}
static inline bool narrative_final(const narrative_context_t *c){
 if(c->state.legacy_final||johto_story_final_ready(&c->story,&c->chapter,c->defeated,c->feather))return true;
 return johto_final_open(&c->chapter,c->defeated)&&c->story.tower_seen&&(c->story.ruins&1)&&c->story.rescues&&c->feather&&(c->state.bug_evidence||c->bug_completed);
}
static inline bool narrative_allowed(const narrative_context_t *c,unsigned s){
 unsigned b=johto_badges(&c->chapter);
 if(s>=N_SCENE_COUNT||c->chapter.phase==JOHTO_HIDDEN)return false;
 if(s==N_LETTER)return true;
 if(s==N_ARRIVAL)return c->chapter.phase>=JOHTO_VOYAGE;
 if(c->chapter.phase<JOHTO_ACTIVE)return false;
 switch(s){
 case N_WELCOME:return true;
 case N_FIELD:return c->chapter.research[0]||b;
 case N_EGG:return b>=1;
 case N_BUG_INVITE:return b>=2;
 case N_BUG_REPORT:return c->state.bug_evidence||c->bug_completed;
 case N_RUIN_INVITE:return b>=3;
 case N_RUIN_REPORT:return c->story.ruins&1;
 case N_TOWER_INVITE:return b>=4;
 case N_TOWER_REPORT:return c->story.tower_seen;
 case N_LAKE_INVITE:return b>=5;
 case N_LAKE_REPORT:return c->lake==LAKE_RECEIVED;
 case N_SEA_INVITE:return b>=6;
 case N_SEA_REPORT:return c->feather;
 case N_ROOF:return b>=8&&c->chapter.legend_clues[0]==3&&c->chapter.legend_clues[1]==3&&c->chapter.legend_clues[2]==3;
 case N_ELM:return narrative_final(c);
 case N_ENDING:case N_FOREST:return c->chapter.phase==JOHTO_COMPLETE;
 default:return c->state.legend==s-N_LEGEND_RAI+1||(c->story.legend_visits&(1u<<(s-N_LEGEND_RAI)));
 }
}
// The world invokes this only on a transaction candidate under its save lock.
static inline unsigned narrative_begin(narrative_context_t *c,unsigned s){
 if(!narrative_allowed(c,s))return N_LOCKED;
 if(c->activity||c->battle||c->dungeon)return N_BUSY;
 if(c->state.scene==s+1)return N_OK;
 c->state.version=1;c->state.scene=s+1;c->state.page=0;return N_OK;
}
static inline unsigned narrative_advance(narrative_context_t *c,unsigned s,unsigned page,unsigned answer){
 if(c->state.scene!=s+1||c->state.page!=page||!narrative_allowed(c,s))return N_LOCKED;
 if(c->activity||c->battle||c->dungeon)return N_BUSY;
 if(page+1==narrative_pages(s)){
  if((s==N_BUG_REPORT&&answer!=1)||(s==N_RUIN_REPORT&&answer!=2))return N_WRONG;
  if(s==N_TOWER_REPORT){if(answer>2)return N_LOCKED;c->state.focus=answer;}
  c->state.seen|=UINT64_C(1)<<s;c->state.scene=0;c->state.page=0;
 }else c->state.page++;
 return N_OK;
}
// An explicit next destination is always available, including locked-route prerequisites.
static inline narrative_goal_t narrative_goal(const narrative_context_t *c){
 #define GO(t,p,d,a,i) return (narrative_goal_t){t,p,d,a,i}
 const johto_state_t *j=&c->chapter;const johto_story_t *s=&c->story;unsigned b=johto_badges(j);
 if(c->battle)GO("继续当前对战","对战现场","完成对战后继续调查",N_GO_BATTLE,0);
 if(c->activity)GO("正在进行的调查","城都活动","先带回本次调查记录",N_GO_ACTIVITY,c->activity);
 if(c->dungeon)GO("继续当前秘境","秘境营地","结束后可以继续剧情",N_GO_DUNGEON,0);
 if(c->state.legend)GO("传说就在眼前","调查现场","锁定的遭遇仍在等你",N_GO_LEGEND,c->state.legend-1);
 if(j->phase<JOHTO_ACTIVE)GO("抵达城都","空木研究所","选择同行伙伴",N_GO_STARTER,0);
 if(j->phase==JOHTO_COMPLETE){
  if(!(s->forest_visits&1))GO("森林里的回声","关都任一探索地图","调查一次熟悉的地方",N_GO_KANTO_ROUTE,0);
  if(j->legend_clues[5]<3)GO("重叠的森林","桧皮林地","沿树木的回声继续调查",N_GO_ROUTE,1);
  if(!(s->legend_visits&(1u<<5)))GO("时间另一侧","桧皮林地","前往回声交汇的地方",N_GO_LEGEND,5);
  GO("旅程仍在继续","城都各地","自由探索与重复调查",N_GO_FREE,0);
 }
 if(c->state.legacy_final)GO("最后一项研究","空木研究所","之前的挑战资格仍然有效",N_GO_GYM,8);
 if(!b){if(!j->research[0])GO("新的调查记录","若叶郊野","观察一次迁徙的伙伴",N_GO_ROUTE,0);GO("调查者的准备","阿速道馆","赢得首枚城都徽章",N_GO_GYM,0);}
 if(b<2)GO("林地的邀请","阿笔道馆","取得第二枚城都徽章",N_GO_GYM,1);
 if(!c->state.bug_evidence&&!c->bug_completed)GO("虫群为何绕路","捕虫调查","走完六个观察点即可",N_GO_BUG,0);
 if(b<3)GO("前往遗迹","小茜道馆","取得第三枚城都徽章",N_GO_GYM,2);
 if(!(s->ruins&1))GO("石壁上的记录","缘朱遗迹","读懂第一组符号",N_GO_RUIN,0);
 if(!s->rescues){if(johto_rescue_ready(s,j)||s->rescue_step)GO("原野传来求救声","满金伙伴救助","跟随足迹接回伙伴",N_GO_RESCUE,0);GO("寻找失散的伙伴","满金原野","继续调查留下的足迹",N_GO_ROUTE,2);}
 if(b<4)GO("塔中的影子","松叶道馆","取得第四枚城都徽章",N_GO_GYM,3);
 if(!s->tower_seen)GO("三道身影","烧焦塔","记录塔里的异象",N_GO_TOWER,0);
 if(b>=5&&c->lake!=LAKE_RECEIVED)GO("湖上的红影","愤怒之湖","循着鳞片调查电波",N_GO_LAKE,0);
 if(b>=6&&!c->feather)GO("海上的呼唤","漩涡分层远征","深入海渊取得银色之羽",N_GO_SEA,0);
 for(unsigned n=0;n<3;n++){
  unsigned id=(c->state.focus+n)%3,clue=j->legend_clues[id];
  if(clue==3){if(!(s->legend_visits&(1u<<id)))GO("痕迹的尽头","传说调查现场","确认接近 可暂缓返回",N_GO_LEGEND,id);continue;}
  if(id==2&&clue==2)GO("让清水再次流动","水君净水试炼","观察水流受阻的原因",N_GO_PURIFY,0);
  unsigned route=id==0?(unsigned[]){4,2,5}[clue]:id==1?(unsigned[]){4,1,7}[clue]:(unsigned[]){2,6}[clue];
  if(!johto_route_open(j,route))GO("通往下一条线索",JOHTO_TRAINERS[b].name,"先取得下一枚城都徽章",N_GO_GYM,b);
  GO(id==0?"追寻雷鸣":id==1?"追寻焦痕":"追寻清水",JOHTO_ROUTES[route].name,id==0?"寻找被雷击的树木":id==1?"辨认温热的足迹":"寻找清澈水流的源头",N_GO_ROUTE,route);
 }
 if(b<8)GO("塔顶的许可",JOHTO_TRAINERS[b].name,"取得下一枚城都徽章",N_GO_GYM,b);
 if(j->legend_clues[3]<3)GO("银羽的回应","漩涡列岛","继续调查海风的方向",N_GO_ROUTE,6);
 if(!(s->legend_visits&(1u<<3)))GO("银羽的回应","漩涡列岛","接近海渊声音的主人",N_GO_LEGEND,3);
 if(j->legend_clues[4]<3)GO("壁画中的彩虹","铃铛塔","寻找羽毛留下的光",N_GO_ROUTE,7);
 if(!(s->legend_visits&(1u<<4)))GO("彩虹的主人","铃铛塔","循着光靠近塔顶",N_GO_LEGEND,4);
 if((c->defeated&0x20ff)!=0x20ff)GO("来自关都的约定","关都道馆与赤红","完成关都八徽章及赤红战",N_GO_KANTO,0);
 GO("最后一项研究","空木研究所","以完整队伍接受考验",N_GO_GYM,8);
 #undef GO
}
// Return one new scene at a safe UI boundary. No popping mid-battle or mid-reward.
static inline unsigned narrative_next(const narrative_context_t *c){
 if(c->activity||c->battle||c->dungeon)return N_SCENE_COUNT;
 if(c->state.scene)return c->state.scene-1;
 if(c->state.legend){unsigned s=N_LEGEND_RAI+c->state.legend-1;return narrative_seen(&c->state,s)?N_SCENE_COUNT:s;}
 if(c->chapter.phase==JOHTO_INVITED)return narrative_seen(&c->state,N_LETTER)?N_SCENE_COUNT:N_LETTER;
 if(c->chapter.phase==JOHTO_VOYAGE)return narrative_seen(&c->state,N_ARRIVAL)?N_SCENE_COUNT:N_ARRIVAL;
 if(c->chapter.phase<JOHTO_ACTIVE)return N_SCENE_COUNT;
 if(c->chapter.phase==JOHTO_COMPLETE){unsigned s=!narrative_seen(&c->state,N_ENDING)?N_ENDING:N_FOREST;return narrative_seen(&c->state,s)?N_SCENE_COUNT:s;}
 for(unsigned s=N_WELCOME;s<=N_ELM;s++)if(!narrative_seen(&c->state,s)&&narrative_allowed(c,s)){
  // Context comes first: a report cannot precede its activity; late-game saves
  // get a short recap, then the next actionable scene, never forced replays.
  if(s==N_BUG_INVITE&&(c->state.bug_evidence||c->bug_completed))continue;
  if(s==N_RUIN_INVITE&&(c->story.ruins&1))continue;
  if(s==N_TOWER_INVITE&&c->story.tower_seen)continue;
  if(s==N_LAKE_INVITE&&c->lake==LAKE_RECEIVED)continue;
  if(s==N_SEA_INVITE&&c->feather)continue;
  return s;
 }
 return N_SCENE_COUNT;
}
