#pragma once
#include <stdbool.h>

// Independent NVS preference: old game saves remain byte-compatible.
// A missing preference uses the public default; saved choices survive updates.
// Unreadable/invalid preferences stay quiet. A failed write keeps the old value.
#define AUDIO_MUTED_DEFAULT false
void audio_settings_init(void);
bool audio_settings_muted(void);
bool audio_settings_set_muted(bool muted);

#include <stdint.h>
#define AUDIO_VOLUME_DEFAULT 55
uint8_t audio_settings_volume(void);
bool audio_settings_set_volume(uint8_t percent);
