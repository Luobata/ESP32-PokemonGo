// main/encounter.c —— S1 遭遇 + S5 图鉴 + S8 闪光。
//
// PC 侧 sim/systems.py + sim/state.py。整块确定性，逐值对账
// （tools/pipeline/verify_encounter.py）。
//
// ## 为什么种子是 crc32(bssid|小时) 而不是随机数
//
// 确定性刷新是设计要求（docs/03-spawning.md#36），不是实现偷懒：
// 两人站一起看到同一批怪、社区能做「这个 AP 下午三点出火系」的攻略、
// 不用存刷新表随时能重算。用随机数这三条全没了。
//
// ## 字符串拼接必须与 PC 侧逐字节一致
//
// PC 侧算的是 `f"{bssid}|{ts//3600}"` 的 UTF-8 字节，
// 其中 bssid 是 "aa:bb:cc:dd:ee:ff" 这种小写冒号分隔的**字符串**，
// 不是 6 字节原始数组。这里必须先格式化再算 crc ——
// 直接对 6 字节算会得到完全不同的值，而且两边都「能跑」，
// 只是刷出来的怪不一样（sensing.c 的 hash_bssid 踩过同一个坑）。

#include <stdio.h>
#include <string.h>

#include "encounter.h"
#include "assets.h"

#ifdef HOST_BUILD
#include <zlib.h>
#define CRC32(buf, len) ((uint32_t)crc32(0UL, (const unsigned char *)(buf), (len)))
#else
#include "esp_rom_crc.h"
#define CRC32(buf, len) esp_rom_crc32_le(0U, (const uint8_t *)(buf), (len))
#endif

#define TIME_BUCKET 3600      // 一小时一换
#define SHINY_DENOM 512       // 1/512，不是原版 1/8192 —— 见下

// 强度档：种族值总和的区间。实测 151 只的分布是
// 最低 175（绿毛虫）中位 345 最高 590（超梦），四分位 275/345/420。
// 各档物种数 18/46/37/42/8，都不为空。
static const uint16_t TIER_LO[5] = {0, 250, 320, 400, 480};
static const uint16_t TIER_HI[5] = {250, 320, 400, 480, 9999};

// 把 6 字节 BSSID 写成 PC 侧那种小写冒号分隔的 17 字符串。
static int fmt_bssid(const uint8_t b[6], char *out)
{
    return snprintf(out, 18, "%02x:%02x:%02x:%02x:%02x:%02x",
                    b[0], b[1], b[2], b[3], b[4], b[5]);
}

uint32_t enc_spawn_seed(const uint8_t bssid[6], uint32_t ts)
{
    char key[48];
    char mac[18];
    fmt_bssid(bssid, mac);
    int n = snprintf(key, sizeof(key), "%s|%u", mac,
                     (unsigned)(ts / TIME_BUCKET));
    return CRC32(key, (size_t)n);
}

bool enc_roll_shiny(const uint8_t bssid[6], uint32_t ts, uint8_t rarity)
{
    // 独立 salt 而非复用 spawn_seed 的低位 —— 否则闪光判定与种类判定
    // 相关，某些种类会**永远不闪光**（那种 bug 要玩几个月才发现）。
    //
    // 1/512 而非原版 1/8192：原版一天遇几百只，本项目一天 10~30 次，
    // 8192 意味着平均一年才见一只。
    char key[64];
    char mac[18];
    fmt_bssid(bssid, mac);
    int n = snprintf(key, sizeof(key), "%s|%u|shiny", mac,
                     (unsigned)(ts / TIME_BUCKET));
    uint32_t denom = (rarity >= 5) ? (SHINY_DENOM / 2) : SHINY_DENOM;
    return (CRC32(key, (size_t)n) % denom) == 0;
}

uint8_t enc_rarity_from_ap(int8_t rssi, uint8_t auth, bool has_ssid,
                           bool is_transient)
{
    // 稀有度直接挂在 AP 属性上（docs/03-spawning.md#31）：
    // 信号弱、隐藏 SSID、企业级加密、转瞬即逝 —— 天然就是稀有刷新点。
    uint8_t r = 1;
    if (rssi < -80) r++;
    if (!has_ssid) r++;
    // 企业级：wifi_auth_mode_t 里 WPA2_ENTERPRISE=5、WPA3_ENTERPRISE=8
    if (auth == 5 || auth == 8) r++;
    if (is_transient) r++;
    return r > 5 ? 5 : r;
}

uint16_t enc_pick_species(const uint8_t bssid[6], uint32_t ts, uint8_t rarity)
{
    // 按稀有度取物种池，**不是均匀采样 151 只**。
    //
    // 均匀采样的后果是实测出来的：Lv12 的初期主宠会遇到鸭嘴火兽
    // （种族值 395）甚至超梦，打 46 回合都赢不了。
    // 原版靠「不同区域不同等级带」解决，本项目没有地图，
    // 改用 AP 稀有度决定物种池 —— 稀有 AP 才出强种。
    uint8_t idx = (rarity >= 1 && rarity <= 5) ? (uint8_t)(rarity - 1) : 0;
    uint16_t lo = TIER_LO[idx], hi = TIER_HI[idx];

    // 先数池子大小，再取第 k 只。**两趟扫描而不是先收集到数组** ——
    // 数组要 151×2 字节，而这个函数每次遭遇才调一次，两趟不值一提。
    uint16_t n = 0;
    uint32_t total = assets_species_count();
    species_t sp;
    for (uint16_t id = 1; id <= total; id++) {
        if (!assets_species(id, &sp)) continue;
        uint16_t sum = (uint16_t)sp.hp + sp.attack + sp.defense
                     + sp.special + sp.speed;
        if (sum >= lo && sum < hi) n++;
    }
    if (n == 0) {
        // 池空则退回全表（与 sim 的 `pool or list(...)` 同）
        uint32_t seed = enc_spawn_seed(bssid, ts);
        return (uint16_t)((seed >> 8) % (total ? total : 1) + 1);
    }

    uint32_t seed = enc_spawn_seed(bssid, ts);
    uint16_t k = (uint16_t)((seed >> 8) % n);
    for (uint16_t id = 1; id <= total; id++) {
        if (!assets_species(id, &sp)) continue;
        uint16_t sum = (uint16_t)sp.hp + sp.attack + sp.defense
                     + sp.special + sp.speed;
        if (sum >= lo && sum < hi) {
            if (k == 0) return id;
            k--;
        }
    }
    return 1;
}

// ---------------------------------------------------------------------------
// 队列
// ---------------------------------------------------------------------------

void enc_queue_init(enc_queue_t *q)
{
    memset(q, 0, sizeof(*q));
    q->next_uid = 1;          // 0 留作「无效/未选中」
}

encounter_t *enc_queue_find(enc_queue_t *q, uint16_t uid)
{
    if (!uid) return NULL;
    for (uint8_t i = 0; i < q->count; i++) {
        if (q->items[i].uid == uid) return &q->items[i];
    }
    return NULL;
}

bool enc_queue_take_uid(enc_queue_t *q, uint16_t uid, encounter_t *out)
{
    if (!uid) return false;
    for (uint8_t i = 0; i < q->count; i++) {
        if (q->items[i].uid != uid) continue;
        return enc_queue_take(q, i, out);
    }
    return false;             // 已被后台淘汰 —— 正常，不是错误
}

bool enc_queue_push(enc_queue_t *q, const encounter_t *e)
{
    // 发号在入队时做，调用方不用管 uid。
    // 回绕：u16 到 65535 后回到 1 —— 一天几十条，回绕要几年，
    // 且真回绕了最坏是「跨页面选中的那条找不到」，会被当成已淘汰处理。
    if (q->next_uid == 0) q->next_uid = 1;
    uint16_t uid = q->next_uid++;

    if (q->count < ENC_QUEUE_CAP) {
        q->items[q->count] = *e;
        q->items[q->count].uid = uid;
        q->items[q->count].exp_granted = false;
        q->count++;
        return false;
    }

    // 满了 —— 找**最低稀有度里最旧的**那条挤掉。
    //
    // 不是单纯丢最旧：玩家一天可能遇 30 次而只处理 10 次，
    // 单纯 FIFO 会让攒到的稀有个体被后来的常见个体挤掉，
    // 与「稀有度驱动收集」直接矛盾。
    //
    // **新来的也参与比较**（sim 那边是先 append 再找最低，
    // 等价于把新条目算进候选）—— 所以一条比池子里全部都差的遭遇
    // 会当场被丢掉，而不是挤走一条更好的。实测对齐过 sim 的行为。
    uint8_t min_r = e->rarity;
    for (uint8_t i = 0; i < q->count; i++) {
        if (q->items[i].rarity < min_r) min_r = q->items[i].rarity;
    }
    q->dropped++;

    // 新来的就是最差的（且队列里没有同样差的）→ 直接不收
    if (e->rarity == min_r) {
        bool tie = false;
        for (uint8_t i = 0; i < q->count; i++) {
            if (q->items[i].rarity == min_r) { tie = true; break; }
        }
        if (!tie) return true;
    }

    // 数组按入队顺序排，所以第一个命中最低稀有度的就是最旧的那条
    for (uint8_t i = 0; i < q->count; i++) {
        if (q->items[i].rarity != min_r) continue;
        for (uint8_t k = i; k + 1 < q->count; k++) q->items[k] = q->items[k + 1];
        q->items[q->count - 1] = *e;
        q->items[q->count - 1].uid = uid;
        q->items[q->count - 1].exp_granted = false;
        return true;
    }
    return true;
}

bool enc_queue_take(enc_queue_t *q, uint8_t index, encounter_t *out)
{
    if (index >= q->count) return false;
    if (out) *out = q->items[index];
    for (uint8_t k = index; k + 1 < q->count; k++) q->items[k] = q->items[k + 1];
    q->count--;
    return true;
}

// ---------------------------------------------------------------------------
// 图鉴
// ---------------------------------------------------------------------------

static void bit_set(uint8_t *bm, uint16_t sid)
{
    if (sid < 1 || sid > DEX_SPECIES) return;
    uint16_t i = (uint16_t)(sid - 1);
    bm[i >> 3] |= (uint8_t)(1u << (i & 7));
}

static bool bit_get(const uint8_t *bm, uint16_t sid)
{
    if (sid < 1 || sid > DEX_SPECIES) return false;
    uint16_t i = (uint16_t)(sid - 1);
    return (bm[i >> 3] >> (i & 7)) & 1;
}

static uint16_t bit_count(const uint8_t *bm)
{
    uint16_t n = 0;
    for (int i = 0; i < DEX_BYTES; i++) {
        uint8_t b = bm[i];
        while (b) { n += b & 1; b >>= 1; }
    }
    return n;
}

void dex_init(dex_t *d) { memset(d, 0, sizeof(*d)); }

void dex_mark_seen(dex_t *d, uint16_t sid, bool shiny)
{
    bit_set(d->seen, sid);
    if (shiny) bit_set(d->shiny_seen, sid);
}

void dex_mark_caught(dex_t *d, uint16_t sid, bool shiny)
{
    // 抓到必然见过 —— 两个位都置，与 sim 的 mark_caught 一致
    bit_set(d->seen, sid);
    bit_set(d->caught, sid);
    if (shiny) {
        bit_set(d->shiny_seen, sid);
        bit_set(d->shiny_caught, sid);
    }
}

bool dex_is_seen(const dex_t *d, uint16_t sid) { return bit_get(d->seen, sid); }
bool dex_is_caught(const dex_t *d, uint16_t sid) { return bit_get(d->caught, sid); }
bool dex_is_shiny_caught(const dex_t *d, uint16_t sid)
{
    return bit_get(d->shiny_caught, sid);
}
uint16_t dex_count_caught(const dex_t *d) { return bit_count(d->caught); }
uint16_t dex_count_seen(const dex_t *d) { return bit_count(d->seen); }

// ---------------------------------------------------------------------------

bool enc_selftest(void)
{
    bool ok = true;

    // ① 队列淘汰规则：稀有的不该被常见的挤掉
    enc_queue_t q;
    enc_queue_init(&q);
    encounter_t e = {0};
    // 先塞 1 条 ★★★★★ 再塞满 ★
    e.rarity = 5; e.species_id = 150; e.ts = 1;
    enc_queue_push(&q, &e);
    for (int i = 0; i < ENC_QUEUE_CAP + 5; i++) {
        e.rarity = 1; e.species_id = (uint16_t)(10 + i); e.ts = (uint32_t)(2 + i);
        enc_queue_push(&q, &e);
    }
    bool found5 = false;
    for (uint8_t i = 0; i < q.count; i++) {
        if (q.items[i].rarity == 5) found5 = true;
    }
    if (!found5) {
        printf("encounter: ★★★★★ 被 ★ 挤掉了 —— 淘汰规则退化成 FIFO 了\n");
        ok = false;
    }
    if (q.count != ENC_QUEUE_CAP) {
        printf("encounter: 队列长度 %u ≠ %d\n", q.count, ENC_QUEUE_CAP);
        ok = false;
    }

    // ①b **uid 在淘汰后仍然认得出同一条** —— 这条是真机抓出来的。
    //
    // 玩家在 P3/P4 期间后台还在塞遭遇，队列满了淘汰会让下标整体左移。
    // 用下标认的后果实测是：打的是 #64，抓到的是 #23，
    // 而且连打三轮只有第一轮真的捕获（另两轮 take 落到别的条目上）。
    //
    // 被观察的那条必须是**最高稀有度**，否则它自己先被淘汰掉，
    // 后面的断言根本不会执行（第一版就是这样，用 ★3 观察、灌 ★4，
    // 它第 17 条进来时就被挤走了 —— 退化版本照样"通过"）。
    enc_queue_init(&q);
    e.rarity = 5; e.species_id = 111; e.ts = 1;
    enc_queue_push(&q, &e);
    uint16_t watched = q.items[0].uid;
    uint8_t idx_before = 0;                    // 它现在在 0 号位

    // 灌 ★1，触发淘汰。★5 不会被挤掉，但**它前面的位置会变**吗？
    // 不会 —— 淘汰的是它后面的。所以还要制造一次「它左边的被挤掉」：
    // 先塞几条 ★1 占住 0..n，再让它们被挤掉。
    enc_queue_init(&q);
    for (int i = 0; i < 3; i++) {              // 先放 3 条 ★1
        e.rarity = 1; e.species_id = (uint16_t)(50 + i); e.ts = (uint32_t)(i);
        enc_queue_push(&q, &e);
    }
    e.rarity = 5; e.species_id = 111; e.ts = 100;   // ★5 在 3 号位
    enc_queue_push(&q, &e);
    watched = q.items[3].uid;
    idx_before = 3;

    for (int i = 0; i < ENC_QUEUE_CAP + 6; i++) {   // 灌到淘汰
        e.rarity = 2; e.species_id = (uint16_t)(20 + i); e.ts = (uint32_t)(200 + i);
        enc_queue_push(&q, &e);
    }

    encounter_t *found = enc_queue_find(&q, watched);
    if (!found) {
        printf("encounter: ★5 被挤掉了 —— 淘汰规则错了\n");
        ok = false;
    } else {
        if (found->species_id != 111) {
            printf("encounter: uid %u 找到的是 #%u，不是 #111 —— 张冠李戴\n",
                   watched, found->species_id);
            ok = false;
        }
        // 下标确实变了才说明这个用例有意义
        uint8_t idx_now = (uint8_t)(found - q.items);
        if (idx_now == idx_before) {
            printf("encounter: 下标没变（%u）—— 这个用例没测到东西\n", idx_now);
            ok = false;
        }
        encounter_t taken;
        if (!enc_queue_take_uid(&q, watched, &taken) ||
            taken.species_id != 111) {
            printf("encounter: take_uid 取到的不是 #111\n");
            ok = false;
        }
    }

    // 取一个不存在的 uid 应当安静地失败，不能误伤别人
    uint8_t before_n = q.count;
    if (enc_queue_take_uid(&q, 60000, NULL)) {
        printf("encounter: 不存在的 uid 竟然取成功了\n");
        ok = false;
    }
    if (q.count != before_n) {
        printf("encounter: 取失败却改了队列长度\n");
        ok = false;
    }

    // ② 取走
    enc_queue_init(&q);
    e.rarity = 5; e.species_id = 150; e.ts = 1;
    enc_queue_push(&q, &e);
    for (int i = 0; i < 3; i++) {
        e.rarity = 1; e.species_id = (uint16_t)(10 + i); e.ts = (uint32_t)(2 + i);
        enc_queue_push(&q, &e);
    }
    encounter_t got;
    uint8_t before = q.count;
    if (!enc_queue_take(&q, 0, &got) || q.count != before - 1) {
        printf("encounter: take 之后长度不对\n");
        ok = false;
    }

    // ③ 图鉴位图
    dex_t d;
    dex_init(&d);
    dex_mark_seen(&d, 25, false);
    dex_mark_caught(&d, 1, true);
    if (!dex_is_seen(&d, 25) || dex_is_caught(&d, 25)) {
        printf("encounter: seen/caught 分不开\n");
        ok = false;
    }
    if (!dex_is_caught(&d, 1) || !dex_is_seen(&d, 1) ||
        !dex_is_shiny_caught(&d, 1)) {
        printf("encounter: 抓到应当同时置 seen 与 shiny\n");
        ok = false;
    }
    if (dex_count_seen(&d) != 2 || dex_count_caught(&d) != 1) {
        printf("encounter: 计数 seen=%u caught=%u，期望 2/1\n",
               dex_count_seen(&d), dex_count_caught(&d));
        ok = false;
    }
    // 边界：1 与 151 都要能存（位图 19 字节 = 152 位，末位不能越界）
    dex_mark_caught(&d, 151, false);
    if (!dex_is_caught(&d, 151)) {
        printf("encounter: #151 存不进去 —— 位图边界错了\n");
        ok = false;
    }
    dex_mark_caught(&d, 152, false);      // 越界应当被忽略而不是踩内存
    if (dex_count_caught(&d) != 2) {
        printf("encounter: #152 越界没被挡住\n");
        ok = false;
    }

    if (ok) {
        printf("encounter: 自检 全部通过"
               "（淘汰规则 · uid 稳定 · 取走 · 图鉴位图 · 边界）\n");
    }
    return ok;
}
