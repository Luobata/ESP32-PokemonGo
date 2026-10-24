#pragma once
#include "battle_fx.h"
#include "battle_presentation.h"
#include "gb_clock.h"
#include "gold_fx.h"

// Gold executes moveanim (including its after-animation), then applydamage,
// critical/effect text, and checkfaint. These stages must not overlap. Track
// samples remain 45 ms of source time; comfort playback stretches only motion.
enum { BATTLE_TIME_TEXT, BATTLE_TIME_MOVE, BATTLE_TIME_HIT,
       BATTLE_TIME_HP, BATTLE_TIME_FEEDBACK, BATTLE_TIME_FAINT, BATTLE_TIME_DONE };
typedef struct {
    uint32_t track_end, hit_start, hit_end, hp_start[2], hp_ms[2];
    uint32_t feedback_start, faint_start, end;
    uint16_t track_frames;
    uint8_t target, faint_mask;
    bool hit;
} battle_timing_t;

// Original battle HP bar: 48 source pixels, two VBlanks per changed pixel.
// Retain our 540 ms minimum for small changes on the larger portrait display.
static inline unsigned battle_timing_hp_ms(unsigned before, unsigned after,
                                           unsigned maximum)
{
    if (before == after || !maximum) return 0;
    unsigned a = (uint32_t)before * 48u / maximum;
    unsigned b = (uint32_t)after * 48u / maximum;
    unsigned ms = gb_frames_to_ms(2u * (a > b ? a - b : b - a));
    return battle_motion_ms(ms > 540u ? ms : 540u);
}

static inline battle_timing_t battle_timing_plan(const battle_round_t *r,
    const uint16_t before[2], const uint16_t after[2], const uint16_t maximum[2])
{
    battle_timing_t p = {0};
    p.target = r->by_pet ? 1 : 0;
    p.hit = r->damage && !r->missed && !r->no_effect && !r->self_target &&
            !r->charging && !r->skipped;
    p.track_frames = gold_fx_enabled(r) ? battle_fx_hit_frame(r) : battle_fx_frames(r) - 2u;
    p.track_end = BATTLE_FX_LEAD_MS + battle_motion_ms(p.track_frames * BATTLE_FX_TICK_MS);
    // Restore HUD: 1 + 4 frames. Enemy blink: 6 * (5+1) + ret + setup.
    // Player screen reaction: (40+1) + ret + setup. Revert + final wait: 4.
    p.hit_start = p.track_end + gb_frames_to_ms(5);
    p.hit_end = p.hit_start + (p.hit ? battle_motion_ms(gb_frames_to_ms(r->by_pet ? 38 : 43)) : 0);
    uint32_t cursor = p.hit_end + gb_frames_to_ms(4);
    // Drain/recoil/healing update their own bar AFTER the defender's bar.
    for (unsigned i = 0; i < 2; ++i) {
        unsigned side = p.target ^ i;
        p.hp_start[side] = cursor;
        p.hp_ms[side] = battle_timing_hp_ms(before[side], after[side], maximum[side]);
        cursor += p.hp_ms[side];
        if (before[side] && !after[side]) p.faint_mask |= 1u << side;
    }
    p.feedback_start = cursor;
    p.faint_start = cursor + BATTLE_PRESENTATION_TURN_PAUSE_MS;
    // Original faint drop is 7 rows * 2 frames; the next-mon handoff has a
    // 60-frame wait. Text holds remain explicit adaptations for automatic play.
    p.end = p.faint_start + (p.faint_mask ? battle_motion_ms(gb_frames_to_ms(14)) + gb_frames_to_ms(60) : 0);
    return p;
}

static inline unsigned battle_timing_phase(const battle_timing_t *p, uint32_t ms)
{
    if (ms < BATTLE_FX_LEAD_MS) return BATTLE_TIME_TEXT;
    if (ms < p->track_end) return BATTLE_TIME_MOVE;
    if (ms < p->hit_end) return BATTLE_TIME_HIT;
    if (ms < p->feedback_start) return BATTLE_TIME_HP;
    if (ms < p->faint_start) return BATTLE_TIME_FEEDBACK;
    return ms < p->end ? BATTLE_TIME_FAINT : BATTLE_TIME_DONE;
}

static inline unsigned battle_timing_hp_frame(const battle_timing_t *p,
                                               uint32_t ms, unsigned side)
{
    if (ms <= p->hp_start[side]) return 0;
    uint32_t elapsed = ms - p->hp_start[side];
    return elapsed >= p->hp_ms[side] ? BATTLE_PRESENTATION_HP_FRAMES :
        elapsed * BATTLE_PRESENTATION_HP_FRAMES / p->hp_ms[side];
}

static inline bool battle_timing_visible(const battle_timing_t *p,
                                         uint32_t ms, unsigned side)
{
    if ((p->faint_mask & (1u << side)) && ms >= p->faint_start + battle_motion_ms(gb_frames_to_ms(14))) return false;
    if (!p->hit || side != p->target || ms < p->hit_start || ms >= p->hit_end) return true;
    // Preserve the project's target-only flash for both directions. Gold's
    // player-side reaction is a screen shake; its duration is kept separately.
    unsigned frame = gb_frames_from_ms(battle_motion_source_ms(ms - p->hit_start));
    return frame >= 36 || ((frame / 6) & 1u);
}

// Drop seven source tile rows, holding each for two VBlanks. Render the top
// h-rows source rows at y+rows*scale; the sprite's original bottom is the clip.
static inline unsigned battle_timing_faint_rows(const battle_timing_t *p,
    uint32_t ms, unsigned side, unsigned height)
{
    if (!(p->faint_mask & (1u<<side)) || ms<p->faint_start) return 0;
    unsigned step=1u+gb_frames_from_ms(battle_motion_source_ms(ms-p->faint_start))/2u;
    return step>=7 ? height : step*height/7u;
}
