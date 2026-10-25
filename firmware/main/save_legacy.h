// Frozen V5–V22 on-disk layouts. Never resize these when runtime capacity changes.
#pragma once
typedef struct { uint16_t evolutions, claimed; } achievement_v25_t;
// Historical Pokedex bitmaps are always 151 bits (19 bytes each).
typedef struct { uint8_t seen[19],caught[19],shiny_seen[19],shiny_caught[19]; } dex_v23_t;
typedef struct { uint8_t disabled[24]; } move_policy_v23_t;
typedef struct {
    mon_v27_t party[6];
    uint8_t party_count;
    mon_v27_t box[453];
    move_policy_v23_t policies[459];
} party_v23_t;
_Static_assert(sizeof(party_v23_t)==16528,"V23 party layout is immutable");
typedef struct { uint8_t disabled[32]; } move_policy_v24_t;
typedef struct {
 mon_v27_t party[6]; uint8_t party_count; mon_v27_t box[453];
 move_policy_v24_t policies[459];
} party_v24_t;
_Static_assert(sizeof(party_v24_t)==20200,"V24 party layout is immutable");
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
    dex_v23_t dex;

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
    dex_v23_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    uint8_t legacy_padding[sizeof(save_v5_t) - offsetof(save_v5_t, opening_seen) - sizeof(bool)];
    inventory_v25_t inventory;
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
    dex_v23_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    uint8_t legacy_padding[sizeof(save_v5_t) - offsetof(save_v5_t, opening_seen) - sizeof(bool)];
    inventory_v25_t inventory;

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
    dex_v23_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    uint8_t legacy_padding[sizeof(save_v5_t) - offsetof(save_v5_t, opening_seen) - sizeof(bool)];
    inventory_v25_t inventory;

        };
    };
    trainer_store_v8_t challenge;
        };
    };
    achievement_v25_t achievements;
} save_v8_t;

// V9 keeps the established V6 party/inventory prefix, then the expanded combat state.
typedef struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;
} save_v9_t;
typedef struct {
 union {
  save_v9_t v9;
  struct {
 union {
  save_v6_t v6;
  struct {
   uint16_t version; nurture_t pet; uint16_t species; uint8_t level; uint32_t exp;
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
   uint8_t party[LEGACY_PARTY_BYTES]; enc_queue_t queue; dex_v23_t dex; uint32_t motion_q10,scans;
   int64_t last_uptime_us; bool opening_seen;
   uint8_t legacy_padding[sizeof(save_v5_t)-offsetof(save_v5_t,opening_seen)-sizeof(bool)];
   inventory_v25_t inventory;
  };
 };
 trainer_store_t challenge;
 achievement_v25_t achievements;

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
 move_policy_v23_t move_policies[157];
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

// Public V23 world layout, independent of the current policy stride.
typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    party_v23_t members;
    enc_queue_t queue;
    dex_v23_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    inventory_v25_t inventory;
    trainer_store_t challenge;
    achievement_v25_t achievements;
    enc_refresh_state_t refresh;
    exploration_state_t exploration;
    dungeon_progress_t dungeon;
    exploration_updates_t exploration_updates;
    rest_clock_t rest_clock;
    exploration_regions_t regions;
    uint32_t exploration_wins, playtime_s;
} save_v23_t;
_Static_assert(sizeof(save_v23_t)==18632,"Freeze the published V23 layout");

// Internal V24 development checkpoint; retain its fixed migration fixture.
typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    party_v24_t members;
    enc_queue_t queue;
    dex_v23_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    inventory_v25_t inventory;
    trainer_store_t challenge;
    achievement_v25_t achievements;
    enc_refresh_state_t refresh;
    exploration_state_t exploration;
    dungeon_progress_t dungeon;
    exploration_updates_t exploration_updates;
    rest_clock_t rest_clock;
    exploration_regions_t regions;
    uint32_t exploration_wins, playtime_s;
    johto_state_t johto;
} save_v24_t;
_Static_assert(sizeof(save_v24_t)==22352,"Freeze V24 layout");

// Frozen V25: 251-species dex and first playable Johto chapter.
typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    party_v24_t members;
    enc_queue_t queue;
    dex_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    inventory_v25_t inventory;
    trainer_store_t challenge;
    achievement_v25_t achievements;
    enc_refresh_state_t refresh;
    exploration_state_t exploration;
    dungeon_progress_t dungeon;
    exploration_updates_t exploration_updates;
    rest_clock_t rest_clock;
    exploration_regions_t regions;
    uint32_t exploration_wins, playtime_s;
    johto_state_t johto;
} save_v25_t;
_Static_assert(sizeof(save_v25_t)==22400,"Freeze V25 layout");

// Fixed V26 inventory, claims and research receipts.
typedef struct { uint16_t quantity[24]; } inventory_v26_t;
typedef struct {uint16_t evolutions,cross_gen_evolutions;uint32_t claimed;} achievement_v26_t;
typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    party_v24_t members;
    enc_queue_t queue;
    dex_t dex;
    uint32_t motion_q10, scans;
    int64_t last_uptime_us;
    bool opening_seen;
    inventory_v26_t inventory;
    trainer_store_t challenge;
    achievement_v26_t achievements;
    enc_refresh_state_t refresh;
    exploration_state_t exploration;
    dungeon_progress_t dungeon;
    exploration_updates_t exploration_updates;
    rest_clock_t rest_clock;
    exploration_regions_t regions;
    uint32_t exploration_wins, playtime_s;
    johto_state_t johto;
    uint16_t research_rewards[5]; // Claimed repeat milestones, one per new evolution item.
} save_v26_t;
_Static_assert(sizeof(save_v26_t)==22424,"Freeze V26 layout");

// V27 activity and world are frozen independently of current capacity/traits.
typedef struct {
 trainer_store_t battle; move_policy_v24_t policies[3];
 mon_v27_t members[3],found,candidate; inventory_v26_t earned;
 uint32_t seed,xp,banked_xp;uint16_t observed;
 uint8_t kind,phase,node,attempts,slots[3],count,base_level,hard,path,banked,won;
} activity_run_v27_t;
typedef struct {
 activity_run_v27_t run;inventory_v26_t pending;uint32_t runs;
 uint16_t bug_completed,bug_choices,sea_clears;
 uint8_t version,bug_first_silver,silver_feather,reserved;
} activity_v27_t;
_Static_assert(sizeof(activity_v27_t)==1056,"Freeze V27 activities");
typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    party_v24_t members;
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
    _Alignas(8) activity_v27_t activities;
} save_v27_t;

_Static_assert(sizeof(save_v27_t)==23480,"Freeze V27 world");

typedef struct {uint8_t species_id,level,hp,intimacy;uint16_t explore_value;uint8_t nickname_idx,flags;uint32_t exp;uint8_t special[4];} mon_v28_t;
typedef struct {mon_v28_t party[6];uint8_t party_count;mon_v28_t box[753];move_policy_t policies[759];} party_v28_t;
typedef struct {trainer_store_t battle;move_policy_t policies[3];mon_v28_t members[3],found,candidate;inventory_t earned;uint32_t seed,xp,banked_xp;uint16_t observed;uint8_t kind,phase,node,attempts,slots[3],count,base_level,hard,path,banked,won;} activity_run_v28_t;
typedef struct {activity_run_v28_t run;inventory_t pending;uint32_t runs;uint16_t bug_completed,bug_choices,sea_clears;uint8_t version,bug_first_silver,silver_feather,reserved;} activity_v28_t;
// Frozen V28 753-slot record; member extension semantics are explicit in party.h.
typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    party_v28_t members;
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
    _Alignas(8) activity_v28_t activities;
} save_v28_t;

_Static_assert(sizeof(save_v28_t)==39744,"Freeze V28 world");

// The V29 chapter tail is frozen independently of current story content.
typedef struct {
 uint32_t forms_seen,forms_caught,rescue_seed,rescue_next;
 uint32_t legend_at[6];
 mon_v28_t rescue_partner;
 uint16_t rescues;
 uint8_t version,ruins,ruin_group,ruin_step,ruin_misses[4];
 uint8_t rescue_step,tower_seen,legend_visits,forest_visits,ending_seen;
} story_v29_t;
typedef struct {
    uint16_t version;
    nurture_t pet;
    uint16_t species;
    uint8_t level;
    uint32_t exp;
    party_v28_t members;
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
    _Alignas(8) activity_v28_t activities;
    _Alignas(8) story_v29_t story;
} save_v29_t;
_Static_assert(sizeof(save_v29_t)==39816,"Freeze V29 world");

// Frozen V30 suffix. Do not alias future runtime champion/lake structures.
typedef struct {uint16_t until,exposed;uint8_t entered,broken,hits,player,type,once;} gym_member_v30_t;
typedef struct {gym_member_v30_t member[6];uint16_t round,pause_until,switch_after;uint8_t version,kind,stacks,switches;} gym_rules_v30_t;
typedef struct {gym_rules_v30_t battle;mon_v28_t lake_partner;uint16_t claimed;uint8_t version,champion_gyms,champion_elm,lake_stage,lake_level;} endgame_v30_t;
typedef struct {save_v29_t prefix;_Alignas(8) endgame_v30_t endgame;} save_v30_t;
_Static_assert(sizeof(save_v30_t)==39912,"Freeze V30 world");

// Frozen V31. Do not follow the running narrative or encounter types.
typedef struct { uint64_t seen; uint8_t pending[16]; uint16_t scene; uint8_t page,version,bug_evidence,legacy_final,focus,legend; } narrative_v31_t;
_Static_assert(sizeof(narrative_v31_t)==32,"Freeze V31 narrative");
typedef struct {save_v30_t prefix;_Alignas(8) narrative_v31_t narrative;} save_v31_t;
_Static_assert(sizeof(save_v31_t)==39944,"Freeze V31 world");
