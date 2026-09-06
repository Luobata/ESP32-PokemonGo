#include "exp.h"

uint32_t exp_for_level(uint8_t n)
{
    if (n <= 1) return 0;
    return 5u * n * n * n / 2u;
}

uint8_t exp_to_level(uint32_t exp, uint8_t cap)
{
    uint8_t level = 1;
    while (level < cap && exp >= exp_for_level((uint8_t)(level + 1))) {
        level++;
    }
    return level;
}

void exp_progress(uint32_t exp, uint8_t level, uint32_t *got, uint32_t *need)
{
    uint32_t lo = exp_for_level(level);
    uint32_t hi = exp_for_level((uint8_t)(level + 1));

    *got = exp > lo ? exp - lo : 0;
    *need = hi > lo ? hi - lo : 1;
}
