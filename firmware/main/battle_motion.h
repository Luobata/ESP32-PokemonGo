#pragma once
#include <stdint.h>

// Deliberate comfort tempo: movement runs at 75% source speed. This is not
// the LCD refresh interval or the asset's authoring clock. Text/quiet holds,
// gameplay time and audio sample rates do not pass through this mapping.
static inline uint32_t battle_motion_ms(uint32_t source_ms)
{
    return source_ms + (source_ms + 2u) / 3u;
}

static inline uint32_t battle_motion_source_ms(uint32_t wall_ms)
{
    return (uint32_t)((uint64_t)wall_ms * 3u / 4u);
}

// Difference of cumulative samples preserves fractional time across callbacks.
static inline uint32_t battle_motion_delta(uint32_t before, uint32_t after)
{
    return battle_motion_source_ms(after) - battle_motion_source_ms(before);
}
