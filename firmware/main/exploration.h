#pragma once
#include "encounter_refresh.h"
#include "items.h"
#define EXPLORATION_ROUTES 4
#define EXPLORATION_CAPACITY 24
#define EXPLORATION_CLUES 3

typedef struct {
 uint8_t route, energy, clues[EXPLORATION_ROUTES], pulse[EXPLORATION_ROUTES];
 uint8_t reserved[2];
 uint32_t steps;
} exploration_state_t;
static inline void exploration_init(exploration_state_t *s) {
 *s=(exploration_state_t){.energy=3};
}
static inline bool exploration_valid(const exploration_state_t *s) {
 if(s->route>=EXPLORATION_ROUTES||s->energy>EXPLORATION_CAPACITY)return false;
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
 EXPLORE_NO_ENERGY, EXPLORE_NO_STAMINA, EXPLORE_BLOCKED, EXPLORE_BUSY, EXPLORE_SAVE_FAILED } exploration_kind_t;
typedef struct {
 exploration_kind_t kind;
 uint16_t uid,species;
 uint8_t route,clues,rarity;
 bool shiny;
 uint8_t item,quantity;
 bool item_full;
} exploration_event_t;
typedef struct {
 exploration_state_t state;
 uint32_t discoveries;
 uint16_t defeated;
 uint8_t stamina,exp_percent,rare_bonus;
 uint8_t rare_left,elite_left,pending;
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
