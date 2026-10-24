#pragma once
#include <stdbool.h>
#include <stdint.h>

// Versioned chapter core. Mutate a transaction candidate and persist together
// with stamina, rewards and received individuals through world_johto.inc.
#define JOHTO_ROUTE_COUNT 8
#define JOHTO_GYM_COUNT 8
#define JOHTO_LEGEND_COUNT 6
#define JOHTO_EGG_STEPS 12
#define JOHTO_EGG_SHINY_DENOMINATOR 32
typedef enum { JOHTO_HIDDEN, JOHTO_INVITED, JOHTO_VOYAGE, JOHTO_ACTIVE, JOHTO_COMPLETE } johto_phase_t;
typedef enum { JOHTO_EGG_NONE, JOHTO_EGG_INCUBATING, JOHTO_EGG_READY } johto_egg_status_t;
typedef struct {
    uint32_t last_action, explorations, egg_seed, next_egg_at;
    uint16_t research[JOHTO_ROUTE_COUNT], eggs_hatched;
    uint8_t version, phase, starter, badges;
    uint8_t egg_status, egg_steps;
    uint8_t legend_clues[JOHTO_LEGEND_COUNT];
    uint8_t final_reward_claimed, reserved;
} johto_state_t;
_Static_assert(sizeof(johto_state_t)==48,"Version the candidate chapter before changing its layout");
typedef struct {
    const char *name, *activity;
    uint8_t badges, min_level, max_level;
    uint8_t species[12], count;
} johto_route_t;
typedef struct {
    const char *name, *badge, *opening, *ending;
    uint8_t species[6], levels[6], count;
} johto_trainer_t;
extern const johto_route_t JOHTO_ROUTES[JOHTO_ROUTE_COUNT];
extern const johto_trainer_t JOHTO_TRAINERS[JOHTO_GYM_COUNT+3];

void johto_init(johto_state_t *s);
bool johto_valid(const johto_state_t *s);
// Idempotent eligibility, including old 4/8-badge, Champion and Red saves.
bool johto_offer(johto_state_t *s, uint16_t kanto_defeated);
bool johto_depart(johto_state_t *s);
bool johto_choose_starter(johto_state_t *s, uint16_t species);
unsigned johto_badges(const johto_state_t *s);
bool johto_route_open(const johto_state_t *s, unsigned route);
uint8_t johto_route_level(unsigned route, unsigned player_level, uint32_t roll);
bool johto_gym_open(const johto_state_t *s, unsigned gym);
bool johto_gym_win(johto_state_t *s, unsigned gym);
// action is the globally increasing ID of a committed, stamina-paid action.
// Repeat/out-of-order callbacks and cancelled actions never advance research.
bool johto_explore(johto_state_t *s,unsigned route,uint32_t action,bool paid);
bool johto_receive_egg(johto_state_t *s,uint32_t seed);
bool johto_egg_shiny(const johto_state_t *s);
// Caller supplies true only after receiving the locked individual in the same
// candidate. Full warehouse/cancelled replacement keeps the ready egg intact.
bool johto_hatch(johto_state_t *s,bool received);
bool johto_legend_ready(const johto_state_t *s,unsigned legend);
bool johto_final_open(const johto_state_t *s,uint16_t kanto_defeated);
bool johto_final_win(johto_state_t *s,uint16_t kanto_defeated);
bool johto_claim_final(johto_state_t *s);

// Stable order matches items 19..23 and V26 reward receipts.
#define JOHTO_REWARD_COUNT 5
typedef struct { const char *source; uint8_t route,badges,step; } johto_research_reward_t;
extern const johto_research_reward_t JOHTO_REWARDS[JOHTO_REWARD_COUNT];
unsigned johto_reward_entitled(const johto_state_t *,unsigned reward);
