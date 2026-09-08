// main/play_care.c —— P5 照料页。
//
// 三个照料动作与背包共用一层线性菜单；等级进化条件满足时追加「进化」。
// B 循环，A 执行，C 返回来源页；背包返回时保留动作光标。
// 页面只读 world 快照；动作由 world 在状态锁内完成。

#include <stdio.h>

#include "esp_log.h"
#include "lvgl.h"

#include "assets.h"
#include "evolution.h"
#include "game_ui.h"
#include "items.h"
#include "nav.h"
#include "play.h"
#include "pokemon_names.h"
#include "render.h"
#include "screen.h"
#include "screen_idle.h"
#include "pokemon_animation.h"
#include "sfx.h"
#include "music_director.h"
#include "world.h"

static const char *TAG = "p5";

#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define SCR_H SCREEN_H

#define BASE_ACTION_COUNT 4
#define ACTION_COUNT 5
#define BAG_ACTION 3
#define EVOLUTION_ACTION 4
#define EVOLUTION_FRAMES 12
#define EVOLUTION_TICK_MS (1000 / 30)
#define HOLD_TICKS 30                 // 30 × 33ms ≈ 1.0s

#define ACTION_Y0 80
#define ACTION_STEP 20
#define CARE_SPRITE_X 120
#define CARE_SPRITE_Y 64
#define CARE_SPRITE_SIZE 112
#define CARE_SPRITE_SCALE 2
#define AXIS_Y0 180
#define AXIS_STEP 22
#define EVO_HINT_Y 244
#define NAME_HINT_Y 262
#define TEXT_H 16

SCREEN_ASSERT_WITHIN_BAND(care_action_0, ACTION_Y0, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_action_1, ACTION_Y0 + ACTION_STEP, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_action_2, ACTION_Y0 + ACTION_STEP * 2, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_action_3, ACTION_Y0 + ACTION_STEP * 3, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_action_4, ACTION_Y0 + ACTION_STEP * 4, TEXT_H);
// The 112px box spans bands 0/1/2. Every care action and evolution frame
// calls draw_all(), clearing both the previous and the current sprite bounds.
SCREEN_ASSERT_ALLOW_CROSS_BAND(care_sprite, CARE_SPRITE_Y, CARE_SPRITE_SIZE);
SCREEN_ASSERT_WITHIN_BAND(care_axis_0, AXIS_Y0, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_axis_1, AXIS_Y0 + AXIS_STEP, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_axis_2, AXIS_Y0 + AXIS_STEP * 2, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_evolution_hint, EVO_HINT_Y, TEXT_H);
SCREEN_ASSERT_WITHIN_BAND(care_name_hint, NAME_HINT_Y, TEXT_H);

static const char *ACTIONS[ACTION_COUNT] = {"喂食", "玩耍", "恢复说明", "背包", "进化"};
static uint8_t s_sel;
static world_t s_w;
static bool s_shiny;
static evo_check_t s_evo;
static lv_timer_t *s_evo_tick;
static lv_timer_t *s_motion_tick;
static pokemon_idle_t s_motion;
static bool s_evolving;
static uint8_t s_evo_frame;
static uint16_t s_evo_from;
static uint16_t s_evo_to;
static bool s_hold_active;
static uint8_t s_hold;
static inventory_t s_inventory;
static char s_care_feedback[64];

static void refresh_evolution(void)
{
    species_t sp;
    s_evo = (evo_check_t){0};
    if (assets_species(s_w.species, &sp) && sp.evolve_to <= BOX_SPECIES &&
        sp.evolve_trigger == EVO_TRIGGER_LEVEL) {
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
    screen_band_clear(GAME_UI_BG);
    #define Y(v) ((v) - band_y)

    char buf[32];

    uint16_t display_species = s_evolving && evolution_show_new(s_evo_frame)
                                   ? s_evo_to : s_w.species;
    species_t sp;
    bool has_species = assets_species(display_species, &sp);

    snprintf(buf, sizeof(buf), "等级 %u", s_w.level);
    game_ui_title(band_y, "照料", buf);
    if (has_species) {
        snprintf(buf, sizeof(buf), "%.*s", sp.name_zh_len, sp.name_zh);
        render_text(12, Y(40), buf, GAME_UI_INK);
    }
    snprintf(buf, sizeof(buf), "亲密度 %u", nurture_pct(s_w.pet.intimacy));
    render_text(228 - render_text_width(buf), Y(40), buf, GAME_UI_MUTED);

    uint8_t count = action_count();
    for (uint8_t i = 0; i < count; i++) {
        int y = ACTION_Y0 + i * ACTION_STEP;
        if (i == s_sel) {
            game_ui_cursor(band_y, 12, y + 3);
        }
        const char *label = ACTIONS[i];
        if (i == 0) {
            snprintf(buf, sizeof(buf), "喂食 x%u", s_inventory.quantity[ITEM_BERRY]);
            label = buf;
        }
        render_text(28, Y(y), label, i == s_sel ? GAME_UI_INK : GAME_UI_MUTED);
    }

    uint8_t sprite_size = 0;
    const uint8_t *spr = assets_front_sprite(display_species, &sprite_size);
    if (!s_evolving && !s_hold_active && s_motion.species == display_species && s_motion.sprite.data) {
        spr = s_motion.sprite.data;
        sprite_size = s_motion.sprite.w;
    }
    const int display_size = sprite_size * CARE_SPRITE_SCALE;
    if (spr && has_species && sprite_size && display_size <= CARE_SPRITE_SIZE) {
        uint16_t pal[4];
        assets_palette_variant(sp.palette, s_shiny, pal);
        if (s_evolving && evolution_show_new(s_evo_frame)) {
            uint16_t dark = pal[0];
            pal[0] = pal[2];
            pal[2] = dark;
        }
        game_ui_sprite_centered(band_y, CARE_SPRITE_X, CARE_SPRITE_Y,
                                 CARE_SPRITE_SIZE, CARE_SPRITE_SIZE,
                                 spr, sprite_size, sprite_size, CARE_SPRITE_SCALE, pal);
    }

    static const char *AXIS[3] = {"饱食", "心情", "体能"};
    const uint8_t value[3] = {
        nurture_pct(s_w.pet.satiety),
        nurture_pct(s_w.pet.mood),
        nurture_pct(s_w.pet.stamina),
    };
    for (int i = 0; i < 3; i++) {
        int y = AXIS_Y0 + i * AXIS_STEP;
        render_text(12, Y(y), AXIS[i], GAME_UI_INK);
        game_ui_meter(band_y, 56, y, 128, value[i]);
        snprintf(buf, sizeof(buf), "%u", value[i]);
        render_text(228 - render_text_width(buf), Y(y), buf, GAME_UI_INK);
    }

    snprintf(buf,sizeof(buf),"经验%u%% 稀有+%u.%u%%",nurture_exp_percent(&s_w.pet),nurture_rare_bonus(&s_w.pet)/10,nurture_rare_bonus(&s_w.pet)%10);
    const char *evo_hint = NULL;
    if (s_hold_active && nav_ctx()->done_note == NAV_NOTE_EVOLVED) evo_hint = "进化了";
    else if (s_care_feedback[0]) evo_hint = s_care_feedback;
    else if (s_evo.can && !s_evolving) evo_hint = "可以进化了";
    game_ui_text_centered(band_y,8,EVO_HINT_Y,224,16,evo_hint?evo_hint:buf,GAME_UI_INK);
    game_ui_text_centered(band_y, 12, NAME_HINT_Y, 216, TEXT_H,
                          "体力白天每5分钟恢复1点", GAME_UI_MUTED);

    game_ui_footer(band_y, s_hold_active ? "" : "[A]执行 [B]切换 [C]返回");

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
        world_inventory_snapshot(&s_inventory);
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
        nav_back(PAGE_IDLE);
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
        world_inventory_snapshot(&s_inventory);
        snprintf(s_care_feedback, sizeof(s_care_feedback), "进化保存失败");
        refresh_evolution();
        draw_all();
        return;
    }
    world_snapshot(&s_w);
    world_inventory_snapshot(&s_inventory);
    s_care_feedback[0] = '\0';
    refresh_evolution();
    nav_ctx()->done_note = NAV_NOTE_EVOLVED;
    s_hold_active = true;
    s_hold = 0;
    draw_all();
}

static void start_evolution(void)
{
    species_t sp;
    if (!s_evo.can || !assets_species(s_w.species, &sp) || sp.evolve_trigger != EVO_TRIGGER_LEVEL ||
        sp.evolve_to == 0 || sp.evolve_to > BOX_SPECIES) return;

    s_evo_from = s_w.species;
    s_evo_to = sp.evolve_to;
    s_evo_frame = 0;
    s_evolving = true;
    nav_ctx()->done_note = NAV_NOTE_NONE;
    music_director_play(MUSIC_EVOLUTION);
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

static void motion_tick(lv_timer_t *timer)
{
    (void)timer;
    if (s_evolving || s_hold_active || screen_idle_is_off()) return;
    if (s_motion.species != s_w.species) pokemon_idle_reset(&s_motion, s_w.species);
    if (pokemon_idle_step(&s_motion, 80)) draw_all();
}

void play_care_enter(void)
{
    if (!nav_is_returning()) s_sel = 0;
    s_evo_tick = NULL;
    s_evolving = false;
    s_evo_frame = 0;
    s_hold_active = false;
    s_hold = 0;
    world_snapshot(&s_w);
    world_inventory_snapshot(&s_inventory);
    world_party_t party;
    world_party_snapshot(&party);
    s_shiny = party.count && (party.members[0].flags & 1u);
    s_care_feedback[0] = '\0';
    refresh_evolution();
    pokemon_idle_reset(&s_motion, s_w.species);
    s_motion_tick = lv_timer_create(motion_tick, 80, NULL);
    screen_set_redraw(redraw_for_dump);
    draw_all();
    ESP_LOGI(TAG, "P5：等级 %u 亲密度 %u", s_w.level,
             nurture_pct(s_w.pet.intimacy));
}

void play_care_exit(void)
{
    if (s_motion_tick) { lv_timer_delete(s_motion_tick); s_motion_tick = NULL; }
    if (s_evo_tick) { lv_timer_delete(s_evo_tick); s_evo_tick = NULL; }
    s_evolving = false;
    s_hold_active = false;
    s_hold = 0;
}

bool play_care_screen_busy(void) { return s_evolving || s_hold_active; }

void play_care_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    // 停留期任何页面按键都只加速同一条 timer 导航路径。
    if (s_hold_active) { s_hold = HOLD_TICKS - 1; return; }
    if (btn == BSP_BTN_UP && ev == BSP_BTN_LONG && !s_evolving) {
        pokemon_names_set_style(pokemon_names_get_style() == POKEMON_NAMES_OFFICIAL
                                    ? POKEMON_NAMES_GS_LEGACY : POKEMON_NAMES_OFFICIAL);
        draw_all();
        return;
    }
    if (btn == BSP_BTN_DOWN && ev == BSP_BTN_LONG) { screen_dump(); return; }
    if (ev != BSP_BTN_CLICK) return;
    if (s_evolving) return;

    switch (btn) {
    case BSP_BTN_UP: {                     // A 执行
        if (s_sel == BAG_ACTION) {
            nav_open(PAGE_BAG);
            break;
        }
        if (s_sel == EVOLUTION_ACTION) {
            start_evolution();
            break;
        }
        world_t before = s_w;
        bool applied = true;
        s_care_feedback[0] = '\0';
        if (s_sel == 0) {
            item_use_result_t result;
            item_use_status_t status = world_item_use(s_w.species, ITEM_BERRY, &result);
            applied = status == ITEM_USE_OK;
            const char *message = status == ITEM_USE_OK ? "吃得很满足"
                : status == ITEM_USE_EMPTY ? "树果用完 去战斗"
                : status == ITEM_USE_NOT_APPLICABLE ? "已经吃饱了"
                : status == ITEM_USE_SAVE_FAILED ? "保存失败 请重试"
                : status == ITEM_USE_STORAGE_UNAVAILABLE ? "存档暂不可用"
                : status == ITEM_USE_BUSY ? "请先结束对战" : "伙伴已变 请重试";
            snprintf(s_care_feedback, sizeof(s_care_feedback), "%s", message);
        }
        if (s_sel == 1) world_play();
        if (s_sel == 2) { applied=false;snprintf(s_care_feedback,sizeof(s_care_feedback),"体力仅随时间恢复"); }
        world_snapshot(&s_w);
        world_inventory_snapshot(&s_inventory);
        refresh_evolution();
        if (applied) { pokemon_idle_reset(&s_motion, s_w.species); sfx_play(SFX_CARE); }
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
        world_inventory_snapshot(&s_inventory);
        s_care_feedback[0] = '\0';
        refresh_evolution();
        s_sel = (uint8_t)((s_sel + 1) % action_count());
        draw_all();
        break;

    case BSP_BTN_OK:                       // C 返回
        nav_back(PAGE_IDLE);
        break;

    default:
        break;
    }
}
