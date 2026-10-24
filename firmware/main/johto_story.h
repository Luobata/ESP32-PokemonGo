#pragma once
#include "johto.h"
#include "party.h"
#include "encounter.h"
// Explicit V29 chapter record. IDs and receipts are append-only.
typedef struct {
 uint32_t forms_seen,forms_caught,rescue_seed,rescue_next;
 uint32_t legend_at[6];
 mon_t rescue_partner;
 uint16_t rescues;
 uint8_t version,ruins,ruin_group,ruin_step,ruin_misses[4];
 uint8_t rescue_step,tower_seen,legend_visits,forest_visits,ending_seen;
} johto_story_t;
void johto_story_init(johto_story_t *);
bool johto_story_valid(const johto_story_t *);
void johto_story_explore(johto_story_t *,johto_state_t *,unsigned route);
unsigned johto_rescue_at(const johto_story_t *);
bool johto_rescue_ready(const johto_story_t *,const johto_state_t *);
bool johto_rescue_begin(johto_story_t *,const johto_state_t *,uint32_t seed);
unsigned johto_rescue_answer(const johto_story_t *);
bool johto_rescue_choose(johto_story_t *,unsigned choice);
bool johto_rescue_claim(johto_story_t *,const johto_state_t *);
unsigned johto_ruin_answer(unsigned group,unsigned step);
bool johto_ruin_choose(johto_story_t *,const johto_state_t *,unsigned group,unsigned choice);
unsigned johto_ruin_form(johto_story_t *,unsigned group,uint32_t roll);
bool johto_story_legend_ready(const johto_story_t *,const johto_state_t *,unsigned legend,bool feather);
const char *johto_story_legend_hint(const johto_story_t *,const johto_state_t *,unsigned legend,bool feather);
bool johto_story_final_ready(const johto_story_t *,const johto_state_t *,uint16_t defeated,bool feather);
