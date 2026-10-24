#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "encounter.h"
#include "items.h"
#include "johto.h"
#include "endgame.h"
#define ACHIEVEMENT_COUNT 43
// Append-only IDs: claimed bits remain stable across content updates.
typedef struct { uint16_t evolutions, cross_gen_evolutions; uint32_t claimed; } achievement_store_t;
typedef struct { const char *name, *description; uint8_t kind; uint16_t target; uint8_t item, quantity; } achievement_info_t;
typedef struct { achievement_store_t store; uint16_t caught, shiny, defeated, johto_caught, johto_shiny, sea_clears; uint8_t ruins, champion_gyms,champion_elm,lake_stage;uint16_t endgame_claimed; johto_state_t johto; } achievement_view_t;
// CAPPED is a successful claim: stock reaches its cap, excess is not added.
typedef enum { ACH_CLAIM_OK, ACH_CLAIM_LOCKED, ACH_CLAIM_ALREADY, ACH_CLAIM_CAPPED, ACH_CLAIM_FAILED, ACH_CLAIM_FULL } achievement_claim_t;
const achievement_info_t *achievement_info(unsigned id);
void achievement_view(achievement_view_t *out, const achievement_store_t *store, const dex_t *dex, uint16_t defeated);
unsigned achievement_progress(const achievement_view_t *view, unsigned id);
achievement_claim_t achievement_claim(achievement_store_t *store, inventory_t *inventory, const achievement_view_t *view, unsigned id);

static inline void achievement_endgame_view(achievement_view_t *v,const endgame_t *e){v->champion_gyms=e->champion_gyms;v->champion_elm=e->champion_elm;v->lake_stage=e->lake_stage;v->endgame_claimed=e->claimed;}
bool achievement_claimed(const achievement_view_t *,unsigned);
achievement_claim_t achievement_claim_extended(achievement_store_t *,endgame_t *,inventory_t *,const achievement_view_t *,unsigned);
