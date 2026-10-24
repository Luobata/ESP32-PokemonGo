#pragma once
#include <stdbool.h>
#include <stdint.h>

// Display callbacks sample time; they never manufacture animation ticks.
// Each scene starts AFTER its gameplay transaction. Frozen time is discarded,
// including the first callback after wake, instead of being caught up at once.
typedef struct {
    uint32_t last_ms, elapsed_ms;
    bool frozen;
} presentation_clock_t;

static inline void presentation_clock_start(presentation_clock_t *c, uint32_t now)
{
    *c = (presentation_clock_t){.last_ms = now};
}

static inline uint32_t presentation_clock_sample(presentation_clock_t *c,
                                                  uint32_t now, bool frozen)
{
    uint32_t delta = now - c->last_ms;
    c->last_ms = now;
    if (!frozen && !c->frozen) c->elapsed_ms += delta;
    c->frozen = frozen;
    return c->elapsed_ms;
}

static inline unsigned presentation_sample(uint32_t ms, unsigned quantum,
                                            unsigned last)
{
    unsigned frame = ms / quantum;
    return frame < last ? frame : last;
}
