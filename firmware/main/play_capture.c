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

#include "capture_presentation.h"
#include "screen_idle.h"
#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"
#include "presentation_clock.h"
#include "lvgl.h"

#include "assets.h"
#include "battle.h"
#include "ball_assets.h"
#include "capture.h"
#include "exp.h"
#include "exploration.h"
#include "game_ui.h"
#include "nav.h"
#include "music_director.h"
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

// 白底金银框：正面精灵 2x 居中于 y40..151；球、说明和整个判定框
// 收进带 2，结果与统一消息框收进带 3。闪白始终重画精灵的两条带。
#define SPRITE_Y 40
#define SPRITE_SIZE 112
#define SPRITE_SCALE 2
#define BALL_Y 160
#define INSTRUCTION_Y 188
#define BAR_BOX_Y 208
#define BAR_H 16
// Frame 1's ink is asymmetric within its tiles: this 32px box's interior
// spans offsets 7..26. Center the bar there, leaving 2px above and below.
#define BAR_Y (BAR_BOX_Y + 9)
#define BAR_X ((SCR_W - CAP_BAR_WIDTH) / 2)
#define MSG_Y 248
#define BAR_BAND (BAR_Y / BAND_H)     // 判定条所在的带号
#define CAPTURE_TICK_MS 40
#define HOLD_TICKS 25                 // 25 × 40ms = 1.0s

SCREEN_ASSERT_ALLOW_CROSS_BAND(capture_sprite, SPRITE_Y, SPRITE_SIZE);
SCREEN_ASSERT_ALLOW_CROSS_BAND(capture_ball, BALL_Y, 24);
SCREEN_ASSERT_ALLOW_CROSS_BAND(capture_instruction, INSTRUCTION_Y, 16);
SCREEN_ASSERT_ALLOW_CROSS_BAND(capture_bar_box, BAR_BOX_Y, 32);
SCREEN_ASSERT_ALLOW_CROSS_BAND(capture_bar, BAR_Y, BAR_H);
SCREEN_ASSERT_ALLOW_CROSS_BAND(capture_message, MSG_Y, 16);
SCREEN_ASSERT_ALLOW_CROSS_BAND(capture_footer, 280, 40);

static lv_timer_t *s_tick;
static battle_session_t s_session;
extern uint32_t dbg_battle_seed;

static cap_ball_t s_ball;
static inventory_t s_inventory;
_Static_assert(CAP_BALL_COUNT == ITEM_BALL_COUNT, "Capture and inventory ball IDs must match");
static int64_t s_t0;
static cap_result_t s_last;
static cap_result_t s_visible; // Exact geometry used by the last displayed bar.
static bool s_press_handled;
static bool s_thrown;
static bool s_caught;
static bool s_fled;
static bool s_no_ball;
static bool s_save_failed;
static bool s_box_full;
static bool s_capture_pending;
static mon_t s_pending_mon;
enum { REPLACE_NONE, REPLACE_LIST, REPLACE_CONFIRM, REPLACE_DISCARD };
static unsigned s_replace, s_replace_choice, s_replace_row, s_replace_count, s_replace_slot;
static uint16_t s_replace_ids[BOX_CAPACITY];
static mon_t s_replace_expected;
static box_view_options_t s_replace_options;
static const char *s_replace_message;
static void load_replacements(void) {
    s_replace_count=world_box_view(&s_replace_options,s_replace_ids);
    if(s_replace_row>=s_replace_count)s_replace_row=0;
}
static void capture_member_label(const mon_t *mon,char *out,size_t size) {
    species_t sp;
    if(assets_species(mon->species_id,&sp))snprintf(out,size,"%.*s Lv%u%s",sp.name_zh_len,sp.name_zh,mon->level,mon->flags&1?" ★":"");
    else snprintf(out,size,"#%u Lv%u",mon->species_id,mon->level);
}
static void draw_replacements(int band) {
    char text[80], capacity[16];
    snprintf(capacity,sizeof(capacity),"%u格",BOX_CAPACITY);
    game_ui_title(band,s_replace==REPLACE_LIST?"仓库已满":s_replace==REPLACE_DISCARD?"放走新伙伴？":"替换伙伴？",capacity);

    if(s_replace==REPLACE_LIST){
        game_ui_text_fitted(band,12,64,216,"选择要替换的仓库伙伴",GAME_UI_INK);
        for(unsigned i=0,top=s_replace_row/5*5;i<5&&top+i<s_replace_count;i++){
            mon_t m;if(!world_box_at(s_replace_ids[top+i],&m))continue;
            capture_member_label(&m,text,sizeof(text));
            game_ui_text_fitted(band,36,94+i*30,192,text,GAME_UI_INK);
            game_ui_list_marker(band,14,94+i*30,top+i,s_replace_count,s_replace_row);
        }
        game_ui_text_fitted(band,12,252,216,s_replace_message?s_replace_message:"长按A切换排序",GAME_UI_MUTED);
        game_ui_footer(band,"A上 B下 C选择 长按B放走");
    }else{
        game_ui_box(band,8,80,224,136);
        if(s_replace==REPLACE_CONFIRM){
            game_ui_text_fitted(band,20,96,200,"将放生以下伙伴",GAME_UI_INK);
            capture_member_label(&s_replace_expected,text,sizeof(text));
            game_ui_text_fitted(band,20,130,200,text,GAME_UI_INK);
            game_ui_text_fitted(band,20,174,200,s_replace_expected.flags&1?"这是闪光伙伴，无法撤销":"替换后无法撤销",GAME_UI_ACCENT);
        }else{
            game_ui_text_fitted(band,20,108,200,"保留仓库所有伙伴",GAME_UI_INK);
            game_ui_text_fitted(band,20,156,200,"新捕获的伙伴将离开",GAME_UI_ACCENT);
        }
        if(s_replace_message)game_ui_text_fitted(band,12,244,216,s_replace_message,GAME_UI_ACCENT);
        static const char *const replace_actions[]={"取消","确认替换"};
        static const char *const discard_actions[]={"取消","确认放走"};
        game_ui_actions(band,s_replace==REPLACE_CONFIRM?replace_actions:discard_actions,2,s_replace_choice);
    }
    // Draw the common incoming identity last, above either list or modal.
    capture_member_label(&s_pending_mon,text,sizeof(text));
    game_ui_text_fitted(band,12,40,216,text,GAME_UI_ACCENT);
}

static bool s_chain_prompt;
static uint8_t s_chain_choice;

static bool s_hold_active;
static bool s_return_to_battle;
static uint16_t s_capture_exp;
static bool s_hold_skip;
static presentation_clock_t s_clock;
static void start_clock(void){presentation_clock_start(&s_clock,(uint32_t)(esp_timer_get_time()/1000));}

// Outcome commits once at throw time; presentation never rerolls or spends items.
// Gold ThrowPokeBall: 36+16+16, return 8+16, bounce 4*32+8,
// then four 48-frame checks. Each anim_wait also has its dispatch frame.
// This yields 434 frames before the result, plus 36 for breakout. Keep the original
// phase clock with the absorption adaptation in capture_presentation.h,
// sampled on our 40 ms display timer; outcomes still commit once.
#define CAPTURE_REVEAL_FRAME 434u
#define CAPTURE_END_FRAME 470u
#define CAPTURE_REVEAL_MS capture_frame_ms(CAPTURE_REVEAL_FRAME)
#define CAPTURE_END_MS capture_frame_ms(CAPTURE_END_FRAME)
static bool s_animating;
static uint32_t s_anim_ms;
static music_id_t s_previous_music;

static void capture_reveal(void)
{
    if (s_caught) music_director_play(MUSIC_CAUGHT);
    else if (!s_capture_pending) {
        music_director_play(s_previous_music);
        sfx_play(SFX_ESCAPED);
    }
}

// Nearest-neighbour sampling keeps the shrinking sprite crisp. Rotation is
// deliberately limited to the small ball's rocking motion, about its centre.
static void capture_image(int band_y, const uint8_t *data, int w, int h,
                          int cx, int cy, int size, int tilt, const uint16_t *pal)
{
    if (!data || size <= 0) return;
    // Reject whole off-band images before sampling. Keep the original integer
    // transform (including truncation for negative tilt) for identical pixels.
    int margin = (size * (tilt < 0 ? -tilt : tilt) + 31) / 32;
    int top = cy - size / 2, left = cx - size / 2;
    int y0 = band_y - top - margin, y1 = band_y + SCREEN_BAND_H - top + margin;
    if (y0 < 0) y0 = 0;
    if (y1 > size) y1 = size;
    int x0 = -left - margin, x1 = SCREEN_W - left + margin;
    if (x0 < 0) x0 = 0;
    if (x1 > size) x1 = size;
    int stride = (w + 3) / 4;
    for (int y = y0; y < y1; y++) {
      int sy = y * h / size;
      for (int x = x0; x < x1; x++) {
        int dx = x - size / 2, dy = y - size / 2;
        int px = cx + dx - dy * tilt / 16;
        int py = cy + dy + dx * tilt / 16 - band_y;
        if ((unsigned)px >= SCREEN_W || (unsigned)py >= SCREEN_BAND_H) continue;
        int sx = x * w / size;
        int shade = (data[sy * stride + sx / 4] >> (6 - (sx % 4) * 2)) & 3;
        if (shade == 3) continue;
        screen_px(px, py, pal[shade]);
      }
    }
}

static void capture_star(int band_y, int x, int y, int radius, uint16_t color)
{
    for (int i = -radius; i <= radius; i++) {
        screen_px(x + i, y - band_y, color);
        screen_px(x, y + i - band_y, color);
    }
}

static void draw_capture_stage(int band_y, const uint8_t *spr, int size,
                               const uint16_t *pal)
{
    unsigned t = capture_source_frame(s_anim_ms);
    int monster_size = size * 2;
    if (t >= 71 && t < 80) monster_size = monster_size * (80 - t) / 9;
    else if (t >= 80 && (t < CAPTURE_REVEAL_FRAME || s_caught || s_capture_pending)) monster_size = 0;
    else if (t >= CAPTURE_REVEAL_FRAME && t < CAPTURE_END_FRAME)
        monster_size = monster_size * (t - CAPTURE_REVEAL_FRAME) / (CAPTURE_END_FRAME - CAPTURE_REVEAL_FRAME);
    int monster_y = 98;
    if (t >= CAPTURE_REVEAL_FRAME && t < CAPTURE_END_FRAME && !s_caught && !s_capture_pending)
        monster_y = 184 - 86 * (t - CAPTURE_REVEAL_FRAME) / (CAPTURE_END_FRAME - CAPTURE_REVEAL_FRAME);
    capture_image(band_y, spr, size, size, 120, monster_y, monster_size, 0, pal);

    capture_ball_pose_t pose=capture_ball_pose(s_anim_ms);
    int bx=pose.x,by=pose.y,tilt=pose.tilt;
    ui_art_t ball;
    bool broken = t >= CAPTURE_REVEAL_FRAME && !s_caught && !s_capture_pending;
    bool opened = (t >= 37 && t < 97) || (broken && t < CAPTURE_REVEAL_FRAME + 14);
    if ((!broken || opened) && assets_ui(opened ? "ball_open" : "ball_24", &ball))
        capture_image(band_y, ball.data, ball.w, ball.h, bx, by, 32, tilt,
                      ball_assets_palette(s_ball));
    if (t >= CAPTURE_REVEAL_FRAME && t < CAPTURE_END_FRAME) {
        int spread = 12 + (t - CAPTURE_REVEAL_FRAME);
        uint16_t color = s_caught ? RGB_HEX(0xe8b820) : GAME_UI_ACCENT;
        capture_star(band_y, 120 - spread, 168 - spread / 2, 4, color);
        capture_star(band_y, 120 + spread, 168 - spread / 2, 4, color);
        capture_star(band_y, 120, 160 - spread, 5, color);
    }
}

static cap_context_t capture_context(void)
{
    species_t sp;
    cap_context_t out = {.pet_level = s_session.pet_level, .wild_level = s_session.wild_level};
    if (assets_species(nav_ctx()->enc.species_id, &sp)) {
        out.wild_speed = sp.speed;
        out.wild_weight_hg = sp.weight_hg;
    }
    return out;
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
    bonus = bonus * nurture_capture_percent(&w.pet) / 100;

    cap_context_t context = capture_context();
    return cap_window_width_context(cr, (uint16_t)bonus, s_ball, c->enc.hp_ratio, &context);
}

static bool s_replaying;

static void draw_bar_band(int band_y)
{
    // 位置仍为 capture.c 的 0..200，包含两端；框不占用判定尺度。
    // 投球后冻结当次窗口，与冻结的 s_last.pointer 使用同一结果。
    uint16_t w = s_thrown ? s_last.window_w : s_replaying ? s_visible.window_w : current_window();
    uint16_t offset = s_thrown ? s_last.window_start : s_replaying ? s_visible.window_start : (CAP_BAR_WIDTH - w) / 2;
    uint16_t start = (uint16_t)(BAR_X + offset);
    uint16_t end = (uint16_t)(start + w);
    uint32_t elapsed = (uint32_t)((esp_timer_get_time() - s_t0) / 1000);
    uint16_t p = s_thrown ? s_last.pointer : s_replaying ? s_visible.pointer : cap_pointer_position(elapsed);

    if (!s_thrown && !s_replaying) {
        s_visible = (cap_result_t){.window_w = w, .window_start = offset,
            .window_end = (uint16_t)(offset + w), .pointer = p, .ball = s_ball,
            .caught = p >= offset && p <= offset + w};
    }
    game_ui_box(band_y, 8, BAR_BOX_Y, 224, 32);
    for (int dy = 0; dy < BAR_H; dy++) {
        int y = BAR_Y + dy - band_y;
        for (int dx = 0; dx <= CAP_BAR_WIDTH; dx++) {
            int x = BAR_X + dx;
            bool in_win = (x >= start && x <= end);
            screen_px(x, y, in_win ? GAME_UI_ACCENT : GAME_UI_BG);
        }
    }
    // 黑色竖线与像素箭头的尖端都落在真实判定坐标 p。
    for (int dy = 0; dy < BAR_H; dy++) {
        screen_px(BAR_X + p, BAR_Y + dy - band_y, GAME_UI_INK);
    }
    ui_art_t cursor;
    if (assets_ui("cursor", &cursor)) {
        game_ui_cursor(band_y, BAR_X + p - cursor.w + 1,
                        BAR_Y + (BAR_H - cursor.h) / 2);
    }
}

static void draw_band(int band_y)
{
    screen_band_clear(GAME_UI_BG);
    if(s_replace && !s_animating){draw_replacements(band_y);screen_push_band(band_y);return;}
    #define Y(v) ((v) - band_y)

    const nav_ctx_t *c = nav_ctx();
    char buf[64];
    species_t sp;
    bool has = assets_species(c->enc.species_id, &sp);

    if (has) {
        snprintf(buf, sizeof(buf), "%.*s", sp.name_zh_len, sp.name_zh);
    } else {
        snprintf(buf, sizeof(buf), "#%03u", c->enc.species_id);
    }
    game_ui_title(band_y, "捕获", buf);

    // 正面按实际源尺寸 2x 居中。缺图回退也必须读取 BACK 的真实尺寸，
    // 不能把 GSC 48px 记录按旧的 32px 步长解码。
    uint8_t sprite_size = 0;
    const uint8_t *spr = assets_front_form(c->enc.species_id,c->enc.biome, &sprite_size);
    if (!spr) {
        sprite_asset_t fallback;
        if (assets_back_sprite_info(c->enc.species_id, &fallback) && fallback.w == fallback.h) {
            spr = fallback.data;
            sprite_size = fallback.w;
        }
    }
    int display_size = sprite_size * SPRITE_SCALE;
    if (spr && has && sprite_size && display_size <= SPRITE_SIZE) {
        uint16_t pal[4];
        assets_palette_variant(sp.palette, c->enc.is_shiny, pal);
        if (s_thrown) draw_capture_stage(band_y, spr, sprite_size, pal);
        else
        game_ui_sprite_centered(band_y, (SCR_W - SPRITE_SIZE) / 2, SPRITE_Y,
                                  SPRITE_SIZE, SPRITE_SIZE, spr,
                                  sprite_size, sprite_size, SPRITE_SCALE, pal);
    }

    if (s_chain_prompt) {
        game_ui_box(band_y, 8, 160, 224, 112);
        render_text(20, Y(174), "要中断连胜并捕获吗？", GAME_UI_INK);
        snprintf(buf, sizeof(buf), "当前连胜 %lu", (unsigned long)world_exploration_chain());
        render_text(20, Y(196), buf, GAME_UI_INK);
        game_ui_text_fitted(band_y, 20, 218, 200, "确认后不论成败都会清零", GAME_UI_MUTED);
        static const char *const labels[] = {"取消", "捕获"};
        game_ui_action_row(band_y, 20, 246, 200, labels, 2, s_chain_choice);
        game_ui_footer(band_y, s_save_failed ? "保存失败，请重试" : GAME_UI_NAV_HINT);
        screen_push_band(band_y);
        return;
    }

    if (!s_thrown) {
    // Original GSC ball: 32px source canvas, visible 24px bounds. A captured
    // Pokémon stays inside the closed ball; colors distinguish the three kinds.
    ui_art_t ball;
    if (assets_ui("ball_24", &ball)) {
        ball_asset_bounds_t bounds = ball_assets_visible(false);
        render_sprite_2bpp_wh(12 - bounds.x, Y(BALL_Y - bounds.y),
                              ball.data, ball.w, ball.h, 1, ball_assets_palette(s_ball));
    }
    snprintf(buf, sizeof(buf), "%s ×%u", cap_ball_name(s_ball),
             s_inventory.quantity[s_ball]);
    render_text(44, Y(BALL_Y + 4), buf, GAME_UI_INK);
    render_text(12, Y(INSTRUCTION_Y), s_box_full ? "满仓：捕获后选择替换" : s_session.won ? "战斗获胜，仅此一球"
                : "在蓝色区域投球", GAME_UI_MUTED);

    // 判定条
    if (band_y < BAR_BOX_Y+32 && band_y+BAND_H > BAR_BOX_Y) draw_bar_band(band_y);

    }

    // 结果
    if (s_animating && s_anim_ms < CAPTURE_REVEAL_MS) {
        render_text(12, Y(MSG_Y), s_anim_ms < capture_frame_ms(97) ? "投出精灵球！" : "捕获中", GAME_UI_INK);
    } else if (s_capture_pending) {
        render_text(12, Y(MSG_Y), "已命中，保存失败", GAME_UI_INK);
    } else if (s_hold_active && c->done_note == NAV_NOTE_CAUGHT) {
        render_text(12, Y(MSG_Y), "已捕获", GAME_UI_INK);
        snprintf(buf,sizeof(buf),"经验 +%u",s_capture_exp);const char *note = buf;
        render_text(228 - render_text_width(note), Y(MSG_Y), note, GAME_UI_MUTED);
    } else if (s_caught) {
        render_text(12, Y(MSG_Y), "捕获成功", GAME_UI_INK);
    } else if (s_fled) {
        render_text(12, Y(MSG_Y), "跑掉了", GAME_UI_INK);
    } else if (s_return_to_battle) {
        render_text(12, Y(MSG_Y), "捕获失败，准备反击", GAME_UI_INK);
    } else if (s_box_full) {
        render_text(12, Y(MSG_Y), "仓库已满，可手动替换", GAME_UI_INK);
    } else if (s_save_failed) {
        render_text(12, Y(MSG_Y), "保存失败，请重试", GAME_UI_INK);
    } else if (s_no_ball) {
        render_text(12, Y(MSG_Y), "没有球了", GAME_UI_INK);
    } else if (s_thrown) {
        render_text(12, Y(MSG_Y), s_last.caught ? "命中" : "未命中", GAME_UI_INK);
    }

    game_ui_footer(band_y, s_animating ? "捕获中……" : s_capture_pending ? "[C]重试保存" : s_hold_active ? "[C]继续"
                : (s_caught || s_fled ? "[C]继续" : "A上 B下 C投球 长按B返回"));

    #undef Y
    screen_push_band(band_y);
}

static void draw_all(void)
{
    for (int y = 0; y < SCR_H; y += BAND_H) draw_band(y);
}

static bool save_caught_result_at(unsigned slot,const mon_t *expected)
{
    nav_ctx_t *c = nav_ctx();world_t before,after;world_snapshot(&before);
    world_capture_result_t result=world_capture_replace_uid(c->uid,&s_pending_mon,slot,expected);
    if (result!=WORLD_CAPTURE_OK) {
        s_save_failed=result!=WORLD_CAPTURE_FULL && result!=WORLD_CAPTURE_STALE;
        if(result==WORLD_CAPTURE_FULL){
            s_replace=REPLACE_LIST;s_replace_choice=s_replace_row=0;
            s_replace_options=(box_view_options_t){.sort=BOX_SORT_LEVEL_ASC};load_replacements();
            s_replace_message=NULL;
        }else if(result==WORLD_CAPTURE_STALE){
            s_replace=REPLACE_LIST;load_replacements();s_replace_message="伙伴已变，请重新选择";
        }else s_replace_message="保存失败，请重试";
        s_capture_pending = true;
        return false;
    }
    world_snapshot(&after);s_capture_exp=(uint16_t)(after.exp-before.exp);
    s_capture_pending = false;
    s_save_failed=false;
    s_replace=REPLACE_NONE;s_replace_message=NULL;
    s_caught = true;
    c->done_note = NAV_NOTE_CAUGHT;
    c->valid = false;
    return true;
}

static bool save_caught_result(void){return save_caught_result_at(BOX_CAPACITY,NULL);}

static void redraw_for_dump(void)
{
    // Reproduce the last presented pointer; a screenshot must not move the
    // visible hit window or change which throw would succeed between ticks.
    s_replaying = true;
    draw_all();
    s_replaying = false;
}

static void tick_impl(lv_timer_t *t)
{
    uint32_t ms=presentation_clock_sample(&s_clock,(uint32_t)(esp_timer_get_time()/1000),screen_idle_is_off());
    if (s_chain_prompt || screen_idle_is_off()) return;
    if (s_animating) {
        uint32_t before = s_anim_ms;
        s_anim_ms=ms;
        for(unsigned shake=0;shake<3;shake++) {
            uint32_t cue=capture_frame_ms(287+shake*49);
            if(before<cue&&s_anim_ms>=cue)sfx_play(SFX_MENU);
        }
        if (before < CAPTURE_REVEAL_MS && s_anim_ms >= CAPTURE_REVEAL_MS) {
            capture_reveal();
#ifdef CONFIG_POKEWALK_DEBUG_KEYS
            ESP_LOGI(TAG,"@@CAPTURE_PHASE result elapsed_ms=%lu",(unsigned long)s_anim_ms);
#endif
        }
        if (s_anim_ms >= CAPTURE_END_MS) {
#ifdef CONFIG_POKEWALK_DEBUG_KEYS
            ESP_LOGI(TAG,"@@CAPTURE_PHASE end elapsed_ms=%lu",(unsigned long)s_anim_ms);
#endif
            s_anim_ms = CAPTURE_END_MS;
            s_animating = false;
            s_hold_active = !s_capture_pending;
            s_hold_skip = false; start_clock();
        }
        draw_all();
        return;
    }

    if (s_hold_active) {
        if (!s_hold_skip && ms < (s_caught ? 3200u : HOLD_TICKS * CAPTURE_TICK_MS)) return;

        // 先清状态和 timer 指针，再从唯一出口切页；exit 不会重复删除。
        s_hold_active = false;
        s_hold_skip = false; start_clock();
        s_tick = NULL;
        lv_timer_delete(t);
        if(s_return_to_battle)nav_go(PAGE_BATTLE);else nav_end_encounter();
        return;
    }

    if (s_caught || s_fled || s_capture_pending) return;
    // **只重画判定条那一带** —— 指针在动，别的都是静态的。
    // 全屏重画 150KB/帧跑不动 1.2 秒的往复。
    for (int y=(BAR_BOX_Y/BAND_H)*BAND_H;y<BAR_BOX_Y+32;y+=BAND_H) draw_band(y);
}

static void tick(lv_timer_t *timer)
{
    screen_cadence_begin(CAPTURE_TICK_MS);
    tick_impl(timer);
    screen_cadence_end();
}

void play_capture_enter(void)
{
    nav_ctx_t *c = nav_ctx();
    encounter_t current;
    if (!world_get_encounter_uid(c->uid, &current) || current.ts != c->enc.ts ||
        !world_battle_get_uid(c->uid, &s_session)) {
        c->valid = false;
        nav_end_encounter();
        return;
    }
    c->enc = current;
    if (!s_session.initialized) {
        world_t w; world_snapshot(&w);
        uint32_t seed = dbg_battle_seed ? dbg_battle_seed : (c->enc.ts ? c->enc.ts : 1u);
        if (!battle_session_init(&s_session, w.species, w.level,
                                  c->enc.species_id, (c->enc.level ? c->enc.level : battle_wild_level_for_pet(c->enc.rarity, w.level)),
                                  nurture_ability_factor(&w.pet), seed)) { nav_end_encounter(); return; }
        if (c->enc.hp_ratio && c->enc.hp_ratio < 100) {
            s_session.wild_hp = (uint32_t)s_session.wild_hp_max * c->enc.hp_ratio / 100;
            if (!s_session.wild_hp) s_session.wild_hp = 1;
        }
        s_session.intro_seen = true;
        if (!world_battle_set_uid(c->uid, &s_session)) { nav_end_encounter(); return; }
    }
    if (!battle_session_can_capture(&s_session)) { nav_go(PAGE_BATTLE); return; }
    c->enc.hp_ratio = battle_session_hp_ratio(&s_session);
    c->battled = s_session.finished;
    c->battle_won = s_session.won;
    s_ball = CAP_BALL_POKE;
    world_inventory_snapshot(&s_inventory);
    for (unsigned i = 0; i < CAP_BALL_COUNT; i++)
        if (s_inventory.quantity[i]) { s_ball = (cap_ball_t)i; break; }
    s_t0 = esp_timer_get_time();
    s_thrown = s_caught = s_fled = s_no_ball = false;
    s_press_handled = false;
    s_save_failed = false;
    s_capture_pending = false;
    s_save_failed=false;
    s_replace=REPLACE_NONE;s_replace_message=NULL;
    s_box_full = !world_capture_has_room(current.species_id);
    s_chain_prompt = exploration_chain_encounter(&current) && world_exploration_chain() > 0;
    s_chain_choice = 0;
    memset(&s_pending_mon, 0, sizeof(s_pending_mon));
    s_hold_active = false;
    s_return_to_battle = false;s_capture_exp=0;
    s_hold_skip = false; start_clock();
    nav_ctx()->done_note = NAV_NOTE_NONE;
    s_animating = false;
    s_anim_ms = 0;
    memset(&s_last, 0, sizeof(s_last));

    screen_set_redraw(redraw_for_dump);
    draw_all();
    s_tick = lv_timer_create(tick, CAPTURE_TICK_MS, NULL); // 25fps，指针要跟手

    // **不做自动截图** —— P1 那个是在只有一页时加的，
    // 现在有了 dbg.c 的按键注入，截图由 walk.py 显式发 's' 触发。
    // 页面自己再截一张只会与之交错，让 PC 侧收到半张（踩过一次）。

    ESP_LOGI(TAG, "P4：#%u HP %u%% 窗口 %u px",
             c->enc.species_id, c->enc.hp_ratio, current_window());
}

void play_capture_exit(void)
{
    if (s_tick) { lv_timer_delete(s_tick); s_tick = NULL; }
    s_hold_active = false;
    s_animating = false;
    s_hold_skip = false; start_clock();
}

bool play_capture_can_leave(void) { return !s_chain_prompt && !s_animating && !s_capture_pending && !s_hold_active && s_session.finished; }

bool play_capture_screen_busy(void)
{
    // The pre-throw pointer waits for input and never throws automatically.
    // Keep the throw, shakes and timed result visible through navigation.
    return s_animating || s_hold_active;
}

void play_capture_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    // Resolve confirmations on CLICK only: a PRESS must not change pages
    // and leak its delayed CLICK into the battle, or break a chain on long C.
    if (s_chain_prompt) {
        int direction = nav_direction(btn, ev);
        if (direction) s_chain_choice = nav_list_selection(btn, ev, 2, s_chain_choice);
        if (nav_return(btn, ev) || (nav_confirm(btn, ev) && !s_chain_choice)) {
            nav_go(PAGE_BATTLE);
            return;
        }
        if (nav_confirm(btn, ev)) {
            if (world_capture_break_chain_uid(nav_ctx()->uid)) {
                s_chain_prompt = false;
                s_save_failed = false;
                s_t0 = esp_timer_get_time();
            } else s_save_failed = true;
        }
        draw_all();
        return; // The confirmation key must never also throw the ball.
    }
    // Hardware CLICK waits for release and double-click classification. Throw
    // on PRESS; semantic browser/debug CLICK remains supported. Consume the
    // delayed CLICK even if the immediate attempt failed to save/spend a ball.
    if (btn == BSP_BTN_OK && ev == BSP_BTN_CLICK && s_press_handled) {
        s_press_handled = false;
        return;
    }
    if (btn == BSP_BTN_OK && ev == BSP_BTN_PRESS && !s_thrown) {
        s_press_handled = true;
        ev = BSP_BTN_CLICK;
    }
    if (s_animating) return;
    if(s_replace){
        bool confirm=nav_confirm(btn,ev),back=nav_return(btn,ev);
        int direction=nav_direction(btn,ev);
        if(s_replace==REPLACE_LIST){
            if(back){s_replace=REPLACE_DISCARD;s_replace_choice=0;s_replace_message=NULL;}
            else if(btn==BSP_BTN_UP && ev==BSP_BTN_LONG){
                s_replace_options.sort=s_replace_options.sort==BOX_SORT_LEVEL_ASC?BOX_SORT_DEX:BOX_SORT_LEVEL_ASC;
                load_replacements();s_replace_message=NULL;
            }else if(direction){s_replace_row=nav_list_selection(btn,ev,s_replace_count,s_replace_row);s_replace_message=NULL;}
            else if(confirm && s_replace_row<s_replace_count){
                s_replace_slot=s_replace_ids[s_replace_row];
                if(world_box_at(s_replace_slot,&s_replace_expected)){s_replace=REPLACE_CONFIRM;s_replace_choice=0;s_replace_message=NULL;}
                else{load_replacements();s_replace_message="伙伴已变，请重新选择";}
            }
        }else{
            s_replace_choice=nav_list_selection(btn,ev,2,s_replace_choice);
            if(back || (confirm&&!s_replace_choice)){s_replace=REPLACE_LIST;s_replace_message=NULL;}
            else if(confirm){
                if(s_replace==REPLACE_DISCARD){
                    world_take_uid(nav_ctx()->uid,NULL);nav_ctx()->valid=false;
                    s_capture_pending=false;s_replace=REPLACE_NONE;
                    music_director_play(s_previous_music);nav_end_encounter();return;
                }
                if(save_caught_result_at(s_replace_slot,&s_replace_expected)){
                    capture_reveal();s_hold_active=true;s_hold_skip=false;start_clock();
                }
            }
        }
        draw_all();return;
    }

    // 停留期任何页面按键都只加速同一条 timer 导航路径。
    if (s_hold_active) {
        if (nav_confirm(btn, ev)) s_hold_skip = true;
        return;
    }
    if (nav_return(btn, ev)) {
        if (!s_thrown && !s_capture_pending) nav_go(PAGE_BATTLE);
        return;
    }
    if (ev != BSP_BTN_CLICK) return;

    if (s_capture_pending) {
        if (btn == BSP_BTN_OK) {
            if (save_caught_result()) { capture_reveal(); s_hold_active = true; s_hold_skip = false; start_clock(); }
            draw_all();
        }
        return;
    }

    nav_ctx_t *c = nav_ctx();

    switch (btn) {
    case BSP_BTN_OK: {                     // Confirm throws immediately
        if (s_thrown) return;
        s_box_full = !world_capture_has_room(c->enc.species_id);
        if (!world_battle_get_uid(c->uid, &s_session)) {
            c->valid = false; nav_end_encounter(); return;
        }
        if (!battle_session_can_capture(&s_session)) { nav_go(PAGE_BATTLE); return; }
        world_inventory_snapshot(&s_inventory);
        if (s_inventory.quantity[s_ball] == 0) {
            ESP_LOGI(TAG, "没有球了");
            s_no_ball = true;
            for (int y=(MSG_Y/BAND_H)*BAND_H;y<MSG_Y+16;y+=BAND_H) draw_band(y);
            return;
        }
        s_no_ball = false;
        s_save_failed = false;
        // Freeze before any NVS transaction. Drawing and judging share the
        // same pointer/window, irrespective of flash latency or frame interval.
        s_last = s_visible;
        // Consume a victory's only chance before resolving or displaying it.
        // Returning, changing balls and queued button events cannot restore it.
        if (s_session.won) s_session.capture_used_after_win = true;
        // Detach before consuming a ball: persistence failure must not spend
        // the item or leave a handled encounter in the pending queue.
        if (!s_session.started) {
            world_t current;
            world_snapshot(&current);
            s_session.ability_factor_q10 = nurture_ability_factor(&current.pet);
        }
        s_session.started = true;
        if (!world_capture_ball_spend_uid(c->uid, (uint8_t)s_ball, &s_session)) {
            s_save_failed = true;
            world_battle_get_uid(c->uid, &s_session);
            draw_all();
            return;
        }
        world_inventory_snapshot(&s_inventory);
        s_thrown = true;

        if (s_last.caught) {
            s_pending_mon = (mon_t){
                .species_id = c->enc.species_id,
                .level = s_session.wild_level,
                .exp = exp_for_level(s_session.wild_level),
                .hp = c->enc.hp_ratio ? c->enc.hp_ratio : 1,
                .nickname_idx = 0xFF,
                .intimacy = s_ball == CAP_BALL_FRIEND ? 40 : 0,
                .flags = c->enc.is_shiny ? 1u : 0u,
            };
            save_caught_result();
        }
        if (!s_caught && !s_capture_pending) {
            world_mark_seen(c->enc.species_id, c->enc.is_shiny);
            // The encounter phase, rather than a second random flee roll,
            // determines every failed throw's consequence.
            if (s_session.won || !world_battle_get_uid(c->uid, &s_session)) {
                s_fled = true;
                s_last.fled = true;
                world_take_uid(c->uid, NULL);
                c->valid = false;
            } else {
                s_session.retaliation_pending = true;
                s_session.started = true;
                if (world_battle_set_uid(c->uid, &s_session)) {
                    s_return_to_battle = true;
                    s_last.fled = false;
                } else {
                    s_fled = true;
                    c->valid = false;
                }
            }
        }
        s_animating = true;
        s_anim_ms = 0;
        start_clock();
        s_previous_music = music_director_current();
        music_director_play(MUSIC_NONE);
        sfx_play(SFX_BALL_THROW);
        s_hold_active = false;
        s_hold_skip = false; start_clock();
        draw_all();
        break;
    }

    case BSP_BTN_UP:
    case BSP_BTN_DOWN:                     // Previous/next available ball
        if (s_thrown) break;
        world_inventory_snapshot(&s_inventory);
        for (unsigned i = 0; i < CAP_BALL_COUNT; i++) {
            s_ball = (cap_ball_t)((s_ball + CAP_BALL_COUNT + nav_direction(btn, ev)) % CAP_BALL_COUNT);
            if (s_inventory.quantity[s_ball]) break;
        }
        s_thrown = false;
        s_no_ball = false;
        s_save_failed = false;
        draw_all();
        break;


    default:
        break;
    }
}
