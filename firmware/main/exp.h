#pragma once

#include <stdint.h>

#define LEVEL_MAX       100
#define EXP_ON_CAPTURE   60
#define EXP_ON_CARE      30
#define EXP_ON_MOTION     8

uint32_t exp_for_level(uint8_t n);
uint8_t exp_to_level(uint32_t exp, uint8_t cap);
void exp_progress(uint32_t exp, uint8_t level, uint32_t *got, uint32_t *need);
