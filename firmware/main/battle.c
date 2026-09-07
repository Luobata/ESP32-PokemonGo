// main/battle.c —— S3 自动战斗。
//
// PC 侧是 sim/systems.py 的 auto_battle。这份移植有一处**刻意的偏离**：
// 随机源不同。
//
// ## 为什么不复刻 Python 的随机序列
//
// sim 用 `random.Random(seed)`，那是 Mersenne Twister ——
// 在 C 里重写要上百行状态机，且一处写错就全错（而「全错」表现为
// 「战斗结果不一样」，很难反查到是 PRNG）。
//
// 战斗的观感取决于**胜率分布**，不取决于第 7 场第 3 回合的伤害。
// 所以这里用 xorshift32，对账相应改成两层：
//   · 确定性部分逐值对账 —— 相克表、伤害公式、effective_stat、
//     wild_level。这是大头，82/225 个相克格子全部逐个比对
//   · 随机部分对统计分布 —— 1000 场胜率在容差内
// 见 tools/pipeline/verify_battle.py。
//
// ## 伤害公式的分母是 25 不是 50
//
// 初代原式 `((2*Lv/5+2) * Atk * Power / Def) / 50 + 2` 配合的是
// 原版的等级成长曲线。本项目主宠等级偏低而野怪种族值可能很高 ——
// 实测 Lv12 打 Lv10 鸭嘴火兽只有 3 伤害/回合，要 46 回合才打完。
// 压到 25 让战斗落在 4~8 回合，符合「30 秒会话」的预算，
// 也让 HP 条的逐步扣减看得出变化。（sim/systems.py:780 记的同一件事）

#include <string.h>

#include "battle.h"

// ---------------------------------------------------------------------------
// 属性相克
// ---------------------------------------------------------------------------

// 15×15 相克表，值 = 倍率 ×100。
//
// **这张表是从 sim/systems.py 机器生成的**，不是手抄：
//     python3 -c "...for a in TYPES: [effectiveness(a,[b]) for b in TYPES]"
// 手抄 82 个非 100 的格子必然出错，而错一格的表现是
// 「某个属性组合的伤害不对」—— 玩起来只觉得「怪」，查不到。
//
// 含 4 条**初代特有**差异（现代已改，见 docs/systems/S3-battle.md）：
//   幽灵→超能 0（著名 bug）　毒→虫 200　虫→毒 200　冰→火 100
// 它们在表里分别是 [13][10]、[7][11]、[11][7]、[5][1]。
static const uint8_t EFF[BATTLE_TYPE_COUNT][BATTLE_TYPE_COUNT] = {
//        一般 火  水  电  草  冰  格斗 毒 地面 飞行 超能 虫 岩石 幽灵 龙
/*一般*/ {100,100,100,100,100,100,100,100,100,100,100,100, 50,  0,100},
/*火  */ {100, 50, 50,100,200,200,100,100,100,100,100,200, 50,100, 50},
/*水  */ {100,200, 50,100, 50,100,100,100,200,100,100,100,200,100, 50},
/*电  */ {100,100,200, 50, 50,100,100,100,  0,200,100,100,100,100, 50},
/*草  */ {100, 50,200,100, 50,100,100, 50,200, 50,100, 50,200,100, 50},
/*冰  */ {100,100, 50,100,200, 50,100,100,200,200,100,100,100,100,200},
/*格斗*/ {200,100,100,100,100,200,100, 50,100, 50, 50, 50,200,  0,100},
/*毒  */ {100,100,100,100,200,100,100, 50, 50,100,100,200, 50, 50,100},
/*地面*/ {100,200,100,200, 50,100,100,200,100,  0,100, 50,200,100,100},
/*飞行*/ {100,100,100, 50,200,100,200,100,100,100,100,200, 50,100,100},
/*超能*/ {100,100,100,100,100,100,200,200,100,100, 50,100,100,100,100},
/*虫  */ {100, 50,100,100,200,100, 50,200,100, 50,200,100,100, 50,100},
/*岩石*/ {100,200,100,100,100,200, 50,100, 50,200,100,200,100,100,100},
/*幽灵*/ {  0,100,100,100,100,100,100,100,100,100,  0,100,100,200,100},
/*龙  */ {100,100,100,100,100,100,100,100,100,100,100,100,100,100,200},
};

#define STAB 150              // 本属性加成 ×1.5（初代原版就是这个数）
#define ACC_ALWAYS_HIT 255    // moves.bin 里 255 = 必中（高速星星）

uint16_t battle_effectiveness(uint8_t atk, uint8_t def1, uint8_t def2)
{
    if (atk >= BATTLE_TYPE_COUNT) return 100;
    uint16_t mult = 100;
    if (def1 < BATTLE_TYPE_COUNT) mult = mult * EFF[atk][def1] / 100;
    if (def2 < BATTLE_TYPE_COUNT) mult = mult * EFF[atk][def2] / 100;
    return mult;
}

const char *battle_eff_label(uint16_t mult)
{
    if (mult == 0) return "没有效果…";
    if (mult >= 200) return "效果绝佳！";
    if (mult <= 50) return "效果不好…";
    return NULL;              // 正常倍率**不提示**，见 battle.h
}

uint16_t battle_effective_stat(uint8_t base, uint8_t level)
{
    // sim: int(base * (1.0 + level / 50.0))
    // 整数版：base + base*level/50。C3 无 FPU，且这个函数每回合都调。
    //
    // 截断方向与 Python 的 int() 一致（都是向零截断，而两边都是正数）。
    uint32_t v = (uint32_t)base + (uint32_t)base * level / 50;
    return (uint16_t)(v < 1 ? 1 : v);
}

uint8_t battle_wild_level(uint8_t rarity)
{
    // 绝对等级带 —— **不跟主宠涨**。跟着涨的话主宠 Lv40 打 ★★ 照样输，
    // 练级毫无意义（S3 文档把这条列为实测暴露的平衡缺陷之一）。
    static const uint8_t BAND[6] = {12, 5, 12, 20, 30, 45};  // [0] 是兜底
    uint8_t band = (rarity <= 5) ? BAND[rarity] : 12;
    return band < 2 ? 2 : band;
}

// ---------------------------------------------------------------------------
// 随机源
// ---------------------------------------------------------------------------

// xorshift32 —— 8 行，状态一个 u32。
// 不用 rand()：newlib 的 rand 每次调用会取锁（可重入），在战斗循环里
// 调几百次不值当；而且它的序列不受我们控制，回放就无从谈起。
static uint32_t s_rng;

static uint32_t rng_next(void)
{
    uint32_t x = s_rng;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    s_rng = x;
    return x;
}

static uint32_t rng_below(uint32_t n)
{
    return n ? rng_next() % n : 0;
}

// ---------------------------------------------------------------------------
// 选招
// ---------------------------------------------------------------------------

// 权重 = 威力 × 相克 × 本属性加成。倍率 0 的招权重 0 ——
// AI 不会选一个必定打不中的招，除非它没有别的选择。
static uint32_t move_weight(const move_t *m, uint8_t atk_t1, uint8_t atk_t2,
                            uint8_t def1, uint8_t def2)
{
    uint16_t mult = battle_effectiveness(m->type, def1, def2);
    uint32_t w = (uint32_t)m->power * mult / 100;
    if (m->type == atk_t1 || m->type == atk_t2) w = w * STAB / 100;
    return w;
}

static const move_t *pick_move(const move_t *moves, int n,
                               uint8_t atk_t1, uint8_t atk_t2,
                               uint8_t def1, uint8_t def2)
{
    if (n <= 0) return NULL;
    uint32_t ws[8], total = 0;
    if (n > 8) n = 8;
    for (int i = 0; i < n; i++) {
        ws[i] = move_weight(&moves[i], atk_t1, atk_t2, def1, def2);
        total += ws[i];
    }
    // 全 0（比如只会一般系招的打幽灵）→ 等概率。总得出一招，哪怕打不中。
    if (total == 0) return &moves[rng_below((uint32_t)n)];

    uint32_t r = rng_below(total);
    for (int i = 0; i < n; i++) {
        if (r < ws[i]) return &moves[i];
        r -= ws[i];
    }
    return &moves[n - 1];
}

// ---------------------------------------------------------------------------
// 一次攻击
// ---------------------------------------------------------------------------

typedef struct {
    uint16_t hp, atk, def, spc, spd;
} stats_t;

static void load_stats(const species_t *sp, uint8_t lv, stats_t *out)
{
    out->hp  = battle_effective_stat(sp->hp, lv);
    out->atk = battle_effective_stat(sp->attack, lv);
    out->def = battle_effective_stat(sp->defense, lv);
    out->spc = battle_effective_stat(sp->special, lv);
    out->spd = battle_effective_stat(sp->speed, lv);
}

// 返回伤害；倍率、招名、是否未命中由出参带出。
static uint16_t do_hit(const species_t *atk_sp, const stats_t *a, uint8_t a_lv,
                       const species_t *def_sp, const stats_t *d,
                       const move_t *moves, int n_moves,
                       uint16_t factor_q10,
                       uint16_t *out_mult, const move_t **out_mv,
                       bool *out_miss)
{
    *out_mult = 100;
    *out_mv = NULL;
    *out_miss = false;

    const move_t *mv = pick_move(moves, n_moves, atk_sp->type1, atk_sp->type2,
                                 def_sp->type1, def_sp->type2);
    if (!mv) return 0;
    *out_mv = mv;

    if (mv->accuracy != ACC_ALWAYS_HIT && rng_below(100) >= mv->accuracy) {
        *out_miss = true;
        return 0;
    }

    uint16_t mult = battle_effectiveness(mv->type, def_sp->type1, def_sp->type2);
    *out_mult = mult;
    if (mult == 0) return 0;

    // 初代分物理/特殊：物理用 attack/defense，特殊用 special 双向。
    // 这是招式带来的新层次 —— 同样种族值，特攻高的用特殊招更疼。
    uint32_t A = mv->special ? a->spc : a->atk;
    uint32_t D = mv->special ? d->spc : d->def;
    if (D == 0) D = 1;

    // ability_factor 缩放有效 attack/special（消沉约 0.6，Q10 614）。
    // 与 sim 的施加位置一致：能力最低为 1，公式的 +2 不属于能力，不打折。
    // 614/1024 略小于 0.6，边界处仍可能与浮点参考相差一次取整。
    A = A * factor_q10 / 1024;
    if (A == 0) A = 1;

    // 分母 25（不是原版 50）—— 理由见文件头
    uint32_t base = (2u * a_lv / 5 + 2) * A * mv->power / D / 25 + 2;

    uint32_t stab = (mv->type == atk_sp->type1 || mv->type == atk_sp->type2)
                    ? STAB : 100;
    uint32_t dmg = base * mult / 100 * stab / 100;
    return (uint16_t)(dmg < 1 ? 1 : dmg);
}

// ---------------------------------------------------------------------------

void battle_run(uint16_t pet_species, uint8_t pet_level,
                uint16_t wild_species, uint8_t wild_level,
                uint16_t ability_factor_q10, uint32_t seed,
                battle_result_t *out)
{
    memset(out, 0, sizeof(*out));
    s_rng = seed ? seed : 1;      // xorshift32 的 0 是不动点，必须避开

    species_t pet_sp, wild_sp;
    if (!assets_species(pet_species, &pet_sp) ||
        !assets_species(wild_species, &wild_sp)) {
        return;
    }

    stats_t ps, ws;
    load_stats(&pet_sp, pet_level, &ps);
    load_stats(&wild_sp, wild_level, &ws);

    uint16_t p_hp_max = ps.hp * 2 + pet_level;
    uint16_t w_hp_max = ws.hp * 2 + wild_level;
    uint16_t p_hp = p_hp_max, w_hp = w_hp_max;
    out->pet_hp_max = p_hp_max;
    out->wild_hp_max = w_hp_max;

    // 各自会哪些招 —— **现算不存**（与 sim 的 known_moves 同取向，
    // 所以队伍里的 Mon 不用存招式列表，省 8 字节/只）
    move_t p_moves[8], w_moves[8];
    int p_n = assets_known_moves(pet_species, pet_level, p_moves, 8);
    int w_n = assets_known_moves(wild_species, wild_level, w_moves, 8);

    bool pet_first = ps.spd >= ws.spd;

    for (int r = 0; r < BATTLE_MAX_ROUNDS && out->round_count < BATTLE_MAX_ROUNDS; r++) {
        for (int k = 0; k < 2; k++) {
            bool by_pet = pet_first ? (k == 0) : (k == 1);
            if (p_hp == 0 || w_hp == 0) break;
            if (out->round_count >= BATTLE_MAX_ROUNDS) break;

            uint16_t mult;
            const move_t *mv;
            bool miss;
            uint16_t dmg;

            if (by_pet) {
                dmg = do_hit(&pet_sp, &ps, pet_level, &wild_sp, &ws,
                             p_moves, p_n, ability_factor_q10,
                             &mult, &mv, &miss);
                w_hp = (dmg >= w_hp) ? 0 : (uint16_t)(w_hp - dmg);
            } else {
                // 野怪没有消沉，factor 恒为 1.0
                dmg = do_hit(&wild_sp, &ws, wild_level, &pet_sp, &ps,
                             w_moves, w_n, 1024, &mult, &mv, &miss);
                p_hp = (dmg >= p_hp) ? 0 : (uint16_t)(p_hp - dmg);
            }

            battle_round_t *br = &out->rounds[out->round_count++];
            br->by_pet = by_pet;
            br->damage = dmg;
            br->mult = mult;
            br->pet_hp = p_hp;
            br->wild_hp = w_hp;
            br->move_zh = mv ? mv->name_zh : NULL;
            br->move_zh_len = mv ? mv->name_zh_len : 0;
            br->missed = miss;
        }
        if (p_hp == 0 || w_hp == 0) break;
    }

    out->won = (w_hp == 0 && p_hp > 0);

    // 野怪 HP 比例传给 S2 —— **不允许降到 0**，
    // 否则「打死了还能抓」不合逻辑。胜利时留 1% 表示濒死，
    // 那也正是捕获窗口最宽的状态。
    uint32_t ratio = w_hp_max ? (uint32_t)w_hp * 100 / w_hp_max : 100;
    out->wild_hp_ratio = (uint8_t)(ratio < 1 ? 1 : ratio);

    out->exp = (uint16_t)(wild_level * 8 + (out->won ? 20 : 0));
}
