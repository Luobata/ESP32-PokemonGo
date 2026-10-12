// Frozen V5–V22 on-disk layouts. Never resize these when runtime capacity changes.
#pragma once
typedef struct {
    uint16_t version;

    // 养成（S4）
    nurture_t pet;

    // 主宠身份的兼容镜像；权威值来自下面队伍区的队首。
    uint16_t species;
    uint8_t level;
    uint32_t exp;

    // 队伍 6 格 + 仓库 151 格（V12起按实际格子保留同类），布局由 party.c 统一编解码。
    uint8_t party[LEGACY_PARTY_BYTES];

    // 遭遇队列（S1）与图鉴（S5/S8）
    enc_queue_t queue;
    dex_t dex;

    // 累积量：今日行程的来源、诊断用的扫描计数
    uint32_t motion_q10;
    uint32_t scans;

    // 上次存盘时的开机微秒数。**不是墙钟** —— 设备没有 RTC 对时。
    // 用途是算「关机了多久」：下次开机的 esp_timer 从 0 开始，
    // 所以只能知道「上次跑了多久」，不知道中间隔了多久。
    // 这正是 S4 的 on_reunion（「好久不见」）现在接不上的原因。
    int64_t last_uptime_us;

    // S16 开场只播一次。save.c 同时用独立的单调 NVS 键保存它，避免
    // world 生成整块快照时把这个页面侧字段清零。
    bool opening_seen;
} save_v5_t;

// The first 2296 bytes retain V5's exact layout, including tail padding. This
// makes migration a bounded prefix read; all new inventory fields are explicit.
typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    uint8_t party[LEGACY_PARTY_BYTES];
    enc_queue_t queue;
    dex_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    uint8_t legacy_padding[sizeof(save_v5_t) - offsetof(save_v5_t, opening_seen) - sizeof(bool)];
    inventory_t inventory;
} save_v6_t;

typedef struct {
    union {
        save_v6_t v6;
        struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    uint8_t party[LEGACY_PARTY_BYTES];
    enc_queue_t queue;
    dex_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    uint8_t legacy_padding[sizeof(save_v5_t) - offsetof(save_v5_t, opening_seen) - sizeof(bool)];
    inventory_t inventory;

        };
    };
    trainer_store_v8_t challenge;
} save_v7_t;

typedef struct {
    union {
        save_v7_t v7;
        struct {
    union {
        save_v6_t v6;
        struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    uint8_t party[LEGACY_PARTY_BYTES];
    enc_queue_t queue;
    dex_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    uint8_t legacy_padding[sizeof(save_v5_t) - offsetof(save_v5_t, opening_seen) - sizeof(bool)];
    inventory_t inventory;

        };
    };
    trainer_store_v8_t challenge;
        };
    };
    achievement_store_t achievements;
} save_v8_t;

// V9 keeps the established V6 party/inventory prefix, then the expanded combat state.
typedef struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;
} save_v9_t;
typedef struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;
} save_v10_t;
typedef struct {
 union {
  save_v10_t v10;
  struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;

  };
 };
 exploration_state_t exploration;
} save_v14_t;
typedef struct {
 union {
  save_v14_t v14;
  struct {
 union {
  save_v10_t v10;
  struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;

  };
 };
 exploration_state_t exploration;

  };
 };
 dungeon_progress_t dungeon;
} save_v15_t;
typedef struct {
 union {
  save_v14_t v14;
  struct {
 union {
  save_v10_t v10;
  struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;

  };
 };
 exploration_state_t exploration;

  };
 };
 dungeon_progress_t dungeon;
 uint8_t v15_padding[sizeof(save_v15_t)-offsetof(save_v15_t,dungeon)-sizeof(dungeon_progress_t)];
 exploration_updates_t exploration_updates;
} save_v16_t;
typedef struct {
 union {
  save_v14_t v14;
  struct {
 union {
  save_v10_t v10;
  struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;

  };
 };
 exploration_state_t exploration;

  };
 };
 dungeon_progress_t dungeon;
 uint8_t v15_padding[sizeof(save_v15_t)-offsetof(save_v15_t,dungeon)-sizeof(dungeon_progress_t)];
 exploration_updates_t exploration_updates;
 rest_clock_t rest_clock;
} save_v17_t;
typedef struct {
 union {
  save_v14_t v14;
  struct {
 union {
  save_v10_t v10;
  struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;

  };
 };
 exploration_state_t exploration;

  };
 };
 dungeon_progress_t dungeon;
 uint8_t v15_padding[sizeof(save_v15_t)-offsetof(save_v15_t,dungeon)-sizeof(dungeon_progress_t)];
 exploration_updates_t exploration_updates;
 rest_clock_t rest_clock;
 exploration_regions_t regions;
} save_v18_t;
typedef struct {
 union {
  save_v18_t v18;
  struct {
 union {
  save_v14_t v14;
  struct {
 union {
  save_v10_t v10;
  struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;

  };
 };
 exploration_state_t exploration;

  };
 };
 dungeon_progress_t dungeon;
 uint8_t v15_padding[sizeof(save_v15_t)-offsetof(save_v15_t,dungeon)-sizeof(dungeon_progress_t)];
 exploration_updates_t exploration_updates;
 rest_clock_t rest_clock;
 exploration_regions_t regions;
  };
 };
 uint32_t exploration_wins; // Only exploration wild victories; defeat resets.
} save_v19_t;
typedef struct {
 union {
  save_v19_t v19;
  struct {
 union {
  save_v18_t v18;
  struct {
 union {
  save_v14_t v14;
  struct {
 union {
  save_v10_t v10;
  struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;

  };
 };
 exploration_state_t exploration;

  };
 };
 dungeon_progress_t dungeon;
 uint8_t v15_padding[sizeof(save_v15_t)-offsetof(save_v15_t,dungeon)-sizeof(dungeon_progress_t)];
 exploration_updates_t exploration_updates;
 rest_clock_t rest_clock;
 exploration_regions_t regions;
  };
 };
 uint32_t exploration_wins; // Only exploration wild victories; defeat resets.
  };
 };
 uint32_t playtime_s; // Cumulative visible game time; no offline/screen-off time.
} save_v20_t;
typedef struct {
 union { save_v20_t v20; struct {
 union {
  save_v19_t v19;
  struct {
 union {
  save_v18_t v18;
  struct {
 union {
  save_v14_t v14;
  struct {
 union {
  save_v10_t v10;
  struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_store_t achievements;

  };
 };
 enc_refresh_state_t refresh;

  };
 };
 exploration_state_t exploration;

  };
 };
 dungeon_progress_t dungeon;
 uint8_t v15_padding[sizeof(save_v15_t)-offsetof(save_v15_t,dungeon)-sizeof(dungeon_progress_t)];
 exploration_updates_t exploration_updates;
 rest_clock_t rest_clock;
 exploration_regions_t regions;
  };
 };
 uint32_t exploration_wins; // Only exploration wild victories; defeat resets.
  };
 };
 uint32_t playtime_s; // Cumulative visible game time; no offline/screen-off time.
 }; };
 move_policy_t move_policies[157];
} save_v22_t;
typedef save_v22_t save_v21_t; // V22 keeps the decoded V21 layout; only storage changes.
_Static_assert(sizeof(save_v21_t)==7792,"Freeze V21 decoded world layout");
_Static_assert(sizeof(save_v20_t)==4024,"Freeze V20 world layout");
_Static_assert(offsetof(save_v22_t,move_policies)==sizeof(save_v20_t),"V21 preserves V20 including tail padding");
_Static_assert(sizeof(save_v19_t)==4016,"Freeze V19 world layout");
_Static_assert(offsetof(save_v22_t,playtime_s)==sizeof(save_v19_t),"V20 preserves all V19 bytes including tail padding");

_Static_assert(sizeof(save_v18_t)==4008,"Freeze V18 world layout");
_Static_assert(offsetof(save_v22_t,exploration_wins)==sizeof(save_v18_t),"V19 preserves all V18 bytes including tail padding");
_Static_assert(sizeof(save_v17_t)==3816,"Freeze V17 world layout");
_Static_assert(offsetof(save_v22_t,regions)==sizeof(save_v17_t),"V18 preserves V17 prefix");
_Static_assert(offsetof(save_v22_t,rest_clock)==sizeof(save_v16_t),"V17 preserves V16 prefix");
_Static_assert(offsetof(save_v22_t,exploration_updates)==sizeof(save_v15_t),"V16 preserves complete V15 prefix");
_Static_assert(sizeof(encounter_t)==16 && offsetof(encounter_t,ts)==4,"V16 uses legacy encounter padding");
_Static_assert(offsetof(save_v22_t,dungeon)==sizeof(save_v14_t),"V15 preserves complete V14 prefix");
_Static_assert(sizeof(save_v10_t)==3648,"V10 save layout changed");
_Static_assert(offsetof(save_v22_t,exploration)==sizeof(save_v10_t),"V11 preserves V10 prefix");
_Static_assert(sizeof(save_v9_t)==3104,"V9 save layout changed");
_Static_assert(offsetof(save_v22_t,refresh)==sizeof(save_v9_t),"V10 preserves V9 prefix");
_Static_assert(sizeof(save_v8_t)==2696,"V8 save layout changed");
_Static_assert(sizeof(save_v7_t) == 2688, "V7 save layout changed");
_Static_assert(offsetof(save_v8_t, achievements) == sizeof(save_v7_t), "V8 preserves V7 prefix");
_Static_assert(offsetof(save_v22_t, challenge) == sizeof(save_v6_t), "V7 preserves V6 prefix");
_Static_assert(sizeof(save_v5_t) == 2296, "legacy save layout changed");
_Static_assert(offsetof(save_v22_t, inventory) == sizeof(save_v5_t), "V6 must preserve the complete V5 prefix");
_Static_assert(offsetof(save_v22_t, opening_seen) == offsetof(save_v5_t, opening_seen), "V5 field offset changed");
