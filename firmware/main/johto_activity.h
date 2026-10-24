#pragma once
#include "trainer.h"
#include "johto.h"
#include "capture.h"
enum { ACT_NONE, ACT_BUG, ACT_SEA, ACT_ICE, ACT_TOWER };
enum { ACT_PATH, ACT_FIND, ACT_COMPARE, ACT_SETTLE, ACT_BATTLE, ACT_CAMP, ACT_RELAY, ACT_DEEP_PATH };
#define ACTIVITY_VERSION 1
#define ACTIVITY_BUG_NODES 6
#define ACTIVITY_BUG_TRIES 3
// V27 appends this independent activity record. Never change it without migration.
typedef struct {
 trainer_store_t battle;
 move_policy_t policies[3];
 mon_t members[3], found, candidate;
 inventory_t earned;
 uint32_t seed, xp, banked_xp;
 uint16_t observed;
 uint8_t kind,phase,node,attempts,slots[3],count,base_level,hard,path,banked,won;
} activity_run_t;
typedef struct {
 activity_run_t run;
 inventory_t pending;
 uint32_t runs;
 uint16_t bug_completed,bug_choices,sea_clears;
 uint8_t version,bug_first_silver,silver_feather,reserved;
} activity_store_t;
void activity_init(activity_store_t *);
bool activity_valid(const activity_store_t *);
bool activity_open(unsigned kind,const johto_state_t *);
bool activity_begin(activity_store_t *,unsigned kind,const mon_t *,const move_policy_t *,const uint8_t *,unsigned count,unsigned seed,bool hard);
unsigned activity_score(const activity_run_t *);
unsigned activity_observations(const activity_run_t *);
unsigned activity_rarity(unsigned species);
const char *activity_habitat(unsigned);
const char *activity_habitat_hint(unsigned);
bool activity_investigate(activity_run_t *,unsigned habitat);
bool activity_throw(activity_run_t *,unsigned ball,uint32_t elapsed,unsigned bonus,cap_result_t *);
bool activity_keep(activity_run_t *,bool replace);
bool activity_skip(activity_run_t *);
bool activity_sea_next(activity_run_t *,unsigned choice);
bool activity_finish_battle(activity_run_t *);
// Compute rewards before the same world transaction credits them and any EXP.
bool activity_bank(activity_store_t *);
bool activity_settle(activity_store_t *);

bool activity_expedition(unsigned);
const char *activity_name(unsigned);
unsigned activity_min_level(unsigned,bool);
unsigned activity_max_level(unsigned,bool);
