// main/world.c —— 跨页面的游戏状态与后台扫描（F9-①）。
//
// 设计说明见 world.h。这里记实现上的三个决定。
//
// ## 为什么是独立任务而不是继续用 lv_timer
//
// lv_timer 跑在 LVGL 任务里，而 LVGL 任务还要画屏。一次 WiFi 扫描
// 阻塞 1.4 秒，期间屏幕完全冻住 —— P1 的呼吸动效会卡成幻灯片。
// 更要命的是 lv_timer 属于**页面**：页面一销毁定时器就没了。
//
// 独立任务两个问题都解决：扫描慢不影响画面，页面切换不影响采集。
//
// ## 栈要多大
//
// 3584 字节的主栈曾经被 sensing 的局部数组撑爆过（sens_core_t 2.6KB +
// 平滑窗口 1.9KB，Guru Meditation）。那次的修法是把大数组全改 static。
// 这里给 4096 —— 大数组仍是 static，栈上只有扫描结果的指针与循环变量。
//
// ## 互斥锁的粒度
//
// 只锁快照的拷贝，不锁扫描本身。扫描要 1.4 秒，锁那么久页面会卡；
// 常规快照只是几十字节 memcpy，存档快照也只是内存中的 2.3 KiB 编码。
// NVS 写入在锁外串行执行，因此临界区保持在微秒级。
// 代价是快照可能比最新扫描晚一拍 —— 对显示完全无所谓。

#include <inttypes.h>
#include <stdint.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"
#include "freertos/task.h"
#include "nvs_flash.h"

#include "bsp_battery.h"

#include "assets.h"
#include "evolution.h"
#include "exp.h"
#include "save.h"
#include "world.h"
#include "sfx.h"

static const char *TAG = "world";

#define SCAN_INTERVAL_MS 30000     // 与 sim/ 的采集间隔一致
#define MAX_APS 64

// 「今日行程」满格对应的移动量。
//
// **这个数字来自真实数据**，不是拍脑袋：用 data/raw/ 的三份实测跑
// sim/sensing.py 累加移动中的 distance ——
//   通勤 26 分钟 = 9.3　　家里 1.2 小时 = 0.3　　办公 8 小时 = 1.5
// 一天两趟通勤约 18.6。取 20 满格的效果是：
//   正常通勤日 93%（有成就感但不会轻易顶满）
//   纯坐办公室 7.5%（明显偏低，促使出门 —— 这正是这条轴的目的）
// 单位是 Q10（sensing 的 distance 就是 Q10），所以 20 × 1024。
#define PROGRESS_FULL_Q10 (20 * 1024)

static world_t s_w;
static SemaphoreHandle_t s_lock;
static SemaphoreHandle_t s_save_lock;
static bool s_wifi_ok;
static bool s_storage_ready;
static bool s_starter_pending = true;

// 扫描结果。**static** —— 64 × 76 字节放栈上必炸（见文件头）。
static wifi_ap_record_t s_recs[MAX_APS];
static sens_ap_t s_aps[MAX_APS];
static uint16_t s_last_n;   // 最近一次扫到几个，spawn_one 要用

// 移动量累积，Q10。今日行程由它映射。
static uint32_t s_motion_q10;

// 感知核心。**static** —— sens_core_t 有 2.6KB，放栈上会炸
// （这正是当年 Guru Meditation 的原因，见 sensing.c 顶部）。
static sens_core_t s_core;

// Pending encounters and dex are saved in V5. The queue retains 16 physical
// slots for compatibility, but only the newest five are available in gameplay.
static enc_queue_t s_queue;
static dex_t s_dex;
static party_t s_party;
static inventory_t s_inventory;
static trainer_store_t s_challenge;
static achievement_store_t s_achievements;
// Protected by s_save_lock; a candidate is never visible before save_write()
// succeeds. Keep this ~1.9 KiB object off the button task's stack.
static party_t s_starter_party;

typedef struct {
    uint16_t uid;
    uint32_t ts;
    battle_session_t session;
} world_battle_slot_t;
static world_battle_slot_t s_battles[ENC_QUEUE_LIMIT];
static struct {
    encounter_t encounter; // uid zero means there is no active encounter.
    battle_session_t session;
} s_active; // Runtime only; its pending removal is durable before publication.

// save_t 含 1886 B 队伍区，不能放进 4 KiB 的 world task 栈。
static save_t s_save_buf;

static bool s_dirty;
static enc_refresh_state_t s_refresh;
static exploration_state_t s_exploration;
static int64_t s_refresh_clock_us;
static enc_refresh_ap_t s_refresh_aps[MAX_APS];

static void refresh_clock_locked(void)
{
    int64_t now=esp_timer_get_time();
    int64_t seconds=(now-s_refresh_clock_us)/1000000;
    if(seconds>0) {
        uint64_t total=(uint64_t)s_refresh.online_s+(uint64_t)seconds;
        s_refresh.online_s=total>UINT32_MAX?UINT32_MAX:(uint32_t)total;
        s_refresh_clock_us+=seconds*1000000;
        s_dirty=true;
    }
}

uint8_t world_progress_from_motion(uint32_t motion_q10)
{
    uint32_t pct = (uint32_t)((uint64_t)motion_q10 * 100 / PROGRESS_FULL_Q10);
    return (uint8_t)(pct > 100 ? 100 : pct);
}

void world_snapshot(world_t *out)
{
    if (!out || !s_lock) return;

    // 接口没有错误返回值，所以超时后偷读 s_w 无法给出一致性保证。
    // NVS 已移出状态锁，临界区只剩内存操作；这里等待短临界区完成，
    // 比维护一份容易漏同步的影子副本更小也更可靠。
    if (xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;
    memcpy(out, &s_w, sizeof(*out));
    xSemaphoreGive(s_lock);
}

bool world_needs_starter(void)
{
    if (!s_lock || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return true;
    bool pending = s_starter_pending;
    xSemaphoreGive(s_lock);
    return pending;
}

// 存档节流。
//
// **不是每次变化都写 flash** —— 遭遇每 30 秒可能产生一条，
// 图鉴每次捕获变一次，而 flash 擦写有寿命（典型 10 万次）。
// 每 5 分钟一次 + 关键事件立刻写，是寿命与「丢多少」的折中：
// 最坏情况丢 5 分钟的三条轴推进（衰减 4/小时 → 0.33 格），看不出来。
//
// **捕获与图鉴变化立刻写** —— 那是玩家真正在乎的东西，
// 丢一只刚抓到的怪比丢 5 分钟衰减严重得多。
#define SAVE_INTERVAL_US (5 * 60 * 1000000LL)
static int64_t s_last_save_us;

// Older capture pages stored the wild level but left EXP at zero. Preserve
// that earned level and every other member field; only fill a missing EXP
// baseline. Reconcile earned EXP with the easier curve without reducing levels
// or accumulated EXP. Includes boxed members; repeated loads are idempotent.
static uint16_t normalize_party_exp(party_t *party)
{
    uint16_t repaired = 0;
    for (unsigned i = 0; i < PARTY_MAX + BOX_SPECIES; i++) {
        if (i < PARTY_MAX && i >= party->party_count) continue;
        mon_t *member = i < PARTY_MAX ? &party->party[i] : &party->box[i - PARTY_MAX];
        if (!member->species_id || member->level < 1 || member->level > LEVEL_MAX) continue;
        uint32_t minimum = exp_for_level(member->level);
        bool changed = false;
        if (member->exp < minimum) { member->exp = minimum; changed = true; }
        uint8_t earned = exp_to_level(member->exp, LEVEL_MAX);
        if (earned > member->level) { member->level = earned; changed = true; }
        if (changed) repaired++;
    }
    return repaired;
}

static void sync_leader_locked(void)
{
    if (s_party.party_count == 0) return;
    mon_t *leader = &s_party.party[0];
    leader->level = s_w.level;
    leader->exp = s_w.exp;
    leader->intimacy = nurture_pct(s_w.pet.intimacy);
    leader->explore_value = s_w.explore_value;
    s_w.species = leader->species_id;
}

static void collect_save_locked(save_t *sv)
{
    sync_leader_locked();
    memset(sv, 0, sizeof(*sv));
    sv->version = SAVE_VERSION;
    sv->pet = s_w.pet;
    const mon_t *leader = party_leader(&s_party);
    if (leader) {
        sv->species = leader->species_id;
        sv->level = leader->level;
        sv->exp = leader->exp;
    }
    party_serialize(&s_party, sv->party);
    sv->queue = s_queue;
    sv->dex = s_dex;
    sv->motion_q10 = s_motion_q10;
    sv->scans = s_w.scans;
    sv->last_uptime_us = esp_timer_get_time();
    sv->inventory = s_inventory;
    sv->challenge = s_challenge;
    sv->achievements = s_achievements;
    refresh_clock_locked();
    sv->refresh = s_refresh;
    sv->exploration = s_exploration;
}

// 状态锁内只生成不可变快照，真正的 NVS 写入在锁外。
// 独立的保存锁保证两个任务不会复用 s_save_buf，也不会让旧快照后写覆盖新快照。
static bool save_now(const char *why)
{
    if (!s_lock || !s_save_lock || !s_storage_ready) return false;
    if (xSemaphoreTake(s_save_lock, portMAX_DELAY) != pdTRUE) return false;

    xSemaphoreTake(s_lock, portMAX_DELAY);
    collect_save_locked(&s_save_buf);
    uint16_t caught = dex_count_caught(&s_dex);
    uint8_t queue_count = s_queue.count;
    // 这份快照已覆盖当前改动。写入期间的新改动会重新把 dirty 置 true。
    s_dirty = false;
    xSemaphoreGive(s_lock);

    bool ok = save_write(&s_save_buf);       // 慢操作：绝不持有 s_lock
    int64_t saved_at = esp_timer_get_time();

    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (ok) {
        s_last_save_us = saved_at;
    } else {
        // 快照没有落盘，保留重试凭证；不覆盖写入期间产生的 dirty=true。
        s_dirty = true;
    }
    xSemaphoreGive(s_lock);

    if (ok) {
        ESP_LOGI(TAG, "已存档（%s）：图鉴 %u 队列 %u", why,
                 caught, queue_count);
    }
    xSemaphoreGive(s_save_lock);
    return ok;
}

world_starter_result_t world_choose_starter(uint16_t species)
{
    if (species != 1 && species != 4 && species != 7 && species != 25)
        return WORLD_STARTER_INVALID;
    if (!s_lock || !s_save_lock ||
        xSemaphoreTake(s_save_lock, portMAX_DELAY) != pdTRUE)
        return WORLD_STARTER_STORAGE_UNAVAILABLE;

    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (!s_starter_pending || !s_storage_ready) {
        world_starter_result_t result = !s_starter_pending ? WORLD_STARTER_ALREADY_CHOSEN
                                                          : WORLD_STARTER_STORAGE_UNAVAILABLE;
        xSemaphoreGive(s_lock);
        xSemaphoreGive(s_save_lock);
        return result;
    }

    collect_save_locked(&s_save_buf);
    s_starter_party = s_party;
    mon_t starter = {.species_id = (uint8_t)species, .level = exp_to_level(0, LEVEL_MAX),
                     .hp = 100, .nickname_idx = 0xFF};
    if (!party_receive(&s_starter_party, &starter)) {
        xSemaphoreGive(s_lock);
        xSemaphoreGive(s_save_lock);
        return WORLD_STARTER_INVALID;
    }
    nurture_init(&s_save_buf.pet);
    s_save_buf.species = species;
    s_save_buf.level = starter.level;
    s_save_buf.exp = starter.exp;
    s_save_buf.opening_seen = true;
    party_serialize(&s_starter_party, s_save_buf.party);
    dex_mark_caught(&s_save_buf.dex, species, false);
    s_dirty = false; // Later background changes mark themselves dirty again.
    xSemaphoreGive(s_lock);

    bool ok = save_write(&s_save_buf); // NVS remains outside the world lock.
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (ok) {
        s_party = s_starter_party;
        s_w.pet = s_save_buf.pet;
        s_w.species = species;
        s_w.level = starter.level;
        s_w.exp = starter.exp;
        s_w.explore_value = 0;
        dex_mark_caught(&s_dex, species, false);
        s_starter_pending = false;
        s_last_save_us = esp_timer_get_time();
    } else {
        s_dirty = true;
    }
    xSemaphoreGive(s_lock);
    xSemaphoreGive(s_save_lock);
    if (ok) ESP_LOGI(TAG, "starter saved: #%u", species);
    else ESP_LOGE(TAG, "starter save failed; choice remains pending");
    return ok ? WORLD_STARTER_OK : WORLD_STARTER_SAVE_FAILED;
}

const enc_queue_t *world_queue(void) { return &s_queue; }
const dex_t *world_dex(void) { return &s_dex; }

void world_queue_snapshot(enc_queue_t *out)
{
    if (!out) return;
    memset(out, 0, sizeof(*out));
    if (!s_lock || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;
    *out = s_queue;
    xSemaphoreGive(s_lock);
}

void world_inventory_snapshot(inventory_t *out)
{
    if (!out) return;
    memset(out, 0, sizeof(*out));
    if (!s_lock || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;
    *out = s_inventory;
    xSemaphoreGive(s_lock);
}

static mon_t leader_view_locked(void)
{
    mon_t leader = s_party.party[0];
    leader.level = s_w.level;
    leader.exp = s_w.exp;
    int32_t intimacy = s_w.pet.intimacy / NURT_Q;
    leader.intimacy = (uint8_t)(intimacy < 0 ? 0 : intimacy > 100 ? 100 : intimacy);
    leader.explore_value = s_w.explore_value;
    return leader;
}

static void party_snapshot_locked(world_party_t *out)
{
    memset(out, 0, sizeof(*out));
    out->count = s_party.party_count;
    memcpy(out->members, s_party.party, sizeof(out->members));
    // A snapshot is read-only: fresh leader mirrors live only in the copy.
    // Use the same integer representation as the switch's expected check.
    if (out->count) out->members[0] = leader_view_locked();
    out->box_count = (uint8_t)(party_total(&s_party) - s_party.party_count);
    out->switch_locked = !s_storage_ready || s_starter_pending || s_active.encounter.uid != 0 || s_challenge.session.active || s_challenge.league_active;
}

void world_party_snapshot(world_party_t *out)
{
    if (!out) return;
    memset(out, 0, sizeof(*out));
    out->switch_locked = true;
    if (!s_lock || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;
    party_snapshot_locked(out);
    xSemaphoreGive(s_lock);
}

// Queue mutations take the save lock first. A first-action transaction can
// therefore persist a candidate outside the state lock without a scan replacing
// its target before commit; read-only snapshots remain available during NVS I/O.
static bool lock_encounter_change(void)
{
    if (!s_lock || !s_save_lock ||
        xSemaphoreTake(s_save_lock, portMAX_DELAY) != pdTRUE) return false;
    if (xSemaphoreTake(s_lock, portMAX_DELAY) == pdTRUE) return true;
    xSemaphoreGive(s_save_lock);
    return false;
}

static void unlock_encounter_change(void)
{
    xSemaphoreGive(s_lock);
    xSemaphoreGive(s_save_lock);
}

world_switch_result_t world_set_leader(uint8_t index, const mon_t *expected,
                                      world_party_t *out)
{
    // Copy before clearing out: callers may pass &out->members[index].
    if (!expected || index >= PARTY_MAX) return WORLD_SWITCH_INVALID;
    const mon_t wanted = *expected;
    if (out) memset(out, 0, sizeof(*out));
    if (!lock_encounter_change()) return WORLD_SWITCH_STORAGE_UNAVAILABLE;
    if (!s_storage_ready || s_starter_pending) {
        unlock_encounter_change(); return WORLD_SWITCH_STORAGE_UNAVAILABLE;
    }
    if (s_active.encounter.uid || s_challenge.session.active || s_challenge.league_active) { unlock_encounter_change(); return WORLD_SWITCH_BUSY; }
    if (index >= s_party.party_count) { unlock_encounter_change(); return WORLD_SWITCH_INVALID; }
    const mon_t outgoing = leader_view_locked();
    const mon_t selected = index ? s_party.party[index] : outgoing;
    if (memcmp(&wanted, &selected, sizeof(wanted)) != 0) {
        unlock_encounter_change(); return WORLD_SWITCH_STALE;
    }
    if (!index) {
        if (out) party_snapshot_locked(out);
        unlock_encounter_change(); return WORLD_SWITCH_ALREADY_LEADER;
    }

    // collect_save refreshes legacy mirrors. Restore those private RAM bytes
    // before leaving the lock, so even a failed switch publishes no change.
    const mon_t original_mirror = s_party.party[0];
    collect_save_locked(&s_save_buf);
    s_starter_party = s_party;
    s_party.party[0] = original_mirror;
    s_starter_party.party[0] = outgoing;
    normalize_party_exp(&s_starter_party);
    if (!party_set_leader(&s_starter_party, index)) {
        unlock_encounter_change(); return WORLD_SWITCH_INVALID;
    }
    const mon_t next_leader = s_starter_party.party[0];
    s_save_buf.species = next_leader.species_id;
    s_save_buf.level = next_leader.level;
    s_save_buf.exp = next_leader.exp;
    s_save_buf.pet.intimacy = (int32_t)next_leader.intimacy * NURT_Q;
    party_serialize(&s_starter_party, s_save_buf.party);
    s_dirty = false;
    xSemaphoreGive(s_lock);
    bool ok = save_write(&s_save_buf);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (ok) {
        s_party = s_starter_party;
        s_w.species = next_leader.species_id;
        s_w.level = next_leader.level;
        s_w.exp = next_leader.exp;
        s_w.pet.intimacy = s_save_buf.pet.intimacy;
        s_w.explore_value = next_leader.explore_value;
        // Unstarted encounter previews may have cached the old leader's
        // battle stats, even when two members share the same species ID.
        memset(s_battles, 0, sizeof(s_battles));
        s_last_save_us = esp_timer_get_time();
        if (out) party_snapshot_locked(out);
    } else s_dirty = true;
    unlock_encounter_change();
    return ok ? WORLD_SWITCH_OK : WORLD_SWITCH_SAVE_FAILED;
}

static encounter_t *find_encounter_locked(uint16_t uid)
{
    if (!uid) return NULL;
    if (s_active.encounter.uid == uid) return &s_active.encounter;
    return enc_queue_find(&s_queue, uid);
}

static void prune_battles_locked(void)
{
    for (int i = 0; i < ENC_QUEUE_LIMIT; i++) {
        world_battle_slot_t *slot = &s_battles[i];
        if (!slot->uid) continue;
        const encounter_t *entry = enc_queue_find(&s_queue, slot->uid);
        if (!entry || entry->ts != slot->ts) memset(slot, 0, sizeof(*slot));
    }
}

bool world_get_encounter_uid(uint16_t uid, encounter_t *out)
{
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    if (!s_lock || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return false;
    const encounter_t *entry = find_encounter_locked(uid);
    if (entry) *out = *entry;
    xSemaphoreGive(s_lock);
    return entry != NULL;
}

void world_end_active_encounter(void)
{
    if (!lock_encounter_change()) return;
    // Pending removal was already committed before active became observable.
    memset(&s_active, 0, sizeof(s_active));
    unlock_encounter_change();
}

bool world_battle_get_uid(uint16_t uid, battle_session_t *out)
{
    if (!out) return false;
    memset(out, 0, sizeof(*out));
    if (!uid || !s_lock || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return false;
    prune_battles_locked();
    bool found = find_encounter_locked(uid) != NULL;
    if (s_active.encounter.uid == uid) *out = s_active.session;
    else if (found) for (int i = 0; i < ENC_QUEUE_LIMIT; i++) {
        if (s_battles[i].uid == uid) { *out = s_battles[i].session; break; }
    }
    xSemaphoreGive(s_lock);
    return found;
}

bool world_battle_set_uid(uint16_t uid, const battle_session_t *session)
{
    if (!session || !uid || !lock_encounter_change()) return false;
    if (s_challenge.session.active || s_challenge.league_active) { unlock_encounter_change(); return false; }
    prune_battles_locked();
    if (s_active.encounter.uid == uid) {
        // A started encounter must never be reset into a fresh pending battle.
        bool ok = session->started;
        if (ok) {
            battle_session_t next = *session;
            // Page-local copies may predate a committed award. Once guards
            // belong to world and cannot be cleared by a stale animation copy.
            if (s_active.session.loot_checked) {
                next.loot_checked = true;
                next.loot_item = s_active.session.loot_item;
                next.loot_qty = s_active.session.loot_qty;
                next.loot_full = s_active.session.loot_full;
            }
            if (s_active.session.defeat_applied) next.defeat_applied = true;
            if (s_active.session.reward_settled) next.reward_settled = true;
            s_active.session = next;
        }
        unlock_encounter_change();
        return ok;
    }
    const encounter_t *entry = enc_queue_find(&s_queue, uid);
    if (!entry || (session->started && (s_active.encounter.uid || !s_storage_ready || s_starter_pending))) {
        unlock_encounter_change();
        return false;
    }
    if (session->started) {
        collect_save_locked(&s_save_buf);
        enc_queue_take_uid(&s_save_buf.queue, uid, NULL);
        s_dirty = false; // A concurrent non-queue change marks itself dirty.
        xSemaphoreGive(s_lock);
        bool ok = save_write(&s_save_buf);
        xSemaphoreTake(s_lock, portMAX_DELAY);
        if (ok) {
            enc_queue_take_uid(&s_queue, uid, &s_active.encounter);
            s_active.session = *session;
            s_w.pending = s_queue.count;
            s_last_save_us = esp_timer_get_time();
            prune_battles_locked();
        } else {
            s_dirty = true;
            ESP_LOGE(TAG, "battle start save failed; pending encounter unchanged");
        }
        unlock_encounter_change();
        return ok;
    }
    world_battle_slot_t *target = NULL;
    for (int i = 0; i < ENC_QUEUE_LIMIT; i++) {
        if (s_battles[i].uid == uid) { target = &s_battles[i]; break; }
        if (!target && !s_battles[i].uid) target = &s_battles[i];
    }
    if (target) *target = (world_battle_slot_t){.uid = uid, .ts = entry->ts, .session = *session};
    unlock_encounter_change();
    return target != NULL;
}

static bool take_encounter_uid_locked(uint16_t uid, encounter_t *out)
{
    if (uid && s_active.encounter.uid == uid) {
        if (out) *out = s_active.encounter;
        memset(&s_active, 0, sizeof(s_active));
        return true;
    }
    bool ok = enc_queue_take_uid(&s_queue, uid, out);
    if (ok) {
        prune_battles_locked();
        s_w.pending = s_queue.count;
        s_dirty = true;
    }
    return ok;
}

bool world_battle_loot_uid(uint16_t uid, item_loot_t *out)
{
    if (out) *out = (item_loot_t){.item_id = ITEM_NONE};
    if (!uid || !lock_encounter_change()) return false;
    battle_session_t *session = &s_active.session;
    if (s_active.encounter.uid != uid || !session->initialized || !session->started ||
        !session->finished || !session->won || s_starter_pending || !s_storage_ready ||
        session->pet_species != s_w.species) {
        unlock_encounter_change(); return false;
    }
    if (session->loot_checked) {
        if (out) *out = (item_loot_t){.item_id = session->loot_item,
            .quantity = session->loot_qty, .full = session->loot_full};
        unlock_encounter_change(); return true;
    }
    const encounter_t *entry = &s_active.encounter;
    item_loot_t loot = items_roll_loot(entry->rarity,
        items_loot_seed(entry->uid, entry->ts, entry->species_id, entry->rarity));
    collect_save_locked(&s_save_buf);
    if (s_save_buf.challenge.wild_wins < UINT16_MAX) s_save_buf.challenge.wild_wins++;
    if (loot.item_id < ITEM_COUNT) {
        uint16_t *quantity = &s_save_buf.inventory.quantity[loot.item_id];
        uint16_t room = items_capacity(loot.item_id) - *quantity;
        loot.full = room < loot.quantity;
        if (loot.quantity > room) loot.quantity = (uint8_t)room;
        *quantity += loot.quantity;
    }
    s_dirty = false;
    xSemaphoreGive(s_lock);
    bool ok = save_write(&s_save_buf);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (ok) {
        s_inventory = s_save_buf.inventory;
        s_challenge = s_save_buf.challenge;
        s_achievements = s_save_buf.achievements;
        session->loot_checked = true;
        session->loot_item = loot.item_id;
        session->loot_qty = loot.quantity;
        session->loot_full = loot.full;
        s_last_save_us = esp_timer_get_time();
        if (out) *out = loot;
    } else s_dirty = true;
    unlock_encounter_change();
    return ok;
}

bool world_capture_ball_spend_uid(uint16_t uid, uint8_t ball,
                                  const battle_session_t *item_session)
{
    if (!uid || ball >= ITEM_BALL_COUNT || !item_session ||
        !item_session->initialized || !item_session->started || !lock_encounter_change()) return false;
    if (s_challenge.session.active || s_challenge.league_active) { unlock_encounter_change(); return false; }
    prune_battles_locked();
    encounter_t *entry = find_encounter_locked(uid);
    battle_session_t current = {0};
    bool active = s_active.encounter.uid == uid;
    if (active) current = s_active.session;
    else for (unsigned i = 0; i < ENC_QUEUE_LIMIT; i++)
        if (s_battles[i].uid == uid) { current = s_battles[i].session; break; }
    bool can_capture = current.initialized && !current.retaliation_pending &&
        (current.finished ? current.won && !current.capture_used_after_win && current.loot_checked
                          : !current.auto_battle && current.pet_hp > 0);
    if (!entry || !can_capture || !s_storage_ready || s_starter_pending ||
        (!active && s_active.encounter.uid) || s_inventory.quantity[ball] == 0 ||
        item_session->pet_species != s_w.species || item_session->wild_species != entry->species_id ||
        item_session->rng != current.rng || item_session->attack_count != current.attack_count ||
        item_session->pet_hp != current.pet_hp || item_session->wild_hp != current.wild_hp ||
        item_session->finished != current.finished || item_session->won != current.won ||
        (current.won && !item_session->capture_used_after_win)) {
        unlock_encounter_change(); return false;
    }
    battle_session_t next = *item_session;
    if (current.loot_checked) {
        next.loot_checked = true; next.loot_item = current.loot_item;
        next.loot_qty = current.loot_qty; next.loot_full = current.loot_full;
    }
    collect_save_locked(&s_save_buf);
    s_save_buf.inventory.quantity[ball]--;
    if (!active) enc_queue_take_uid(&s_save_buf.queue, uid, NULL);
    s_dirty = false;
    xSemaphoreGive(s_lock);
    bool ok = save_write(&s_save_buf);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (ok) {
        s_inventory = s_save_buf.inventory;
        if (!active) enc_queue_take_uid(&s_queue, uid, &s_active.encounter);
        s_active.session = next;
        s_w.pending = s_queue.count;
        s_last_save_us = esp_timer_get_time();
        prune_battles_locked();
    } else s_dirty = true;
    unlock_encounter_change();
    return ok;
}

// Bonus experience for existing nonparticipants; one award in the enclosing
// durable settlement, never paid again by a retry or animation callback.
bool world_capture_uid(uint16_t uid, const mon_t *mon)
{
    if (!mon || mon->species_id < 1 || mon->species_id > BOX_SPECIES) return false;
    if (!lock_encounter_change()) return false;
    encounter_t *entry = find_encounter_locked(uid);
    if (s_challenge.session.active || s_challenge.league_active || s_starter_pending || !s_storage_ready || !entry || entry->species_id != mon->species_id) {
        unlock_encounter_change(); return false;
    }
    collect_save_locked(&s_save_buf);
    s_starter_party = s_party;
    if (!party_receive(&s_starter_party, mon)) { unlock_encounter_change(); return false; }
    normalize_party_exp(&s_starter_party);
    uint16_t earned=exp_scaled(exp_scaled((uint16_t)(mon->level*8+20),60),nurture_exp_percent(&s_w.pet));
    mon_t *leader=&s_starter_party.party[0];leader->exp=leader->exp>UINT32_MAX-earned?UINT32_MAX:leader->exp+earned;
    leader->level=exp_to_level(leader->exp,LEVEL_MAX);
    exp_share_party(&s_starter_party,((1u<<s_party.party_count)-1)&~1u,earned);
    s_save_buf.level=leader->level;
    s_save_buf.exp = leader->exp;
    party_serialize(&s_starter_party, s_save_buf.party);
    dex_mark_caught(&s_save_buf.dex, mon->species_id, (mon->flags & 1u) != 0);
    enc_queue_take_uid(&s_save_buf.queue, uid, NULL);
    s_dirty = false;
    xSemaphoreGive(s_lock);
    bool ok = save_write(&s_save_buf);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (ok) {
        s_party = s_starter_party;
        s_w.exp = s_party.party[0].exp;s_w.level=s_party.party[0].level;
        take_encounter_uid_locked(uid, NULL);
        dex_mark_caught(&s_dex, mon->species_id, (mon->flags & 1u) != 0);
        s_last_save_us = esp_timer_get_time();
        ESP_LOGI(TAG, "@@PARTY receive #%u party=%u total=%u", mon->species_id,
                 s_party.party_count, party_total(&s_party));
    } else s_dirty = true;
    unlock_encounter_change();
    return ok;
}

bool world_take_encounter(uint8_t index, encounter_t *out)
{
    bool ok = false;
    if (lock_encounter_change()) {
        ok = enc_queue_take(&s_queue, index, out);
        if (ok) {
            prune_battles_locked();
            s_w.pending = s_queue.count;
            s_dirty = true;
        }
        unlock_encounter_change();
    }
    return ok;
}

bool world_take_uid(uint16_t uid, encounter_t *out)
{
    bool ok = false;
    if (lock_encounter_change()) {
        ok = take_encounter_uid_locked(uid, out);
        unlock_encounter_change();
    }
    return ok;
}

void world_update_hp_uid(uint16_t uid, uint8_t hp_ratio)
{
    if (lock_encounter_change()) {
        encounter_t *e = find_encounter_locked(uid);
        if (e) { e->hp_ratio = hp_ratio > 100 ? 100 : hp_ratio; s_dirty = true; }
        unlock_encounter_change();
    }
}

bool world_mark_exp_granted_uid(uint16_t uid)
{
    bool marked = false;
    if (lock_encounter_change()) {
        encounter_t *e = find_encounter_locked(uid);
        if (e && !e->exp_granted) { e->exp_granted = true; s_dirty = true; marked = true; }
        unlock_encounter_change();
    }
    return marked;
}

void world_mark_seen(uint16_t sid, bool shiny)
{
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        dex_mark_seen(&s_dex, sid, shiny);
        s_dirty = true;
        xSemaphoreGive(s_lock);
    }
}

void world_feed(void)
{
    world_t snapshot = {0};
    world_snapshot(&snapshot);
    (void)world_item_use(snapshot.species, ITEM_BERRY, NULL);
}

void world_play(void)
{
    if (lock_encounter_change()) {
        if (!s_starter_pending) { nurture_play(&s_w.pet); s_dirty = true; }
        unlock_encounter_change();
    }
}

void world_rest(void)
{
    if (lock_encounter_change()) {
        if (!s_starter_pending) { nurture_rest(&s_w.pet); s_dirty = true; }
        unlock_encounter_change();
    }
}

void world_grant_exp(uint16_t amount)
{
    if (amount == 0) return;

    uint8_t old_level = 0;
    uint8_t new_level = 0;
    uint32_t new_exp = 0;
    bool granted = false;
    if (lock_encounter_change()) {
        if (s_starter_pending) { unlock_encounter_change(); return; }
        old_level = s_w.level;
        uint32_t minimum = exp_for_level(s_w.level);
        uint32_t base = s_w.exp < minimum ? minimum : s_w.exp;
        s_w.exp = base > UINT32_MAX - amount ? UINT32_MAX : base + amount;
        s_w.level = exp_to_level(s_w.exp, LEVEL_MAX);
        sync_leader_locked();
        s_dirty = true;
        new_level = s_w.level;
        new_exp = s_w.exp;
        granted = true;
        unlock_encounter_change();
    }

    if (!granted) return;
    if (new_level != old_level) {
        ESP_LOGI(TAG, "level up: %u -> %u (exp +%u = %" PRIu32 ")",
                 old_level, new_level, amount, new_exp);
    }

    // 经验是战斗的长期回报，结算后立刻落盘，不能等 5 分钟节流。
    save_now("experience");
}

bool world_apply_defeat_uid(uint16_t uid)
{
    if (!uid || !lock_encounter_change()) return false;
    battle_session_t *session = &s_active.session;
    if (s_active.encounter.uid != uid || !session->finished || session->won ||
        s_starter_pending || session->pet_species != s_w.species) {
        unlock_encounter_change();
        return false;
    }
    if(session->defeat_applied){unlock_encounter_change();return true;}
    collect_save_locked(&s_save_buf);nurture_defeat(&s_save_buf.pet);
    xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
    if(ok){nurture_defeat(&s_w.pet);s_active.session.defeat_applied=true;s_last_save_us=esp_timer_get_time();}
    else s_dirty=true;
    unlock_encounter_change();return ok;
}

static item_use_status_t use_item_or_natural(uint16_t expected_species, uint8_t item_id,
                                            uint16_t natural_target, item_use_result_t *out)
{
    if (out) memset(out, 0, sizeof(*out));
    if (expected_species < 1 || expected_species > BOX_SPECIES ||
        (item_id >= ITEM_COUNT && item_id != ITEM_NONE)) return ITEM_USE_INVALID;
    if (!lock_encounter_change()) return ITEM_USE_STORAGE_UNAVAILABLE;
    if (!s_storage_ready || s_starter_pending) {
        unlock_encounter_change(); return ITEM_USE_STORAGE_UNAVAILABLE;
    }
    if (s_active.encounter.uid || s_challenge.session.active || s_challenge.league_active) { unlock_encounter_change(); return ITEM_USE_BUSY; }
    if (s_w.species != expected_species || !s_party.party_count ||
        s_party.party[0].species_id != expected_species) {
        unlock_encounter_change(); return ITEM_USE_WRONG_TARGET;
    }
    if (item_id != ITEM_NONE && !s_inventory.quantity[item_id]) {
        unlock_encounter_change(); return ITEM_USE_EMPTY;
    }
    item_use_result_t result;
    item_use_status_t status;
    if (item_id == ITEM_NONE) {
        species_t sp; evo_check_t check;
        if (!assets_species(expected_species, &sp) || sp.evolve_trigger != EVO_TRIGGER_LEVEL ||
            sp.evolve_to != natural_target || !natural_target || natural_target > BOX_SPECIES) {
            unlock_encounter_change(); return ITEM_USE_NOT_APPLICABLE;
        }
        evo_check(nurture_pct(s_w.pet.intimacy), s_w.explore_value,
                  sp.evolve_trigger, sp.evolve_to, sp.evolve_level, &check);
        if (!check.can) { unlock_encounter_change(); return ITEM_USE_NOT_APPLICABLE; }
        result = (item_use_result_t){.species_before = expected_species, .species_after = natural_target,
                                    .before = s_w.pet, .after = s_w.pet};
        result.after.mood += 15 * NURT_Q;
        if (result.after.mood > NURT_MAX) result.after.mood = NURT_MAX;
        status = ITEM_USE_OK;
    } else status = items_apply(item_id, expected_species, s_w.level, &s_w.pet, &result);
    if (status != ITEM_USE_OK) { unlock_encounter_change(); return status; }
    collect_save_locked(&s_save_buf);
    s_starter_party = s_party;
    mon_t *leader = &s_starter_party.party[0];
    leader->species_id = (uint8_t)result.species_after;
    leader->intimacy = nurture_pct(result.after.intimacy);
    s_save_buf.species = result.species_after;
    s_save_buf.pet = result.after;
    party_serialize(&s_starter_party, s_save_buf.party);
    if (result.species_after != expected_species) {
        dex_mark_caught(&s_save_buf.dex, result.species_after, (leader->flags & 1u) != 0);
        if (s_save_buf.achievements.evolutions < UINT16_MAX) s_save_buf.achievements.evolutions++;
    }
    if (item_id != ITEM_NONE) {
        s_save_buf.inventory.quantity[item_id]--;
        result.remaining = s_save_buf.inventory.quantity[item_id];
    }
    s_dirty = false;
    xSemaphoreGive(s_lock);
    bool ok = save_write(&s_save_buf);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (ok) {
        s_party = s_starter_party;
        s_inventory = s_save_buf.inventory;
        s_achievements = s_save_buf.achievements;
        s_w.species = result.species_after;
        s_w.pet = result.after;
        if (result.species_after != expected_species)
            dex_mark_caught(&s_dex, result.species_after, (leader->flags & 1u) != 0);
        s_last_save_us = esp_timer_get_time();
        if (out) *out = result;
    } else s_dirty = true;
    unlock_encounter_change();
    return ok ? ITEM_USE_OK : ITEM_USE_SAVE_FAILED;
}

item_use_status_t world_item_use(uint16_t expected_species, uint8_t item_id, item_use_result_t *out)
{
    if (item_id >= ITEM_COUNT) return ITEM_USE_INVALID;
    return use_item_or_natural(expected_species, item_id, 0, out);
}

bool world_evolve_leader(uint16_t expected_species, uint16_t evolve_to)
{
    // Natural LEVEL nurture/exploration remains free. Stone and trade routes
    // are exclusively available through the corresponding inventory item.
    return use_item_or_natural(expected_species, ITEM_NONE, evolve_to, NULL) == ITEM_USE_OK;
}

static esp_err_t wifi_bring_up(void)
{
    esp_err_t err = nvs_flash_init();
    // WiFi must not erase the game save to repair an NVS initialization error.
    if (err != ESP_OK) return err;

    ESP_ERROR_CHECK(esp_netif_init());
    ESP_ERROR_CHECK(esp_event_loop_create_default());
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_STA));
    ESP_ERROR_CHECK(esp_wifi_start());
    return ESP_OK;
}

// ---------------------------------------------------------------------------
// NDJSON 输出 —— **原样搬自 play_collect.c**，不是重写。
//
// 我第一版在这里手写了个简化的 emitter，只打 bssid/rssi/channel。
// 那会**静默破坏两件事**：
//   · auth 字段没了 → classify_biome 用它区分野外/城区，直接失效
//   · bat 字段没了 → 续航实测（soak.py）读的就是它
// 而 NDJSON 仍然是合法 JSON，collect.py 照收不误，
// 只有下游算出奇怪结果时才会发现。
//
// 教训与 sprite 那次同源：**动格式之前先看清楚下游消费了哪些字段**。
// ---------------------------------------------------------------------------

static const char *auth_name(wifi_auth_mode_t m)
{
    switch (m) {
    case WIFI_AUTH_OPEN:            return "open";
    case WIFI_AUTH_WEP:             return "wep";
    case WIFI_AUTH_WPA_PSK:         return "wpa";
    case WIFI_AUTH_WPA2_PSK:        return "wpa2";
    case WIFI_AUTH_WPA_WPA2_PSK:    return "wpa2";
    case WIFI_AUTH_WPA3_PSK:        return "wpa3";
    case WIFI_AUTH_WPA2_WPA3_PSK:   return "wpa3";
    case WIFI_AUTH_WPA2_ENTERPRISE: return "wpa2-ent";
    case WIFI_AUTH_WPA3_ENTERPRISE: return "wpa3-ent";
    case WIFI_AUTH_WAPI_PSK:        return "wapi";
    default:                        return "unknown";
    }
}

// JSON 字符串转义 —— SSID 里可能有引号、反斜杠、控制字符。
//
// 不转义的后果很具体：一个带引号的 SSID 会让整行 NDJSON 解析失败，
// 而那一行可能是走到某个关键地点时采的。
static void json_escape(const char *in, char *out, size_t cap)
{
    size_t o = 0;
    for (size_t i = 0; in[i] && o + 7 < cap; i++) {
        unsigned char c = (unsigned char)in[i];
        if (c == '"' || c == '\\') {
            out[o++] = '\\';
            out[o++] = (char)c;
        } else if (c < 0x20) {
            o += (size_t)snprintf(out + o, cap - o, "\\u%04x", c);
        } else {
            out[o++] = (char)c;
        }
    }
    out[o] = '\0';
}

// 把一次扫描结果按 NDJSON 打到串口。
//
// 用 printf 而非 ESP_LOGI：日志带 "I (1234) collect:" 前缀，
// 收集端还要剥一层。直接 printf 出来的就是干净的一行 JSON。
static void emit_ndjson(uint16_t n)
{
    // ts 用 Unix 时间还是开机毫秒？
    //
    // 设备没有 RTC 对时（NFC 对时那条还没结论），开机时钟从 0 开始。
    // 所以这里输出**开机秒数**，由 collect.py 加上主机的墙钟基准 ——
    // 主机知道现在几点，设备不知道。
    int64_t up_s = esp_timer_get_time() / 1000000;

    printf("{\"ts\":%" PRId64 ",\"aps\":[", up_s);
    char esc[80];
    for (uint16_t i = 0; i < n; i++) {
        const wifi_ap_record_t *r = &s_recs[i];
        json_escape((const char *)r->ssid, esc, sizeof(esc));
        printf("%s{\"b\":\"%02x:%02x:%02x:%02x:%02x:%02x\","
               "\"s\":\"%s\",\"r\":%d,\"c\":%u,\"a\":\"%s\"}",
               i ? "," : "",
               r->bssid[0], r->bssid[1], r->bssid[2],
               r->bssid[3], r->bssid[4], r->bssid[5],
               esc, r->rssi, r->primary, auth_name(r->authmode));
    }
    // 附带电量 —— 续航实测靠它，顺路采了不额外花电
    printf("],\"bat\":%d}\n", bsp_battery_soc());
    fflush(stdout);
}

// Debug-only encounter injection; normal gameplay uses refresh_from_scan.
//
// 选哪个 AP：用 `ts % n` 挑，与 sim 的 `aps[result.ts % len(aps)]` 一致。
// 看着随意，但它是**确定性**的 —— 同一时刻同一批 AP 永远挑同一个，
// 这是整套确定性刷新的一环（见 encounter.c 顶部）。
static void spawn_one(uint32_t ts, bool transient, uint8_t *made)
{
    if (s_last_n == 0) return;
    uint16_t idx = (uint16_t)(ts % s_last_n);
    const wifi_ap_record_t *ap = &s_recs[idx];

    uint8_t rarity = enc_rarity_from_ap(ap->rssi, (uint8_t)ap->authmode,
                                        ap->ssid[0] != 0, transient);

    encounter_t e;
    memset(&e, 0, sizeof(e));
    e.ts = ts;
    e.rarity = rarity;
    e.species_id = enc_pick_species(ap->bssid, ts, rarity);
    e.is_shiny = enc_roll_shiny(ap->bssid, ts, rarity);
    e.is_transient = transient;
    e.hp_ratio = 100;
    e.biome = 0;                  // TODO: classify_biome 还没移植

    if (lock_encounter_change()) {
        // The active uid is outside the queue; reserve it as well when the
        // 16-bit sequence wraps. enc_queue_push also skips pending identities.
        do {
            if (!s_queue.next_uid) s_queue.next_uid = 1;
            if (s_queue.next_uid != s_active.encounter.uid &&
                !enc_queue_find(&s_queue, s_queue.next_uid)) break;
            s_queue.next_uid++;
        } while (true);
        enc_queue_push(&s_queue, &e);
        prune_battles_locked();
        s_w.pending = s_queue.count;
        s_dirty = true;
        unlock_encounter_change();
        (*made)++;
        sfx_encounter(e.rarity, e.is_shiny);
    }

    ESP_LOGI(TAG, "遭遇 #%u ★%u%s（%s）队列 %u",
             e.species_id, e.rarity, e.is_shiny ? " 闪光!" : "",
             transient ? "猎场" : "基地", s_queue.count);
}

static uint8_t refresh_from_scan(bool exploring,uint16_t distance_q10)
{
    // Snapshot + atomic commit: refresh progress, cooldowns, pity and queue
    // become visible together. A reset cannot show an uncommitted boot gift.
    for(unsigned i=0;i<s_last_n;i++) {
        memcpy(s_refresh_aps[i].bssid,s_recs[i].bssid,6);
        s_refresh_aps[i].rssi=s_recs[i].rssi;
        s_refresh_aps[i].auth=(uint8_t)s_recs[i].authmode;
        s_refresh_aps[i].has_ssid=s_recs[i].ssid[0]!=0;
    }
    uint8_t made=0;
    if(lock_encounter_change()) {
        refresh_clock_locked();
        if(s_storage_ready && !s_starter_pending) {
            collect_save_locked(&s_save_buf);
            made=enc_refresh_collect(&s_save_buf.refresh,s_refresh_aps,s_last_n,
                exploring,distance_q10,EXPLORATION_CAPACITY-s_exploration.energy);
            s_save_buf.exploration.energy+=made;
            if(made || s_save_buf.refresh.hunt_q10!=s_refresh.hunt_q10) {
                xSemaphoreGive(s_lock);
                bool saved=save_write(&s_save_buf);
                xSemaphoreTake(s_lock,portMAX_DELAY);
                if(saved) {
                    s_refresh=s_save_buf.refresh;
                    s_exploration=s_save_buf.exploration;
                    s_last_save_us=esp_timer_get_time();
                } else {made=0;ESP_LOGW(TAG,"exploration credit save failed; no credit published");}
            } else s_refresh=s_save_buf.refresh;
        }
        s_dirty=true;
        unlock_encounter_change();
    }
    // Banked chances are intentionally quiet: rare/shiny alerts only happen
    // when the player reveals an actual Pokémon in the exploration page.
    return made;
}

// 一次扫描 + 喂给 sensing + 更新状态。
static void scan_once(void)
{
    // 阻塞式扫描（第二个参数 true）—— 我们在自己的任务里，
    // 阻塞 1.4 秒不影响任何人。Collect 页当年必须用非阻塞 +
    // 事件回调，正是因为它跑在 LVGL 任务里。
    if (esp_wifi_scan_start(NULL, true) != ESP_OK) return;

    uint16_t n = MAX_APS;
    if (esp_wifi_scan_get_ap_records(&n, s_recs) != ESP_OK) return;
    if (n == 0) return;
    s_last_n = (n < MAX_APS) ? n : MAX_APS;

    for (uint16_t i = 0; i < n && i < MAX_APS; i++) {
        memcpy(s_aps[i].bssid, s_recs[i].bssid, 6);
        s_aps[i].rssi = s_recs[i].rssi;
        s_aps[i].channel = s_recs[i].primary;
        s_aps[i].auth = (uint8_t)s_recs[i].authmode;
    }

    sens_result_t r;
    uint32_t ts = (uint32_t)(esp_timer_get_time() / 1000000);
    sens_feed(&s_core, ts, s_aps, (uint8_t)n, &r);

    refresh_from_scan(r.state==SENS_MOVING && r.transient_aps>0,r.distance);

    if (lock_encounter_change()) {
        if (r.state == SENS_MOVING) {
            s_motion_q10 += r.distance;
            if (!s_starter_pending) {
                if (s_w.explore_value < UINT16_MAX) s_w.explore_value++;
                int32_t happier = s_w.pet.mood + 2 * NURT_Q;
                s_w.pet.mood = happier > NURT_MAX ? NURT_MAX : happier;
                sync_leader_locked();
            }
        }
        s_w.state = r.state;
        s_w.place_id = r.place_id;
        s_w.progress = world_progress_from_motion(s_motion_q10);
        s_w.scans++;
        s_w.last_ap_count = (uint8_t)n;
        s_dirty = true;
        unlock_encounter_change();
    }

    emit_ndjson(n);
}

static void world_task(void *arg)
{
    (void)arg;
    int64_t next_scan = 0;

    for (;;) {
        int64_t now = esp_timer_get_time();

        // 养成结算。**放在这里而不是页面的 tick 里** ——
        // 页面切换不该影响宠物的时间流逝，而且 P1 不在前台时
        // 它的 lv_timer 根本不跑。
        if (lock_encounter_change()) {
            refresh_clock_locked();
            // is_night 仍写死 false —— 判夜要墙钟时间，现在只有开机微秒数。
            // 等 S10 日切接上 RTC 一起做。
            if (!s_starter_pending) nurture_tick(&s_w.pet, now, 0, false);
            unlock_encounter_change();
        }

        if (s_wifi_ok && now >= next_scan) {
            scan_once();
            next_scan = esp_timer_get_time() + SCAN_INTERVAL_MS * 1000LL;
        }

        // 节流存档 —— 见 SAVE_INTERVAL_US 上方的说明
        bool save_due = false;
        if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
            save_due = s_dirty && now - s_last_save_us >= SAVE_INTERVAL_US;
            xSemaphoreGive(s_lock);
        }
        if (save_due) save_now("定时");

        // 1 秒一轮。养成结算需要这个频率（nurture 按时长算，
        // 频率只影响响应粒度不影响正确性），扫描自己看时间。
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

bool world_debug_spawn(void)
{
    if (s_last_n == 0) {
        ESP_LOGW(TAG, "还没扫到 AP —— 等第一次扫描完成");
        return false;
    }
    uint8_t made = 0;
    spawn_one((uint32_t)(esp_timer_get_time() / 1000000), true, &made);
    if (made && s_lock &&
        xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        s_w.pending = s_queue.count;
        xSemaphoreGive(s_lock);
    }
    return made > 0;
}

void world_debug_save(void)
{
    save_now("手动");
}

#ifdef CONFIG_POKEWALK_DEBUG_KEYS
bool world_debug_evolution_ready(void)
{
    bool ready = false;
    uint8_t need_intimacy = 0;
    uint16_t need_explore = 0;
    if (lock_encounter_change()) {
        mon_t *leader = s_party.party_count ? &s_party.party[0] : NULL;
        species_t sp;
        evo_check_t check;
        if (leader && assets_species(leader->species_id, &sp)) {
            evo_check(0, 0, sp.evolve_trigger, sp.evolve_to,
                      sp.evolve_level, &check);
            if (sp.evolve_to && sp.evolve_to <= BOX_SPECIES &&
                sp.evolve_trigger != EVO_TRIGGER_NONE) {
                need_intimacy = check.need_intimacy;
                need_explore = check.need_explore;
                s_w.pet.intimacy = need_intimacy * NURT_Q;
                s_w.explore_value = need_explore;
                sync_leader_locked();
                s_dirty = true;
                ready = true;
            }
        }
        unlock_encounter_change();
    }
    if (ready) {
        ESP_LOGI(TAG, "@@EVOLVE_READY intimacy=%u explore=%u",
                 need_intimacy, need_explore);
    }
    return ready;
}
#endif

bool world_wifi_ready(void) { return s_wifi_ok; }

static bool saved_bool_valid(const bool *value)
{
    const bool no = false, yes = true;
    // Read the representation as bytes: evaluating a malformed persisted _Bool
    // before validation would itself be undefined behavior.
    return memcmp(value, &no, sizeof(no)) == 0 ||
           memcmp(value, &yes, sizeof(yes)) == 0;
}

static bool loaded_queue_valid(const enc_queue_t *queue)
{
    if (queue->count > ENC_QUEUE_CAP) return false;
    for (unsigned i = 0; i < queue->count; i++) {
        const encounter_t *entry = &queue->items[i];
        if (!entry->uid || entry->species_id < 1 || entry->species_id > DEX_SPECIES ||
            entry->rarity < 1 || entry->rarity > 5 || entry->hp_ratio > 100 ||
            !saved_bool_valid(&entry->is_shiny) ||
            !saved_bool_valid(&entry->is_transient) ||
            !saved_bool_valid(&entry->exp_granted)) return false;
        for (unsigned prior = 0; prior < i; prior++)
            if (queue->items[prior].uid == entry->uid) return false;
    }
    // next_uid == 0 is the valid state immediately after assigning UINT16_MAX.
    // Removed entries leave stale tail bytes; only the active prefix is owned.
    return true;
}

static bool migrate_loaded_queue(enc_queue_t *queue)
{
    bool changed = false;
    // Old V5 stored fought targets in the pending queue. These fields prove
    // an encounter was processed; remove them instead of offering another fight.
    // A legacy full-HP encounter with no EXP mark cannot reveal a missed attack.
    for (uint8_t i = 0; i < queue->count;) {
        if (queue->items[i].hp_ratio < 100 || queue->items[i].exp_granted) {
            enc_queue_take(queue, i, NULL);
            changed = true;
        } else i++;
    }
    return enc_queue_trim(queue) != 0 || changed;
}

static bool loaded_party_valid(const save_t *saved)
{
    const uint8_t *raw = saved->party;
    if (raw[0] > PARTY_MAX) return false;
    uint8_t box_count = 0;
    for (unsigned i = 0; i < PARTY_MAX + BOX_SPECIES; i++) {
        const uint8_t *mon = raw + 2 + i*MON_BYTES;
        bool active = i < PARTY_MAX ? i < raw[0] : mon[0] != 0;
        if (!active) {
            for (unsigned b = 0; b < MON_BYTES; b++) if (mon[b] != 0) return false;
        } else {
            if (mon[0] < 1 || mon[0] > BOX_SPECIES || mon[1] < 1 || mon[1] > LEVEL_MAX)
                return false;
            if (i >= PARTY_MAX) {
                // party_deserialize relocates valid box IDs and drops invalid
                // ones; reject either case before those bytes can be rewritten.
                if (mon[0] != i - PARTY_MAX + 1) return false;
                box_count++;
            }
        }
    }
    if (raw[1] != box_count ||
        !party_deserialize(&s_party, raw, sizeof(saved->party))) return false;
    if (!s_party.party_count) {
        // Empty V5 snapshots are produced while a fresh game awaits a choice.
        // An absent leader with prior ownership/progress is not a new game.
        for (unsigned i = 0; i < DEX_BYTES; i++)
            if (saved->dex.caught[i] || saved->dex.shiny_caught[i]) return false;
        return party_total(&s_party) == 0 && saved->species == 0 &&
               saved->level == 0 && saved->exp == 0;
    }
    return true;
}

bool world_start(void)
{
    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) {
        ESP_LOGE(TAG, "互斥锁创建失败");
        return false;
    }
    s_save_lock = xSemaphoreCreateMutex();
    if (!s_save_lock) {
        ESP_LOGE(TAG, "save mutex create failed");
        return false;
    }

    memset(&s_w, 0, sizeof(s_w));
    memset(&s_challenge, 0, sizeof(s_challenge));
    memset(&s_achievements, 0, sizeof(s_achievements));
    nurture_init(&s_w.pet);
    party_init(&s_party);
    items_inventory_init(&s_inventory);
    s_starter_pending = true;
    s_storage_ready = false;
    s_motion_q10 = 0;
    memset(&s_refresh,0,sizeof(s_refresh));
    exploration_init(&s_exploration);
    s_refresh_clock_us=esp_timer_get_time();
    s_dirty = false;
    s_last_save_us = 0;
    memset(s_battles, 0, sizeof(s_battles));
    memset(&s_active, 0, sizeof(s_active));
    enc_queue_init(&s_queue);
    dex_init(&s_dex);
    sens_init(&s_core);

    // 读档。没有存档就用刚才那份初始状态（新游戏）。
    //
    // **不恢复 nurture 的 last_us** —— 它是上次开机的微秒数，
    // 而本次开机从 0 重新计。直接沿用会让 dt 变成巨大的负数，
    // nurture_tick 里 `dt <= 0` 会挡住，但那等于「时间不流动」。
    // 置 -1 让它下一拍重新起算（与首次开机同）。
    // 代价是**关机期间不衰减** —— 那要墙钟时间，S10 日切一起做。
    // **先初始化 NVS 再读档** —— 这条依赖搞反过一次：
    // nvs_flash_init 当时藏在 wifi_bring_up 里，而那个在读档之后，
    // 结果每次开机都是「新游戏」而存档其实写成功了。
    save_read_result_t loaded = save_init() ? save_read_status(&s_save_buf) : SAVE_READ_ERROR;
    bool migrated = loaded == SAVE_READ_MIGRATED;
    if ((loaded == SAVE_READ_OK || migrated) &&
        (!loaded_queue_valid(&s_save_buf.queue) || !loaded_party_valid(&s_save_buf))) {
        loaded = SAVE_READ_ERROR;
        party_init(&s_party);
        ESP_LOGE(TAG, "invalid saved party or queue; preserving save and disabling writes");
    }
    s_storage_ready = loaded != SAVE_READ_ERROR;
    if (loaded == SAVE_READ_OK || loaded == SAVE_READ_MIGRATED) {
        uint16_t exp_repaired = normalize_party_exp(&s_party);
        s_w.pet = s_save_buf.pet;
        s_w.pet.last_us = -1;
        const mon_t *leader = party_leader(&s_party);
        if (leader) {
            s_w.species = leader->species_id;
            s_w.exp = leader->exp;
            s_w.level = leader->level;
            s_w.explore_value = leader->explore_value;
            s_starter_pending = false;
        }
        s_queue = s_save_buf.queue;
        // Validate all 16 legacy slots before filtering; malformed old bytes
        // must remain protected, not be hidden by the new five-entry limit.
        s_dirty = migrate_loaded_queue(&s_queue) || migrated || exp_repaired != 0;
        s_inventory = s_save_buf.inventory;
        s_challenge = s_save_buf.challenge;
        s_achievements = s_save_buf.achievements;
        s_dex = s_save_buf.dex;
        s_motion_q10 = s_save_buf.motion_q10;
        s_refresh=s_save_buf.refresh;
        s_exploration=s_save_buf.exploration;
        s_refresh_clock_us=esp_timer_get_time();
        s_w.scans = s_save_buf.scans;
        s_w.pending = s_queue.count;
        s_w.progress = world_progress_from_motion(s_motion_q10);
        ESP_LOGI(TAG, "读档：图鉴 %u/%u 队列 %u 行程 %u%% party %u total %u",
                 dex_count_caught(&s_dex), DEX_SPECIES,
                 s_queue.count, s_w.progress, s_party.party_count,
                 party_total(&s_party));
        if (exp_repaired) {
            ESP_LOGI(TAG, "reconciled EXP curve/baseline for %u members", exp_repaired);
            // Repair all members on load, not only whichever one is selected
            // later. A failed commit leaves the original bytes and dirty retry.
            save_now("legacy_experience");
        } else if (migrated) {
            save_now("refresh_migration");
        }
    } else if (loaded == SAVE_READ_EMPTY) {
        ESP_LOGI(TAG, "no save; waiting for starter selection");
    } else {
        memset(&s_inventory, 0, sizeof(s_inventory));
        ESP_LOGE(TAG, "save unavailable; new-game writes disabled to preserve existing data");
    }

    esp_err_t err = wifi_bring_up();
    s_wifi_ok = (err == ESP_OK);
    if (!s_wifi_ok) {
        // WiFi 起不来不是致命的 —— 养成照常走，只是没有感知数据。
        // 页面能画，玩家看得出行程不涨。
        ESP_LOGE(TAG, "WiFi 起不来: %s —— 感知停摆，养成照常",
                 esp_err_to_name(err));
    }

    // 4096 栈：大数组都是 static，栈上只有指针与循环变量。
    // 优先级 4 —— 低于 LVGL（5），扫描不该抢画面的 CPU。
    BaseType_t ok = xTaskCreate(world_task, "world", 4096, NULL, 4, NULL);
    if (ok != pdPASS) {
        ESP_LOGE(TAG, "任务创建失败");
        return false;
    }

    ESP_LOGI(TAG, "后台任务已起（扫描 %d 秒/次，行程满格 %d 移动量）",
             SCAN_INTERVAL_MS / 1000, PROGRESS_FULL_Q10 / 1024);
    return true;
}


void world_challenge_snapshot(trainer_store_t *out)
{
    if (!out) return;
    memset(out, 0, sizeof(*out));
    if (!s_lock || xSemaphoreTake(s_lock, portMAX_DELAY) != pdTRUE) return;
    *out = s_challenge;
    xSemaphoreGive(s_lock);
}

// Called with both locks. Preserve world updates made while flash is writing;
// only campaign/explicit reward fields are published from this transaction.
static bool challenge_commit(bool reward, bool inventory_changed)
{
    xSemaphoreGive(s_lock);
    bool ok = save_write(&s_save_buf);
    xSemaphoreTake(s_lock, portMAX_DELAY);
    if (ok) {
        s_challenge = s_save_buf.challenge;
        s_achievements = s_save_buf.achievements;
        if (inventory_changed) s_inventory = s_save_buf.inventory;
        if (reward) {
            s_party = s_starter_party;
            const mon_t *leader = party_leader(&s_party);
            s_w.exp = leader->exp;
            s_w.level = leader->level;
        }
        s_last_save_us = esp_timer_get_time();
    }
    unlock_encounter_change();
    return ok;
}

bool world_challenge_begin(uint8_t id)
{
    if (!lock_encounter_change()) return false;
    if (!s_storage_ready || s_starter_pending || s_active.encounter.uid) { unlock_encounter_change(); return false; }
    collect_save_locked(&s_save_buf);
    if (!trainer_begin(&s_save_buf.challenge, id, s_party.party, s_party.party_count,
                       nurture_ability_factor(&s_w.pet), (uint32_t)esp_timer_get_time())) {
        unlock_encounter_change(); return false;
    }
    return challenge_commit(false, false);
}

bool world_challenge_step(trainer_event_t *out)
{
    if (!out || !lock_encounter_change()) return false;
    if (!s_storage_ready) { unlock_encounter_change(); return false; }
    collect_save_locked(&s_save_buf);
    trainer_event_t candidate;
    if (!trainer_step(&s_save_buf.challenge, &candidate)) { unlock_encounter_change(); return false; }
    bool ok = challenge_commit(false, false);
    if (ok) *out = candidate;
    return ok;
}

bool world_challenge_move(uint8_t slot)
{
    if (!lock_encounter_change()) return false;
    collect_save_locked(&s_save_buf);
    if (!s_storage_ready || !trainer_choose_move(&s_save_buf.challenge, slot)) { unlock_encounter_change(); return false; }
    return challenge_commit(false, false);
}

bool world_challenge_switch(uint8_t slot, bool forced)
{
    if (!lock_encounter_change()) return false;
    collect_save_locked(&s_save_buf);
    if (!s_storage_ready || !trainer_switch(&s_save_buf.challenge, slot, forced)) { unlock_encounter_change(); return false; }
    return challenge_commit(false, false);
}

bool world_challenge_retire(void)
{
    if (!lock_encounter_change()) return false;
    if (!s_storage_ready || !s_challenge.session.active) { unlock_encounter_change(); return false; }
    collect_save_locked(&s_save_buf);trainer_retire(&s_save_buf.challenge);
    return challenge_commit(false, false);
}

bool world_challenge_settle(void)
{
    if (!lock_encounter_change()) return false;
    if (!s_challenge.session.active) { unlock_encounter_change(); return true; }
    if (!s_storage_ready || !s_challenge.session.finished) { unlock_encounter_change(); return false; }
    collect_save_locked(&s_save_buf);
    uint16_t reward = exp_scaled(trainer_reward(&s_challenge),nurture_exp_percent(&s_w.pet));
    s_starter_party = s_party;
    unsigned participants = 0;
    for (unsigned i=0;i<s_party.party_count;i++) participants += !!(s_challenge.session.participated & (1u<<i));
    if (reward && participants) {
        unsigned remainder=reward%participants;
        for (unsigned i=0;i<s_starter_party.party_count;i++) if (s_challenge.session.participated & (1u<<i)) {
            mon_t *m=&s_starter_party.party[i];uint32_t amount=reward/participants;
            if(remainder){amount++;remainder--;}
            if(m->exp<exp_for_level(m->level))m->exp=exp_for_level(m->level);
            m->exp = m->exp>UINT32_MAX-amount?UINT32_MAX:m->exp+amount;
            m->level=exp_to_level(m->exp, LEVEL_MAX);
        }
    }
    exp_share_party(&s_starter_party,((1u<<s_starter_party.party_count)-1)&~s_challenge.session.participated,reward);
    party_serialize(&s_starter_party, s_save_buf.party);
    s_save_buf.exp=s_starter_party.party[0].exp;s_save_buf.level=s_starter_party.party[0].level;
    bool first = !(s_challenge.defeated & (1u<<s_challenge.session.trainer));
    if (s_challenge.session.won && first) {
        unsigned milk=s_save_buf.inventory.quantity[ITEM_MILK]+2;
        s_save_buf.inventory.quantity[ITEM_MILK]=milk>items_capacity(ITEM_MILK)?items_capacity(ITEM_MILK):milk;
    }
    uint8_t prize=trainer_rematch_prize(&s_challenge);
    if(prize!=ITEM_NONE&&s_save_buf.inventory.quantity[prize]<items_capacity(prize))s_save_buf.inventory.quantity[prize]++;
    if (!s_challenge.session.won && !s_challenge.session.retired) {
        s_save_buf.pet.stamina = s_save_buf.pet.stamina>20*NURT_Q?s_save_buf.pet.stamina-20*NURT_Q:0;
        s_save_buf.pet.mood = s_save_buf.pet.mood>15*NURT_Q?s_save_buf.pet.mood-15*NURT_Q:0;
    }
    trainer_settle(&s_save_buf.challenge);
    // Apply defeat to current nurture only after the campaign/result commit.
    bool defeat = !s_challenge.session.won && !s_challenge.session.retired;
    xSemaphoreGive(s_lock);
    bool ok=save_write(&s_save_buf);
    xSemaphoreTake(s_lock,portMAX_DELAY);
    if(ok) {
        s_challenge=s_save_buf.challenge;s_party=s_starter_party;s_inventory=s_save_buf.inventory;
        s_w.exp=s_save_buf.exp;s_w.level=s_save_buf.level;
        if(defeat) {
            s_w.pet.stamina=s_w.pet.stamina>20*NURT_Q?s_w.pet.stamina-20*NURT_Q:0;
            s_w.pet.mood=s_w.pet.mood>15*NURT_Q?s_w.pet.mood-15*NURT_Q:0;
        }
        s_last_save_us=esp_timer_get_time();
    }
    unlock_encounter_change();return ok;
}

bool world_challenge_recover(uint8_t slot)
{
    if (!lock_encounter_change()) return false;
    if (!s_storage_ready || !s_inventory.quantity[ITEM_MILK] ||
        !(s_challenge.session.active || s_challenge.league_active) ||
        slot>=s_challenge.session.sides[0].count) { unlock_encounter_change(); return false; }
    collect_save_locked(&s_save_buf);
    trainer_mon_t *m=&s_save_buf.challenge.session.sides[0].mons[slot];
    if(!m->hp || (m->hp==m->max_hp&&!m->status)) { unlock_encounter_change(); return false; }
    unsigned hp=m->hp+50;m->hp=hp>m->max_hp?m->max_hp:hp;m->status=m->sleep=0;
    s_save_buf.inventory.quantity[ITEM_MILK]--;
    if(s_save_buf.challenge.session.active){s_save_buf.challenge.session.next=1;s_save_buf.challenge.session.acted=1;}
    return challenge_commit(false, true);
}

void world_achievements_snapshot(achievement_view_t *out)
{
    if (!out) return;
    memset(out,0,sizeof(*out));
    if (!s_lock || xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE) return;
    achievement_view(out,&s_achievements,&s_dex,s_challenge.defeated);
    xSemaphoreGive(s_lock);
}
achievement_claim_t world_achievement_claim(unsigned id)
{
    if (!lock_encounter_change()) return ACH_CLAIM_FAILED;
    if (!s_storage_ready || s_starter_pending) { unlock_encounter_change(); return ACH_CLAIM_FAILED; }
    collect_save_locked(&s_save_buf);
    achievement_view_t view;
    achievement_view(&view,&s_achievements,&s_dex,s_challenge.defeated);
    achievement_claim_t result=achievement_claim(&s_save_buf.achievements,&s_save_buf.inventory,&view,id);
    if (result!=ACH_CLAIM_OK) { unlock_encounter_change(); return result; }
    s_dirty=false;
    xSemaphoreGive(s_lock);
    bool ok=save_write(&s_save_buf);
    xSemaphoreTake(s_lock,portMAX_DELAY);
    if (ok) {
        s_achievements=s_save_buf.achievements;
        s_inventory=s_save_buf.inventory;
        s_last_save_us=esp_timer_get_time();
    } else s_dirty=true;
    unlock_encounter_change();
    return ok?ACH_CLAIM_OK:ACH_CLAIM_FAILED;
}


void world_exploration_snapshot(exploration_view_t *out)
{
    if(!out)return;
    memset(out,0,sizeof(*out));
    if(!s_lock||xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE)return;
    out->state=s_exploration;out->discoveries=s_refresh.discoveries;out->defeated=s_challenge.defeated;
    out->rare_left=8-s_refresh.since_rare;out->elite_left=30-s_refresh.since_elite;
    out->pending=s_queue.count;out->stamina=nurture_pct(s_w.pet.stamina);out->exp_percent=nurture_exp_percent(&s_w.pet);out->rare_bonus=nurture_rare_bonus(&s_w.pet);out->party_bonus=exploration_team_bonus(&s_party,s_exploration.route);
    xSemaphoreGive(s_lock);
}
exploration_kind_t world_exploration_select(uint8_t route)
{
    if(route>=EXPLORATION_ROUTES)return EXPLORE_BLOCKED;
    if(!lock_encounter_change())return EXPLORE_SAVE_FAILED;
    if(!s_storage_ready||s_starter_pending){unlock_encounter_change();return EXPLORE_SAVE_FAILED;}
    if(s_active.encounter.uid||s_challenge.session.active||s_challenge.league_active){unlock_encounter_change();return EXPLORE_BUSY;}
    if(s_exploration.route==route){unlock_encounter_change();return EXPLORE_NONE;}
    collect_save_locked(&s_save_buf);s_save_buf.exploration.route=route;
    xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
    if(ok){s_exploration=s_save_buf.exploration;s_last_save_us=esp_timer_get_time();}
    else s_dirty=true;
    unlock_encounter_change();return ok?EXPLORE_NONE:EXPLORE_SAVE_FAILED;
}
exploration_kind_t world_exploration_track(uint16_t species)
{
 int route=exploration_habitat(species,NULL);
 if(species&&route<0)return EXPLORE_BLOCKED;
 if(!lock_encounter_change())return EXPLORE_SAVE_FAILED;
 if(!s_storage_ready||s_starter_pending){unlock_encounter_change();return EXPLORE_SAVE_FAILED;}
 if(s_active.encounter.uid||s_challenge.session.active||s_challenge.league_active){unlock_encounter_change();return EXPLORE_BUSY;}
 if(species&&!exploration_species_open(species,s_challenge.defeated)){unlock_encounter_change();return EXPLORE_BLOCKED;}
 collect_save_locked(&s_save_buf);
 exploration_state_t *x=&s_save_buf.exploration;
 if(x->tracked_species!=species){
  // A new target must earn its own trail; switching cannot spend another trail.
  if(x->tracked_species){int old=exploration_habitat(x->tracked_species,NULL);if(old>=0){x->clues[old]=0;x->pulse[old]=0;}}
  if(species){x->clues[route]=0;x->pulse[route]=0;}
 }
 x->tracked_species=species;if(species)x->route=route;
 xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
 if(ok){s_exploration=s_save_buf.exploration;s_last_save_us=esp_timer_get_time();}
 unlock_encounter_change();return ok?EXPLORE_NONE:EXPLORE_SAVE_FAILED;
}
exploration_event_t world_explore(void)
{
    exploration_event_t event={.kind=EXPLORE_SAVE_FAILED};
    if(!lock_encounter_change())return event;
    if(!s_storage_ready||s_starter_pending){unlock_encounter_change();return event;}
    if(s_active.encounter.uid||s_challenge.session.active||s_challenge.league_active) {
        event.kind=EXPLORE_BUSY;unlock_encounter_change();return event;
    }
    collect_save_locked(&s_save_buf);
    if(s_w.pet.stamina<NURT_EXPLORE_COST){event.kind=EXPLORE_NO_STAMINA;unlock_encounter_change();return event;}
    event=exploration_step_team(&s_save_buf.exploration,&s_save_buf.refresh,&s_save_buf.queue,&s_save_buf.dex,s_active.encounter.uid,s_challenge.defeated,&s_save_buf.inventory,&s_w.pet,exploration_team_bonus(&s_party,s_exploration.route));
    if(event.kind!=EXPLORE_ENCOUNTER&&event.kind!=EXPLORE_CLUE&&event.kind!=EXPLORE_TARGET) {
        unlock_encounter_change();return event;
    }
    s_save_buf.pet.stamina-=NURT_EXPLORE_COST;
    // Map discoveries advance the same individual exploration stat as walking.
    // Serialize the candidate first: failed storage must not advance evolution.
    s_starter_party=s_party;
    if(s_starter_party.party[0].explore_value<UINT16_MAX)s_starter_party.party[0].explore_value++;
    party_serialize(&s_starter_party,s_save_buf.party);
    xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
    if(ok) {
        s_w.pet.stamina=s_w.pet.stamina>NURT_EXPLORE_COST?s_w.pet.stamina-NURT_EXPLORE_COST:0;
        s_exploration=s_save_buf.exploration;s_refresh=s_save_buf.refresh;s_queue=s_save_buf.queue;s_inventory=s_save_buf.inventory;
        if(s_w.explore_value<UINT16_MAX)s_w.explore_value++;
        sync_leader_locked();
        if(event.species)dex_mark_seen(&s_dex,event.species,event.shiny);
        s_w.pending=s_queue.count;prune_battles_locked();s_last_save_us=esp_timer_get_time();
    } else {event.kind=EXPLORE_SAVE_FAILED;s_dirty=true;}
    unlock_encounter_change();
    if(ok&&event.species)sfx_encounter(event.rarity,event.shiny);
    return event;
}

bool world_battle_reward_uid(uint16_t uid,uint16_t *amount) {
 if(amount)*amount=0;
 if(!lock_encounter_change())return false;
 battle_session_t *b=&s_active.session;
 if(!s_storage_ready||s_starter_pending||s_active.encounter.uid!=uid||!b->finished){unlock_encounter_change();return false;}
 if(b->reward_settled||s_active.encounter.exp_granted){unlock_encounter_change();return true;}
 uint16_t gain=exp_scaled(battle_session_exp(b),nurture_exp_percent(&s_w.pet));
 collect_save_locked(&s_save_buf);s_starter_party=s_party;
 mon_t *leader=&s_starter_party.party[0];leader->exp=leader->exp>UINT32_MAX-gain?UINT32_MAX:leader->exp+gain;
 leader->level=exp_to_level(leader->exp,LEVEL_MAX);exp_share_party(&s_starter_party,((1u<<s_starter_party.party_count)-1)&~1u,gain);party_serialize(&s_starter_party,s_save_buf.party);
 s_save_buf.exp=leader->exp;s_save_buf.level=leader->level;
 xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
 if(ok){s_party=s_starter_party;s_w.exp=s_save_buf.exp;s_w.level=s_save_buf.level;
  s_active.session.reward_settled=true;s_active.encounter.exp_granted=true;s_last_save_us=esp_timer_get_time();if(amount)*amount=gain;}
 else s_dirty=true;
 unlock_encounter_change();return ok;
}

void world_box_snapshot(mon_t out[BOX_SPECIES]){
 if(!out)return;
 memset(out,0,BOX_SPECIES*sizeof(mon_t));
 if(!s_lock||xSemaphoreTake(s_lock,portMAX_DELAY)!=pdTRUE)return;
 memcpy(out,s_party.box,sizeof(s_party.box));xSemaphoreGive(s_lock);
}
world_switch_result_t world_box_exchange(uint8_t slot,const mon_t *outgoing,const mon_t *incoming){
 if(!outgoing||!incoming||slot>=PARTY_MAX||incoming->species_id<1||incoming->species_id>BOX_SPECIES)return WORLD_SWITCH_INVALID;
 mon_t old=*outgoing,in=*incoming;
 if(!lock_encounter_change())return WORLD_SWITCH_STORAGE_UNAVAILABLE;
 if(!s_storage_ready||s_starter_pending){unlock_encounter_change();return WORLD_SWITCH_STORAGE_UNAVAILABLE;}
 if(s_active.encounter.uid||s_challenge.session.active||s_challenge.league_active){unlock_encounter_change();return WORLD_SWITCH_BUSY;}
 mon_t actual=slot?s_party.party[slot]:leader_view_locked();
 if(slot>=s_party.party_count||memcmp(&old,&actual,sizeof(old))||memcmp(&in,&s_party.box[in.species_id-1],sizeof(in))){unlock_encounter_change();return WORLD_SWITCH_STALE;}
 collect_save_locked(&s_save_buf);s_starter_party=s_party;
 if(!party_exchange(&s_starter_party,slot,in.species_id)){unlock_encounter_change();return WORLD_SWITCH_INVALID;}
 normalize_party_exp(&s_starter_party);mon_t next=s_starter_party.party[0];
 party_serialize(&s_starter_party,s_save_buf.party);s_save_buf.species=next.species_id;s_save_buf.level=next.level;s_save_buf.exp=next.exp;
 if(!slot)s_save_buf.pet.intimacy=next.intimacy*NURT_Q;
 xSemaphoreGive(s_lock);bool ok=save_write(&s_save_buf);xSemaphoreTake(s_lock,portMAX_DELAY);
 if(ok){s_party=s_starter_party;s_w.species=next.species_id;s_w.level=next.level;s_w.exp=next.exp;
  if(!slot){s_w.pet.intimacy=next.intimacy*NURT_Q;s_w.explore_value=next.explore_value;}
  memset(s_battles,0,sizeof(s_battles));s_last_save_us=esp_timer_get_time();}
 else s_dirty=true;
 unlock_encounter_change();return ok?WORLD_SWITCH_OK:WORLD_SWITCH_SAVE_FAILED;
}
