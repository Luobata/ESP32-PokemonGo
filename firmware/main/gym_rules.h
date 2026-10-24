#pragma once
#include "combat.h"
// V30 sidecar; never change the historical trainer_session_t layout.
enum { GYM_NONE, GYM_WIND, GYM_SWARM, GYM_CHEER, GYM_VEIL, GYM_FIST, GYM_ARMOR, GYM_COLD, GYM_DRAGON, GYM_ELM, GYM_LAKE };
typedef struct {
 uint16_t until, exposed;
 uint8_t entered, broken, hits, player, type, once;
} gym_member_t;
typedef struct {
 gym_member_t member[6];
 uint16_t round, pause_until, switch_after;
 uint8_t version, kind, stacks, switches;
} gym_rules_t;
struct trainer_session;
typedef struct { gym_rules_t *rules; struct trainer_session *session; unsigned side; } gym_context_t;
void gym_rules_begin(gym_rules_t *,struct trainer_session *,bool champion);
bool gym_rules_valid(const gym_rules_t *);
void gym_rules_enter(gym_rules_t *,struct trainer_session *);
void gym_rules_round(gym_rules_t *);
unsigned gym_rules_speed(const gym_rules_t *,unsigned side,unsigned speed);
combat_context_t gym_rules_context(gym_context_t *);
void gym_rules_after(gym_context_t *,const struct battle_round *,unsigned old_sub,int old_attack,int old_speed,unsigned old_status);
int gym_rules_switch(gym_rules_t *,const struct trainer_session *);
const char *gym_rules_name(unsigned kind);
const char *gym_rules_hint(unsigned kind);

const char *gym_rules_effect(unsigned kind);
