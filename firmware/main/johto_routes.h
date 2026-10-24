#pragma once
#include "save.h"
#define JOHTO_PATH_COUNT 3
// UI/result only; no new persistent layout. Visits retain their historical meaning.
typedef struct {const char *name;uint8_t species[4];} johto_path_t;
typedef enum { JOHTO_SEARCH_CLUE, JOHTO_SEARCH_ENCOUNTER, JOHTO_SEARCH_TARGET } johto_search_kind_t;
typedef struct {encounter_t encounter;uint8_t kind,route,path,clues,target,item,quantity,item_full;} johto_search_t;
const johto_path_t *johto_path(unsigned route,unsigned path);
unsigned johto_track_clues(const johto_state_t *,unsigned route);
unsigned johto_track_target(const johto_state_t *,unsigned route);
// Mutates only the caller's locked transaction candidate. Publish after save succeeds.
bool johto_search_apply(save_t *,unsigned route,unsigned path,uint32_t seed,johto_search_t *);

// Fieldwork completes the existing ordered legend evidence; no new save bytes.
#define JOHTO_PROBE_COUNT 17
#define JOHTO_PROBE_NONE JOHTO_PROBE_COUNT
typedef struct {
 uint8_t legend,step,route,path,type1,type2;
 // Ability/environment hints only; concrete helper examples live in the guide.
 const char *title,*clue[2],*help,*observation,*action,*found,*next;
} johto_probe_t;
enum { PROBE_OK,PROBE_LOCKED,PROBE_WRONG_PATH,PROBE_WRONG_PARTNER,PROBE_NO_STAMINA };
const johto_probe_t *johto_probe(unsigned id);
bool johto_probe_available(const johto_state_t *,const johto_story_t *,bool feather,unsigned id);
unsigned johto_probe_next(const johto_state_t *,const johto_story_t *,bool feather,unsigned route,unsigned focus);
bool johto_probe_member(unsigned id,const mon_t *);
unsigned johto_probe_apply(save_t *,unsigned id,unsigned path,unsigned slot,const mon_t *expected);
