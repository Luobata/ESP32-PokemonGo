// main/play_capture.c —— P4 捕获。
//
// 对应 docs/pages/P4-capture.md。
//
// ## 时机判定而不是概率掷骰
//
// 概率掷骰玩家只能接受结果；时机判定让玩家**参与**。
// 这是整个游戏里唯一需要手眼配合的地方，也是「养成反哺探索」的落点：
// 心情高 → 窗口宽（S2 的 catch_window_bonus）。
//
// 四个乘数对应四条能动性（页面文档的表）：
//   catch_rate 种族固有 · 心情 养成产出 · 球种 探索产出 · 打残 战斗产出
// 三条能改的都指向不同玩法 —— 捕获因此是各系统的汇聚点。
//
// ## 只重绘指针条
//
// 指针条那一带 240×80 = 37.5KB/帧，sprite 静止不重绘。
// 页面文档算的是 240×20=9.4KB，但我们的横带粒度是 80px，
// 所以实际是一整条带。**仍然只画一条而不是四条** ——
// 这是 1.2 秒往复能跑顺的前提。

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"
#include "lvgl.h"

#include "assets.h"
#include "battle.h"
#include "capture.h"
#include "nav.h"
#include "nurture.h"
#include "play.h"
#include "render.h"
#include "screen.h"
#include "sfx.h"
#include "world.h"

static const char *TAG = "p4";

#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define SCR_H SCREEN_H

#define C_BG    RGB_HEX(0x9bbc0f)
#define C_INK   RGB_HEX(0x0f380f)
#define C_MID   RGB_HEX(0x306230)
#define C_LIGHT RGB_HEX(0x8bac0f)

// 布局（不跨带边界）
//   y=4    捕获                          带 0
//   y=32   [ 野怪 sprite 64px 居中 ]      带 0~1
//   y=176  当前球种点阵 + 球名 ×数量        带 2
//   y=208  判定条（窗口 + 指针）          带 2  ← 只有这一带每帧重画
//   y=248  结果文案                       带 3
//   y=292  ───────────────────
//   y=298  [A]投球 [B]换球 [C]取消        带 3
#define SPRITE_Y 32
#define BALL_Y 176
#define BAR_Y 208
#define BAR_X ((SCR_W - CAP_BAR_WIDTH) / 2)
#define MSG_Y 248
#define BAR_BAND (BAR_Y / BAND_H)     // 判定条所在的带号
#define CAPTURE_TICK_MS 40
#define HOLD_TICKS 25                 // 25 × 40ms = 1.0s

SCREEN_ASSERT_WITHIN_BAND(capture_ball, BALL_Y, 24);
SCREEN_ASSERT_WITHIN_BAND(capture_message, MSG_Y, 16);

static lv_timer_t *s_tick;

static cap_ball_t s_ball;
static const char *const BALL_ART[CAP_BALL_COUNT] = {
    [CAP_BALL_POKE] = "ball_24",
    [CAP_BALL_GREAT] = "ball_great",
    [CAP_BALL_ULTRA] = "ball_ultra",
};
static uint8_t s_balls[CAP_BALL_COUNT] = {12, 3, 1};   // TODO(S9): 接道具系统
static int64_t s_t0;
static cap_result_t s_last;
static bool s_thrown;
static bool s_caught;
static bool s_fled;
static bool s_no_ball;
static bool s_hold_active;
static uint8_t s_hold;

// 捕获成功的闪白。**这是整局最值得给反馈的一瞬间** ——
// 页面文档把捕获称作「各系统的汇聚点」，四个乘数在这里结算。
//
// 闪的是 sprite（用全亮调色板画它），不是整屏 ——
// 整屏闪在 GB 绿背景上会很刺眼，而且要重画四条带。
#define FLASH_FRAMES 6
static uint8_t s_flash_i = FLASH_FRAMES;

static void hline_at(int y)
{
    for (int x = 0; x < SCR_W; x++) screen_px(x, y, C_MID);
}

// 判定窗口宽度 —— 四个乘数都在这里汇合
static uint16_t current_window(void)
{
    const nav_ctx_t *c = nav_ctx();
    species_t sp;
    uint8_t cr = assets_species(c->enc.species_id, &sp) ? sp.catch_rate : 45;

    // 心情 → 窗口加成。sim 的 catch_window_bonus 是
    // 1.0 + (mood - 50)/100，Q10 化：1024 + (mood-50)*1024/100
    world_t w;
    world_snapshot(&w);
    int mood = nurture_pct(w.pet.mood);
    int32_t bonus = 1024 + (int32_t)(mood - 50) * 1024 / 100;
    if (bonus < 1) bonus = 1;

    return cap_window_width(cr, (uint16_t)bonus, s_ball, c->enc.hp_ratio);
}

static void draw_bar_band(int band_y)
{
    // 判定条：窗口是亮区，指针是竖线。
    uint16_t w = current_window();
    uint16_t start = (uint16_t)(BAR_X + (CAP_BAR_WIDTH - w) / 2);
    uint32_t elapsed = (uint32_t)((esp_timer_get_time() - s_t0) / 1000);
    uint16_t p = s_thrown ? s_last.pointer : cap_pointer_position(elapsed);

    for (int dy = 0; dy < 20; dy++) {
        int y = BAR_Y + dy - band_y;
        for (int dx = 0; dx < CAP_BAR_WIDTH; dx++) {
            int x = BAR_X + dx;
            bool border = (dy == 0 || dy == 19);
            bool in_win = (x >= start && x < start + w);
            screen_px(x, y, border ? C_INK : (in_win ? C_MID : C_LIGHT));
        }
    }
    // 指针 —— 3px 宽的深色竖线，压在窗口之上
    for (int dx = -1; dx <= 1; dx++) {
        for (int dy = 1; dy < 19; dy++) {
            screen_px(BAR_X + p + dx, BAR_Y + dy - band_y, C_INK);
        }
    }
}

static void draw_band(int band_y)
{
    screen_band_clear(C_BG);
    #define Y(v) ((v) - band_y)

    const nav_ctx_t *c = nav_ctx();
    char buf[64];
    species_t sp;
    bool has = assets_species(c->enc.species_id, &sp);

    render_text(8, Y(4), "捕获", C_INK);
    if (has) {
        snprintf(buf, sizeof(buf), "%.*s", sp.name_zh_len, sp.name_zh);
        render_text(SCR_W - 8 - render_text_width(buf), Y(4), buf, C_INK);
    }

    // 野怪 sprite
    const uint8_t *spr = assets_back_sprite(c->enc.species_id);
    if (spr && has) {
        uint16_t pal[4];
        assets_palette(sp.palette, pal);
        // 捕获成功的闪白帧：三档前景全画成最亮色。
        //
        // **不用色号 3** —— 那是透明，闪出来是背景色不是白
        // （与 sprite 内部高光那次同源：色号 3 在我们这里永远是透明）。
        if (render_flash_on(s_flash_i, FLASH_FRAMES)) {
            pal[0] = pal[1] = pal[2] = RGB_HEX(0xf8f8f8);
        }
        render_sprite_2bpp((SCR_W - 64) / 2, Y(SPRITE_Y), spr, 32, 2, pal);
    }

    // 按球种选择对应点阵，B 换球后图案、球名和数量同步变化。
    ui_art_t ball;
    if (assets_ui(BALL_ART[s_ball], &ball)) {
        static const uint16_t PAL[4] = {
            RGB_HEX(0x0f380f), RGB_HEX(0xd05030),
            RGB_HEX(0xf8f8f8), 0,
        };
        render_sprite_2bpp_wh(8, Y(BALL_Y), ball.data, ball.w, ball.h, 1, PAL);
    }
    snprintf(buf, sizeof(buf), "%s ×%u", cap_ball_name(s_ball),
             s_balls[s_ball]);
    render_text(40, Y(BALL_Y + 4), buf, C_INK);

    // 判定条
    if (band_y == BAR_BAND * BAND_H) draw_bar_band(band_y);

    // 结果
    if (s_hold_active && c->done_note == NAV_NOTE_CAUGHT) {
        render_text(8, Y(MSG_Y), "已捕获", C_INK);
        render_text(96, Y(MSG_Y), "图鉴 +1", C_MID);
    } else if (s_caught) {
        render_text(8, Y(MSG_Y), "捕获成功", C_INK);
    } else if (s_fled) {
        render_text(8, Y(MSG_Y), "跑掉了", C_INK);
    } else if (s_no_ball) {
        render_text(8, Y(MSG_Y), "没有球了", C_INK);
    } else if (s_thrown) {
        render_text(8, Y(MSG_Y), s_last.caught ? "命中" : "未命中", C_INK);
    }

    hline_at(Y(292));
    if (!s_hold_active) {
        render_text(8, Y(298), "[A]投球 [B]换球 [C]取消", C_INK);
    }

    #undef Y
    screen_push_band(band_y);
}

static void draw_all(void)
{
    for (int y = 0; y < SCR_H; y += BAND_H) draw_band(y);
}

static void redraw_for_dump(void) { draw_all(); }

static void tick(lv_timer_t *t)
{
    // 捕获成功的闪白 —— 只重画 sprite 那两条带
    if (s_flash_i < FLASH_FRAMES) {
        s_flash_i++;
        draw_band(0);
        draw_band(BAND_H);
    }

    if (s_hold_active) {
        if (++s_hold < HOLD_TICKS) return;

        // 先清状态和 timer 指针，再从唯一出口切页；exit 不会重复删除。
        s_hold_active = false;
        s_hold = 0;
        s_tick = NULL;
        lv_timer_delete(t);
        nav_go(PAGE_ENCOUNTER);
        return;
    }

    if (s_caught || s_fled) return;
    // **只重画判定条那一带** —— 指针在动，别的都是静态的。
    // 全屏重画 150KB/帧跑不动 1.2 秒的往复。
    draw_band(BAR_BAND * BAND_H);
}

void play_capture_enter(void)
{

    s_ball = CAP_BALL_POKE;
    s_t0 = esp_timer_get_time();
    s_thrown = s_caught = s_fled = s_no_ball = false;
    s_hold_active = false;
    s_hold = 0;
    nav_ctx()->done_note = NAV_NOTE_NONE;
    s_flash_i = FLASH_FRAMES;
    memset(&s_last, 0, sizeof(s_last));

    screen_set_redraw(redraw_for_dump);
    draw_all();
    s_tick = lv_timer_create(tick, CAPTURE_TICK_MS, NULL); // 25fps，指针要跟手

    // **不做自动截图** —— P1 那个是在只有一页时加的，
    // 现在有了 dbg.c 的按键注入，截图由 walk.py 显式发 's' 触发。
    // 页面自己再截一张只会与之交错，让 PC 侧收到半张（踩过一次）。

    const nav_ctx_t *c = nav_ctx();
    ESP_LOGI(TAG, "P4：#%u HP %u%% 窗口 %u px",
             c->enc.species_id, c->enc.hp_ratio, current_window());
}

void play_capture_exit(void)
{
    if (s_tick) { lv_timer_delete(s_tick); s_tick = NULL; }
    s_hold_active = false;
    s_hold = 0;
}

void play_capture_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    // 停留期任何页面按键都只加速同一条 timer 导航路径。
    if (s_hold_active) { s_hold = HOLD_TICKS - 1; return; }
    if (btn == BSP_BTN_DOWN && ev == BSP_BTN_LONG) { screen_dump(); return; }
    if (ev != BSP_BTN_CLICK) return;

    nav_ctx_t *c = nav_ctx();

    switch (btn) {
    case BSP_BTN_UP: {                     // A 投球
        if (s_caught || s_fled) { nav_go(PAGE_ENCOUNTER); return; }
        if (s_balls[s_ball] == 0) {
            ESP_LOGI(TAG, "没有球了");
            s_no_ball = true;
            draw_band((MSG_Y / BAND_H) * BAND_H);
            return;
        }
        s_no_ball = false;
        s_balls[s_ball]--;
        uint32_t elapsed = (uint32_t)((esp_timer_get_time() - s_t0) / 1000);
        species_t sp;
        uint8_t cr = assets_species(c->enc.species_id, &sp) ? sp.catch_rate : 45;
        world_t w;
        world_snapshot(&w);
        int mood = nurture_pct(w.pet.mood);
        int32_t bonus = 1024 + (int32_t)(mood - 50) * 1024 / 100;
        if (bonus < 1) bonus = 1;

        cap_attempt(cr, (uint16_t)bonus, s_ball, c->enc.hp_ratio,
                    c->enc.rarity, elapsed,
                    c->enc.ts * 31 + elapsed, &s_last);
        s_thrown = true;

        if (s_last.caught) {
            mon_t mon = {
                .species_id = c->enc.species_id,
                .level = battle_wild_level(c->enc.rarity),
                .hp = c->enc.hp_ratio ? c->enc.hp_ratio : 1,
                .nickname_idx = 0xFF,
                .flags = c->enc.is_shiny ? 1u : 0u,
            };
            if (world_capture_uid(c->uid, &mon)) {
                s_caught = true;
                s_flash_i = 0;          // 开始闪
                s_hold_active = true;
                s_hold = 0;
                c->done_note = NAV_NOTE_CAUGHT;
                sfx_play(SFX_CAUGHT);
                if (c->enc.is_shiny) sfx_play(SFX_SHINY);
                ESP_LOGI(TAG, "捕获成功 #%u%s", c->enc.species_id,
                         c->enc.is_shiny ? " 闪光!" : "");
            }
        } else {
            // 没抓到也算见过 —— S5 的 seen 位图，承载「遇到了但跑了」
            world_mark_seen(c->enc.species_id, c->enc.is_shiny);
            if (s_last.fled) {
                s_fled = true;
                world_take_uid(c->uid, NULL);
                ESP_LOGI(TAG, "跑掉了 #%u", c->enc.species_id);
            }
        }
        draw_all();
        break;
    }

    case BSP_BTN_DOWN:                     // B 换球
        if (s_caught || s_fled) break;
        s_ball = (cap_ball_t)((s_ball + 1) % CAP_BALL_COUNT);
        s_thrown = false;
        s_no_ball = false;
        draw_all();
        break;

    case BSP_BTN_OK:                       // C 取消
        nav_go(PAGE_ENCOUNTER);
        break;

    default:
        break;
    }
}
