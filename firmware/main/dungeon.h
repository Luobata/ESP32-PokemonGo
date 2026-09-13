#pragma once
#include <stddef.h>
#include "trainer.h"
#include "dungeon_rewards.h"
#include "world.h"
#include "nav.h"
enum {DUNGEON_EMPTY,DUNGEON_BATTLE,DUNGEON_REWARD,DUNGEON_FORK,DUNGEON_CAMP,DUNGEON_WON,DUNGEON_LOST,DUNGEON_SETTLEMENT,DUNGEON_ENTRY};
typedef struct {
 uint32_t version,seed,xp;
 trainer_store_t battle;
 uint16_t cards;
 uint8_t phase,node,ids[3],choices[3],wins,guards,berries,stone;
} dungeon_v1_t;
typedef struct {
 union {dungeon_v1_t v1;struct {
 uint32_t version,seed,xp;
 trainer_store_t battle;
 uint16_t cards;
 uint8_t phase,node,ids[3],choices[3],wins,guards,berries,stone;

 };};
 uint32_t run_id;
 inventory_t earned;
 dungeon_receipt_t receipt;
 uint8_t next_phase,pending,relay_mask;
} dungeon_v2_t;
// v3 uses owned party slots; battle attributes are snapshotted at admission.
typedef struct {
 union {dungeon_v2_t v2;struct {
  union {dungeon_v1_t v1;struct {
   uint32_t version,seed,xp;
   trainer_store_t battle;
   uint16_t cards;
   uint8_t phase,node,ids[3],choices[3],wins,guards,berries,stone;
  };};
  uint32_t run_id;
  inventory_t earned;
  dungeon_receipt_t receipt;
  uint8_t next_phase,pending,relay_mask;
 };};
 mon_t members[3];
 uint8_t slots[3],count,base_level;
} dungeon_t;
_Static_assert(offsetof(dungeon_t,members)==sizeof(dungeon_v2_t),"Preserve v2 dungeon prefix");
_Static_assert(offsetof(dungeon_t,run_id)==sizeof(dungeon_v1_t),"Preserve old dungeon save prefix");
#define DUNGEON_CARD_COUNT 15
extern const char *const dungeon_nodes[8];
extern const char *const dungeon_cards[DUNGEON_CARD_COUNT];
extern const char *const dungeon_desc[DUNGEON_CARD_COUNT];
void dungeon_load(void);
const dungeon_t *dungeon_get(void);
bool dungeon_new(const uint8_t slots[3],unsigned count,uint32_t seed);
bool dungeon_abandon(void);
bool dungeon_party_locked(void);
unsigned dungeon_recipients(uint32_t id,uint8_t slots[3]);
bool dungeon_choose(unsigned choice);
bool dungeon_finish(void);
bool dungeon_resume(void);
const char *dungeon_feedback(void);
bool dungeon_step(trainer_event_t *out);
bool dungeon_switch(unsigned slot,bool forced);
bool dungeon_retire(void);
void dungeon_snapshot(trainer_store_t *out,world_party_t *party);
bool dungeon_playing(void);
void dungeon_set_playing(bool playing);
void play_dungeon_enter(void);
void play_dungeon_exit(void);
bool play_dungeon_screen_busy(void);
void play_dungeon_key(bsp_btn_t b,bsp_btn_ev_t e);
