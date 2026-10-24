#include "johto_routes.h"
#include "assets.h"
#include "battle.h"
#include <limits.h>
#include <string.h>
static const johto_path_t PATHS[8][3]={
 {{"草丛小路",{161,165,179,191}},{"林间树梢",{163,167,187,173}},{"池塘岸边",{194,172,174,183}}},
 {{"树干调查",{165,166,167,168}},{"林冠穿行",{177,187,188,193}},{"密林深处",{190,204,206,214}}},
 {{"花田小径",{189,191,192,185}},{"牧场围栏",{179,180,209,241}},{"河岸草地",{183,184,216,231}}},
 {{"古木阴影",{177,178,198,200}},{"石壁暗道",{202,203,207,213}},{"遗迹营地",{234,235,236,203}}},
 {{"焦木长廊",{156,162,164,181}},{"塔底水洼",{195,197,205,210}},{"余烬深处",{215,218,228,229}}},
 {{"雪原足迹",{215,217,220,221}},{"结冰水道",{225,238,224,232}},{"岩壁洞穴",{239,240,246,247}}},
 {{"浅滩水草",{158,159,184,195}},{"珊瑚海湾",{170,211,222,223}},{"潮汐深处",{171,224,226,230}}},
 {{"古塔庭院",{154,157,160,182}},{"月光长廊",{169,186,196,199}},{"塔顶回廊",{208,212,227,248}}}
};
static uint32_t route_mix(uint32_t x){x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);}
const johto_path_t *johto_path(unsigned route,unsigned path){return route<8&&path<3?&PATHS[route][path]:NULL;}
// Keep progress useful even after the historical 16-bit research counter saturates.
static uint32_t visits(const johto_state_t *s,unsigned route){return s->research[route]==UINT16_MAX?s->explorations:s->research[route];}
unsigned johto_track_clues(const johto_state_t *s,unsigned route){return route<8?visits(s,route)%4:0;}
unsigned johto_track_target(const johto_state_t *s,unsigned route){
 if(route>=8)return 0;
 const johto_route_t *r=&JOHTO_ROUTES[route];return r->species[8+(visits(s,route)/4+route)%4];
}
static unsigned rarity(unsigned id){species_t sp;if(!assets_species(id,&sp))return 1;unsigned total=sp.hp+sp.attack+sp.defense+sp.special+sp.speed;return total<250?1:total<330?2:total<400?3:total<470?4:5;}
bool johto_search_apply(save_t *s,unsigned route,unsigned path,uint32_t seed,johto_search_t *out){
 const johto_path_t *p=johto_path(route,path);
 if(!s||!out||!p||!johto_route_open(&s->johto,route)||s->pet.stamina<NURT_EXPLORE_COST||s->johto.last_action==UINT32_MAX)return false;
 unsigned clues=johto_track_clues(&s->johto,route),target=johto_track_target(&s->johto,route);
 if(!johto_explore(&s->johto,route,s->johto.last_action+1,true))return false;
 johto_story_explore(&s->story,&s->johto,route);s->pet.stamina-=NURT_EXPLORE_COST;
 uint32_t roll=route_mix(seed^s->johto.explorations*0x9e3779b9u);
 *out=(johto_search_t){.route=route,.path=path,.target=target,.clues=johto_track_clues(&s->johto,route),.item=ITEM_NONE};
 if(clues==3||roll%100<60){
  unsigned species=target;
  if(clues!=3){unsigned total=0,weights[4];for(unsigned i=0;i<4;i++){weights[i]=(unsigned[]){0,40,28,16,7,2}[rarity(p->species[i])];total+=weights[i];}unsigned pick=route_mix(roll)%total;for(unsigned i=0;i<4;i++){if(pick<weights[i]){species=p->species[i];break;}pick-=weights[i];}}
  encounter_t e={.species_id=species,.rarity=rarity(species),.hp_ratio=100,.level=johto_route_level(route,s->level,roll>>16),.activity=ENC_ACTIVITY_EXPLORATION,.ts=s->johto.explorations,.is_shiny=enc_shiny_from_roll(route_mix(roll^0x619ab3e5),SHINY_EXPLORATION)};
  enc_queue_push(&s->queue,&e);e=s->queue.items[s->queue.count-1];
  exploration_event_t bonus={.uid=e.uid,.chain_roll=route_mix(roll^0xab31e059)};exploration_chain_discovery(&bonus,&s->queue,&s->dex,s->exploration_wins);
  e.is_shiny=bonus.shiny;out->encounter=e;out->kind=clues==3?JOHTO_SEARCH_TARGET:JOHTO_SEARCH_ENCOUNTER;
 }else{
  out->kind=JOHTO_SEARCH_CLUE;
  // Clue stops supply food and better balls; full stacks use the existing overflow rule.
  unsigned item=(unsigned[]){ITEM_BERRY,ITEM_BERRY,ITEM_MILK,ITEM_GREAT,ITEM_JOY_COOKIE}[route_mix(roll)%5];
  item_loot_t loot={.item_id=item,.quantity=item==ITEM_BERRY?2:1};loot=items_fit_loot(loot,&s->inventory,route_mix(roll^7));s->inventory.quantity[loot.item_id]+=loot.quantity;
  out->item=loot.item_id;out->quantity=loot.quantity;out->item_full=loot.full;
 }
 return true;
}

// Each entry consumes one existing evidence step. Old completed steps remain
// completed, including saves made before these preparation requirements existed.
static const johto_probe_t PROBES[JOHTO_PROBE_COUNT]={
 {0,0,4,0,TY_ELECTRIC,TY_NONE,"焦木间的电光",{"烧焦木柱还闪着微光。","靠近时，毛发微微竖起。"},"能储存电的伙伴可以回应。","试着让微光连成一道电流。","电光沿木纹亮起了！","雷击痕迹指向满金原野。","到牧场围栏寻找地面的变化。"},
 {0,1,2,1,TY_GROUND,TY_NONE,"围栏下的震动",{"围栏下留下深深的脚印。","泥土里传来细小的震动。"},"请熟悉泥土的伙伴听一听。","震动藏在脚下，不在风中。","伙伴伏低身子感知地面。","足迹正向冰雪之径延伸。","岩壁洞穴似乎留住了回声。"},
 {0,2,5,2,TY_GROUND,TY_ROCK,"岩壁里的回声",{"雪中的脚印在石壁前消失。","洞穴深处传来低沉回声。"},"找能感知岩土回声的伙伴。","轻叩石壁，也许会有回应。","伙伴敲击岩壁，回声响起。","三处痕迹连成了雷鸣的方向。","回到调查册，接近雷鸣。"},
 {1,0,4,2,TY_FIRE,TY_NONE,"余烬仍然温热",{"木炭早已冷却。","只有深处的灰烬还温热。"},"不怕火焰的伙伴更能靠近。","余温需要另一团火来唤醒。","伙伴唤起了灰烬中的火星。","温热的足迹延伸向桧皮林地。","到密林深处寻找暖风。"},
 {1,1,1,2,TY_FIRE,TY_NONE,"密林中的暖风",{"越往深处，草叶越干燥。","无风时也有热气拂过。"},"熟悉火焰的伙伴能辨别。","热气散去前，循着余温找。","伙伴朝暖风吹来的方向回应。","足迹越过林地，通向铃铛塔。","先取得通往古塔的徽章。"},
 {1,2,7,0,TY_FIRE,TY_NONE,"庭院里的余温",{"庭院石阶上落着一圈灰。","靠近花草的石面仍然温热。"},"让能唤起火焰的伙伴试试。","石阶似乎在等待火星回应。","石阶上的火星再次亮起。","三处余温指向同一道身影。","回到调查册，循着焦痕靠近。"},
 {2,0,2,2,TY_WATER,TY_NONE,"逆流而行的波纹",{"河岸的草叶被水打湿。","一道清澈波纹正向上游移动。"},"熟悉水流的伙伴能跟上它。","波纹逆流而行，并非风吹。","伙伴潜入浅水，跟上波纹。","清澈的水流通向漩涡列岛。","先取得前往列岛的徽章。"},
 {2,1,6,0,TY_WATER,TY_GRASS,"浅滩里的清泉",{"潮水退后，水草仍在摇动。","清泉被缠绕的根须挡住了。"},"请亲近水或草木的伙伴。","泉眼或许就在根须之间。","伙伴拨开水草，找到了泉眼。","水流受阻的原因已经清楚了。","前往调查册，完成净水试炼。"},
 {3,0,6,0,TY_WATER,TY_NONE,"银羽映出的潮线",{"银色之羽映着细细的潮线。","浅滩水草朝着同一方向摆动。"},"熟悉潮水的伙伴能辨方向。","顺着水草，留意银羽的变化。","伙伴带着银羽迎向潮水。","第一道潮线通向珊瑚海湾。","那里有一串忽明忽暗的光点。"},
 {3,1,6,1,TY_ELECTRIC,TY_NONE,"珊瑚间的光点",{"珊瑚间的光点有节奏地闪着。","像在等待另一束光回应。"},"让能放出电光的伙伴回应。","光点正在等待相同的节奏。","伙伴发出电光，光点连成线。","第二道潮线指向潮汐深处。","找能适应海浪的伙伴同行。"},
 {3,2,6,2,TY_WATER,TY_FLYING,"风与潮交汇处",{"最深处的海浪突然分开。","海风正托起那枚银色之羽。"},"会乘风或游水的伙伴能靠近。","海浪与高风，任一条都可通。","伙伴穿过浪花，银羽鸣响。","三道潮线交汇在海渊之上。","回到调查册，回应海的呼唤。"},
 {4,0,7,0,TY_FIRE,TY_NONE,"壁画上的晨光",{"庭院壁画上的日轮暗了。","三道身影围着一处火焰刻纹。"},"让能唤起火焰的伙伴照亮。","刻纹还缺一束温暖的光。","火光照亮了壁画的第一部分。","日轮旁显出月亮的符号。","去月光长廊读懂新的刻纹。"},
 {4,1,7,1,TY_PSYCHIC,TY_GHOST,"月下无声的铃",{"长廊里的铃铛没有摆动。","墙上的影子却轻轻摇晃。"},"请能感知无形力量的伙伴。","铃声藏在眼睛看不见的地方。","伙伴注视暗影，铃铛轻响。","月影在墙上指向塔顶。","带能乘风的伙伴登上回廊。"},
 {4,2,7,2,TY_FLYING,TY_NONE,"塔顶的虹光",{"塔顶的铃声被风带得很远。","一束虹光停在高处的檐角。"},"会乘风的伙伴或许能靠近。","虹光在高处，沿风寻找入口。","伙伴飞向檐角，虹光洒落。","壁画与三兽的记录相互呼应。","回到调查册，迎接虹光主人。"},
 {5,0,1,0,TY_GRASS,TY_NONE,"古树的两圈年轮",{"树干的两圈年轮重叠在一起。","嫩芽回应着关都森林的气息。"},"熟悉草木的伙伴能听见它。","两圈年轮在等同一个回应。","嫩芽随着伙伴的回应舒展开。","回声从古树传入密林深处。","寻找影子与树木错开的地方。"},
 {5,1,1,2,TY_PSYCHIC,TY_GHOST,"迟到了一步的影子",{"密林中的树影慢了一步。","脚步停止，影子才慢慢停下。"},"请能感知无形力量的伙伴。","影子似乎落在了另一个时刻。","伙伴凝望树影，景色重叠。","两个时刻交汇在林冠之上。","带熟悉草木的伙伴靠近树梢。"},
 {5,2,1,1,TY_GRASS,TY_NONE,"两个时刻的嫩芽",{"树梢同时长出新叶与旧叶。","回声正从重叠的枝叶间传来。"},"让亲近草木的伙伴回应。","新叶与旧叶正在等待共鸣。","伙伴唤醒嫩芽，林间亮起来。","森林里的两个时刻终于重合。","回到调查册，寻找回声主人。"},
};
const johto_probe_t *johto_probe(unsigned id){return id<JOHTO_PROBE_COUNT?&PROBES[id]:NULL;}
bool johto_probe_available(const johto_state_t *j,const johto_story_t *s,bool feather,unsigned id){
 const johto_probe_t *p=johto_probe(id);
 if(!p||!johto_route_open(j,p->route)||!s->tower_seen||j->legend_clues[p->legend]!=p->step)return false;
 if(p->legend==3&&(!feather||johto_badges(j)<6))return false;
 if(p->legend==4&&(johto_badges(j)<8||j->legend_clues[0]<3||j->legend_clues[1]<3||j->legend_clues[2]<3))return false;
 if(p->legend==5&&(j->phase!=JOHTO_COMPLETE||!(s->forest_visits&1)))return false;
 return true;
}
unsigned johto_probe_next(const johto_state_t *j,const johto_story_t *s,bool feather,unsigned route,unsigned focus){
 for(unsigned n=0;n<6;n++){unsigned legend=n<3?(n+focus%3)%3:n;
  for(unsigned id=0;id<JOHTO_PROBE_COUNT;id++)if(PROBES[id].legend==legend&&PROBES[id].route==route&&johto_probe_available(j,s,feather,id))return id;
 }return JOHTO_PROBE_NONE;
}
bool johto_probe_member(unsigned id,const mon_t *m){
 const johto_probe_t *p=johto_probe(id);species_t sp;
 if(!p||!m||!m->species_id||!m->hp||!assets_species(m->species_id,&sp))return false;
 return sp.type1==p->type1||sp.type2==p->type1||(p->type2!=TY_NONE&&(sp.type1==p->type2||sp.type2==p->type2));
}
unsigned johto_probe_apply(save_t *s,unsigned id,unsigned path,unsigned slot,const mon_t *expected){
 const johto_probe_t *p=johto_probe(id);
 if(!s||!p||!johto_probe_available(&s->johto,&s->story,s->activities.silver_feather,id))return PROBE_LOCKED;
 if(path>=JOHTO_PATH_COUNT||path!=p->path)return PROBE_WRONG_PATH;
 if(!expected||slot>=s->members.party_count||memcmp(expected,&s->members.party[slot],sizeof(*expected)))return PROBE_LOCKED;
 if(!johto_probe_member(id,expected))return PROBE_WRONG_PARTNER;
 if(s->pet.stamina<NURT_EXPLORE_COST)return PROBE_NO_STAMINA;
 if(s->johto.last_action==UINT32_MAX||!johto_explore(&s->johto,p->route,s->johto.last_action+1,true))return PROBE_LOCKED;
 johto_story_explore(&s->story,&s->johto,p->route);
 s->johto.legend_clues[p->legend]++;s->pet.stamina-=NURT_EXPLORE_COST;return PROBE_OK;
}
