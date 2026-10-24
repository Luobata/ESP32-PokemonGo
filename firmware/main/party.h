#pragma once

#include <stdbool.h>
#include <stdint.h>
#include "move_policy.h"

#define PARTY_MAX     6
#define BOX_SPECIES 251
#define LEGACY_BOX_SPECIES 151
#define MON_BYTES    12
#define BOX_CAPACITY 753
#define LEGACY_PARTY_BYTES (2 + (PARTY_MAX + 151) * MON_BYTES)
#define PARTY_BYTES LEGACY_PARTY_BYTES // Historical codec only; V23 stores native members.

typedef struct {uint8_t species_id,level,hp,intimacy;uint16_t explore_value;uint8_t nickname_idx,flags;uint32_t exp;} mon_v27_t;
_Static_assert(sizeof(mon_v27_t)==12,"Historical individual");

typedef struct {
    uint8_t  species_id, level, hp, intimacy;
    uint16_t explore_value;
    uint8_t  nickname_idx, flags;   // flags bit0 = shiny
    uint32_t exp;
    // V28 explicit per-individual extension: Smeargle has four recorded moves;
    // other species use form / Hidden Power type (0 = deterministic legacy default).
    union { uint8_t sketch[4]; struct {uint8_t form,hp_type,reserved[2];} traits; } special;

} mon_t;

typedef struct {
    mon_t   party[PARTY_MAX];
    uint8_t party_count;
    mon_t   box[BOX_CAPACITY];       // physical slots; duplicates remain distinct after exchanges
    move_policy_t policies[PARTY_MAX + BOX_CAPACITY]; // follows physical individuals
} party_t;

void    party_init(party_t *p);
bool    party_better(const mon_t *a, const mon_t *b);
// Every capture is an individual. Full storage requires explicit replacement.
bool    party_can_receive(const party_t *p, uint16_t species);
bool    party_receive(party_t *p, const mon_t *m);
bool    party_set_leader(party_t *p, uint8_t index);
const mon_t *party_leader(const party_t *p);
uint16_t party_total(const party_t *p);
void    party_serialize(const party_t *p, uint8_t *out);
bool    party_deserialize(party_t *p, const uint8_t *in, uint16_t len);

// Swap into the vacated physical slot, preserving every individual.
int party_box_find(const party_t *p,uint16_t species);
int party_box_match(const party_t *p,const mon_t *mon);
bool party_exchange_at(party_t *p,uint8_t slot,uint16_t box_slot);
bool party_exchange(party_t *p,uint8_t slot,uint16_t species);
