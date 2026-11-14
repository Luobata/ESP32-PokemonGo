#include "language.h"
#include "render.h"
#include <stdatomic.h>
#include <stddef.h>
#include <string.h>
#include "language_data.h"
#include "language_glyphs.h"
#include "language_english.h"
#include "language_latin.h"

static atomic_uchar current_language;
language_t language_get(void) { return atomic_load(&current_language); }
bool language_set_runtime(language_t language) {
    if ((unsigned)language >= LANGUAGE_COUNT) return false;
    atomic_store(&current_language, language); return true;
}
const char *language_label(void) {
    switch (language_get()) {
    case LANGUAGE_ZH_HANT: return "繁體中文";
    case LANGUAGE_EN: return "English";
    default: return "简体中文";
    }
}
language_reader_t language_reader(const char *text) {
    return (language_reader_t){.source=language_text(text), .traditional=language_get()==LANGUAGE_ZH_HANT};
}
const char *language_text_n(const char *text, size_t bytes) {
    if (!text || language_get()!=LANGUAGE_EN || !bytes) return text;
    uint32_t hash=2166136261u,check=5381u;bool non_ascii=false;
    for(size_t i=0;i<bytes;i++) {
        uint8_t c=(uint8_t)text[i];hash=(hash^c)*16777619u;check=check*33u+c;
        non_ascii|=c>=128;
    }
    if(!non_ascii)return text;
    check=(check^((uint32_t)bytes*2654435761u))&0xffffu;
    unsigned lo=0,hi=sizeof(language_english)/sizeof(*language_english);
    while(lo<hi) {unsigned mid=(lo+hi)/2;if(language_english[mid].hash<hash)lo=mid+1;else hi=mid;}
    for(;lo<sizeof(language_english)/sizeof(*language_english)&&language_english[lo].hash==hash;lo++) {
        if(language_english[lo].check==check)return language_english_pool+language_english[lo].offset;
    }
    return text;
}
const char *language_text(const char *text) {
    return text && language_get()==LANGUAGE_EN ? language_text_n(text,strlen(text)) : text;
}
const char *language_species_name(uint16_t species) {
    return language_get()==LANGUAGE_EN && species>0 && species<252 ? language_english_species[species] : NULL;
}
const char *language_move_name(uint16_t move) {
    return language_get()==LANGUAGE_EN && move>0 && move<252 ? language_english_moves[move] : NULL;
}
uint16_t language_next(language_reader_t *r) {
    if (!r || !r->source || !*r->source) return 0;
    uint16_t cp; unsigned bytes=render_utf8_next(r->source,&cp);
    if (!r->traditional || (cp<0x3400 && !r->remaining)) { r->source+=bytes; return cp; }
    if (!r->remaining) {
        unsigned lo=0,hi=sizeof(language_phrase_groups)/sizeof(*language_phrase_groups);
        while (lo<hi) {
            unsigned mid=(lo+hi)/2;
            if (language_phrase_groups[mid].first<cp) lo=mid+1; else hi=mid;
        }
        if (lo<sizeof(language_phrase_groups)/sizeof(*language_phrase_groups) && language_phrase_groups[lo].first==cp) {
            unsigned end=language_phrase_groups[lo].start+language_phrase_groups[lo].count;
            for (unsigned i=language_phrase_groups[lo].start;i<end;i++) {
                if (!strncmp(r->source,language_phrases[i].from,language_phrases[i].bytes)) {
                    r->replacement=language_phrases[i].to;r->remaining=language_phrases[i].bytes;break;
                }
            }
        }
    }
    if (r->remaining) {
        unsigned used=render_utf8_next(r->replacement,&cp);
        r->replacement+=used;r->remaining-=used;
    } else {
        unsigned lo=0,hi=sizeof(language_chars)/sizeof(*language_chars);
        while(lo<hi) { unsigned mid=(lo+hi)/2;if(language_chars[mid].from<cp)lo=mid+1;else hi=mid; }
        if(lo<sizeof(language_chars)/sizeof(*language_chars)&&language_chars[lo].from==cp)cp=language_chars[lo].to;
    }
    r->source+=bytes;return cp;
}
const uint8_t *language_glyph(uint16_t cp) {
    if(language_get()==LANGUAGE_EN && cp>=32 && cp<127)return language_latin_pixels[cp-32];
    if(language_get()!=LANGUAGE_ZH_HANT || cp<0x3400) return NULL;
    unsigned lo=0,hi=sizeof(language_glyph_codes)/sizeof(*language_glyph_codes);
    while(lo<hi) { unsigned mid=(lo+hi)/2;if(language_glyph_codes[mid]<cp)lo=mid+1;else hi=mid; }
    return lo<sizeof(language_glyph_codes)/sizeof(*language_glyph_codes)&&language_glyph_codes[lo]==cp?language_glyph_pixels[lo]:NULL;
}
void language_convert_in_place(char *text) {
    language_reader_t r=language_reader(text);char *out=text;
    if(!r.traditional || !text)return;
    while(*r.source) {
        uint16_t cp=language_next(&r);
        if(cp<0x80)*out++=cp;
        else if(cp<0x800){*out++=0xc0|(cp>>6);*out++=0x80|(cp&63);}
        else{*out++=0xe0|(cp>>12);*out++=0x80|((cp>>6)&63);*out++=0x80|(cp&63);}
    }
    *out=0;
}
