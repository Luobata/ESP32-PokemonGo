#pragma once
#include "world.h"
void activity_battle_snapshot(trainer_store_t *,world_party_t *);
bool activity_battle_step(trainer_event_t *);
bool activity_battle_switch(unsigned,bool);
bool activity_battle_finish(void);
bool activity_battle_retire(void);
