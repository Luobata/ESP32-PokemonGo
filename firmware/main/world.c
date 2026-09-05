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
// 而拷一个 world_t 是几十字节的 memcpy，微秒级。
// 代价是快照可能比最新扫描晚一拍 —— 对显示完全无所谓。

#include <inttypes.h>
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
static bool s_wifi_ok;

// 扫描结果。**static** —— 64 × 76 字节放栈上必炸（见文件头）。
static wifi_ap_record_t s_recs[MAX_APS];
static sens_ap_t s_aps[MAX_APS];

// 移动量累积，Q10。今日行程由它映射。
static uint32_t s_motion_q10;

// 感知核心。**static** —— sens_core_t 有 2.6KB，放栈上会炸
// （这正是当年 Guru Meditation 的原因，见 sensing.c 顶部）。
static sens_core_t s_core;

uint8_t world_progress_from_motion(uint32_t motion_q10)
{
    uint32_t pct = (uint32_t)((uint64_t)motion_q10 * 100 / PROGRESS_FULL_Q10);
    return (uint8_t)(pct > 100 ? 100 : pct);
}

void world_snapshot(world_t *out)
{
    if (!out) return;
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(50)) == pdTRUE) {
        memcpy(out, &s_w, sizeof(*out));
        xSemaphoreGive(s_lock);
    } else {
        // 拿不到锁就给上一次的值 —— **不能返回半个结构**。
        // 50ms 拿不到锁说明扫描任务卡住了，那时旧值比撕裂的新值有用。
        memcpy(out, &s_w, sizeof(*out));
    }
}

void world_feed(void)
{
    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        nurture_feed(&s_w.pet);
        xSemaphoreGive(s_lock);
    }
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

    for (uint16_t i = 0; i < n && i < MAX_APS; i++) {
        memcpy(s_aps[i].bssid, s_recs[i].bssid, 6);
        s_aps[i].rssi = s_recs[i].rssi;
        s_aps[i].channel = s_recs[i].primary;
        s_aps[i].auth = (uint8_t)s_recs[i].authmode;
    }

    sens_result_t r;
    uint32_t ts = (uint32_t)(esp_timer_get_time() / 1000000);
    sens_feed(&s_core, ts, s_aps, (uint8_t)n, &r);

    if (r.state == SENS_MOVING) s_motion_q10 += r.distance;

    if (s_lock && xSemaphoreTake(s_lock, pdMS_TO_TICKS(100)) == pdTRUE) {
        s_w.state = r.state;
        s_w.place_id = r.place_id;
        s_w.progress = world_progress_from_motion(s_motion_q10);
        s_w.scans++;
        s_w.last_ap_count = (uint8_t)n;
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

        // 1 秒一轮。养成结算需要这个频率（nurture 按时长算，
        // 频率只影响响应粒度不影响正确性），扫描自己看时间。
        vTaskDelay(pdMS_TO_TICKS(1000));
    }
}

bool world_wifi_ready(void) { return s_wifi_ok; }

bool world_start(void)
{
    s_lock = xSemaphoreCreateMutex();
    if (!s_lock) {
        ESP_LOGE(TAG, "互斥锁创建失败");
        return false;
    }

    memset(&s_w, 0, sizeof(s_w));
    nurture_init(&s_w.pet);
    sens_init(&s_core);

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
