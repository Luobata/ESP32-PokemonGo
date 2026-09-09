#include "exploration.h"
#include "assets.h"
#include <stddef.h>

static const exploration_route_t ROUTES[4]={
 {"常青森林","草丛与树梢的伙伴",{"树上留下电击痕迹","草丛传来细小叫声","黄色身影一闪而过"},25,0x3ce7},
 {"月见山洞","寻找岩壁深处的伙伴",{"地面出现巨大拖痕","岩壁传来低沉回声","碎石正在轻轻震动"},95,0x9c53},
 {"海边浅滩","寻找潮汐带来的伙伴",{"沙滩留下宽阔足迹","海上传来悠长歌声","水面浮现蓝色背影"},131,0x3d7f},
 {"废弃电站","寻找电流中的伙伴",{"电线旁留下焦黑痕迹","远处传来电流声","黑黄身影穿过机房"},125,0xfde0},
};
// Curated route habitats. Rarity is encounter frequency, not a stat-total filter.
static const uint8_t POOLS[4][5][16]={
 {{10,13,16,43,46,21,23},{11,14,25,69,1,29,32,48,102},{12,15,44,70,2,17,22,24,30,33,49,47},{3,45,71,114,123,18,31,34,83,122},{127,103,149,151}},
 {{74,41,27,50},{35,66,111,104,39,56,37,4},{75,42,51,67,28,5,57},{95,105,112,76,68,36,40,38,6,106,107,108},{142,143,150,115,113}},
 {{129,72,60,98,54},{7,116,118,90,79,86,120},{8,61,117,99,55,73,119,80},{9,62,87,134,139,141,91,121,138,140,147,148},{130,131,144,124}},
 {{19,100,81,88,52},{25,109,137,132,20,58,77,84,96,92,63,133},{82,101,26,110,53,78,85,97,93,64},{125,126,89,135,136,65,94},{145,59,146,128}}
};
const exploration_route_t *exploration_route(unsigned id) {return id<4?&ROUTES[id]:&ROUTES[0];}
static const exploration_chapter_t CHAPTERS[EXPLORATION_CHAPTERS]={
 {"初出茅庐","开始冒险","大木：去寻找身边的伙伴","四条基础路线",0,0,{25,95,131,125},ITEM_BERRY},
 {"森林的守望者","获得一枚徽章","小刚：林中有挥舞双镰的影子","森林深处与叶之石",1,0,{123,95,131,125},ITEM_LEAF_STONE},
 {"潮汐的秘密","获得两枚徽章","小霞：退潮时留意古老贝壳","化石海滩与水之石",2,0,{123,95,138,125},ITEM_WATER_STONE},
 {"远古的回声","获得四枚徽章","研究员：岩层中传来翅膀声","远古岩窟与月之石",4,0,{123,142,138,125},ITEM_MOON_STONE},
 {"沉睡的电流","获得六枚徽章","工人：机房里的电流回来了","电站核心与雷之石",6,0,{123,142,138,135},ITEM_THUNDER_STONE},
 {"火焰的足迹","获得八枚徽章","夏伯：山中出现不灭的火羽","火焰鸟与火之石",8,0,{123,146,138,135},ITEM_FIRE_STONE},
 {"天空与海的传说","战胜全部四天王","阿渡：去追寻天空中的传说","冰雷双鸟与通讯机器",8,0x0f00,{149,146,144,145},ITEM_LINK_MACHINE},
 {"禁地的访客","战胜联盟冠军","大木：洞穴深处有未知力量","超梦线索与成长机器",8,0x1f00,{149,150,144,145},ITEM_GROWTH_MACHINE},
 {"最初的幻影","战胜赤红","赤红：森林里还有最后的谜","梦幻线索与大师球",8,0x3f00,{151,150,144,145},ITEM_MASTER},
};
const exploration_chapter_t *exploration_chapter(unsigned chapter){return &CHAPTERS[chapter<EXPLORATION_CHAPTERS?chapter:0];}
bool exploration_chapter_open(unsigned chapter,uint16_t defeated){
 if(chapter>=EXPLORATION_CHAPTERS)return false;
 unsigned badges=0;for(unsigned i=0;i<8;i++)badges+=!!(defeated&(1u<<i));
 const exploration_chapter_t *c=&CHAPTERS[chapter];return badges>=c->badges&&(defeated&c->wins)==c->wins;
}
unsigned exploration_chapter_current(uint16_t defeated){unsigned n=0;for(unsigned i=1;i<EXPLORATION_CHAPTERS;i++)if(exploration_chapter_open(i,defeated))n=i;return n;}
uint16_t exploration_target(unsigned route,uint16_t defeated){return exploration_chapter(exploration_chapter_current(defeated))->targets[route<4?route:0];}
bool exploration_species_open(unsigned species,uint16_t defeated){
 unsigned c=exploration_chapter_current(defeated);
 if(species==151)return c>=8;
 if(species==150)return c>=7;
 if(species==144||species==145)return c>=6;
 if(species==146||species==149)return c>=5;
 if(species==142)return c>=3;
 if(species>=138&&species<=141)return c>=2;
 return true;
}
int exploration_habitat(unsigned species,unsigned *rarity) {
 for(unsigned route=0;route<4;route++)for(unsigned tier=0;tier<5;tier++)for(unsigned i=0;i<16&&POOLS[route][tier][i];i++)
  if(POOLS[route][tier][i]==species){if(rarity)*rarity=tier+1;return route;}
 return -1;
}
unsigned exploration_unlock_chapter(unsigned species) {
 if(species==151)return 8;
 if(species==150)return 7;
 if(species==144||species==145)return 6;
 if(species==146||species==149)return 5;
 if(species==142)return 3;
 if(species>=138&&species<=141)return 2;
 return 0;
}
uint16_t exploration_focus(const exploration_state_t *s,uint16_t defeated) {
 return s->tracked_species&&exploration_species_open(s->tracked_species,defeated)&&exploration_habitat(s->tracked_species,NULL)==s->route?s->tracked_species:exploration_target(s->route,defeated);
}
const char *exploration_story(unsigned species,unsigned clue) {
 static const char *const fossil[]={"岩层露出了古老的纹路","发现尚有温度的化石","岩壁后传来了生命的回声"};
 static const char *const bird[]={"远处的天空突然变了颜色","羽毛中蕴藏着强大的力量","传说的羽翼就在前方"};
 static const char *const mewtwo[]={"找到了遗落的研究记录","未知的力量在洞穴中回响","实验室深处传来了呼唤"};
 static const char *const mew[]={"树叶间闪过粉色的影子","小小的足迹又突然消失","它似乎也在好奇地观察你"};
 static const char *const normal[]={"足迹延伸向路线深处","远处传来目标的叫声","目标就在附近"};
 if(clue>2)clue=2;
 return (species==151?mew:species==150?mewtwo:species>=144&&species<=146?bird:species>=138&&species<=142?fossil:normal)[clue];
}
static uint32_t mix(uint32_t x) {
 x^=x>>16;x*=0x7feb352du;x^=x>>15;x*=0x846ca68bu;return x^(x>>16);
}
static bool pending(const enc_queue_t *q,unsigned species) {
 for(unsigned i=0;i<q->count;i++)if(q->items[i].species_id==species)return true;
 return false;
}
static exploration_event_t step(exploration_state_t *s,enc_refresh_state_t *r,
 enc_queue_t *q,dex_t *dex,uint16_t active_uid,uint16_t defeated,bool campaign,unsigned nurture_bonus)
{
 exploration_event_t e={.kind=EXPLORE_NONE,.item=ITEM_NONE};
 if(!s||!r||!q||!dex||!exploration_valid(s)||!enc_refresh_valid(r))return e;
 e.route=s->route;e.clues=s->clues[s->route];
 if(!s->energy){e.kind=EXPLORE_NO_ENERGY;return e;}
 unsigned route=s->route;
 // Clue events are discoveries, not battles: do not advance rarity pity.
 if(s->clues[route]<3 && s->pulse[route]) {
  s->energy--;s->steps++;s->pulse[route]=0;s->clues[route]++;
  e.kind=EXPLORE_CLUE;e.clues=s->clues[route];return e;
 }
 bool target=s->clues[route]>=3;
 unsigned bonus=r->discoveries/10;if(bonus>10)bonus=10;
 uint32_t seed=mix(s->steps^r->serial*0x9e3779b9u^route*0x85ebca6bu^0x51a78u);
 unsigned roll=seed%1000;
 uint8_t rarity=roll<10+2*bonus+nurture_bonus/10?5:roll<60+4*bonus+nurture_bonus*2/5?4:roll<250+10*bonus+nurture_bonus?3:roll<650?2:1;
 if(target && rarity<3)rarity=3;
 if(r->since_elite>=29)rarity=5;
 else if(r->since_rare>=7 && rarity<4)rarity=4;
 unsigned species=0;
 if(target) {
  species=campaign?exploration_focus(s,defeated):ROUTES[route].target;
  unsigned native_rarity;if(exploration_habitat(species,&native_rarity)>=0&&rarity<native_rarity)rarity=native_rarity;
  if(pending(q,species)){e.kind=EXPLORE_BLOCKED;return e;}
 } else {
  const uint8_t *pool=POOLS[route][rarity-1];
  unsigned n=0;while(n<16&&pool[n])n++;
  // Three of four rolls prefer uncaught species within the same unlocked tier.
  if(campaign&&(seed&3)!=0)for(unsigned i=0;i<n;i++){
   unsigned candidate=pool[(seed/1000+i)%n];
   if(exploration_species_open(candidate,defeated)&&!pending(q,candidate)&&!dex_is_caught(dex,candidate)){species=candidate;break;}
  }
  for(unsigned i=0;!species&&i<n;i++) {
   unsigned candidate=pool[(seed/1000+i)%n];
   if((!campaign||exploration_species_open(candidate,defeated))&&!pending(q,candidate)){species=candidate;break;}
  }
  if(!species){e.kind=EXPLORE_BLOCKED;return e;}
 }
 species_t sp;
 if(!assets_species(species,&sp)){e.kind=EXPLORE_BLOCKED;return e;}
 uint32_t shiny=mix(seed^0x735a91cdu);
 encounter_t encounter={.ts=r->online_s,.species_id=species,.rarity=rarity,
  .biome=route,.hp_ratio=100,.is_transient=true,.is_shiny=shiny%(rarity==5?256:512)==0};
 while(!q->next_uid||q->next_uid==active_uid||enc_queue_find(q,q->next_uid))q->next_uid++;
 enc_queue_push(q,&encounter);
 dex_mark_seen(dex,species,encounter.is_shiny);
 s->energy--;s->steps++;
 if(target){s->clues[route]=0;s->pulse[route]=0;}else s->pulse[route]=1;
 r->since_rare=rarity>=4?0:r->since_rare+1;
 r->since_elite=rarity>=5?0:r->since_elite+1;
 e.kind=target?EXPLORE_TARGET:EXPLORE_ENCOUNTER;
 e.uid=q->items[q->count-1].uid;e.species=species;e.rarity=rarity;e.shiny=encounter.is_shiny;
 e.clues=s->clues[route];return e;
}

// Baseline rule harness retained for V11 regression. Runtime uses progress API.
exploration_event_t exploration_step(exploration_state_t *s,enc_refresh_state_t *r,enc_queue_t *q,dex_t *d,uint16_t active){return step(s,r,q,d,active,0,false,0);}
exploration_event_t exploration_step_team(exploration_state_t *s,enc_refresh_state_t *r,enc_queue_t *q,dex_t *d,uint16_t active,uint16_t defeated,inventory_t *bag,const nurture_t *pet,unsigned team_bonus){
 exploration_event_t e=step(s,r,q,d,active,defeated,true,nurture_rare_bonus(pet)+(team_bonus>30?30:team_bonus));
 if(e.kind!=EXPLORE_CLUE||!bag)return e;
 unsigned chapter=exploration_chapter_current(defeated);
 uint32_t roll=mix(s->steps^r->serial*0x9e3779b9u^s->route*0x85ebca6bu^0x18b479u);
 if(roll%100>=40)return e;
 // Previously unlocked supplies remain available. Master Balls remain uncommon among
 // clue discoveries after Red, and never replace the champion reward.
 unsigned reward=(roll/100)%(chapter+1);
 if(reward==8 && (roll/1000)%4!=0)reward=7;
 e.item=exploration_chapter(reward)->item;
 if(bag->quantity[e.item]>=items_capacity(e.item)){e.item_full=true;return e;}
 bag->quantity[e.item]++;e.quantity=1;return e;
}

exploration_event_t exploration_step_progress(exploration_state_t *s,enc_refresh_state_t *r,enc_queue_t *q,dex_t *d,uint16_t active,uint16_t defeated,inventory_t *bag){return exploration_step_nurtured(s,r,q,d,active,defeated,bag,NULL);}

exploration_event_t exploration_step_nurtured(exploration_state_t *s,enc_refresh_state_t *r,enc_queue_t *q,dex_t *d,uint16_t active,uint16_t defeated,inventory_t *bag,const nurture_t *pet){return exploration_step_team(s,r,q,d,active,defeated,bag,pet,0);}

unsigned exploration_team_bonus(const party_t *party,unsigned route) {
 if(!party||route>=4)return 0;
 // GEN1 type IDs: grass/bug, rock/ground, water/ice, electric/poison.
 static const uint8_t types[4][2]={{4,11},{12,8},{2,5},{3,7}};
 unsigned matches=0;for(unsigned i=0;i<party->party_count;i++){
  bool duplicate=false;for(unsigned j=0;j<i;j++)if(party->party[j].species_id==party->party[i].species_id)duplicate=true;
  species_t sp;if(duplicate||!assets_species(party->party[i].species_id,&sp))continue;
  if(sp.type1==types[route][0]||sp.type2==types[route][0]||sp.type1==types[route][1]||sp.type2==types[route][1])matches++;
 }
 return matches>3?30:matches*10;
}

void exploration_research_progress(unsigned route,const dex_t *dex,uint8_t *seen,uint8_t *caught){
 *seen=*caught=0;if(route>=4||!dex)return;
 bool counted[152]={0};
 for(unsigned tier=0;tier<5;tier++)for(unsigned i=0;i<16&&POOLS[route][tier][i];i++){
  unsigned id=POOLS[route][tier][i];if(counted[id])continue;counted[id]=true;
  *seen+=dex_is_seen(dex,id);*caught+=dex_is_caught(dex,id);
 }
}
exploration_kind_t exploration_research_claim(exploration_state_t *s,const dex_t *dex,unsigned route){
 if(!s||route>=4)return EXPLORE_BLOCKED;
 if(s->research_flags&(1u<<route))return EXPLORE_RESEARCH_CLAIMED;
 uint8_t seen,caught;exploration_research_progress(route,dex,&seen,&caught);
 if(seen<5||caught<3||!(s->research_flags&(16u<<route)))return EXPLORE_RESEARCH_LOCKED;
 s->research_flags|=1u<<route;return EXPLORE_NONE;
}
