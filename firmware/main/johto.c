#include "johto.h"
#include <limits.h>
#include <string.h>

const johto_route_t JOHTO_ROUTES[8]={
 {"若叶郊野","初始伙伴研究",0,35,44,{161,163,165,167,179,187,191,194,172,173,174,183},12},
 {"桧皮林地","虫类观察",1,38,48,{165,166,167,168,177,187,188,190,193,204,206,214},12},
 {"满金原野","伙伴救助",2,42,52,{189,179,180,183,184,185,191,192,209,216,231,241},12},
 {"缘朱遗迹","遗迹调查",3,48,58,{177,178,198,200,201,202,203,207,213,234,235,236},12},
 {"烧焦塔","三兽踪迹",4,52,62,{156,162,164,181,195,197,205,210,215,218,228,229},12},
 {"冰雪之径","冰原远征",5,58,68,{215,217,220,221,225,238,239,240,246,247,224,232},12},
 {"漩涡列岛","银色之羽调查",6,64,76,{158,159,170,171,184,195,211,222,223,224,226,230},12},
 {"铃铛塔","虹色之羽调查",7,70,82,{154,157,160,169,182,186,196,199,208,212,227,248},12},
};
const johto_trainer_t JOHTO_TRAINERS[11]={
 {"阿速","飞翼徽章","让你看看飞行的力量！","你的伙伴已经学会乘风前进。",{164,176,18},{40,41,42},3},
 {"阿笔","昆虫徽章","小小的身体也有无限可能。","这枚徽章属于你的观察与耐心。",{166,168,214,212},{44,45,46,47},4},
 {"小茜","标准徽章","准备好面对我们的默契了吗？","下一次，我们还会更强！",{210,203,217,241},{49,50,51,52},4},
 {"松叶","魅影徽章","看清眼前，也看清心中的影子。","你已获得继续调查传说的资格。",{200,94,198,197},{54,55,56,57},4},
 {"阿四","打击徽章","真正的力量来自不断磨练。","带着你的伙伴，继续前进吧！",{237,107,106,62,214},{58,59,60,61,62},5},
 {"阿蜜","钢铁徽章","温柔，也可以很坚强。","银色之羽的线索就在海的另一边。",{82,205,227,212,208},{64,65,66,67,68},5},
 {"柳伯","冰之徽章","经历风雪，才能懂得坚持。","你的热情，已经融化了冰雪。",{87,91,215,225,221},{70,71,72,73,74},5},
 {"小椿","升龙徽章","让我们见识你与伙伴的羁绊。","你已经证明自己。去完成最后的调查吧！",{130,148,181,248,230,149},{75,76,77,78,79,80},6},
 {"空木博士","城都研究大师","这一次，让我看看你们一路学到的一切。","答案，就在你和伙伴共同走过的旅途中。",{212,248,243,245,249,250},{88,88,89,90,91,92},6},
 {"空木·坚守","接力防守","观察防守的节奏，寻找突破口。","每次选择，都让我们的研究更进一步。",{212,248,243,245,249,250},{88,88,89,90,91,92},6},
 {"空木·疾风","高速进攻","速度与力量，都需要伙伴的默契。","下一次，再来试试新的伙伴组合吧。",{212,248,243,245,249,250},{88,88,89,90,91,92},6},
};

void johto_init(johto_state_t *s){memset(s,0,sizeof(*s));s->version=1;}
unsigned johto_badges(const johto_state_t *s){unsigned n=0;for(unsigned v=s->badges;v;v>>=1)n+=v&1;return n;}
bool johto_valid(const johto_state_t *s){
 if(!s||s->version!=1||s->phase>JOHTO_COMPLETE||s->reserved||s->final_reward_claimed>1)return false;
 if(s->badges!=((1u<<johto_badges(s))-1u))return false;
 if(s->phase<JOHTO_ACTIVE&&(s->starter||s->badges||s->explorations||s->egg_status))return false;
 if(s->phase>=JOHTO_ACTIVE&&s->starter!=152&&s->starter!=155&&s->starter!=158)return false;
 if(s->egg_status>JOHTO_EGG_READY||s->egg_steps>JOHTO_EGG_STEPS)return false;
 if(s->egg_status==JOHTO_EGG_NONE&&(s->egg_steps||s->egg_seed))return false;
 if(s->egg_status==JOHTO_EGG_READY&&s->egg_steps!=JOHTO_EGG_STEPS)return false;
 if(s->egg_status==JOHTO_EGG_INCUBATING&&s->egg_steps>=JOHTO_EGG_STEPS)return false;
 if(s->final_reward_claimed&&s->phase!=JOHTO_COMPLETE)return false;
 if(s->phase==JOHTO_COMPLETE&&s->badges!=255)return false;
 for(unsigned i=0;i<6;i++)if(s->legend_clues[i]>3)return false;
 return true;
}
bool johto_offer(johto_state_t *s,uint16_t defeated){
 unsigned n=0;for(unsigned i=0;i<8;i++)n+=(defeated>>i)&1;
 if(n<4||s->phase!=JOHTO_HIDDEN)return false;
 s->phase=JOHTO_INVITED;return true;
}
bool johto_depart(johto_state_t *s){if(s->phase!=JOHTO_INVITED)return false;s->phase=JOHTO_VOYAGE;return true;}
bool johto_choose_starter(johto_state_t *s,uint16_t species){
 if(s->phase!=JOHTO_VOYAGE||(species!=152&&species!=155&&species!=158))return false;
 s->starter=species;s->phase=JOHTO_ACTIVE;return true;
}
bool johto_route_open(const johto_state_t *s,unsigned route){return route<8&&s->phase>=JOHTO_ACTIVE&&johto_badges(s)>=JOHTO_ROUTES[route].badges;}
uint8_t johto_route_level(unsigned route,unsigned level,uint32_t roll){
 if(route>=8)return 0;
 unsigned lo=JOHTO_ROUTES[route].min_level,hi=JOHTO_ROUTES[route].max_level;
 if(level<lo)level=lo;
 if(level>hi)level=hi;
 // A route always enforces its floor/ceiling; +/-2 variation stays in band.
 int result=(int)level+(int)(roll%5)-2;
 return result<(int)lo?lo:result>(int)hi?hi:(unsigned)result;
}
bool johto_gym_open(const johto_state_t *s,unsigned gym){
 return gym<8&&s->phase>=JOHTO_ACTIVE&&johto_badges(s)>=gym;
}
bool johto_gym_win(johto_state_t *s,unsigned gym){
 if(!johto_gym_open(s,gym)||(s->badges&(1u<<gym)))return false;
 s->badges|=1u<<gym;return true;
}
bool johto_explore(johto_state_t *s,unsigned route,uint32_t action,bool paid){
 if(!paid||!action||action<=s->last_action||!johto_route_open(s,route)||s->explorations==UINT32_MAX)return false;
 s->last_action=action;s->explorations++;
 if(s->research[route]<UINT16_MAX)s->research[route]++;
 if(s->egg_status==JOHTO_EGG_INCUBATING&&++s->egg_steps==JOHTO_EGG_STEPS)s->egg_status=JOHTO_EGG_READY;
 // Story-specific route progression is committed by the world transaction.
 return true;
}
bool johto_receive_egg(johto_state_t *s,uint32_t seed){
 if(s->phase<JOHTO_ACTIVE||!s->badges||s->egg_status||s->explorations<s->next_egg_at)return false;
 s->egg_status=JOHTO_EGG_INCUBATING;s->egg_seed=seed;s->egg_steps=0;return true;
}
bool johto_egg_shiny(const johto_state_t *s){return s->egg_status&&s->egg_seed%JOHTO_EGG_SHINY_DENOMINATOR==0;}
bool johto_hatch(johto_state_t *s,bool received){
 if(s->egg_status!=JOHTO_EGG_READY||!received)return false;
 s->egg_status=JOHTO_EGG_NONE;s->egg_steps=0;s->egg_seed=0;
 if(s->eggs_hatched<UINT16_MAX)s->eggs_hatched++;
 s->next_egg_at=s->explorations>UINT32_MAX-12?UINT32_MAX:s->explorations+12;return true;
}
bool johto_legend_ready(const johto_state_t *s,unsigned legend){return legend<6&&s->legend_clues[legend]==3;}
bool johto_final_open(const johto_state_t *s,uint16_t defeated){
 if(s->phase<JOHTO_ACTIVE||s->badges!=255||(defeated&0x20ff)!=0x20ff)return false;
 for(unsigned i=0;i<5;i++)if(!johto_legend_ready(s,i))return false;
 return true;
}
bool johto_final_win(johto_state_t *s,uint16_t defeated){
 if(!johto_final_open(s,defeated)||s->phase==JOHTO_COMPLETE)return false;
 s->phase=JOHTO_COMPLETE;return true;
}
bool johto_claim_final(johto_state_t *s){
 if(s->phase!=JOHTO_COMPLETE||s->final_reward_claimed)return false;
 s->final_reward_claimed=1;return true;
}

const johto_research_reward_t JOHTO_REWARDS[JOHTO_REWARD_COUNT]={
 {"桧皮林地调查",1,1,6},{"冰雪小径调查",5,6,6},{"缘朱遗迹调查",3,3,6},
 {"漩涡列岛调查",6,6,6},{"满金原野调查",2,2,6},
};
unsigned johto_reward_entitled(const johto_state_t *s,unsigned id){
 if(id>=JOHTO_REWARD_COUNT||s->phase<JOHTO_ACTIVE||johto_badges(s)<JOHTO_REWARDS[id].badges)return 0;
 return s->research[JOHTO_REWARDS[id].route]/JOHTO_REWARDS[id].step;
}
