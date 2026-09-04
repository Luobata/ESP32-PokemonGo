// main/play_collect.c —— WiFi 指纹采集器
//
// 这是本项目在真机上的第一个玩法，但它先不是游戏，而是**采集器**。
//
// ## 为什么第一个做采集而不是游戏
//
// 两件事卡在缺数据上，而这台设备正好能采：
//
//   ① 野外 biome 是死代码（docs/00-handoff.md 的 P0-②）
//      classify_biome 里 MIN_APS_FOR_BIOME=4 先返回 UNKNOWN，
//      后面的 `if n <= 3: return BIOME_WILD` 数学上不可达。
//      三份真实数据 1061 次扫描里野外出现 0 次 →
//      第 1、5 馆锁死 → 道馆线性 → 八个馆全打不了。
//      修它需要**真实户外采集**（公园/街道的 AP 数分布），
//      而我试过的两版阈值都是拿合成数据的编造分布调参。
//
//   ② 口袋 RSSI 基线未标定 —— 现在用的是电脑天线数据。
//      设备装兜里天线被身体遮挡，RSSI 会整体偏低多少，没人知道。
//
//   ③ F5 一致性检验（docs/07-roadmap.md）要求
//      「把 data/raw/*.ndjson 灌进固件，算出与 sim/replay.py
//      完全相同的状态序列」。那需要固件与 PC 侧读同一份数据 ——
//      先有采集，才谈得上对齐。
//
// ## 输出格式与 PC 侧逐字段一致
//
// 串口打印的每行就是一条 NDJSON，键名与 tools/collector 的输出相同：
//
//     {"ts":1234567,"aps":[{"b":"aa:bb:...","s":"SSID","r":-67,"c":6,"a":"wpa2"}]}
//
// 于是 `tools/device/collect.py` 收下来存成 .ndjson，
// 可以直接喂给 sim/sensing.py、orchestrate.py、inspector ——
// 不需要任何格式转换。这是刻意的：**格式一致是 F5 的前提**。
//
// ## 契约
//
// 上游 AGENTS.md 的两条硬规矩，这里都遵守：
//   · LVGL 非线程安全 → 扫描回调里不碰 LVGL，只置标志位，由 lv_timer 刷屏
//   · 按键回调不得阻塞 → key() 只改状态，慢活留给 tick

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_event.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "nvs_flash.h"

#include "bsp_battery.h"
#include "bsp_display.h"
#include "demo.h"
#include "ui_pixel.h"

static const char *TAG = "collect";

// 一次扫描最多记多少个 AP。
//
// 实测真实环境：家 6~18 个、公司 20~65 个（data/raw 的统计）。
// 取 48 是因为 wifi_ap_record_t 有 80 字节，48 个 = 3.8KB 栈上放不下，
// 所以下面用 static 分配 —— 而可用堆只有 187KB（真机实测），
// 每一 KB 都要算。48 覆盖了实测最大值 65 的大部分，
// 超出的部分 esp_wifi_scan_get_ap_records 会按信号强度截断，
// 丢掉的是最弱的那些 —— 对指纹识别影响最小。
#define MAX_APS 48

// 扫描间隔。
//
// PC 侧采集用的是 30 秒（data/raw 的 ts 间隔），感知层的
// VISIT_MIN_SCANS=10 等阈值都是按这个标定的。**必须保持一致**，
// 否则采回来的数据喂给 sim/ 会得出不同的驻留/访问判定。
#define SCAN_INTERVAL_MS 30000

typedef enum {
    ST_IDLE = 0,      // 停着，不扫
    ST_RUNNING,       // 定时扫描中
    ST_SCANNING,      // 本次扫描进行中（等 SCAN_DONE 事件）
} state_t;

static state_t s_state = ST_IDLE;
static lv_obj_t *s_scr;
static lv_obj_t *s_title, *s_stat, *s_last;
static lv_timer_t *s_tick;
static esp_event_handler_instance_t s_scan_handler;
static bool s_wifi_started;

static uint32_t s_scan_count;      // 已完成多少次扫描
static uint32_t s_ap_total;        // 累计记录多少条 AP
static int64_t s_next_scan_us;     // 下次该扫的时刻
static volatile bool s_done_flag;  // 扫描完成 —— 事件回调置，tick 消费

static wifi_ap_record_t s_recs[MAX_APS];

// authmode → PC 侧用的字符串。
//
// 取值必须与 tools/collector 一致，否则 gameplay.classify_biome 的
// 「企业级占比」判据会失效 —— 它按 auth 里有没有 "ent" 判办公区。
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

static void on_scan_done(void *arg, esp_event_base_t base,
                         int32_t id, void *data)
{
    (void)arg; (void)base; (void)id; (void)data;
    // ⚠️ 这里是 WiFi 事件任务，**不能碰 LVGL**（非线程安全，
    // 见上游 AGENTS.md）。只置标志，刷屏交给 tick。
    s_done_flag = true;
}

static esp_err_t wifi_bring_up(void)
{
    esp_err_t err = nvs_flash_init();
    if (err == ESP_ERR_NVS_NO_FREE_PAGES || err == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_ERROR_CHECK(nvs_flash_erase());
        err = nvs_flash_init();
    }
    if (err != ESP_OK) return err;

    err = esp_netif_init();
    if (err != ESP_OK) return err;
    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) return err;
    esp_netif_create_default_wifi_sta();

    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    err = esp_wifi_init(&cfg);
    if (err != ESP_OK) return err;

    err = esp_event_handler_instance_register(WIFI_EVENT,
                                              WIFI_EVENT_SCAN_DONE,
                                              on_scan_done, NULL,
                                              &s_scan_handler);
    if (err != ESP_OK) return err;

    err = esp_wifi_set_mode(WIFI_MODE_STA);
    if (err != ESP_OK) return err;
    err = esp_wifi_start();
    if (err != ESP_OK) return err;

    s_wifi_started = true;
    return ESP_OK;
}

static void collect_scan_results(void)
{
    uint16_t n = MAX_APS;
    if (esp_wifi_scan_get_ap_records(&n, s_recs) != ESP_OK) return;
    emit_ndjson(n);
    s_scan_count++;
    s_ap_total += n;
}

static void ui_refresh(void)
{
    // 只在 LVGL 任务里调 —— tick 就是 lv_timer 回调，安全
    lv_label_set_text_fmt(s_stat, "%s  %" PRIu32 " scans",
                          s_state == ST_IDLE ? "STOPPED" : "RUNNING",
                          s_scan_count);
    if (s_scan_count) {
        lv_label_set_text_fmt(s_last, "%" PRIu32 " APs total\navg %.1f/scan\nbat %d%%",
                              s_ap_total,
                              (double)s_ap_total / (double)s_scan_count,
                              bsp_battery_soc());
    } else {
        lv_label_set_text(s_last, "OK: start/stop\nlogs -> serial");
    }
}

static void tick(lv_timer_t *t)
{
    (void)t;

    if (s_done_flag) {
        s_done_flag = false;
        collect_scan_results();
        s_state = ST_RUNNING;
        s_next_scan_us = esp_timer_get_time() + SCAN_INTERVAL_MS * 1000LL;
        ui_refresh();
    }

    if (s_state == ST_RUNNING && esp_timer_get_time() >= s_next_scan_us) {
        if (esp_wifi_scan_start(NULL, false) == ESP_OK) {
            s_state = ST_SCANNING;
        } else {
            // 扫描起不来就等下一轮，别刷屏报错
            s_next_scan_us = esp_timer_get_time() + SCAN_INTERVAL_MS * 1000LL;
        }
    }
}

void play_collect_enter(void)
{
    s_scr = ui_pixel_screen_create("Collect");
    s_title = lv_label_create(s_scr);
    lv_label_set_text(s_title, "WiFi fingerprint");
    lv_obj_align(s_title, LV_ALIGN_TOP_LEFT, 8, 40);

    s_stat = lv_label_create(s_scr);
    lv_obj_align(s_stat, LV_ALIGN_TOP_LEFT, 8, 70);

    s_last = lv_label_create(s_scr);
    lv_obj_set_width(s_last, 220);
    lv_obj_align(s_last, LV_ALIGN_TOP_LEFT, 8, 100);

    s_scan_count = 0;
    s_ap_total = 0;
    s_state = ST_IDLE;
    s_done_flag = false;

    if (!s_wifi_started) {
        esp_err_t err = wifi_bring_up();
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "WiFi 起不来: %s", esp_err_to_name(err));
            lv_label_set_text(s_stat, "WiFi INIT FAILED");
        }
    }

    ui_refresh();
    lv_screen_load(s_scr);
    s_tick = lv_timer_create(tick, 200, NULL);
}

void play_collect_exit(void)
{
    // 顺序有讲究：先停定时器再删屏。
    // 反过来的话 tick 可能在屏已删除后触发，访问野指针 ——
    // 上游 AGENTS.md 专门点了这条（「删 screen 前必须停止所有
    // 可能访问其 UI 的任务、定时器、回调」）。
    if (s_tick) { lv_timer_delete(s_tick); s_tick = NULL; }
    if (s_state == ST_SCANNING) esp_wifi_scan_stop();
    s_state = ST_IDLE;
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; }
}

void play_collect_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (ev != BSP_BTN_CLICK) return;
    if (btn != BSP_BTN_OK) return;

    // 按键回调不得阻塞（AGENTS.md）—— 这里只切状态，
    // 真正的扫描由 tick 发起。
    if (s_state == ST_IDLE) {
        s_state = ST_RUNNING;
        s_next_scan_us = 0;          // 立刻扫第一次
        ESP_LOGI(TAG, "采集开始，间隔 %d ms", SCAN_INTERVAL_MS);
    } else {
        s_state = ST_IDLE;
        ESP_LOGI(TAG, "采集停止：%" PRIu32 " 次扫描，%" PRIu32 " 条 AP",
                 s_scan_count, s_ap_total);
    }
    ui_refresh();
}
