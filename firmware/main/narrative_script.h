#pragma once
#include "narrative.h"
enum { N_ART_PERSON,N_ART_FOREST,N_ART_RUINS,N_ART_TOWER,N_ART_SEA,N_ART_MON,N_ART_JOURNEY };
#define N_ACTOR_OAK (-1)
typedef struct {int16_t actor;uint16_t species;uint8_t art;const char *speaker,*line[3];} narrative_page_t;
typedef struct {const char *title;narrative_page_t page[3];const char *choice[3],*hint;uint8_t choices;} narrative_script_t;
const narrative_script_t *narrative_script(unsigned scene);
