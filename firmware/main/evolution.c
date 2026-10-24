#include "evolution.h"

bool evo_level_ready(uint8_t level, uint8_t trigger, uint16_t target, uint8_t required)
{
    return trigger == EVO_TRIGGER_LEVEL && target > 0 && target <= 251 &&
           required > 0 && required <= 100 && level >= required;
}

#define DEFAULT_INTIMACY 60
#define DEFAULT_EXPLORE_MIN 10
#define DEFAULT_EXPLORE_MULT 2
#define TRADE_INTIMACY 90
#define TRADE_EXPLORE_MIN 20
#define TRADE_EXPLORE_MULT 4

void evo_check(uint8_t intimacy_pct, uint16_t explore_value,
               uint8_t trigger, uint8_t evolve_to, uint8_t evolve_level,
               evo_check_t *out)
{
    if (!out) return;

    *out = (evo_check_t){
        .cur_intimacy = intimacy_pct,
        .cur_explore = explore_value,
    };
    if (trigger == EVO_TRIGGER_NONE || evolve_to == 0) return;

    uint8_t need_intimacy = DEFAULT_INTIMACY;
    uint16_t need_explore = (uint16_t)evolve_level * DEFAULT_EXPLORE_MULT;
    if (need_explore < DEFAULT_EXPLORE_MIN) need_explore = DEFAULT_EXPLORE_MIN;

    if (trigger == EVO_TRIGGER_TRADE) {
        need_intimacy = TRADE_INTIMACY;
        need_explore = (uint16_t)evolve_level * TRADE_EXPLORE_MULT;
        if (need_explore < TRADE_EXPLORE_MIN) need_explore = TRADE_EXPLORE_MIN;
    }

    out->need_intimacy = need_intimacy;
    out->need_explore = need_explore;
    out->can = intimacy_pct >= need_intimacy && explore_value >= need_explore;
}

#include "items.h"
unsigned evo_options(uint16_t species,uint8_t trigger,uint16_t target,uint8_t level,evo_option_t out[EVO_OPTION_MAX]) {
    static const struct {uint8_t from; evo_option_t option;} special[]={
#define ITEM(from,to,id) {from,{to,id,0,0,0,0}}
        ITEM(37,38,ITEM_FIRE_STONE),ITEM(58,59,ITEM_FIRE_STONE),ITEM(133,136,ITEM_FIRE_STONE),
        ITEM(61,62,ITEM_WATER_STONE),ITEM(90,91,ITEM_WATER_STONE),ITEM(120,121,ITEM_WATER_STONE),ITEM(133,134,ITEM_WATER_STONE),
        ITEM(25,26,ITEM_THUNDER_STONE),ITEM(133,135,ITEM_THUNDER_STONE),
        ITEM(44,45,ITEM_LEAF_STONE),ITEM(70,71,ITEM_LEAF_STONE),ITEM(102,103,ITEM_LEAF_STONE),
        ITEM(30,31,ITEM_MOON_STONE),ITEM(33,34,ITEM_MOON_STONE),ITEM(35,36,ITEM_MOON_STONE),ITEM(39,40,ITEM_MOON_STONE),
        ITEM(64,65,ITEM_LINK_MACHINE),ITEM(67,68,ITEM_LINK_MACHINE),ITEM(75,76,ITEM_LINK_MACHINE),ITEM(93,94,ITEM_LINK_MACHINE),
        ITEM(44,182,ITEM_SUN_STONE),ITEM(191,192,ITEM_SUN_STONE),
        ITEM(95,208,ITEM_METAL_COAT),ITEM(123,212,ITEM_METAL_COAT),
        ITEM(61,186,ITEM_KINGS_ROCK),ITEM(79,199,ITEM_KINGS_ROCK),
        ITEM(117,230,ITEM_DRAGON_SCALE),ITEM(137,233,ITEM_UPGRADE),
#undef ITEM
#define FRIEND(from,to) {from,{to,ITEM_NONE,0,80,0,0}}
        FRIEND(42,169),FRIEND(113,242),FRIEND(172,25),FRIEND(173,35),FRIEND(174,39),FRIEND(175,176),
#undef FRIEND
        {133,{196,ITEM_NONE,0,80,3,"晨光训练"}},{133,{197,ITEM_NONE,0,80,3,"夜行训练"}},
        {236,{106,ITEM_NONE,20,0,5,"攻击训练"}},{236,{107,ITEM_NONE,20,0,5,"防守训练"}},{236,{237,ITEM_NONE,20,0,5,"均衡训练"}},
    };
    unsigned count=0;
    // Tyrogue's three choices replace its data-file default, never bypass training.
    if(species!=236&&trigger==EVO_TRIGGER_LEVEL&&target&&target<=251&&level)
        out[count++]=(evo_option_t){.target=target,.item=ITEM_NONE,.level=level};
    for(unsigned i=0;i<sizeof(special)/sizeof(*special)&&count<EVO_OPTION_MAX;i++)
        if(special[i].from==species)out[count++]=special[i].option;
    return count;
}
bool evo_option_ready(const evo_option_t *o,unsigned level,unsigned intimacy,unsigned badges,unsigned quantity) {
    return o&&level>=o->level&&intimacy>=o->intimacy&&badges>=o->badges&&(o->item==ITEM_NONE||quantity);
}
