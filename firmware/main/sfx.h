#pragma once

#include "audio.h"

/* Codec output level. 80% is about -10 dB before the board gain correction;
 * the synthesized PCM keeps its separate 0.22 full-scale mix ceiling. */
#define SFX_VOLUME_PERCENT 80

/* Start the priority-5 playback task and prewarm the codec format at boot. */
void sfx_start(void);

/* Nonblocking: a full or unavailable queue drops the new request. */
void sfx_play(sfx_id_t id);
