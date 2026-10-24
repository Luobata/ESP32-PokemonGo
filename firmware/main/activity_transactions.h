#pragma once
#include "save.h"
enum { ACTION_BEGIN, ACTION_SURVEY, ACTION_THROW, ACTION_KEEP, ACTION_SKIP, ACTION_END_SURVEY, ACTION_CAMP, ACTION_BANK, ACTION_CONTINUE, ACTION_PATH, ACTION_STEP, ACTION_SWITCH, ACTION_BATTLE_END, ACTION_RETIRE, ACTION_SETTLE, ACTION_CLAIM, ACTION_PRIZE };
typedef enum { ACT_OK, ACT_LOCKED, ACT_BUSY, ACT_STAMINA, ACT_FULL, ACT_SAVE_FAILED, ACT_STALE } activity_result_t;
typedef struct { uint32_t seed,elapsed; mon_t expected; uint16_t box_slot; uint8_t op,choice,count,slots[3],hard; } activity_request_t;
typedef struct { cap_result_t capture; trainer_event_t event; inventory_t rewards; uint32_t exp_gained; } activity_result_data_t;
activity_result_t activity_apply(save_t *,const activity_request_t *,activity_result_data_t *);
