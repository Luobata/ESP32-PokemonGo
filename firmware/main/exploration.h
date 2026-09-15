#pragma once
#include "encounter_refresh.h"
#include "items.h"
#define EXPLORATION_ROUTES 4
#define EXPLORATION_CAPACITY 24
#define EXPLORATION_CLUES 3

typedef struct {
 // energy is a legacy V14 byte, retained only for save compatibility; ignored by gameplay.
 uint8_t route, energy, clues[EXPLORATION_ROUTES], pulse[EXPLORATION_ROUTES];
 uint8_t tracked_species, research_flags; // Low 4: claimed; high 4: target traced.
 uint32_t steps;
} exploration_state_t;
static inline void exploration_init(exploration_state_t *s) {
 *s=(exploration_state_t){.energy=0};
}
static inline bool exploration_valid(const exploration_state_t *s) {
 if(s->route>=EXPLORATION_ROUTES||s->energy>EXPLORATION_CAPACITY||s->tracked_species>151)return false;
 for(unsigned i=0;i<EXPLORATION_ROUTES;i++)if(s->clues[i]>3||s->pulse[i]>1)return false;
 return true;
}
typedef struct {
 const char *name,*description,*clue[3];
 uint16_t target;
 uint16_t color;
} exploration_route_t;
const exploration_route_t *exploration_route(unsigned id);
typedef enum { EXPLORE_NONE, EXPLORE_ENCOUNTER, EXPLORE_CLUE, EXPLORE_TARGET,
 EXPLORE_RESEARCH_LOCKED, EXPLORE_RESEARCH_CLAIMED, EXPLORE_NO_ENERGY, EXPLORE_NO_STAMINA, EXPLORE_BLOCKED, EXPLORE_BUSY, EXPLORE_SAVE_FAILED } exploration_kind_t;
typedef struct {
 exploration_kind_t kind;
 uint16_t uid,species;
 uint8_t route,clues,rarity,level;
 bool shiny;
 uint8_t item,quantity;
 bool item_full;
 uint16_t exp; // Actual leader gain after the durable discovery settlement.
} exploration_event_t;
// Separate save extension: never enlarge the V11-V15 exploration prefix.
#define EXPLORATION_ACTIVITIES 8
typedef struct {
 uint32_t rounds[4];
 uint8_t targets[4], chapters[4];
 uint8_t activity_progress[8], activity_claimed;
 uint16_t activity_runs[8];
 uint16_t activity_uid[8]; // Outstanding encounter or zero; stale queue entries are reconciled.
} exploration_updates_t;

typedef struct {
 exploration_state_t state;
 exploration_updates_t updates;
 uint32_t discoveries;
 uint16_t defeated;
 uint8_t stamina,exp_percent,rare_bonus,party_bonus;
 uint8_t rare_left,elite_left,pending;
 uint8_t research_seen,research_caught;
 uint16_t supply_q10; // Legacy diagnostic field; no longer a spendable resource.
} exploration_view_t;
// Candidate-only operation. Publish all state and the event after NVS commits.
exploration_event_t exploration_step(exploration_state_t *s,enc_refresh_state_t *r,
 enc_queue_t *q,dex_t *dex,uint16_t active_uid);

#define EXPLORATION_CHAPTERS 9
typedef struct {
 const char *name,*condition,*story,*discovery;
 uint8_t badges;
 uint16_t wins;
 uint16_t targets[4];
 uint8_t item;
} exploration_chapter_t;
const exploration_chapter_t *exploration_chapter(unsigned chapter);
bool exploration_chapter_open(unsigned chapter,uint16_t defeated);
unsigned exploration_chapter_current(uint16_t defeated);
uint16_t exploration_target(unsigned route,uint16_t defeated);
bool exploration_species_open(unsigned species,uint16_t defeated);
exploration_event_t exploration_step_progress(exploration_state_t*,enc_refresh_state_t*,enc_queue_t*,dex_t*,uint16_t,uint16_t,inventory_t*);

exploration_event_t exploration_step_nurtured(exploration_state_t*,enc_refresh_state_t*,enc_queue_t*,dex_t*,uint16_t,uint16_t,inventory_t*,const nurture_t*);

int exploration_habitat(unsigned species, unsigned *rarity);
unsigned exploration_unlock_chapter(unsigned species);
uint16_t exploration_focus(const exploration_state_t *,uint16_t defeated);
const char *exploration_story(unsigned species,unsigned clue);

exploration_event_t exploration_step_team(exploration_state_t*,enc_refresh_state_t*,enc_queue_t*,dex_t*,uint16_t,uint16_t,inventory_t*,const nurture_t*,unsigned);

#include "party.h"
unsigned exploration_team_bonus(const party_t *,unsigned route);

void exploration_research_progress(unsigned route,const dex_t *,uint8_t *seen,uint8_t *caught);
exploration_kind_t exploration_research_claim(exploration_state_t *,const dex_t *,unsigned route);

// Snapshot sync is pure on the caller's copy; world persists it with the next action.
void exploration_targets_sync(exploration_state_t *,exploration_updates_t *,const dex_t *,const enc_queue_t *,uint16_t);
uint16_t exploration_current_target(const exploration_state_t *,const exploration_updates_t *,uint16_t);
void exploration_target_completed(exploration_state_t *,exploration_updates_t *,const dex_t *,const enc_queue_t *,uint16_t,unsigned);
bool exploration_updates_valid(const exploration_updates_t *);
typedef struct {
 const char *name,*story;
 uint8_t route,level,item,species[8];
} exploration_activity_t;
const exploration_activity_t *exploration_activity(unsigned);
bool exploration_activity_open(unsigned,uint16_t);
exploration_event_t exploration_activity_spawn(unsigned,exploration_updates_t *,enc_queue_t *,dex_t *,uint16_t,uint32_t,uint16_t);
void exploration_activity_credit(exploration_updates_t *,const encounter_t *);
exploration_kind_t exploration_activity_claim(unsigned,exploration_updates_t *,inventory_t *,exploration_event_t *);

exploration_event_t exploration_step_with_target(exploration_state_t*,enc_refresh_state_t*,enc_queue_t*,dex_t*,uint16_t,uint16_t,inventory_t*,const nurture_t*,unsigned,unsigned);
