// main/play_enc.c —— P2 遭遇列表。
//
// 对应 docs/pages/P2-encounter-list.md。
//
// ## 为什么要有列表这一层
//
// 遭遇是**后台累积**的（设备在兜里，屏幕不亮）。掏出来时可能攒了三五只，
// 直接进战斗就没得选。列表让玩家先扫一眼稀有度，决定处理顺序 ——
// 页面文档的原话是「这是 30 秒会话里最值钱的 3 秒」。
//
// ## 无动效
//
// 纯静态。这一页的作用是「看清」，动效只会干扰；且它可能是玩家
// 停留最久的一页，省电。所以没有 lv_timer —— **进来画一次，
// 按键才重画**。
//
// ## 光标为什么是点阵不是字符
//
// 页面文档写的是 `▸`，但**字库里没有这个字形**（PingFang 不含它，
// convert_font.py 顶部记了原因）。用字符会渲染成空白，
// 而 render_text 静默跳过缺字 —— 屏幕上就是「光标不见了」。
// ui.bin 里的 cursor 是 sim/pixelart.py 算法生成的 5×9 三角。

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "lvgl.h"

#include "assets.h"
#include "battle.h"
#include "nav.h"
#include "play.h"
#include "render.h"
#include "screen.h"
#include "transition.h"
#include "world.h"

static const char *TAG = "p2";

#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define SCR_H SCREEN_H

#define C_BLACK RGB_HEX(0x000000)

// 布局。**每个元素都不跨横带边界**（边界在 y=80/160/240）——
// 跨界会被两条带各画一半，刷新频率不同就撕裂（P1 栽过一次）。
//
//   y=4    刚才路上遇到              标题      带 0
//   y=32   ▸ 妙蛙种子  ★★☆☆☆ 野外   第 1 条   带 0
//   y=56     小拉达    ★☆☆☆☆ 住宅区 第 2 条   带 0
//   …每条 24px，最多 8 条到 y=200            带 0~2
//   y=264  稀有度越高越难捕获        提示      带 3
//   y=292  ──────────────────────
//   y=298  [A]选中 [B]下条 [C]返回            带 3
#define ROW0_Y 32
#define ROW_H 24
#define VISIBLE_ROWS 8

static uint8_t s_sel;          // 选中第几条
static uint8_t s_top;          // 滚动窗口的第一条

// P2 → P3 遭遇转场。100ms 一拍推进 6 个原始 60fps 帧，实际时长与
// trans_frames() 一致；LVGL timer 只重画屏幕，不阻塞独立的 world 任务。
#define TRANS_TICK_MS 100
#define TRANS_FRAME_STEP 6
static lv_timer_t *s_trans_tick;
static trans_id_t s_trans_id;
static uint16_t s_trans_frame;
static uint16_t s_trans_q;
static bool s_trans_flash_black;
static bool s_trans_finish_hold;

static void draw_stars(int x, int y, uint8_t rarity, uint16_t fg)
{
    // ★☆ 都在字库里（convert_font.py 明确收了这两个）。
    // 不用点阵星星 —— 那是 S8 闪光特效用的，尺寸与文字不匹配。
    char buf[32];
    int n = 0;
    for (int i = 0; i < 5 && n < 28; i++) {
        const char *s = (i < rarity) ? "★" : "☆";
        memcpy(buf + n, s, 3);
        n += 3;
    }
    buf[n] = '\0';
    render_text(x, y, buf, fg);
}

// 画一条横线（分隔线）。各页各留一份 —— 两行代码，
// 而提到公共头文件反而要处理颜色参数。
static void hline_at(int y)
{
    for (int x = 0; x < SCR_W; x++) screen_px(x, y, C_MID);
}

static void overlay_transition(int band_y)
{
    uint16_t *band = screen_band();
    uint8_t gy0 = (uint8_t)(band_y / TRANS_TILE);
    uint8_t gy1 = (uint8_t)((band_y + BAND_H) / TRANS_TILE);

    for (uint8_t gy = gy0; gy < gy1; gy++) {
        int y0 = gy * TRANS_TILE - band_y;
        for (uint8_t gx = 0; gx < TRANS_GRID_W; gx++) {
            if (!trans_tile_covered(s_trans_id, s_trans_q, gx, gy)) continue;
            int x0 = gx * TRANS_TILE;
            for (int dy = 0; dy < TRANS_TILE; dy++) {
                for (int dx = 0; dx < TRANS_TILE; dx++) {
                    band[(y0 + dy) * SCR_W + x0 + dx] = C_BLACK;
                }
            }
        }
    }
}

static void draw_band(int band_y)
{
    screen_band_clear(C_BG);
    #define Y(v) ((v) - band_y)

    const enc_queue_t *q = world_queue();
    char buf[64];
    species_t sp;

    // -- 标题 ----------------------------------------------------------
    render_text(8, Y(4), "刚才路上遇到", C_INK);
    if (q->count) {
        snprintf(buf, sizeof(buf), "%u", q->count);
        render_text(SCR_W - 8 - render_text_width(buf), Y(4), buf, C_MID);
    }
    hline_at(Y(26));

    // -- 列表 ----------------------------------------------------------
    if (q->count == 0) {
        render_text(8, Y(ROW0_Y + 24), "队列是空的", C_MID);
    }
    for (uint8_t i = 0; i < VISIBLE_ROWS; i++) {
        uint8_t idx = (uint8_t)(s_top + i);
        if (idx >= q->count) break;
        const encounter_t *e = &q->items[idx];
        int y = ROW0_Y + i * ROW_H;

        // 光标 —— ui.bin 的点阵，不是 ▸（字库没有那个字形）
        if (idx == s_sel) {
            ui_art_t cur;
            if (assets_ui("cursor", &cur)) {
                static const uint16_t PAL[4] = {
                    C_INK, C_MID,
                    C_LIGHT, 0,
                };
                render_sprite_2bpp_wh(6, Y(y + 3), cur.data, cur.w, cur.h,
                                      1, PAL);
            }
        }

        // 物种名
        if (assets_species(e->species_id, &sp)) {
            snprintf(buf, sizeof(buf), "%.*s", sp.name_zh_len, sp.name_zh);
        } else {
            snprintf(buf, sizeof(buf), "#%03u", e->species_id);
        }
        render_text(18, Y(y), buf, C_INK);

        // 稀有度星 —— 右对齐到 x=200，名字最长 5 字（80px）不会撞
        draw_stars(112, Y(y), e->rarity, C_INK);

        // 闪光标记：star_7 + star_5 一大一小两颗星，替掉原来的「闪」字。
        // 星星是 ui.bin 的 2bpp 点阵；颜色走调用侧调色板，与素材解耦。
        // 行内垂直居中：24px 行高，7px 星 offset 8、5px 星 offset 9。
        if (e->is_shiny) {
            static const uint16_t STAR_PAL[4] = {
                C_INK, RGB_HEX(0xfff0a0), RGB_HEX(0xffffff), 0,
            };
            ui_art_t s7, s5;
            if (assets_ui("star_7", &s7)) {
                render_sprite_2bpp_wh(200, Y(y + (ROW_H - s7.h) / 2),
                                      s7.data, s7.w, s7.h, 1, STAR_PAL);
                if (assets_ui("star_5", &s5)) {
                    render_sprite_2bpp_wh(200 + s7.w + 2,
                                          Y(y + (ROW_H - s5.h) / 2),
                                          s5.data, s5.w, s5.h, 1, STAR_PAL);
                }
            }
        }
    }

    // -- 提示与三键 ------------------------------------------------------
    render_text(8, Y(264), "稀有度越高越难捕获", C_MID);
    hline_at(Y(292));
    render_text(8, Y(298), "[A]选中 [B]下条 [C]返回", C_INK);

    if (s_trans_flash_black) {
        screen_band_clear(C_BLACK);
    } else if (s_trans_q) {
        overlay_transition(band_y);
    }

    #undef Y
    screen_push_band(band_y);
}

static void draw_all(void)
{
    for (int y = 0; y < SCR_H; y += BAND_H) draw_band(y);
}

static void redraw_for_dump(void) { draw_all(); }

static uint16_t covered_tiles(void)
{
    uint16_t n = 0;
    for (uint8_t gy = 0; gy < TRANS_GRID_H; gy++) {
        for (uint8_t gx = 0; gx < TRANS_GRID_W; gx++) {
            if (trans_tile_covered(s_trans_id, s_trans_q, gx, gy)) n++;
        }
    }
    return n;
}

static void transition_tick(lv_timer_t *timer)
{
    if (s_trans_finish_hold) {
        s_trans_tick = NULL;
        lv_timer_delete(timer);
        s_trans_flash_black = false;
        s_trans_q = 0;
        s_trans_finish_hold = false;
        s_trans_frame = 0;
        // 先清状态再切页；play_enc_exit 不会重复删除当前 timer。
        nav_go(PAGE_BATTLE);
        return;
    }

    uint16_t total = trans_frames(s_trans_id);
    uint16_t next = (uint16_t)(s_trans_frame + TRANS_FRAME_STEP);
    s_trans_frame = next < total ? next : total;

    uint16_t geom_start = trans_has_flash(s_trans_id) ? TRANS_FLASH_FRAMES : 0;
    if (s_trans_frame <= geom_start) {
        s_trans_q = 0;
        // Circle 系的 72 帧闪屏压成 6 帧一档，仍保持 1.2 秒总时长。
        s_trans_flash_black = (((s_trans_frame - 1) / TRANS_FRAME_STEP) & 1u) == 0;
    } else {
        s_trans_flash_black = false;
        s_trans_q = (uint16_t)((uint32_t)(s_trans_frame - geom_start) * 1000u /
                               (total - geom_start));
    }

    draw_all();
    ESP_LOGI(TAG, "@@TRANS id=%u frame=%u/%u q=%u tiles=%u/%u flash=%u",
             (unsigned)s_trans_id, s_trans_frame, total, s_trans_q,
             covered_tiles(), TRANS_GRID_W * TRANS_GRID_H,
             s_trans_flash_black ? 1u : 0u);

    // 满黑保留一拍再进 P3，避免最后一帧被新页面同一回调立刻覆盖。
    if (s_trans_frame == total) s_trans_finish_hold = true;
}

static void start_transition(void)
{
    const nav_ctx_t *c = nav_ctx();
    world_t w;
    world_snapshot(&w);

    uint8_t idx;
    uint8_t wild_level = battle_wild_level(c->enc.rarity);
    // biome 顺序与 sensing 的 dwell_by_biome 一致：0 野外、4 交通枢纽。
    bool open_biome = c->enc.biome == 0 || c->enc.biome == 4;
    s_trans_id = trans_pick(false, wild_level, w.level, open_biome, &idx);
    s_trans_frame = 0;
    s_trans_q = 0;
    s_trans_flash_black = false;
    s_trans_finish_hold = false;
    s_trans_tick = lv_timer_create(transition_tick, TRANS_TICK_MS, NULL);
    if (!s_trans_tick) {
        ESP_LOGE(TAG, "转场 timer 创建失败，直接进入战斗");
        nav_go(PAGE_BATTLE);
        return;
    }

    ESP_LOGI(TAG, "@@TRANS start id=%u idx=%u wild=%u pet=%u open=%u frames=%u",
             (unsigned)s_trans_id, idx, wild_level, w.level,
             open_biome ? 1u : 0u, trans_frames(s_trans_id));
}

void play_enc_enter(void)
{
    s_sel = 0;
    s_top = 0;
    s_trans_tick = NULL;
    s_trans_frame = 0;
    s_trans_q = 0;
    s_trans_flash_black = false;
    s_trans_finish_hold = false;
    screen_set_redraw(redraw_for_dump);
    draw_all();

    // **不做自动截图** —— P1 那个是在只有一页时加的，
    // 现在有了 dbg.c 的按键注入，截图由 walk.py 显式发 's' 触发。
    // 页面自己再截一张只会与之交错，让 PC 侧收到半张（踩过一次）。

    ESP_LOGI(TAG, "P2：队列 %u 条", world_queue()->count);
}

void play_enc_exit(void)
{
    if (s_trans_tick) { lv_timer_delete(s_trans_tick); s_trans_tick = NULL; }
    s_trans_flash_black = false;
    s_trans_q = 0;
    s_trans_finish_hold = false;
}

// A 单击 = 选中进战斗。主流程不依赖提示行没有说明的双击手势。
static void on_select(void)
{
    const enc_queue_t *q = world_queue();
    if (q->count == 0) return;

    nav_ctx_t *c = nav_ctx();
    c->enc = q->items[s_sel];
    c->uid = q->items[s_sel].uid;
    c->valid = true;
    c->battled = false;
    c->battle_won = false;
    start_transition();
}

// 丢弃会不可逆地移除遭遇，放在 B 长按，避免和主流程三键争抢单击语义。
// C 长按由 main.c 全局用于退出玩法，不能作为页面手势；截图仍可走 dbg 的 s。
static void discard_selected(void)
{
    const enc_queue_t *q = world_queue();
    if (q->count == 0) return;

    encounter_t dropped;
    if (world_take_encounter(s_sel, &dropped)) {
        ESP_LOGI(TAG, "丢弃 #%u ★%u", dropped.species_id,
                 dropped.rarity);
    }

    // 队列变短了，选中项与滚动窗口都可能越界。
    const enc_queue_t *nq = world_queue();
    if (s_sel >= nq->count && s_sel) s_sel--;
    if (s_top > s_sel) s_top = s_sel;
    draw_all();
}

void play_enc_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    // 转场期间冻结菜单输入；调试截图仍由 dbg.c 的 s 命令处理。
    if (s_trans_tick) return;

    // 破坏性操作使用长按保护，不占用提示行里的三种主操作。
    if (btn == BSP_BTN_DOWN && ev == BSP_BTN_LONG) {
        discard_selected();
        return;
    }

    if (ev != BSP_BTN_CLICK) return;

    const enc_queue_t *q = world_queue();

    switch (btn) {
    case BSP_BTN_UP:                       // A 选中
        on_select();
        break;

    case BSP_BTN_DOWN:                     // B 下移一条
        if (q->count == 0) break;
        s_sel = (uint8_t)((s_sel + 1) % q->count);
        // 滚动窗口跟着选中项走
        if (s_sel < s_top) s_top = s_sel;
        if (s_sel >= s_top + VISIBLE_ROWS) {
            s_top = (uint8_t)(s_sel - VISIBLE_ROWS + 1);
        }
        draw_all();
        break;

    case BSP_BTN_OK:                       // C 返回
        nav_go(PAGE_IDLE);
        break;

    default:
        break;
    }
}
