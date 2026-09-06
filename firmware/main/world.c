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

// 扫描结果。**static** —— 64 × 76 字节放栈上必炸（见文件头）。
static wifi_ap_record_t s_recs[MAX_APS];
static sens_ap_t s_aps[MAX_APS];
static uint16_t s_last_n;   // 最近一次扫到几个，spawn_one 要用

// 移动量累积，Q10。今日行程由它映射。
static uint32_t s_motion_q10;

// 感知核心。**static** —— sens_core_t 有 2.6KB，放栈上会炸
// （这正是当年 Guru Meditation 的原因，见 sensing.c 顶部）。
static sens_core_t s_core;

// 遭遇队列（128 B）与图鉴（76 B）。这两个是玩法的真状态，
// 存档时要落盘（S18，还没接）。
static enc_queue_t s_queue;
static dex_t s_dex;
static party_t s_party;

// save_t 含 1886 B 队伍区，不能放进 4 KiB 的 world task 栈。
static save_t s_save_buf;

// 猎场遭遇的移动量闸门，Q10。攒够 HUNT_COST 出一只。
//
// 没有闸门的话一趟通勤能刷出几十只 —— 实测 26 分钟通勤累计移动量 9.3，
// 而每次扫描只要在移动就产出一只的话是 16 只。用移动量做闸门
// 让「走得多遇得多」成立，同时密度可控（sim/systems.py:36 记的同一件事）。
#define HUNT_COST_Q10 1024        // 1.0 移动量 = 一只
static uint32_t s_hunt_pool;

// 基地遭遇：按**时间**排程，不看移动量。
//
// 这条不能省：窝在家里一整天移动量近乎 0，若只有猎场路径就毫无产出，
// 而「设备永远不会没东西可看」是 docs/02-sensing.md#20 要保证的事。
#define BASE_INTERVAL_S (4 * 3600)

// **初值必须是「不可能的桶号」而不是 0**。
// sim 那边用 -1；这里是无符号，用 UINT32_MAX 达到同一效果。
//
// 写成 0 的话开机头 4 小时（ts/14400 == 0）第一次基地遭遇会被抑制 ——
// 与 sim 的行为正好相反（那边第一次扫描必定出一只）。
// 而表现只是「开机后要等 4 小时才有第一只」，很容易当成设计如此。
static uint32_t s_last_base_bucket = UINT32_MAX;

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
static bool s_dirty;

static void init_default_party(void)
{
    party_init(&s_party);
    mon_t starter = {
        .species_id = 25,
        .level = exp_to_level(0, LEVEL_MAX),
        .hp = 100,
        .nickname_idx = 0xFF,
    };
    party_receive(&s_party, &starter);
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
}

// 状态锁内只生成不可变快照，真正的 NVS 写入在锁外。
// 独立的保存锁保证两个任务不会复用 s_save_buf，也不会让旧快照后写覆盖新快照。
static bool save_now(const char *why)
{
    if (!s_lock || !s_save_lock) return false;
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

const enc_queue_t *world_queue(void) { return &s_queue; }
const dex_t *world_dex(void) { return &s_dex; }

bool world_capture_uid(uint16_t uid, const mon_t *mon)
{
    if (!mon || mon->species_id < 1 || mon->species_id > BOX_SPECIES) {
        return false;
    }

    bool committed = false;
    uint8_t party_count = 0;
    uint16_t total = 0;
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        encounter_t *e = enc_queue_find(&s_queue, uid);
        if (e && e->species_id == mon->species_id &&
            party_receive(&s_party, mon) && enc_queue_take_uid(&s_queue, uid, NULL)) {
            dex_mark_caught(&s_dex, mon->species_id, (mon->flags & 1u) != 0);
            s_w.pending = s_queue.count;
            s_dirty = true;
            party_count = s_party.party_count;
            total = party_total(&s_party);
            committed = true;
        }
        xSemaphoreGive(s_lock);
    }

    if (committed) {
        ESP_LOGI(TAG, "@@PARTY receive #%u party=%u total=%u",
                 mon->species_id, party_count, total);
        // 收容、图鉴和出队已一起进入快照，只做一次关键事件落盘。
        save_now("捕获");
    }
    return committed;
}

bool world_take_encounter(uint8_t index, encounter_t *out)
{
    bool ok = false;
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        ok = enc_queue_take(&s_queue, index, out);
        s_w.pending = s_queue.count;
        s_dirty = true;
        xSemaphoreGive(s_lock);
    }
    return ok;
}

bool world_take_uid(uint16_t uid, encounter_t *out)
{
    bool ok = false;
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        ok = enc_queue_take_uid(&s_queue, uid, out);
        s_w.pending = s_queue.count;
        s_dirty = true;
        xSemaphoreGive(s_lock);
    }
    return ok;
}

void world_update_hp_uid(uint16_t uid, uint8_t hp_ratio)
{
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        encounter_t *e = enc_queue_find(&s_queue, uid);
        if (e) e->hp_ratio = hp_ratio;
        xSemaphoreGive(s_lock);
    }
}

bool world_mark_exp_granted_uid(uint16_t uid)
{
    bool marked = false;
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        encounter_t *e = enc_queue_find(&s_queue, uid);
        if (e && !e->exp_granted) {
            e->exp_granted = true;
            s_dirty = true;
            marked = true;
        }
        xSemaphoreGive(s_lock);
    }
    return marked;
}

void world_mark_seen(uint16_t sid, bool shiny)
{
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        dex_mark_seen(&s_dex, sid, shiny);
        xSemaphoreGive(s_lock);
    }
}

void world_feed(void)
{
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        nurture_feed(&s_w.pet);
        s_dirty = true;
        xSemaphoreGive(s_lock);
    }
}

void world_play(void)
{
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        nurture_play(&s_w.pet);
        s_dirty = true;
        xSemaphoreGive(s_lock);
    }
}

void world_rest(void)
{
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        nurture_rest(&s_w.pet);
        s_dirty = true;
        xSemaphoreGive(s_lock);
    }
}

void world_grant_exp(uint16_t amount)
{
    if (amount == 0) return;

    uint8_t old_level = 0;
    uint8_t new_level = 0;
    uint32_t new_exp = 0;
    bool granted = false;
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        old_level = s_w.level;
        s_w.exp += amount;
        s_w.level = exp_to_level(s_w.exp, LEVEL_MAX);
        sync_leader_locked();
        s_dirty = true;
        new_level = s_w.level;
        new_exp = s_w.exp;
        granted = true;
        xSemaphoreGive(s_lock);
    }

    if (!granted) return;
    if (new_level != old_level) {
        ESP_LOGI(TAG, "level up: %u -> %u (exp +%u = %" PRIu32 ")",
                 old_level, new_level, amount, new_exp);
    }

    // 经验是战斗的长期回报，结算后立刻落盘，不能等 5 分钟节流。
    save_now("experience");
}

bool world_evolve_leader(uint16_t expected_species, uint16_t evolve_to)
{
    if (expected_species < 1 || expected_species > BOX_SPECIES ||
        evolve_to < 1 || evolve_to > BOX_SPECIES) return false;

    bool committed = false;
    uint8_t intimacy = 0;
    uint16_t explore = 0;
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        mon_t *leader = s_party.party_count ? &s_party.party[0] : NULL;
        species_t sp;
        evo_check_t check;
        intimacy = nurture_pct(s_w.pet.intimacy);
        explore = s_w.explore_value;
        if (leader && leader->species_id == expected_species &&
            assets_species(expected_species, &sp) && sp.evolve_to == evolve_to) {
            evo_check(intimacy, explore, sp.evolve_trigger,
                      sp.evolve_to, sp.evolve_level, &check);
            if (check.can) {
                leader->species_id = (uint8_t)evolve_to;
                leader->intimacy = intimacy;
                leader->explore_value = explore;
                s_w.species = evolve_to;
                int32_t happier = s_w.pet.mood + 15 * NURT_Q;
                s_w.pet.mood = happier > NURT_MAX ? NURT_MAX : happier;
                dex_mark_caught(&s_dex, evolve_to, (leader->flags & 1u) != 0);
                s_dirty = true;
                committed = true;
            }
        }
        xSemaphoreGive(s_lock);
    }

    if (!committed) return false;
    ESP_LOGI(TAG, "@@EVOLVE from=%u to=%u intimacy=%u explore=%u",
             expected_species, evolve_to, intimacy, explore);
    if (!save_now("进化")) {
        ESP_LOGE(TAG, "进化存档失败");
    }
    return true;
}

static esp_err_t wifi_bring_up(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
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

// 生成一条遭遇并入队。
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

    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        enc_queue_push(&s_queue, &e);
        xSemaphoreGive(s_lock);
    }
    (*made)++;

    ESP_LOGI(TAG, "遭遇 #%u ★%u%s（%s）队列 %u",
             e.species_id, e.rarity, e.is_shiny ? " 闪光!" : "",
             transient ? "猎场" : "基地", s_queue.count);
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

    // ---- 遭遇生成（S1）----------------------------------------------
    //
    // 两条路径，缺一不可（docs/04-gameplay.md#411）：
    //   猎场 —— 移动中 + 有瞬现 AP，移动量做闸门，密集
    //   基地 —— 驻留时按时间排程，稀少但**永不断流**
    //
    // 只做猎场的话窝在家里一整天毫无产出；只做基地的话出门没有回报。
    uint8_t made = 0;

    if (r.state == SENS_MOVING && r.transient_aps > 0) {
        s_hunt_pool += r.distance;
        // while 而不是 if —— 一次扫描的移动量可能够出好几只
        while (s_hunt_pool >= HUNT_COST_Q10 && made < 4) {
            s_hunt_pool -= HUNT_COST_Q10;
            spawn_one(ts, true, &made);
        }
    }

    uint32_t bucket = ts / BASE_INTERVAL_S;
    if (bucket != s_last_base_bucket) {
        s_last_base_bucket = bucket;
        spawn_one(ts, false, &made);
    }

    if (made && s_lock &&
        xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        s_w.pending = s_queue.count;
        xSemaphoreGive(s_lock);
    }

    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        if (r.state == SENS_MOVING) {
            s_motion_q10 += r.distance;
            if (s_w.explore_value < UINT16_MAX) s_w.explore_value++;
            int32_t happier = s_w.pet.mood + 2 * NURT_Q;
            s_w.pet.mood = happier > NURT_MAX ? NURT_MAX : happier;
            sync_leader_locked();
        }
        s_w.state = r.state;
        s_w.place_id = r.place_id;
        s_w.progress = world_progress_from_motion(s_motion_q10);
        s_w.scans++;
        s_w.last_ap_count = (uint8_t)n;
        s_dirty = true;
        xSemaphoreGive(s_lock);
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
        if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
            // is_night 仍写死 false —— 判夜要墙钟时间，现在只有开机微秒数。
            // 等 S10 日切接上 RTC 一起做。
            nurture_tick(&s_w.pet, now, 0, false);
            xSemaphoreGive(s_lock);
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
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
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
        xSemaphoreGive(s_lock);
    }
    if (ready) {
        ESP_LOGI(TAG, "@@EVOLVE_READY intimacy=%u explore=%u",
                 need_intimacy, need_explore);
    }
    return ready;
}
#endif

bool world_wifi_ready(void) { return s_wifi_ok; }

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
    nurture_init(&s_w.pet);
    init_default_party();
    s_w.species = party_leader(&s_party)->species_id;
    s_w.level = exp_to_level(s_w.exp, LEVEL_MAX);
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
    save_init();

    if (save_read(&s_save_buf)) {
        s_w.pet = s_save_buf.pet;
        s_w.pet.last_us = -1;
        if (!party_deserialize(&s_party, s_save_buf.party,
                               sizeof(s_save_buf.party)) ||
            !party_leader(&s_party) || party_leader(&s_party)->species_id == 0) {
            init_default_party();
        }
        const mon_t *leader = party_leader(&s_party);
        s_w.species = leader->species_id;
        s_w.exp = leader->exp;
        s_w.level = leader->level;
        s_w.explore_value = leader->explore_value;
        s_queue = s_save_buf.queue;
        s_dex = s_save_buf.dex;
        s_motion_q10 = s_save_buf.motion_q10;
        s_w.scans = s_save_buf.scans;
        s_w.pending = s_queue.count;
        s_w.progress = world_progress_from_motion(s_motion_q10);
        ESP_LOGI(TAG, "读档：图鉴 %u/%u 队列 %u 行程 %u%% party %u total %u",
                 dex_count_caught(&s_dex), DEX_SPECIES,
                 s_queue.count, s_w.progress, s_party.party_count,
                 party_total(&s_party));
    } else {
        ESP_LOGI(TAG, "没有存档 —— 新游戏");
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
