#pragma once

// Serialize complete application records, including their final flush, across
// tasks. Never hold this guard while taking a world/save/LVGL lock.
#if defined(ESP_PLATFORM) && !defined(HOST_BUILD)
void console_record_init(void);
void console_record_begin(void);
void console_record_end(void);
#else
#include <stdio.h>
static inline void console_record_init(void) {}
static inline void console_record_begin(void) { flockfile(stdout); }
static inline void console_record_end(void) { funlockfile(stdout); }
#endif
