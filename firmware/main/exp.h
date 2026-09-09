#pragma once

#include <stdint.h>
#include <stdbool.h>

#define LEVEL_MAX       100
#define EXP_ON_CAPTURE   60
#define EXP_ON_CARE      30
#define EXP_ON_MOTION     8

uint32_t exp_for_level(uint8_t n);
uint8_t exp_to_level(uint32_t exp, uint8_t cap);
void exp_progress(uint32_t exp, uint8_t level, uint32_t *got, uint32_t *need);

uint16_t exp_scaled(uint16_t base,uint8_t percent);

#include "party.h"
void exp_share_party(party_t *,unsigned eligible,uint16_t award);

uint16_t exp_battle_base(uint8_t level);
unsigned exp_party_percent(uint8_t level,uint8_t highest,bool participant);
void exp_award_party(party_t *,unsigned participants,unsigned eligible,uint16_t award);
