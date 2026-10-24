#pragma once
#include "activity_transactions.h"
enum { STORY_TOWER,STORY_RESCUE_BEGIN,STORY_RESCUE_CHOOSE,STORY_RESCUE_CLAIM,STORY_RUIN_CHOOSE,STORY_RUIN_BACK,STORY_RUIN_EXPLORE,STORY_PURIFY,STORY_ENDING,STORY_FINAL_PRIZE,STORY_LAKE_BEGIN,STORY_LAKE_CLUE,STORY_LAKE_SWITCH,STORY_LAKE_CLAIM };
typedef struct {uint32_t seed;mon_t expected;uint16_t box_slot;uint8_t op,choice,group;} story_request_t;
typedef struct {encounter_t encounter;mon_t partner;uint8_t received,item;} story_result_t;
activity_result_t story_apply(save_t *,const story_request_t *,story_result_t *);
