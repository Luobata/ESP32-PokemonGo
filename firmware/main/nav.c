// main/nav.c —— 页面导航。设计说明见 nav.h。

#include <stddef.h>

#include "esp_log.h"

#include "nav.h"
#include "play.h"

static const char *TAG = "nav";

typedef struct {
    const char *name;
    void (*enter)(void);
    void (*exit)(void);
    void (*key)(bsp_btn_t, bsp_btn_ev_t);
} page_t;

// **顺序必须与 page_id_t 一致** —— 用下标索引，错位不会报错，
// 只会「按 C 进了图鉴」。加页面时两处一起改。
static const page_t PAGES[PAGE_COUNT] = {
    [PAGE_IDLE]      = {"P1 待机", play_idle_enter, play_idle_exit,
                        play_idle_key},
    [PAGE_ENCOUNTER] = {"P2 遭遇", play_enc_enter, play_enc_exit,
                        play_enc_key},
    [PAGE_BATTLE]    = {"P3 战斗", play_battle_enter, play_battle_exit,
                        play_battle_key},
    [PAGE_CAPTURE]   = {"P4 捕获", play_capture_enter, play_capture_exit,
                        play_capture_key},
    [PAGE_DEX]       = {"P6 图鉴", play_dex_enter, play_dex_exit,
                        play_dex_key},
    [PAGE_OPENING]   = {"P0 开场", play_opening_enter, play_opening_exit,
                        play_opening_key},
    [PAGE_CARE]      = {"P5 照料", play_care_enter, play_care_exit,
                        play_care_key},
};

static page_id_t s_cur = PAGE_IDLE;
static bool s_entered;
static nav_ctx_t s_ctx;

nav_ctx_t *nav_ctx(void) { return &s_ctx; }
page_id_t nav_current(void) { return s_cur; }

void nav_go(page_id_t p)
{
    if (p >= PAGE_COUNT) return;
    if (s_entered && PAGES[s_cur].exit) PAGES[s_cur].exit();
    s_cur = p;
    s_entered = true;
    ESP_LOGI(TAG, "→ %s", PAGES[p].name);
    if (PAGES[p].enter) PAGES[p].enter();
}

void nav_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (s_entered && PAGES[s_cur].key) PAGES[s_cur].key(btn, ev);
}

void nav_start(void) { nav_go(PAGE_IDLE); }

void nav_exit_current(void)
{
    if (s_entered && PAGES[s_cur].exit) PAGES[s_cur].exit();
    s_entered = false;
}
