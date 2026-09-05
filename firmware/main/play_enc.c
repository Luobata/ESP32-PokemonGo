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
#include "nav.h"
#include "play.h"
#include "render.h"
#include "screen.h"
#include "world.h"

static const char *TAG = "p2";

#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define SCR_H SCREEN_H

#define C_BG    RGB_HEX(0x9bbc0f)
#define C_INK   RGB_HEX(0x0f380f)
#define C_MID   RGB_HEX(0x306230)
#define C_LIGHT RGB_HEX(0x8bac0f)

// 布局。**每个元素都不跨横带边界**（边界在 y=80/160/240）——
// 跨界会被两条带各画一半，刷新频率不同就撕裂（P1 栽过一次）。
//
//   y=4    刚才路上遇到              标题      带 0
//   y=32   ▸ 妙蛙种子  ★★☆☆☆ 野外   第 1 条   带 0
//   y=56     小拉达    ★☆☆☆☆ 住宅区 第 2 条   带 0
//   …每条 24px，最多 8 条到 y=200            带 0~2
//   y=264  稀有度越高越难捕获        提示      带 3
//   y=292  ──────────────────────
//   y=298  [A]选中 [B]返回 [C]丢弃            带 3
#define ROW0_Y 32
#define ROW_H 24
#define VISIBLE_ROWS 8

static uint8_t s_sel;          // 选中第几条
static uint8_t s_top;          // 滚动窗口的第一条

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
                    RGB_HEX(0x0f380f), RGB_HEX(0x306230),
                    RGB_HEX(0x8bac0f), 0,
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

        // 闪光标记
        if (e->is_shiny) render_text(200, Y(y), "闪", C_INK);
    }

    // -- 提示与三键 ------------------------------------------------------
    render_text(8, Y(264), "稀有度越高越难捕获", C_MID);
    hline_at(Y(292));
    render_text(8, Y(298), "[A]选中 [B]返回 [C]丢弃", C_INK);

    #undef Y
    screen_push_band(band_y);
}

static void draw_all(void)
{
    for (int y = 0; y < SCR_H; y += BAND_H) draw_band(y);
}

static void redraw_for_dump(void) { draw_all(); }

void play_enc_enter(void)
{

    s_sel = 0;
    s_top = 0;
    screen_set_redraw(redraw_for_dump);
    draw_all();

    // **不做自动截图** —— P1 那个是在只有一页时加的，
    // 现在有了 dbg.c 的按键注入，截图由 walk.py 显式发 's' 触发。
    // 页面自己再截一张只会与之交错，让 PC 侧收到半张（踩过一次）。

    ESP_LOGI(TAG, "P2：队列 %u 条", world_queue()->count);
}

void play_enc_exit(void)
{
    // 这一页没有定时器（无动效，页面文档：它的作用是「看清」），
    // 也不用删屏（那张 LVGL 空屏五页共用）。所以这里什么都不做。
}

// A 双击 = 选中进战斗。
//
// 三键不够用，所以按 docs/09-device.md 那条「靠双击/长按扩展」：
// **A 单击移动光标、A 双击确认**。
// 页面文档只写了「A 选中」没说光标怎么动，而 S1 文档说
// 「队列容量 16 正好是 P2 一屏两页的量」—— 预期有滚动，
// 那就必须有移动键。
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
    nav_go(PAGE_BATTLE);
}

void play_enc_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (btn == BSP_BTN_DOWN && ev == BSP_BTN_LONG) { screen_dump(); return; }

    // A 双击 = 确认选中（单击是移动光标，见 on_select 上方）
    if (btn == BSP_BTN_UP && ev == BSP_BTN_DOUBLE) { on_select(); return; }

    if (ev != BSP_BTN_CLICK) return;

    const enc_queue_t *q = world_queue();

    switch (btn) {
    case BSP_BTN_UP:                       // A 单击 = 下移一条
        if (q->count == 0) { nav_go(PAGE_IDLE); return; }
        s_sel = (uint8_t)((s_sel + 1) % q->count);
        // 滚动窗口跟着选中项走
        if (s_sel < s_top) s_top = s_sel;
        if (s_sel >= s_top + VISIBLE_ROWS) {
            s_top = (uint8_t)(s_sel - VISIBLE_ROWS + 1);
        }
        draw_all();
        break;

    case BSP_BTN_DOWN:                     // B 返回
        nav_go(PAGE_IDLE);
        break;

    case BSP_BTN_OK:                       // C 丢弃
        if (q->count == 0) break;
        {
            encounter_t dropped;
            if (world_take_encounter(s_sel, &dropped)) {
                ESP_LOGI(TAG, "丢弃 #%u ★%u", dropped.species_id,
                         dropped.rarity);
            }
            // 队列变短了，选中项与滚动窗口都可能越界
            const enc_queue_t *nq = world_queue();
            if (s_sel >= nq->count && s_sel) s_sel--;
            if (s_top > s_sel) s_top = s_sel;
        }
        draw_all();
        break;

    default:
        break;
    }
}
