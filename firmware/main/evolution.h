#pragma once

#include <stdbool.h>
#include <stdint.h>

#define EVO_TRIGGER_LEVEL 0
#define EVO_TRIGGER_ITEM  1
#define EVO_TRIGGER_TRADE 2
#define EVO_TRIGGER_NONE  0xFF

// Production natural evolution uses actual level; no nurture prerequisites.
bool evo_level_ready(uint8_t level, uint8_t trigger, uint16_t target, uint8_t required);

// Legacy simulator compatibility only.
// 已知简化：ITEM 当前与 LEVEL 共用默认的亲密度/探索值门槛。
// sim 侧还有 biome 驻留条件，但固件的 biome 判定尚未移植；在它可用前
// 不实现一条永久不可达的分支。补全时需要扩展本接口传入 biome/dwell。

typedef struct {
    bool     can;
    uint8_t  need_intimacy;
    uint16_t need_explore;
    uint8_t  cur_intimacy;
    uint16_t cur_explore;
} evo_check_t;

void evo_check(uint8_t intimacy_pct, uint16_t explore_value,
               uint8_t trigger, uint8_t evolve_to, uint8_t evolve_level,
               evo_check_t *out);

#define EVO_OPTION_MAX 5
// Pure branch catalogue. Base level evolution comes from the species asset.
typedef struct { uint8_t target,item,level,intimacy,badges; const char *training; } evo_option_t;
unsigned evo_options(uint16_t species,uint8_t trigger,uint16_t target,uint8_t level,evo_option_t out[EVO_OPTION_MAX]);
bool evo_option_ready(const evo_option_t *,unsigned level,unsigned intimacy,unsigned badges,unsigned quantity);
