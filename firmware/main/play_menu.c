// P11: GSC's right-side Start menu, adapted to the 240x320 display.
// Frame/cursor are the original shared tiles.
#include <stdio.h>
#include <string.h>

#include "assets.h"
#include "game_ui.h"
#include "nav.h"
#include "play.h"
#include "pokemon_names.h"
#include "render.h"
#include "screen.h"
#include "screen_idle.h"
#include "world.h"
#include "audio_settings.h"

#define MENU_COUNT 9
#define MENU_X 120
#define MENU_Y 40
#define MENU_W 112
#define MENU_H 208
#define ROW_Y 56
#define ROW_STEP 21
#define OPTION_Y 72
#define OPTION_STEP 28
enum { OPTION_NAMES, OPTION_SCREEN_OFF, OPTION_MUTE, OPTION_VOLUME, OPTION_RETURN, OPTION_COUNT };

SCREEN_ASSERT_WITHIN_BAND(menu_title, 8, 16);
SCREEN_ASSERT_ALLOW_CROSS_BAND(menu_portrait, 88, 96);
SCREEN_ASSERT_WITHIN_BAND(menu_description, 252, 16);
SCREEN_ASSERT_ALLOW_CROSS_BAND(menu_option_names, OPTION_Y, 16);
SCREEN_ASSERT_WITHIN_BAND(menu_option_screen, OPTION_Y + OPTION_STEP, 16);
SCREEN_ASSERT_ALLOW_CROSS_BAND(menu_option_return, OPTION_Y + OPTION_STEP * 3, 16);

static const char *LABELS[MENU_COUNT] = {"图鉴", "队伍", "道具", "照料", "挑战", "选项", "成就", "探索", "关闭"};
static const char *DESCRIPTIONS[MENU_COUNT] = {
    "查看见过和捕获的伙伴", "查看伙伴 选择出战队首", "查看和使用随身道具",
    "喂食 玩耍 等待体力恢复", "道馆 徽章 联盟 赤红", "译名 声音与屏幕设置", "查看成长 领取成就奖励", "选择路线 追踪野生伙伴", "回到冒险中",
};
static uint8_t s_selected;
static bool s_options;
static bool s_volume_edit;
static bool s_audio_save_failed;
static uint8_t s_option_selected;
static world_t s_world;
static world_party_t s_party;
static unsigned s_claimable;

static void draw_options(int band_y)
{
    char value[64];
    game_ui_title(band_y, "选项", "");
    game_ui_box(band_y, 8, 56, 224, 160);
    render_text(40, OPTION_Y - band_y, "译名", GAME_UI_INK);
    snprintf(value, sizeof(value), "%s", pokemon_names_style_label());
    render_text(212 - render_text_width(value), OPTION_Y - band_y, value, GAME_UI_ACCENT);
    render_text(40, OPTION_Y + OPTION_STEP - band_y, "立即熄屏", GAME_UI_INK);
    render_text(40, OPTION_Y + OPTION_STEP * 2 - band_y, "静音", GAME_UI_INK);
    render_text(196, OPTION_Y + OPTION_STEP * 2 - band_y,
                audio_settings_muted() ? "开" : "关", GAME_UI_ACCENT);
    render_text(40, OPTION_Y + OPTION_STEP * 3 - band_y, "音量", GAME_UI_INK);
    snprintf(value, sizeof(value), "%u%%", audio_settings_volume());
    render_text(212-render_text_width(value), OPTION_Y + OPTION_STEP * 3-band_y, value, GAME_UI_ACCENT);
    render_text(40, OPTION_Y + OPTION_STEP * 4 - band_y, "返回菜单", GAME_UI_INK);
    game_ui_cursor(band_y, 20, OPTION_Y + s_option_selected * OPTION_STEP + 4);
    const char *hint;
    if (s_option_selected == OPTION_MUTE) {
        snprintf(value, sizeof(value), "%s", audio_settings_muted() ? "音乐和音效已关闭" : "音乐和音效已开启");
        hint = s_audio_save_failed ? "保存失败 按A重试" : "按A切换 重启后保留";
    } else if (s_option_selected == OPTION_VOLUME) {
        snprintf(value, sizeof(value), "%s", audio_settings_muted() ? "静音开启 调整后仍静音" : "音乐 音效 遇敌提示");
        hint = s_audio_save_failed ? "保存失败 请重试" : "音量设置重启后保留";
    } else if (s_option_selected == OPTION_NAMES) {
        snprintf(value, sizeof(value), "设置只影响显示名称");
        hint = "译名设置本次运行有效";
    } else {
        snprintf(value, sizeof(value), "%lu秒无操作自动熄屏", (unsigned long)(screen_idle_timeout_ms() / 1000));
        hint = s_option_selected == OPTION_SCREEN_OFF ? "按A熄屏 任意键亮屏" : "返回上一级菜单";
    }
    game_ui_text_centered(band_y, 12, 224, 216, 16, value, GAME_UI_MUTED);
    game_ui_text_centered(band_y, 12, 248, 216, 16, hint, GAME_UI_INK);
    game_ui_footer(band_y, s_volume_edit ? "[A]加大 [B]减小 [C]完成" : "[A]确定 [B]下一 [C]返回");
}

static void draw_main(int band_y)
{
    char name[48], text[48];
    game_ui_title(band_y, "菜单", "长B上一项");
    species_t species;
    bool found = assets_species(s_world.species, &species);
    if (found) snprintf(name, sizeof(name), "%.*s", species.name_zh_len, species.name_zh);
    else snprintf(name, sizeof(name), "#%03u", s_world.species);
    game_ui_text_centered(band_y, 8, 48, 104, 16, name, GAME_UI_INK);
    snprintf(text, sizeof(text), "Lv%u", s_world.level);
    game_ui_text_centered(band_y, 8, 72, 104, 16, text, GAME_UI_MUTED);
    uint8_t size;
    const uint8_t *front = assets_front_sprite(s_world.species, &size);
    if (found && front) {
        uint16_t palette[4];
        bool shiny = s_party.count && (s_party.members[0].flags & 1);
        assets_palette_variant(species.palette, shiny, palette);
        game_ui_sprite_centered(band_y, 8, 88, 104, 96, front, size, size, 1, palette);
    }
    snprintf(text, sizeof(text), "队伍 %u/%u", s_party.count, PARTY_MAX);
    game_ui_text_centered(band_y, 8, 196, 104, 16, text, GAME_UI_INK);
    snprintf(text, sizeof(text), "捕获 %u", dex_count_caught(world_dex()));
    game_ui_text_centered(band_y, 8, 220, 104, 16, text, GAME_UI_MUTED);

    game_ui_box(band_y, MENU_X, MENU_Y, MENU_W, MENU_H);
    for (unsigned row = 0; row < MENU_COUNT; row++) {
        int y = ROW_Y + row * ROW_STEP;
        render_text(156, y - band_y, LABELS[row], GAME_UI_INK);
        if(row==6&&s_claimable)render_text(212,y-band_y,"!",GAME_UI_ACCENT);
        if (row == s_selected) game_ui_cursor(band_y, 136, y + 4);
    }
    if(s_selected==6&&s_claimable){snprintf(text,sizeof(text),"可领取 %u 项奖励",s_claimable);game_ui_text_centered(band_y,8,252,224,16,text,GAME_UI_INK);}
    else game_ui_text_centered(band_y, 8, 252, 224, 16, DESCRIPTIONS[s_selected], GAME_UI_MUTED);
    game_ui_footer(band_y, "[A]选择 [B]下一 [C]关闭");
}

static void draw_all(void)
{
    for (int band_y = 0; band_y < SCREEN_H; band_y += SCREEN_BAND_H) {
        screen_band_clear(GAME_UI_BG);
        if (s_options) draw_options(band_y);
        else draw_main(band_y);
        screen_push_band(band_y);
    }
}

void play_menu_enter(void)
{
    if (!nav_is_returning()) {
        s_selected = 0;
        s_options = false;
        s_volume_edit = false;
        s_option_selected = 0;
        s_audio_save_failed = false;
    }
    world_snapshot(&s_world);
    world_party_snapshot(&s_party);
    achievement_view_t achievements;world_achievements_snapshot(&achievements);s_claimable=0;
    for(unsigned i=0;i<ACHIEVEMENT_COUNT;i++)
        if(!(achievements.store.claimed&(1u<<i))&&achievement_progress(&achievements,i)==achievement_info(i)->target)s_claimable++;
    screen_set_redraw(draw_all);
    draw_all();
}

void play_menu_exit(void) { }

void play_menu_presentation_snapshot(play_menu_view_t *out)
{
    if (out) *out = (play_menu_view_t){.selected = s_selected, .options = s_options,
                                     .option_selected = s_option_selected};
}

void play_menu_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (s_volume_edit) {
        if (ev != BSP_BTN_CLICK) return;
        if (btn == BSP_BTN_OK) s_volume_edit = false;
        else {
            int next = audio_settings_volume() + (btn == BSP_BTN_UP ? 5 : -5);
            if (next < 0) next = 0;
            if (next > 100) next = 100;
            s_audio_save_failed = !audio_settings_set_volume(next);
        }
        draw_all(); return;
    }
    if (btn == BSP_BTN_DOWN && (ev == BSP_BTN_CLICK || ev == BSP_BTN_LONG)) {
        if (s_options)
            s_option_selected = (s_option_selected + OPTION_COUNT + (ev == BSP_BTN_LONG ? -1 : 1)) % OPTION_COUNT;
        else s_selected = (s_selected + MENU_COUNT + (ev == BSP_BTN_LONG ? -1 : 1)) % MENU_COUNT;
        draw_all();
        return;
    }
    if (ev != BSP_BTN_CLICK) return;
    if (btn == BSP_BTN_OK) {
        if (s_options) { s_options = false; draw_all(); }
        else nav_back(PAGE_IDLE);
    } else if (btn == BSP_BTN_UP) {
        if (s_options) {
            if (s_option_selected == OPTION_SCREEN_OFF) {
                screen_idle_request_off();
                return;
            }
            if (s_option_selected == OPTION_MUTE) {
                s_audio_save_failed = !audio_settings_set_muted(!audio_settings_muted());
            } else if (s_option_selected == OPTION_VOLUME) s_volume_edit = true;
            else if (s_option_selected == OPTION_RETURN) s_options = false;
            else pokemon_names_set_style(pokemon_names_get_style() == POKEMON_NAMES_OFFICIAL
                                             ? POKEMON_NAMES_GS_LEGACY : POKEMON_NAMES_OFFICIAL);
            draw_all();
        } else {
            switch (s_selected) {
            case 0: nav_open(PAGE_DEX); break;
            case 1: nav_open(PAGE_PARTY); break;
            case 2: nav_open(PAGE_BAG); break;
            case 3: nav_open(PAGE_CARE); break;
            case 4: nav_open(PAGE_TRAINER); break;
            case 5: s_options = true; s_option_selected = 0; draw_all(); break;
            case 6: nav_open(PAGE_ACHIEVEMENTS); break;
            case 7: nav_open(PAGE_EXPLORATION); break;
            case 8: nav_back(PAGE_IDLE); break;
            default: break;
            }
        }
    }
}
