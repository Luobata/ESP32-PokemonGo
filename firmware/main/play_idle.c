// main/play_idle.c —— P1 待机页（F8：最小可玩闭环）。
//
// 对应 docs/pages/P1-idle.md。这是「每次点亮屏幕的第一眼」，
// 也是第一个把 sprite、中文、养成三条轴同时画出来的页面。
//
// ## 布局（240×320，全部数字来自页面文档）
//
//     y=0   ┌────────────────────────┐
//           │ 皮卡丘 Lv12      ♥ 78  │  状态栏
//     y=24  ├────────────────────────┤
//           │                        │
//           │        [back]          │  32×32 @scale3 = 96px 居中
//           │                        │  呼吸动效只重绘这 96×96
//     y=200 │                        │
//           │ 饱食 ████████░░         │  三条轴
//           │ 心情 ██████░░░░         │
//           │ 体能 █████████░         │
//           │ 今日行程 ███░░░░░       │
//     y=292 ├────────────────────────┤
//           │ [A]照料 [B]图鉴 [C]遭遇 │  184px / 232px
//     y=320 └────────────────────────┘
//
// ## 呼吸动效：只向上
//
// `sim/effects.py` 实测 151 只 back sprite 的留白：下方 137 只都只有
// 4 行，上方差异很大（0 行的有 22 只）。所以**向下浮动会裁掉贴底边的
// sprite**，只能向上。序列 [0,0,-1,-2,-2,-2,-1,0] ——
// 顶点停留最久，模拟屏息，比等分三角波自然。
//
// ## LVGL 用法
//
// 用 lv_canvas 而非 lv_img：我们要逐像素画 2bpp 与 1bpp 点阵，
// 而 LVGL 的图片系统要先转成它的格式。canvas 更直接，
// 也与将来脱离 LVGL 走裸横带渲染的方向一致。
//
// 缓冲开在 static 而非堆上：240×320×2 = 150KB 装不下（可用堆 231KB
// 但那要留给 WiFi 与 LVGL）。**只开精灵区那块 96×96×2 = 18KB**，
// 其余用 LVGL 对象画 —— 与页面文档「呼吸动效只重绘 96×96」一致。

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"

#include "assets.h"
#include "bsp_battery.h"
#include "bsp_display.h"
#include "play.h"
#include "render.h"
#include "ui_pixel.h"

static const char *TAG = "idle";

// 呼吸序列 —— 与 sim/effects.py 的 breath_sequence(8, rise=2) 逐值相同。
// 硬编码而非现算：8 个 int8 比一个函数省，而且值是定死的。
static const int8_t BREATH[] = {0, 0, -1, -2, -2, -2, -1, 0};
#define BREATH_FRAMES (sizeof(BREATH) / sizeof(BREATH[0]))

// 精灵画布：32×32 @scale3 = 96×96。
// LV_COLOR_FORMAT_RGB565 每像素 2 字节 → 18432 字节。
#define SPR_SIZE 96
static lv_color_t s_spr_buf[SPR_SIZE * SPR_SIZE];

static lv_obj_t *s_scr;
static lv_obj_t *s_canvas;         // 精灵区
static lv_obj_t *s_title, *s_hp;
static lv_obj_t *s_axis_lbl[4], *s_axis_bar[4];
static lv_obj_t *s_keys;
static lv_timer_t *s_tick;
static uint8_t s_breath_i;

// 主宠状态。真正的 S4 养成还没移植（PC 侧在 sim/gameplay.py），
// 这里先用固定值把页面画出来 —— F8 的验收标准是「屏幕上出现
// 主宠与三条轴」，不是「养成逻辑跑通」。
// 接 S4 是 F9 的事，那时这几个字段换成 pet_state_t。
static struct {
    uint16_t species;
    uint8_t level;
    uint8_t satiety, mood, stamina, progress;
    uint8_t intimacy;
    uint8_t pending;               // 待处理遭遇数（C 键角标）
} s_pet = {25, 12, 62, 84, 95, 70, 78, 3};

// 调色板。palettes.bin 的格式是 RGB565 小端，与 LVGL 的 RGB565 一致 ——
// 但 lv_color_t 在不同配置下宽度不同，所以走 lv_color_hex 转一道。
extern const uint8_t pal_bin_start[] asm("_binary_palettes_bin_start");

static void load_palette(uint8_t set_idx, lv_color_t out[4])
{
    const uint8_t *body = pal_bin_start + 12;
    const uint8_t *p = body + (size_t)set_idx * 4 * 2;
    for (int i = 0; i < 4; i++) {
        uint16_t rgb = (uint16_t)(p[i * 2] | (p[i * 2 + 1] << 8));
        uint8_t r = (uint8_t)(((rgb >> 11) & 0x1F) << 3);
        uint8_t g = (uint8_t)(((rgb >> 5) & 0x3F) << 2);
        uint8_t b = (uint8_t)((rgb & 0x1F) << 3);
        out[i] = lv_color_make(r, g, b);
    }
}

// 画精灵到画布。offset_y 是呼吸偏移（负数 = 上浮）。
static void draw_sprite(int8_t offset_y)
{
    lv_canvas_fill_bg(s_canvas, lv_color_hex(0x9bbc0f), LV_OPA_COVER);

    const uint8_t *spr = assets_back_sprite(s_pet.species);
    if (!spr) return;

    species_t sp;
    lv_color_t pal[4];
    load_palette(assets_species(s_pet.species, &sp) ? sp.palette : 0, pal);

    // back sprite 32×32 @scale3。呼吸只改 y —— 见文件头的说明。
    render_sprite_2bpp(s_canvas, 0, offset_y * 3, spr, 32, 3, pal);
}

static void set_bar(lv_obj_t *bar, uint8_t pct)
{
    lv_bar_set_value(bar, pct, LV_ANIM_OFF);
}

static void refresh_stats(void)
{
    species_t sp;
    char buf[64];
    if (assets_species(s_pet.species, &sp)) {
        // 中文名不是 NUL 结尾（指向字符串池），用 %.*s
        snprintf(buf, sizeof(buf), "%.*s Lv%u",
                 sp.name_zh_len, sp.name_zh, s_pet.level);
    } else {
        snprintf(buf, sizeof(buf), "#%03u Lv%u", s_pet.species, s_pet.level);
    }
    lv_label_set_text(s_title, buf);

    // 亲密度用心形 —— ♥ 不在字库（PingFang 没这个字形），
    // 用 pixelart 的手绘点阵。这里先用文字代替，
    // 等 P5 详情页做点阵光标时一起接。
    snprintf(buf, sizeof(buf), "%u", s_pet.intimacy);
    lv_label_set_text(s_hp, buf);

    set_bar(s_axis_bar[0], s_pet.satiety);
    set_bar(s_axis_bar[1], s_pet.mood);
    set_bar(s_axis_bar[2], s_pet.stamina);
    set_bar(s_axis_bar[3], s_pet.progress);
}

static void tick(lv_timer_t *t)
{
    (void)t;
    // 呼吸：4 fps（250ms），8 帧一周期 = 2 秒一次呼吸，
    // 接近静息呼吸节律（sim/effects.py 的说明）。
    s_breath_i = (uint8_t)((s_breath_i + 1) % BREATH_FRAMES);
    draw_sprite(BREATH[s_breath_i]);
}

void play_idle_enter(void)
{
    s_scr = ui_pixel_screen_create("PokeWalk");

    // -- 状态栏 ----------------------------------------------------------
    s_title = lv_label_create(s_scr);
    lv_obj_align(s_title, LV_ALIGN_TOP_LEFT, 8, 34);

    s_hp = lv_label_create(s_scr);
    lv_obj_align(s_hp, LV_ALIGN_TOP_RIGHT, -8, 34);

    // -- 精灵区（canvas）--------------------------------------------------
    s_canvas = lv_canvas_create(s_scr);
    lv_canvas_set_buffer(s_canvas, s_spr_buf, SPR_SIZE, SPR_SIZE,
                         LV_COLOR_FORMAT_RGB565);
    lv_obj_align(s_canvas, LV_ALIGN_TOP_MID, 0, 70);

    // -- 三条轴 + 行程 ---------------------------------------------------
    static const char *AXIS[4] = {"饱食", "心情", "体能", "今日行程"};
    for (int i = 0; i < 4; i++) {
        s_axis_lbl[i] = lv_label_create(s_scr);
        lv_label_set_text(s_axis_lbl[i], AXIS[i]);
        lv_obj_align(s_axis_lbl[i], LV_ALIGN_TOP_LEFT, 8, 186 + i * 22);

        s_axis_bar[i] = lv_bar_create(s_scr);
        lv_obj_set_size(s_axis_bar[i], i == 3 ? 152 : 168, 10);
        lv_obj_align(s_axis_bar[i], LV_ALIGN_TOP_LEFT,
                     i == 3 ? 80 : 64, 188 + i * 22);
        lv_bar_set_range(s_axis_bar[i], 0, 100);
    }

    // -- 三键提示 --------------------------------------------------------
    //
    // 这一行是 P1-③ 那个规格冲突的落点：按半宽算 184px 放得下，
    // 按定长 16px 算 272px 会溢出。render.c 选了半宽方案。
    s_keys = lv_label_create(s_scr);
    lv_label_set_text(s_keys, "[A]照料 [B]图鉴 [C]遭遇");
    lv_obj_align(s_keys, LV_ALIGN_BOTTOM_LEFT, 8, -6);

    refresh_stats();
    s_breath_i = 0;
    draw_sprite(0);

    lv_screen_load(s_scr);
    // 4 fps —— 呼吸不需要更快，且省电（页面文档：状态栏与三条轴
    // 是静态的，不参与逐帧重绘）
    s_tick = lv_timer_create(tick, 250, NULL);

    ESP_LOGI(TAG, "P1 待机页：#%u Lv%u  三键提示 %d px",
             s_pet.species, s_pet.level,
             render_text_width("[A]照料 [B]图鉴 [C]遭遇"));
}

void play_idle_exit(void)
{
    // 先停定时器再删屏 —— 反过来的话 tick 会在屏已删除后访问
    // 野指针。上游 AGENTS.md 专门点了这条。
    if (s_tick) { lv_timer_delete(s_tick); s_tick = NULL; }
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; }
    s_canvas = NULL;
}

void play_idle_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (ev != BSP_BTN_CLICK) return;

    // A 照料 / B 图鉴 / C 遭遇 —— 按使用频率排（页面文档）。
    // 三个目标页还没做，先在串口回显，证明按键分发通了。
    switch (btn) {
    case BSP_BTN_UP:                       // A
        // 照料：喂食 → 饱食 +30（S4 的 feed）
        s_pet.satiety = (uint8_t)(s_pet.satiety + 30 > 100 ? 100
                                                           : s_pet.satiety + 30);
        s_pet.mood = (uint8_t)(s_pet.mood + 5 > 100 ? 100 : s_pet.mood + 5);
        refresh_stats();
        ESP_LOGI(TAG, "照料 → 饱食 %u 心情 %u", s_pet.satiety, s_pet.mood);
        break;
    case BSP_BTN_DOWN:                     // B
        ESP_LOGI(TAG, "图鉴（P6 未实现）");
        break;
    case BSP_BTN_OK:                       // C
        ESP_LOGI(TAG, "遭遇 %u 条待处理（P2 未实现）", s_pet.pending);
        break;
    default:
        break;
    }
}
