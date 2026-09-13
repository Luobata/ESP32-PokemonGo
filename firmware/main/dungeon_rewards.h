#pragma once
#include <stdint.h>
#include <stdbool.h>
#include "items.h"
#define DUNGEON_ENTRY_COST 20
// Stored atomically WITH party EXP and inventory in the world save.
typedef struct {uint32_t xp;inventory_t items;uint8_t first_clear,first_elite,full;} dungeon_receipt_t;
typedef struct {
 uint32_t run_id;
 uint16_t clears;
 uint8_t paid_nodes,last_node,elite_seen;
 dungeon_receipt_t receipt;
} dungeon_progress_t;
bool dungeon_progress_valid(const dungeon_progress_t *p);
void dungeon_reward_plan(unsigned node,uint32_t seed,const dungeon_progress_t *p,dungeon_receipt_t *out);
void world_dungeon_progress(dungeon_progress_t *out);
bool world_dungeon_ready(void);
bool world_dungeon_admit(uint32_t run_id);
bool world_dungeon_award(uint32_t run_id,unsigned node,uint32_t seed,dungeon_receipt_t *out);
