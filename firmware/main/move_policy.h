#pragma once
#include <stdbool.h>
#include <stdint.h>
// Persistent V21 bit assignments: IDs 1..165, then this append-only extra list.
// V24 appends all remaining Gen II IDs. V21-V23 bits 0..190 keep their meaning;
// the previously reserved bit 191 is cleared by migration before reuse.
#define MOVE_POLICY_BYTES 32
typedef struct { uint8_t disabled[MOVE_POLICY_BYTES]; } move_policy_t;
static inline int move_policy_bit(unsigned id) {
 if(id>=1 && id<=165)return (int)id-1;
 static const uint8_t extra[]={172,181,183,185,186,188,189,192,196,198,200,202,204,206,211,223,225,231,238,239,242,245,246,247,249,250};
 for(unsigned i=0;i<sizeof(extra);i++)if(id==extra[i])return 165+i;
 // Append remaining Gen II IDs after the 191 historical bits.
 if(id>=166&&id<=251){
  int bit=191+(int)id-166;
  for(unsigned i=0;i<sizeof(extra);i++)if(extra[i]<id)bit--;
  return bit;
 }
 return -1;
}
static inline bool move_policy_allows(const move_policy_t *p,unsigned id) {
 int bit=move_policy_bit(id);
 return id==165||!p||bit<0||!(p->disabled[bit/8]&(1u<<(bit%8)));
}
static inline void move_policy_set(move_policy_t *p,unsigned id,bool enabled) {
 int bit=move_policy_bit(id);if(!p||bit<0)return;
 if(enabled)p->disabled[bit/8]&=~(1u<<(bit%8));else p->disabled[bit/8]|=1u<<(bit%8);
}
static inline bool move_policy_valid(const move_policy_t *p) {return p && !(p->disabled[31]&0xf8);}
