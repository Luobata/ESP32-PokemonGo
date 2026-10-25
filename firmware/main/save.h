#pragma once
#include <string.h>

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

#include "encounter.h"
#include "nurture.h"
#include "party.h"
#include "items.h"
#include "trainer.h"
#include "trainer_legacy.h"
#include "achievements.h"
#include "encounter_refresh.h"
#include "exploration.h"
#include "dungeon_rewards.h"
#include "rest_clock.h"
#include "johto.h"
#include "johto_activity.h"
#include "johto_story.h"
#include "endgame.h"
#include "narrative.h"
#include "field_adventure.h"

// 存档版本。**加字段时必须 +1** —— load 会拒绝不认识的版本，
// 那比读到错位的字段好（错位不报错，只是数值离谱）。
#define SAVE_VERSION 32 // Append-only radar/map circuits; all V31 bytes remain frozen.
#define SAVE_LEGACY_VERSION 5

typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    party_t members;
    enc_queue_t queue;
    dex_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    inventory_t inventory;
    trainer_store_t challenge;
    achievement_store_t achievements;
    enc_refresh_state_t refresh;
    exploration_state_t exploration;
    dungeon_progress_t dungeon;
    exploration_updates_t exploration_updates;
    rest_clock_t rest_clock;
    exploration_regions_t regions;
    uint32_t exploration_wins, playtime_s;
    johto_state_t johto;
    uint16_t research_rewards[5]; // Claimed repeat milestones, one per new evolution item.
    _Alignas(8) activity_store_t activities;
    _Alignas(8) johto_story_t story;
    _Alignas(8) endgame_t endgame;
    _Alignas(8) narrative_t narrative;
    _Alignas(8) field_state_t field;
} save_t;
// V26 appends five items, 32 achievement claims and research reward receipts.

#include "save_legacy.h"
_Static_assert(offsetof(save_t,story)>=sizeof(save_v28_t)-8,"V28 prefix must be preserved");


static inline void save_store_party(save_t *s,const party_t *p) {
    if (&s->members != p) s->members = *p;
}

// 初始化 NVS。**在任何 save_read/write 之前调**。
// 幂等，且不依赖 WiFi —— 见 save.c 里那段（这条依赖搞反过一次：
// NVS 初始化藏在 wifi_bring_up 里，而读档在起 WiFi 之前，
// 于是每次开机都读不到存档，而写入是成功的）。
bool save_init(void);

// 存。**会阻塞几毫秒**（flash 写），别在渲染循环里调。
// Storage/decoding share a bounded static RTC codec buffer: serialize with the world
// save lock. Boot reads run before tasks; import validation holds that same lock.
bool save_write(const save_t *s);

typedef enum {
    SAVE_READ_OK = 0,
    SAVE_READ_EMPTY,
    SAVE_READ_ERROR,
    SAVE_READ_MIGRATED, // Valid V5 decoded with its one-time initial inventory.
} save_read_result_t;

// Distinguish a genuinely absent save from unreadable/unsupported data. Only
// EMPTY permits new-game writes; ERROR must preserve the existing NVS bytes.
save_read_result_t save_read_status(save_t *out);
// Same bounded decoding/migration and world validation for startup and USB import.
// blob may alias out; unused bytes are zeroed before legacy migration.
save_read_result_t save_decode(save_t *out, const void *blob, size_t len, uint8_t opening_seen);
bool save_validate_world(const save_t *saved, party_t *party);

// Compatibility wrapper. false does not imply a new game; world uses status.
bool save_read(save_t *out);

// 清档（调试用）。
bool save_erase(void);

// 有没有存档 —— 开机时用它决定走「继续」还是「新游戏」。
bool save_exists(void);

// 开场标记只从 false 变 true；独立键让页面无需写整块世界存档。
bool save_opening_seen(void);
bool save_mark_opening_seen(void);

_Static_assert(offsetof(save_t,endgame)==sizeof(save_v29_t),"Preserve the complete V29 prefix");
_Static_assert(offsetof(save_t,narrative)==sizeof(save_v30_t),"Preserve the complete V30 prefix");
_Static_assert(offsetof(save_t,field)==sizeof(save_v31_t),"Preserve the complete V31 prefix");
_Static_assert(sizeof(save_t)==39976,"Version the field adventure world layout");
