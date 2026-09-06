// main/main.c —— FoloToy AI Passport BSP 驱动参考示例:初始化 + 菜单 + 按键分发。
//
// 按键语义(全局统一):
//   上/下 短按   菜单中=移动选中项;演示页中=该页自定义
//   确定  短按   菜单中=进入选中项;演示页中=该页自定义
//   确定  长按   演示页中=返回菜单(由本文件统一拦截)
#include "bsp_i2c.h"
#include "bsp_display.h"
#include "bsp_button.h"
#include "bsp_audio.h"
#include "bsp_battery.h"
#include "bsp_pins.h"      // 错误日志里要打印 BSP_LCD_* 引脚号
#include "demo.h"
#include "play.h"
#include "assets.h"
#include "sensing.h"
#include "nurture.h"
#include "world.h"
#include "encounter.h"
#include "nav.h"
#include "save.h"
#include "screen.h"
#include "dbg.h"
#include "render.h"
#include "ui_pixel.h"
#include "lvgl.h"
#include "esp_log.h"
#include "esp_sleep.h"

static const char *TAG = "main";

static const demo_entry_t DEMOS[] = {
    // 第一项是我们的玩法 —— 菜单默认选中它，省一次按键。
    { "Idle",    play_idle_enter,    play_idle_exit,    play_idle_key    },
    { "Collect", play_collect_enter, play_collect_exit, play_collect_key },
    // 保留三个上游 demo：Button 用来标定 ADC 分压（换硬件时要）、
    // Battery 看电量、Wi-Fi 是扫描对照组。其余删掉以省 flash 与编译时间。
    { "Button",  demo_button_enter,  demo_button_exit,  demo_button_key  },
    { "Battery", demo_battery_enter, demo_battery_exit, demo_battery_key },
    { "Wi-Fi",   demo_wifi_enter,    demo_wifi_exit,    demo_wifi_key    },
};
#define DEMO_COUNT (sizeof(DEMOS) / sizeof(DEMOS[0]))

// 各外设初始化结果:失败的项在菜单里标 [FAIL] 且不允许进入。
static bool s_ok[DEMO_COUNT];

static lv_obj_t *s_menu_scr;
static lv_obj_t *s_cards[DEMO_COUNT];
static lv_obj_t *s_rows[DEMO_COUNT];
static lv_obj_t *s_mascot;
static int  s_sel;                 // 当前选中项
static int  s_active = -1;         // 当前所在演示页;-1 = 在菜单

// 在玩法里（nav 管的那五页）还是在 demo 菜单里。
// 两套分发并存：玩法是链式的，demo 是菜单式的（见 nav.h 的说明）。
static bool s_in_game;

static void menu_refresh(void) {
    for (size_t i = 0; i < DEMO_COUNT; i++) {
        lv_label_set_text_fmt(s_rows[i], "%s%s",
                              DEMOS[i].name,
                              s_ok[i] ? "" : "  [FAIL]");
        ui_pixel_set_selected(s_cards[i], (int)i == s_sel, s_ok[i]);
        lv_obj_set_style_text_color(s_rows[i],
            s_ok[i] ? lv_color_hex(UI_INK) : lv_color_hex(0x7A2020), 0);
    }
}

static void menu_build(void) {
    s_menu_scr = ui_pixel_screen_create("FoloToy");

    for (size_t i = 0; i < DEMO_COUNT; i++) {
        int x = 11 + (int)(i % 2) * 112;
        int y = 52 + (int)(i / 2) * 47;
        s_cards[i] = ui_pixel_panel_create(s_menu_scr, x, y, 102, 40, UI_PAPER);
        s_rows[i] = lv_label_create(s_cards[i]);
        lv_obj_set_style_text_font(s_rows[i], &lv_font_montserrat_14, 0);
        lv_obj_set_style_text_align(s_rows[i], LV_TEXT_ALIGN_CENTER, 0);
        lv_obj_center(s_rows[i]);
    }

    s_mascot = ui_pixel_mascot_create(s_menu_scr, 101, 242);

    menu_refresh();
    lv_screen_load(s_menu_scr);
}

static void enter_menu(void) {
    s_active = -1;
    menu_build();
}

// 按键回调运行在 button 组件的任务里,操作 LVGL 必须加锁。
static void on_key(bsp_btn_t btn, bsp_btn_ev_t ev, void *user) {
    (void)user;
    if (!bsp_lvgl_lock(500)) return;

    if (s_in_game) {
        // 玩法页走 nav（P1↔P2↔P3↔P4↔P6 链式跳转），
        // 长按 OK 才退回上游 demo 菜单。
        if (btn == BSP_BTN_OK && ev == BSP_BTN_LONG) {
            s_in_game = false;
            nav_exit_current();
            enter_menu();
        } else {
            nav_key(btn, ev);
        }
    } else if (s_active >= 0) {
        if (btn == BSP_BTN_OK && ev == BSP_BTN_LONG) {     // 统一返回
            DEMOS[s_active].exit();
            enter_menu();
        } else {
            DEMOS[s_active].key(btn, ev);
        }
    } else if (ev == BSP_BTN_CLICK) {
        if (btn == BSP_BTN_UP)   { s_sel = (s_sel + DEMO_COUNT - 1) % DEMO_COUNT; menu_refresh(); }
        if (btn == BSP_BTN_DOWN) { s_sel = (s_sel + 1) % DEMO_COUNT;              menu_refresh(); }
        if (btn == BSP_BTN_OK && s_ok[s_sel]) {
            s_active = s_sel;
            s_in_game = false;
            ui_pixel_mascot_jump(s_mascot);
            lv_obj_delete(s_menu_scr);
            s_menu_scr = NULL;
            s_mascot = NULL;
            DEMOS[s_active].enter();
        } else if (btn == BSP_BTN_UP || btn == BSP_BTN_DOWN) {
            ui_pixel_mascot_jump(s_mascot);
        }
    }
    bsp_lvgl_unlock();
}

void app_main(void) {
    ESP_LOGI(TAG, "PokeWalk on AI Passport 启动");
    esp_sleep_wakeup_cause_t wakeup = esp_sleep_get_wakeup_cause();
    if (wakeup != ESP_SLEEP_WAKEUP_UNDEFINED) {
        ESP_LOGI(TAG, "休眠唤醒原因: %d", wakeup);
    }

    bsp_i2c_init();
    bsp_i2c_scan();

    // 资产自检 —— 数字要与 PC 侧 inventory_assets.py 对得上。
    // 放在最前面：资产错了后面全是错的，早报早知道。
    if (assets_init()) assets_selftest();
    sens_selftest();
    nurture_selftest();
    enc_selftest();
    if (render_init()) render_selftest();

    // 屏幕是本 demo 的 UI 载体,失败就没有菜单可言 —— 打清楚日志后退出,
    // 不做"串口菜单"降级(那会让本文件复杂一倍,违背参考示例的初衷)。
    if (bsp_display_init() != ESP_OK || !bsp_lvgl_init()) {
        ESP_LOGE(TAG, "显示/LVGL 初始化失败,demo 无法继续。"
                      "检查 SPI 接线(MOSI=%d SCLK=%d CS=%d DC=%d BL=%d)",
                 BSP_LCD_MOSI, BSP_LCD_SCLK, BSP_LCD_CS, BSP_LCD_DC, BSP_LCD_BL);
        return;
    }
    bsp_display_backlight(100);


    // 外设初始化。单项失败不阻塞 —— 菜单里标 [FAIL]，其他项照常可用。
    //
    // ⚠️ 这里曾经写到 s_ok[6]，而 s_ok 是 [DEMO_COUNT] = [4] ——
    // **越界写 2 字节**。上游有 7 个 demo，我把 DEMOS 表砍到 4 项时
    // 忘了跟着改。没炸只是运气（那两字节后面恰好不是活跃数据）。
    // 现在按 DEMO_COUNT 循环，改表时不会再漏。
    // 后台世界：WiFi 扫描 + 感知 + 养成结算。**在页面之前起** ——
    // 页面进来就要 world_snapshot()，而且 world 是 WiFi 的唯一所有者
    // （Collect 页原本自己 bring_up，两个所有者会争同一个射频）。
    bool world_ok = world_start();

    bool btn_ok = (bsp_button_init(on_key, NULL) == ESP_OK);
    bool audio_ok = (bsp_audio_init() == ESP_OK);
    bool batt_ok = (bsp_battery_init() == ESP_OK);
    for (size_t i = 0; i < DEMO_COUNT; i++) s_ok[i] = true;

    // 开机直接进玩法而不是停在菜单。首次冷启动先播 P0 开场；完成或
    // 跳过后写入单调标记，以后复位直接进 P1。
    //
    // 理由是实测的：每次烧写后设备回到菜单，没人按键就什么都不发生。
    // 长按 OK 仍可退回菜单 —— 只是默认状态反过来了。
    //
    // **进 Idle 而不是 Collect** —— 这是 F9-① 换来的。
    // 在那之前扫描绑在 Collect 页的 lv_timer 上，离开那页就停，
    // 所以开机只能进 Collect，否则一晚上的采集数据会因为没人按键而全丢。
    // 现在扫描是 world.c 的后台任务，谁在前台都不影响采集，
    // 开机终于能进真正的主页面。
    if (bsp_lvgl_lock(1000)) {
        // 唯一的那张 LVGL 屏 —— 五个玩法页共用，切页时不再新建。
        screen_own_display();
        s_in_game = true;
        nav_go(save_opening_seen() ? PAGE_IDLE : PAGE_OPENING);
        bsp_lvgl_unlock();
    }

    // 串口注入按键 —— 让整条链路能自动走一遍并逐页截图。
    // 与截图通道是同一思路的两半：那个解决「看不见屏幕」，
    // 这个解决「按不了键」。
    dbg_start();

    ESP_LOGI(TAG, "就绪:Display=1 Button=%d Audio=%d Battery=%d World=%d → 进入玩法",
             btn_ok, audio_ok, batt_ok, world_ok);
}
