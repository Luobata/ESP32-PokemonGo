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

void exp_share_party(party_t *p,unsigned eligible,uint16_t award){exp_award_party(p,0,eligible,award);}

uint16_t exp_battle_base(uint8_t level){
 if(!level)return 0;
 if(level>100)level=100;
 uint32_t need=exp_for_level(level+1)-exp_for_level(level);
 unsigned paced=(need+7)/8,legacy=level*8u+20;
 return paced>legacy?paced:legacy;
}
unsigned exp_party_percent(uint8_t level,uint8_t highest,bool participant){
 unsigned gap=highest>level?highest-level:0;
 unsigned extra=highest?gap*(participant?200u:160u)/highest:0;
 unsigned cap=participant?100:80;if(extra>cap)extra=cap;
 return (participant?100:20)+extra;
}
void exp_award_party(party_t *p,unsigned participants,unsigned eligible,uint16_t award){
 if(!p||!award)return;
 unsigned highest=1,n=0;for(unsigned i=0;i<p->party_count;i++){
  if(p->party[i].level>highest)highest=p->party[i].level;
  if((participants&eligible)&(1u<<i))n++;
 }
 unsigned remainder=n?award%n:0;
 for(unsigned i=0;i<p->party_count;i++)if(eligible&(1u<<i)){
  mon_t *m=&p->party[i];bool fought=!!(participants&(1u<<i));
  unsigned base=fought?(n?award/n:0):award;
  if(fought&&remainder){base++;remainder--;}
  uint32_t gain=base*exp_party_percent(m->level,highest,fought)/100;
  uint32_t minimum=exp_for_level(m->level);if(m->exp<minimum)m->exp=minimum;
  m->exp=m->exp>UINT32_MAX-gain?UINT32_MAX:m->exp+gain;
  m->level=exp_to_level(m->exp,LEVEL_MAX);
 }
}
