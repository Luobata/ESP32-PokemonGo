#pragma once
#include <stdint.h>

// GBC: 154 scanlines * 456 clocks at 4,194,304 Hz, not exactly 60 Hz.
// Use elapsed time, never the LCD's frame rate, to sample source animations.
static inline uint32_t gb_frames_from_ms(uint32_t ms)
{
    return (uint32_t)((uint64_t)ms * 4194304u / (70224ull * 1000u));
}

static inline uint32_t gb_frames_to_ms(uint16_t frames)
{
    return (uint32_t)(((uint64_t)frames * 70224u * 1000u + 4194303u) / 4194304u);
}
