#include "exp.h"

uint32_t exp_for_level(uint8_t n)
{
    if (n <= 1) return 0;
    // 60% of the previous 5*n^3/2 requirement; rewards retain their value.
    return 3u * n * n * n / 2u;
}

uint8_t exp_to_level(uint32_t exp, uint8_t cap)
{
    uint8_t level = 1;
    while (level < cap && exp >= exp_for_level((uint8_t)(level + 1))) {
        level++;
    }
    return level;
}

void exp_progress(uint32_t exp, uint8_t level, uint32_t *got, uint32_t *need)
{
    uint32_t lo = exp_for_level(level);
    uint32_t hi = exp_for_level((uint8_t)(level + 1));

    *got = exp > lo ? exp - lo : 0;
    *need = hi > lo ? hi - lo : 1;
}

uint16_t exp_scaled(uint16_t base,uint8_t percent) { uint32_t n=(uint32_t)base*percent/100;return n>UINT16_MAX?UINT16_MAX:(uint16_t)n; }

void exp_share_party(party_t *party,unsigned eligible,uint16_t award) {
 unsigned bonus=award/5;if(!bonus)return;
 for(unsigned i=0;i<party->party_count;i++)if(eligible&(1u<<i)){
  mon_t *m=&party->party[i];uint32_t base=exp_for_level(m->level);if(m->exp<base)m->exp=base;
  m->exp=m->exp>UINT32_MAX-bonus?UINT32_MAX:m->exp+bonus;m->level=exp_to_level(m->exp,LEVEL_MAX);
 }
}
