#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "encounter.h"
#include "johto.h"
// V32: explicit append-only state. No AP names, MACs, coordinates or wall clock.
#define FIELD_MAP_COUNT 3
#define FIELD_RADAR 3
#define FIELD_COST 5
#define FIELD_RADAR_COOLDOWN 120
#define FIELD_MAP_COOLDOWN 180
typedef struct {
 uint32_t serial, radar_due, map_due[FIELD_MAP_COUNT];
 uint8_t visited[FIELD_MAP_COUNT],version;
 uint32_t radar_claims,map_claims;
} field_state_t;
_Static_assert(sizeof(field_state_t)==32,"Freeze V32 field record");
static inline bool field_state_valid(const field_state_t *s){
 if(!s->version){field_state_t zero={0};return !memcmp(s,&zero,sizeof(zero));}
 return s->version==1&&!(s->visited[0]&~7u)&&!(s->visited[1]&~7u)&&!(s->visited[2]&~7u);
}
static inline unsigned field_remaining(const field_state_t *s,unsigned mode,uint32_t now){uint32_t due=mode==FIELD_RADAR?s->radar_due:mode<FIELD_MAP_COUNT?s->map_due[mode]:0;return due>now?due-now:0;}
static inline unsigned field_shiny_denominator(unsigned mode){return mode==FIELD_RADAR?32:24;}
static inline unsigned field_map_badges(unsigned map){return map<FIELD_MAP_COUNT?(unsigned[]){3,2,4}[map]:99;}
static inline bool field_map_open(const johto_state_t *j,unsigned map){return map<FIELD_MAP_COUNT&&j->phase>=JOHTO_ACTIVE&&johto_badges(j)>=field_map_badges(map);}
typedef struct {
 field_state_t state;
 uint32_t online_s,scans;
 uint16_t place;
 uint8_t signals,open_maps,stamina,simulated;
} field_view_t;
enum { FIELD_OK,FIELD_LOCKED,FIELD_BUSY,FIELD_FULL,FIELD_NO_STAMINA,FIELD_SAVE_FAILED,FIELD_COOLDOWN,FIELD_NO_SIGNAL,FIELD_NEED_CLUES };
void world_field_snapshot(field_view_t *);
unsigned world_field_observe(unsigned map,unsigned point);
unsigned world_field_search(unsigned mode,encounter_t *out);
