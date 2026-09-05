// main/play_dex.c —— P6 图鉴。
//
// 对应 docs/pages/P6-dex.md。
//
// ## 未捕获显示为剪影
//
// `shade_map = (0,0,0,3)` —— 三档前景色全指向最深色，背景保持透明。
// **零额外素材**：同一张 sprite，换个调色板就是剪影。
//
// 已知局限（页面文档记了）：主色偏浅的物种（猫老大、大针蜂）剪影里
// 会漏出白色区域，因为色号 3 既是背景也是「最浅色」，
// sprite 内部的浅色区域会跟着变透明。这是 2bpp 的固有性质不是 bug；
// 彻底解决要加一位掩码（+19 字节/151 只），留待真机看观感再定。
//
// ## 「见过」与「未捕获」要分开
//
// 遇到但没抓到的标「见过」。这一条承载 S8 那份「闪光遇到了但跑了」的
// 遗憾 —— 四个位图而非两个就是为了存下它。

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "lvgl.h"

#include "assets.h"
#include "encounter.h"
#include "nav.h"
#include "play.h"
#include "render.h"
#include "screen.h"
#include "world.h"

static const char *TAG = "p6";

#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define SCR_H SCREEN_H

#define C_BG    RGB_HEX(0x9bbc0f)
#define C_INK   RGB_HEX(0x0f380f)
#define C_MID   RGB_HEX(0x306230)

// 网格：5 列 × 4 行 = 每页 20 只，151 只共 8 页。
// 每格 44×56（sprite 32px @scale1 + 编号）。
#define COLS 5
#define ROWS 4
#define PER_PAGE (COLS * ROWS)
#define CELL_W 46
#define CELL_H 56
#define GRID_X 6
#define GRID_Y 34

static uint8_t s_page;

static void hline_at(int y)
{
    for (int x = 0; x < SCR_W; x++) screen_px(x, y, C_MID);
}

static void draw_band(int band_y)
{
    screen_band_clear(C_BG);
    #define Y(v) ((v) - band_y)

    const dex_t *d = world_dex();
    char buf[48];

    // 标题 + 计数
    render_text(8, Y(4), "图鉴", C_INK);
    snprintf(buf, sizeof(buf), "%u/%u", dex_count_caught(d), DEX_SPECIES);
    render_text(SCR_W - 8 - render_text_width(buf), Y(4), buf, C_INK);
    hline_at(Y(26));

    // 网格
    for (int i = 0; i < PER_PAGE; i++) {
        uint16_t sid = (uint16_t)(s_page * PER_PAGE + i + 1);
        if (sid > DEX_SPECIES) break;
        int cx = GRID_X + (i % COLS) * CELL_W;
        int cy = GRID_Y + (i / COLS) * CELL_H;

        bool caught = dex_is_caught(d, sid);
        bool seen = dex_is_seen(d, sid);

        const uint8_t *spr = assets_back_sprite(sid);
        species_t sp;
        if (spr && assets_species(sid, &sp)) {
            uint16_t pal[4];
            if (caught) {
                assets_palette(sp.palette, pal);
            } else if (seen) {
                // 剪影：三档前景全指最深色，背景仍透明（色号 3）
                pal[0] = pal[1] = pal[2] = C_MID;
                pal[3] = 0;
            } else {
                // 没见过 —— 连剪影都不画，只留编号
                spr = NULL;
            }
            if (spr) render_sprite_2bpp(cx + 4, Y(cy), spr, 32, 1, pal);
        }

        // 编号。见过但没抓到的标一下 —— 「见过」是 P6 的专有状态
        snprintf(buf, sizeof(buf), "%03u", sid);
        render_text(cx + 4, Y(cy + 34), buf, caught ? C_INK : C_MID);
    }

    // 页码
    snprintf(buf, sizeof(buf), "%u/%u", s_page + 1,
             (DEX_SPECIES + PER_PAGE - 1) / PER_PAGE);
    render_text(SCR_W - 8 - render_text_width(buf), Y(268), buf, C_MID);

    hline_at(Y(292));
    render_text(8, Y(298), "[A]详情 [B]翻页 [C]返回", C_INK);

    #undef Y
    screen_push_band(band_y);
}

static void draw_all(void)
{
    for (int y = 0; y < SCR_H; y += BAND_H) draw_band(y);
}

static void redraw_for_dump(void) { draw_all(); }

void play_dex_enter(void)
{

    s_page = 0;
    screen_set_redraw(redraw_for_dump);
    draw_all();

    // **不做自动截图** —— P1 那个是在只有一页时加的，
    // 现在有了 dbg.c 的按键注入，截图由 walk.py 显式发 's' 触发。
    // 页面自己再截一张只会与之交错，让 PC 侧收到半张（踩过一次）。

    const dex_t *d = world_dex();
    ESP_LOGI(TAG, "P6：已捕获 %u 见过 %u", dex_count_caught(d),
             dex_count_seen(d));
}

void play_dex_exit(void)
{
}

void play_dex_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (btn == BSP_BTN_DOWN && ev == BSP_BTN_LONG) { screen_dump(); return; }
    if (ev != BSP_BTN_CLICK) return;

    switch (btn) {
    case BSP_BTN_UP:                       // A 详情（P7 未实现）
        ESP_LOGI(TAG, "详情页未实现");
        break;

    case BSP_BTN_DOWN: {                   // B 翻页
        uint8_t pages = (DEX_SPECIES + PER_PAGE - 1) / PER_PAGE;
        s_page = (uint8_t)((s_page + 1) % pages);
        draw_all();
        break;
    }

    case BSP_BTN_OK:                       // C 返回
        nav_go(PAGE_IDLE);
        break;

    default:
        break;
    }
}
