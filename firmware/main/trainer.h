#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "party.h"
#include "battle.h"
#include "combat.h"
#include "items.h"
#define TRAINER_COUNT 14
#define TRAINER_SLOTS 6
#define TRAINER_MOVES 4

typedef struct {
 const char *name, *badge;
 uint8_t species[6], levels[6], count, kind; // 0 gym,1 elite,2 champion,3 Red
} trainer_info_t;
const trainer_info_t *trainer_info(uint8_t id);
bool trainer_move(uint16_t id,move_t *out);
void trainer_art(uint8_t id,const uint8_t **data,uint16_t palette[4]);
const uint8_t *trainer_player_art(void);
const uint8_t *trainer_badge_art(uint8_t id);

typedef combat_mon_t trainer_mon_t;
typedef struct {
 trainer_mon_t mons[6];
 uint8_t count,active,reflect,light_screen;
} trainer_side_t;
typedef struct {
 trainer_side_t sides[2];
 uint32_t rng;
 uint16_t turns,ability;
 uint8_t trainer,active,finished,won,next,participated;
 uint8_t awaiting_replacement,retired,acted,pending_move;
 uint16_t planned[2];
} trainer_session_t;
typedef struct {
 uint16_t wild_wins,defeated; // stable trainer IDs; bits 0..7 are badges
 uint8_t league_stage,league_active;
 trainer_session_t session;
} trainer_store_t;
typedef enum {TRAINER_ATTACK,TRAINER_SENDOUT,TRAINER_SWITCH_NEEDED,TRAINER_FINISHED,TRAINER_STATUS} trainer_event_kind_t;
typedef struct {
 trainer_event_kind_t kind;
 battle_round_t attack;
 uint8_t side,slot,status;
 uint16_t before_hp[2];
} trainer_event_t;

bool trainer_unlocked(const trainer_store_t *store,uint8_t id);
bool trainer_begin(trainer_store_t *store,uint8_t id,const mon_t *party,uint8_t count,uint16_t ability,uint32_t seed);
bool trainer_step(trainer_store_t *store,trainer_event_t *event);
bool trainer_choose_move(trainer_store_t *store,uint8_t slot);
bool trainer_switch(trainer_store_t *store,uint8_t slot,bool forced);
void trainer_retire(trainer_store_t *store);
bool trainer_store_valid(const trainer_store_t *store);
uint16_t trainer_reward(const trainer_store_t *store);
// Mark progress exactly once in the same world transaction as EXP/items.
void trainer_settle(trainer_store_t *store);

bool trainer_rematch(const trainer_store_t *,uint8_t id);

uint8_t trainer_rematch_prize(const trainer_store_t *);

const char *trainer_victory_line(uint8_t trainer);
void trainer_grant_items(const trainer_store_t *store,inventory_t *bag);
