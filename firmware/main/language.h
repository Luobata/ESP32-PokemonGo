#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef enum { LANGUAGE_ZH_HANS, LANGUAGE_ZH_HANT, LANGUAGE_EN, LANGUAGE_COUNT } language_t;
language_t language_get(void);
const char *language_label(void);
// Persistence lives outside the renderer. Runtime setter is also used by preview.
bool language_set_runtime(language_t language);
void language_settings_init(void);
bool language_settings_set(language_t language);

typedef struct {
    const char *source, *replacement;
    uint8_t remaining;
    bool traditional;
} language_reader_t;
language_reader_t language_reader(const char *text);
uint16_t language_next(language_reader_t *reader);
const uint8_t *language_glyph(uint16_t codepoint);
// Same-length BMP conversion; safe in-place, no heap or temporary text copy.
void language_convert_in_place(char *text);
// Returned translations live in Flash. A missing entry leaves the source intact.
const char *language_text(const char *text);
const char *language_text_n(const char *text, size_t bytes);
const char *language_species_name(uint16_t species);
const char *language_move_name(uint16_t move);
// UI printf subset: integers, chars, strings; literal widths <=40 and .* precision.
// String precision bounds the source name before translation. No floats or %n.
int language_snprintf(char *out, size_t size, const char *format, ...)
    __attribute__((format(printf, 3, 4)));
