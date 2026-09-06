// main/play_care.c —— P5 照料页。
//
// 三个照料动作共用一层线性菜单；满足条件时同层追加「进化」。
// B 循环，A 执行，C 返回 P1，不引入子菜单。
// 页面只读 world 快照；动作由 world 在状态锁内完成。

#include <stdio.h>

#include "esp_log.h"
#include "lvgl.h"

#include "assets.h"
#include "evolution.h"
#include "nav.h"
#include "play.h"
#include "render.h"
#include "screen.h"
#include "sfx.h"
#include "world.h"

static const char *TAG = "p5";

#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define SCR_H SCREEN_H

#define BASE_ACTION_COUNT 3
#define ACTION_COUNT 4
#define EVOLUTION_ACTION 3
#define EVOLUTION_FRAMES 12
#define EVOLUTION_TICK_MS (1000 / 30)
#define HOLD_TICKS 30                 // 30 × 33ms ≈ 1.0s

#define ACTION_Y0 64
#define ACTION_STEP 24
#define CARE_SPRITE_X 168
#define CARE_SPRITE_Y 88
#define CARE_SPRITE_SIZE 64
#define EVO_HINT_Y 248
#define TEXT_H 16

SCREEN_ASSERT_WITHIN_BAND(care_action_0, ACTION_Y0, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_action_1, ACTION_Y0 + ACTION_STEP, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_action_2, ACTION_Y0 + ACTION_STEP * 2, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_action_3, ACTION_Y0 + ACTION_STEP * 3, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_sprite, CARE_SPRITE_Y, CARE_SPRITE_SIZE);
SCREEN_ASSERT_WITHIN_BAND(care_evolution_hint, EVO_HINT_Y, TEXT_H);

static const char *ACTIONS[ACTION_COUNT] = {"喂食", "玩耍", "休息", "进化"};
static uint8_t s_sel;
static world_t s_w;
static evo_check_t s_evo;
static lv_timer_t *s_evo_tick;
static bool s_evolving;
static uint8_t s_evo_frame;
static uint16_t s_evo_from;
static uint16_t s_evo_to;
static bool s_hold_active;
static uint8_t s_hold;

static void hline_at(int y)
{
    for (int x = 0; x < SCR_W; x++) screen_px(x, y, C_MID);
}

static void draw_bar(int x, int y, int w, int h, uint8_t pct)
{
    int fw = w * pct / 100;
    for (int dy = 0; dy < h; dy++) {
        for (int dx = 0; dx < w; dx++) {
            bool border = (dy == 0 || dy == h - 1 || dx == 0 || dx == w - 1);
            uint16_t c = border ? C_INK : (dx < fw ? C_MID : C_LIGHT);
            screen_px(x + dx, y + dy, c);
        }
    }
}

static void refresh_evolution(void)
{
    species_t sp;
    s_evo = (evo_check_t){0};
    if (assets_species(s_w.species, &sp) && sp.evolve_to <= BOX_SPECIES) {
        evo_check(nurture_pct(s_w.pet.intimacy), s_w.explore_value,
                  sp.evolve_trigger, sp.evolve_to, sp.evolve_level, &s_evo);
    }
    if (!s_evo.can && s_sel >= BASE_ACTION_COUNT) s_sel = 0;
}

static uint8_t action_count(void)
{
    return s_evo.can ? ACTION_COUNT : BASE_ACTION_COUNT;
}

// 与 sim/effects.py::evolution_sequence(12) 逐帧同式：前段慢切，
// 后段加快；IDENTITY 帧画旧形态，INVERT 帧画新形态。
static bool evolution_show_new(uint8_t frame)
{
    if (frame >= EVOLUTION_FRAMES) return true;
    uint8_t period = (uint8_t)((EVOLUTION_FRAMES - frame) / 3);
    if (period < 1) period = 1;
    return ((frame / period) & 1u) != 0;
}

static void draw_band(int band_y)
{
    screen_band_clear(C_BG);
    #define Y(v) ((v) - band_y)

    char buf[32];

    uint16_t display_species = s_evolving && evolution_show_new(s_evo_frame)
                                   ? s_evo_to : s_w.species;
    species_t sp;
    bool has_species = assets_species(display_species, &sp);

    render_text(8, Y(4), "照料", C_INK);
    snprintf(buf, sizeof(buf), "等级 %u", s_w.level);
    render_text(SCR_W - 8 - render_text_width(buf), Y(4), buf, C_INK);
    if (has_species) {
        snprintf(buf, sizeof(buf), "%.*s", sp.name_zh_len, sp.name_zh);
        render_text(8, Y(28), buf, C_INK);
    }
    snprintf(buf, sizeof(buf), "亲密度 %u", nurture_pct(s_w.pet.intimacy));
    render_text(SCR_W - 8 - render_text_width(buf), Y(28), buf, C_MID);
    hline_at(Y(52));

    uint8_t count = action_count();
    for (uint8_t i = 0; i < count; i++) {
        int y = ACTION_Y0 + i * ACTION_STEP;
        if (i == s_sel) {
            ui_art_t cur;
            if (assets_ui("cursor", &cur)) {
                static const uint16_t PAL[4] = {
                    C_INK, C_MID, C_LIGHT, 0,
                };
                render_sprite_2bpp_wh(8, Y(y + 3), cur.data, cur.w, cur.h,
                                      1, PAL);
            }
        }
        render_text(24, Y(y), ACTIONS[i], i == s_sel ? C_INK : C_MID);
    }

    const uint8_t *spr = assets_back_sprite(display_species);
    if (spr && has_species) {
        uint16_t pal[4];
        assets_palette(sp.palette, pal);
        if (s_evolving && evolution_show_new(s_evo_frame)) {
            uint16_t dark = pal[0];
            pal[0] = pal[2];
            pal[2] = dark;
        }
        render_sprite_2bpp(CARE_SPRITE_X, Y(CARE_SPRITE_Y), spr, 32, 2, pal);
    }

    static const char *AXIS[3] = {"饱食", "心情", "体能"};
    const uint8_t value[3] = {
        nurture_pct(s_w.pet.satiety),
        nurture_pct(s_w.pet.mood),
        nurture_pct(s_w.pet.stamina),
    };
    for (int i = 0; i < 3; i++) {
        int y = 166 + i * 24;
        render_text(8, Y(y), AXIS[i], C_INK);
        draw_bar(48, Y(y + 3), 136, 10, value[i]);
        snprintf(buf, sizeof(buf), "%u", value[i]);
        render_text(SCR_W - 8 - render_text_width(buf), Y(y), buf, C_INK);
    }

    if (s_hold_active && nav_ctx()->done_note == NAV_NOTE_EVOLVED) {
        render_text(8, Y(EVO_HINT_Y), "进化了", C_INK);
    } else if (s_evo.can && !s_evolving) {
        render_text(8, Y(EVO_HINT_Y), "可以进化了", C_INK);
    }

    hline_at(Y(292));
    if (!s_hold_active) {
        render_text(8, Y(298), "[A]执行 [B]切换 [C]返回", C_INK);
    }

    #undef Y
    screen_push_band(band_y);
}

static void draw_all(void)
{
    for (int y = 0; y < SCR_H; y += BAND_H) draw_band(y);
}

static void redraw_for_dump(void)
{
    if (!s_evolving) {
        world_snapshot(&s_w);
        refresh_evolution();
    }
    draw_all();
}

static void evolution_tick(lv_timer_t *timer)
{
    if (s_hold_active) {
        if (++s_hold < HOLD_TICKS) return;

        // 清完本页状态再切页，play_care_exit 不会重复删除当前 timer。
        s_hold_active = false;
        s_hold = 0;
        s_evo_tick = NULL;
        lv_timer_delete(timer);
        nav_go(PAGE_IDLE);
        return;
    }

    s_evo_frame++;
    if (s_evo_frame < EVOLUTION_FRAMES) {
        draw_all();
        ESP_LOGI(TAG, "@@EVO_FX frame=%u/%u new=%u", s_evo_frame,
                 EVOLUTION_FRAMES, evolution_show_new(s_evo_frame) ? 1u : 0u);
        return;
    }

    s_evolving = false;
    if (!world_evolve_leader(s_evo_from, s_evo_to)) {
        s_evo_tick = NULL;
        lv_timer_delete(timer);
        ESP_LOGE(TAG, "进化提交失败 #%u -> #%u", s_evo_from, s_evo_to);
        world_snapshot(&s_w);
        refresh_evolution();
        draw_all();
        return;
    }
    world_snapshot(&s_w);
    refresh_evolution();
    nav_ctx()->done_note = NAV_NOTE_EVOLVED;
    s_hold_active = true;
    s_hold = 0;
    draw_all();
}

static void start_evolution(void)
{
    species_t sp;
    if (!s_evo.can || !assets_species(s_w.species, &sp) ||
        sp.evolve_to == 0 || sp.evolve_to > BOX_SPECIES) return;

    s_evo_from = s_w.species;
    s_evo_to = sp.evolve_to;
    s_evo_frame = 0;
    s_evolving = true;
    nav_ctx()->done_note = NAV_NOTE_NONE;
    s_evo_tick = lv_timer_create(evolution_tick, EVOLUTION_TICK_MS, NULL);
    if (!s_evo_tick) {
        s_evolving = false;
        ESP_LOGE(TAG, "进化 timer 创建失败");
        return;
    }

    sfx_play(SFX_EVOLVE);
    draw_all();
    ESP_LOGI(TAG, "@@EVO_FX start from=%u to=%u frames=%u",
             s_evo_from, s_evo_to, EVOLUTION_FRAMES);
}

void play_care_enter(void)
{
    s_sel = 0;
    s_evo_tick = NULL;
    s_evolving = false;
    s_evo_frame = 0;
    s_hold_active = false;
    s_hold = 0;
    world_snapshot(&s_w);
    refresh_evolution();
    screen_set_redraw(redraw_for_dump);
    draw_all();
    ESP_LOGI(TAG, "P5：等级 %u 亲密度 %u", s_w.level,
             nurture_pct(s_w.pet.intimacy));
}

void play_care_exit(void)
{
    if (s_evo_tick) { lv_timer_delete(s_evo_tick); s_evo_tick = NULL; }
    s_evolving = false;
    s_hold_active = false;
    s_hold = 0;
}

void play_care_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    // 停留期任何页面按键都只加速同一条 timer 导航路径。
    if (s_hold_active) { s_hold = HOLD_TICKS - 1; return; }
    if (btn == BSP_BTN_DOWN && ev == BSP_BTN_LONG) { screen_dump(); return; }
    if (ev != BSP_BTN_CLICK) return;
    if (s_evolving) return;

    switch (btn) {
    case BSP_BTN_UP: {                     // A 执行
        if (s_sel == EVOLUTION_ACTION) {
            start_evolution();
            break;
        }
        world_t before = s_w;
        if (s_sel == 0) world_feed();
        if (s_sel == 1) world_play();
        if (s_sel == 2) world_rest();
        world_snapshot(&s_w);
        refresh_evolution();
        sfx_play(SFX_CARE);
        draw_all();
        ESP_LOGI(TAG, "@@CARE %s %u/%u/%u/%u -> %u/%u/%u/%u",
                 ACTIONS[s_sel],
                 nurture_pct(before.pet.satiety), nurture_pct(before.pet.mood),
                 nurture_pct(before.pet.stamina), nurture_pct(before.pet.intimacy),
                 nurture_pct(s_w.pet.satiety), nurture_pct(s_w.pet.mood),
                 nurture_pct(s_w.pet.stamina), nurture_pct(s_w.pet.intimacy));
        break;
    }

    case BSP_BTN_DOWN:                     // B 切换
        world_snapshot(&s_w);
        refresh_evolution();
        s_sel = (uint8_t)((s_sel + 1) % action_count());
        draw_all();
        break;

    case BSP_BTN_OK:                       // C 返回
        nav_go(PAGE_IDLE);
        break;

    default:
        break;
    }
}
