#include "achievements.h"
enum { DEX, SHINY, EVOLUTION, BADGES, CHAMPION, RED, ARRIVAL, EGG, CROSS_GEN, JOHTO_BADGES, JOHTO_DEX, NATIONAL_DEX, JOHTO_SHINY, RUINS, DEEP, ELM, CHAMP_GYM, CHAMP_ALL, CHAMP_ELM, RED_LAKE };
static const achievement_info_t INFO[ACHIEVEMENT_COUNT] = {
 {"新的伙伴","图鉴捕获种类达到2",DEX,2,ITEM_GREAT,5},
 {"小小收藏家","图鉴捕获种类达到5",DEX,5,ITEM_THUNDER_STONE,1},
 {"旅行收藏家","图鉴捕获种类达到10",DEX,10,ITEM_WATER_STONE,1},
 {"图鉴研究员","图鉴捕获种类达到25",DEX,25,ITEM_LEAF_STONE,1},
 {"图鉴专家","图鉴捕获种类达到50",DEX,50,ITEM_LINK_MACHINE,1},
 {"百种相遇","图鉴捕获种类达到100",DEX,100,ITEM_GROWTH_MACHINE,2},
 {"关都全图鉴","图鉴捕获种类达到151",DEX,151,ITEM_MASTER,1},
 {"闪耀的相遇","捕获1种闪光宝可梦",SHINY,1,ITEM_MOON_STONE,1},
 {"追逐星光","捕获3种闪光宝可梦",SHINY,3,ITEM_MASTER,1},
 {"成长的瞬间","完成1次宝可梦进化",EVOLUTION,1,ITEM_FIRE_STONE,1},
 {"进化研究家","完成5次宝可梦进化",EVOLUTION,5,ITEM_LINK_MACHINE,1},
 {"第一枚徽章","获得1枚道馆徽章",BADGES,1,ITEM_MILK,5},
 {"道馆挑战者","获得4枚道馆徽章",BADGES,4,ITEM_MOON_STONE,1},
 {"八枚徽章","获得8枚道馆徽章",BADGES,8,ITEM_GROWTH_MACHINE,1},
 {"联盟冠军","战胜联盟冠军青绿",CHAMPION,1,ITEM_MASTER,1},
 {"白银山之巅","战胜白银山的赤红",RED,1,ITEM_LINK_MACHINE,2},
 {"城都的邀请","抵达城都并选择伙伴",ARRIVAL,1,ITEM_BERRY,5},
 {"蛋中的惊喜","孵化1只波克比",EGG,1,ITEM_JOY_COOKIE,5},
 {"新的进化","完成1次跨世代进化",CROSS_GEN,1,ITEM_UPGRADE,1},
 {"城都新星","获得2枚城都徽章",JOHTO_BADGES,2,ITEM_SUN_STONE,1},
 {"城都旅人","获得4枚城都徽章",JOHTO_BADGES,4,ITEM_KINGS_ROCK,1},
 {"钢铁之心","获得6枚城都徽章",JOHTO_BADGES,6,ITEM_METAL_COAT,1},
 {"城都八徽章","获得8枚城都徽章",JOHTO_BADGES,8,ITEM_DRAGON_SCALE,1},
 {"城都收藏家","捕获25种城都伙伴",JOHTO_DEX,25,ITEM_UPGRADE,1},
 {"城都研究员","捕获50种城都伙伴",JOHTO_DEX,50,ITEM_METAL_COAT,2},
 {"城都全图鉴","捕获100种城都伙伴",JOHTO_DEX,100,ITEM_MASTER,1},
 {"跨海的图鉴","全国图鉴达到200种",NATIONAL_DEX,200,ITEM_UPGRADE,2},
 {"全国全图鉴","全国图鉴达到251种",NATIONAL_DEX,251,ITEM_MASTER,1},
 {"城都的星光","捕获1种城都闪光",JOHTO_SHINY,1,ITEM_FRIEND,5},
 {"遗迹的答案","解开四组遗迹符号",RUINS,4,ITEM_KINGS_ROCK,1},
 {"海渊归来","完成一次漩涡海渊挑战",DEEP,1,ITEM_DRAGON_SCALE,1},
 {"研究大师","通过空木最终考验",ELM,1,ITEM_MASTER,1},
 {"破风之翼","击败冠军版阿速",CHAMP_GYM,1,ITEM_FAST,5},
 {"拆巢之策","击败冠军版阿笔",CHAMP_GYM,1,ITEM_SUN_STONE,1},
 {"应援突破","击败冠军版小茜",CHAMP_GYM,1,ITEM_JOY_COOKIE,5},
 {"双相之解","击败冠军版松叶",CHAMP_GYM,1,ITEM_MOON_STONE,1},
 {"重拳破解","击败冠军版阿四",CHAMP_GYM,1,ITEM_LINK_MACHINE,1},
 {"钢阵破甲","击败冠军版阿蜜",CHAMP_GYM,1,ITEM_METAL_COAT,1},
 {"寒潮终结","击败冠军版柳伯",CHAMP_GYM,1,ITEM_WATER_STONE,1},
 {"龙阵接力","击败冠军版小椿",CHAMP_GYM,1,ITEM_DRAGON_SCALE,1},
 {"城都冠军巡礼","战胜八位冠军版馆主",CHAMP_ALL,8,ITEM_MASTER,1},
 {"传说的答案","通过空木传说试炼",CHAMP_ELM,1,ITEM_UPGRADE,2},
 {"红色的羁绊","接回愤怒之湖红色伙伴",RED_LAKE,1,ITEM_FRIEND,5},
};
const achievement_info_t *achievement_info(unsigned id) { return id<ACHIEVEMENT_COUNT?&INFO[id]:0; }
void achievement_view(achievement_view_t *out,const achievement_store_t *store,const dex_t *dex,uint16_t defeated) {
 *out=(achievement_view_t){.store=*store,.defeated=defeated};
 for(unsigned i=1;i<=151;i++)out->caught+=dex_is_caught(dex,i);
 for(unsigned i=0;i<DEX_SPECIES;i++){
  unsigned shiny=!!(dex->shiny_caught[i/8]&(1u<<(i%8)));out->shiny+=shiny;
  if(i>=151){out->johto_caught+=dex_is_caught(dex,i+1);out->johto_shiny+=shiny;}
 }
}
unsigned achievement_progress(const achievement_view_t *v,unsigned id) {
 const achievement_info_t *a=achievement_info(id);if(!a||!v)return 0;
 unsigned n=0;
 switch(a->kind){case DEX:n=v->caught;break;case SHINY:n=v->shiny;break;case EVOLUTION:n=v->store.evolutions;break;
 case BADGES:for(unsigned i=0;i<8;i++)n+=!!(v->defeated&(1u<<i));break;
 case ARRIVAL:n=v->johto.phase>=JOHTO_ACTIVE;break;
 case EGG:n=v->johto.eggs_hatched;break;case CROSS_GEN:n=v->store.cross_gen_evolutions;break;
 case JOHTO_BADGES:n=johto_badges(&v->johto);break;case JOHTO_DEX:n=v->johto_caught;break;
 case NATIONAL_DEX:n=v->caught+v->johto_caught;break;case JOHTO_SHINY:n=v->johto_shiny;break;
 case RUINS:for(unsigned i=0;i<4;i++)n+=!!(v->ruins&(1u<<i));break;
 case DEEP:n=v->sea_clears;break;
 case CHAMP_GYM:n=!!(v->champion_gyms&(1u<<(id-32)));break;
 case CHAMP_ALL:for(unsigned i=0;i<8;i++)n+=!!(v->champion_gyms&(1u<<i));break;
 case CHAMP_ELM:n=v->champion_elm;break;case RED_LAKE:n=v->lake_stage==LAKE_RECEIVED;break;
 case ELM:n=v->johto.phase==JOHTO_COMPLETE;break;
 case CHAMPION:n=!!(v->defeated&(1u<<12));break;case RED:n=!!(v->defeated&(1u<<13));break;}
 return n>a->target?a->target:n;
}
achievement_claim_t achievement_claim(achievement_store_t *s,inventory_t *bag,const achievement_view_t *v,unsigned id) {
 const achievement_info_t *a=achievement_info(id);if(!a||id>=32)return ACH_CLAIM_LOCKED;
 if(s->claimed&(1u<<id))return ACH_CLAIM_ALREADY;
 if(achievement_progress(v,id)<a->target)return ACH_CLAIM_LOCKED;
 unsigned total=(unsigned)bag->quantity[a->item]+a->quantity;
 unsigned cap=items_capacity(a->item);
 // New rare rewards remain claimable when their stack is full.
 if(id>=16&&total>cap)return ACH_CLAIM_FULL;
 bag->quantity[a->item]=total>cap?cap:total;
 s->claimed|=1u<<id;
 return total>cap?ACH_CLAIM_CAPPED:ACH_CLAIM_OK;
}

bool achievement_claimed(const achievement_view_t *v,unsigned id){return id<32?!!(v->store.claimed&(1u<<id)):id<ACHIEVEMENT_COUNT?!!(v->endgame_claimed&(1u<<(id-32))):false;}
achievement_claim_t achievement_claim_extended(achievement_store_t *s,endgame_t *end,inventory_t *bag,const achievement_view_t *v,unsigned id){
 if(id<32)return achievement_claim(s,bag,v,id);
 const achievement_info_t *a=achievement_info(id);if(!a||!end)return ACH_CLAIM_LOCKED;
 if(end->claimed&(1u<<(id-32)))return ACH_CLAIM_ALREADY;
 if(achievement_progress(v,id)<a->target)return ACH_CLAIM_LOCKED;
 unsigned total=bag->quantity[a->item]+a->quantity;if(total>items_capacity(a->item))return ACH_CLAIM_FULL;
 bag->quantity[a->item]=total;end->version=1;end->claimed|=1u<<(id-32);return ACH_CLAIM_OK;
}
