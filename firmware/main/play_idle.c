// main/play_idle.c —— P1 待机页（F8：最小可玩闭环）。
//
// 对应 docs/pages/P1-idle.md。
//
// ## 为什么整页自己画，不用 LVGL 的 label
//
// 第一版用 lv_label_set_text 画文字，真机上**所有汉字都是空心方框** ——
// LVGL 内置字体没有中文字形。而我明明写了 render_text（读 font16.bin
// 的 650 个字形）并跑了自检，自检还通过了 —— 但页面一次都没调它。
//
// 「自检通过 ≠ 画对了」。教训记在这里：**渲染类的东西必须看屏幕**，
// 串口日志与单元自检都证明不了像素对。
//
// 现在整页是一张 canvas，文字与 sprite 全部走 render.c。
//
// ## 分块横带渲染
//
// 整屏 240×320×2 = 150KB，占 231KB 可用堆的 65% —— 太冒险
// （WiFi 栈与 LVGL 还要用）。改成 240×80 的横带（37.5KB），
// 画 4 次推 4 次。
//
// 这正是 docs/01-constitution.md 那条「无法整帧缓冲，必须分块渲染」
// 的落地 —— 那条约束一直写在纸上，到这里才第一次真的执行。
//
// ## 布局（240×320，数字来自页面文档）
//
//     y=0    皮卡丘 Lv12              亲78     状态栏      带 0
//     y=24   ──────────────────────────────
//     y=54   [ back sprite 96×96 居中 ]      呼吸          带 0~1
//     y=160  ...............................愉快           带 2
//     y=180  饱食   ████████░░                              带 2
//     y=204  心情   ██████░░░░                              带 2
//     y=228  体能   █████████░                              带 2
//     y=252  今日行程 ███░░░░░                              带 3
//     y=292  ──────────────────────────────
//     y=298  [A]照料 [B]图鉴 [C]遭遇 3        184px + 角标  带 3
//
// **每个元素都不跨横带边界**（带边界在 y=80/160/240）。
// 跨界的元素会被两条带各画一半，而两条带的重画频率不同 ——
// 上下两半会不同步，屏幕上是撕裂的字。心情文案原本写 y=156
// 正好骑在 159/160 上，挪到 160 才落进单条带内。

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_log.h"
#include "esp_timer.h"
#include "lvgl.h"    // 只用 lv_timer 与空屏对象，绘制全走 screen.c

#include "assets.h"
#include "world.h"
#include "bsp_battery.h"
#include "bsp_display.h"
#include "play.h"
#include "render.h"
#include "screen.h"

static const char *TAG = "idle";

// 横带尺寸走 screen.h —— 那里也是截图与字节序的归属地
#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define SCR_H SCREEN_H

// 呼吸序列 —— 与 sim/effects.py 的 breath_sequence(8, rise=2) 逐值相同。
// 只向上浮动：实测 151 只 back 的下方留白 137 只都只有 4 行。
static const int8_t BREATH[] = {0, 0, -1, -2, -2, -2, -1, 0};
#define BREATH_FRAMES (sizeof(BREATH) / sizeof(BREATH[0]))

// GB 风格配色（与 tools/inspector 的原型一致，那份是对着截图调的）
#define C_BG    RGB_HEX(0x9bbc0f)   // 背景（GB 绿）
#define C_INK   RGB_HEX(0x0f380f)   // 前景（最深）
#define C_MID   RGB_HEX(0x306230)   // 中间调
#define C_LIGHT RGB_HEX(0x8bac0f)   // 亮调

static lv_obj_t *s_scr;
static lv_timer_t *s_tick;
static uint8_t s_breath_i;

// 精灵顶边的 y。分隔线(24) 与第一条轴(180) 之间居中：
// 24 + (180 - 24 - 96) / 2 = 54。页面文档只说「居中」，这里把它算出来。
#define SPRITE_Y 54

// 主宠。三条轴与亲密度走 nurture.c（S4 的 C 移植，与
// sim/gameplay.py 逐拍对账过，见 tools/pipeline/verify_nurture.py）。
//
// 物种与等级仍是固定值 —— 那要等 S14 队伍与 S18 存档接进来。
static struct {
    uint16_t species;
    uint8_t level;
    uint8_t pending;
} s_pet = {25, 12, 3};

// 世界快照。每次重画前刷一次 —— **一帧之内不再变**，
// 否则同一帧里四条轴可能读到不同时刻的值（后台任务随时在改）。
static world_t s_w;

extern const uint8_t pal_bin_start[] asm("_binary_palettes_bin_start");

static void load_palette(uint8_t set_idx, uint16_t out[4])
{
    // palettes.bin 存的就是 RGB565 小端，与我们的帧缓冲同格式 ——
    // 直接拷即可，不用拆成 RGB 再合回去。
    const uint8_t *p = pal_bin_start + 12 + (size_t)set_idx * 4 * 2;
    for (int i = 0; i < 4; i++) {
        out[i] = (uint16_t)(p[i * 2] | (p[i * 2 + 1] << 8));
    }
}

// 画一条横线（分隔线）
static void hline(int y, int x0, int x1, uint16_t c)
{
    for (int x = x0; x < x1; x++) screen_px(x, y, c);
}

// 画进度条：边框 + 填充。**点阵风格，不是矢量描边** ——
// sim/pixelart.py 顶部记过教训：矢量圆在像素画里太平滑，
// 用户一眼看出「画面太生硬」。这里边框是 1px 实线，与点阵同源。
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

// 画一条横带并推到屏幕。band_y 是这条带在整屏里的起始 y。
static void draw_band(int band_y, int8_t breath)
{
    screen_band_clear(C_BG);
    const uint16_t ink = C_INK, mid = C_MID;

    // 画布坐标 = 整屏坐标 - band_y。超出这条带的部分自然被裁掉，
    // 所以每个元素都无脑画，不用判断在不在带内。
    #define Y(v) ((v) - band_y)

    char buf[64];
    species_t sp;

    // -- 状态栏 --------------------------------------------------------
    if (assets_species(s_pet.species, &sp)) {
        snprintf(buf, sizeof(buf), "%.*s Lv%u",
                 sp.name_zh_len, sp.name_zh, s_pet.level);
    } else {
        snprintf(buf, sizeof(buf), "#%03u Lv%u", s_pet.species, s_pet.level);
    }
    render_text(8, Y(4), buf, ink);

    // 亲密度。♥ 不在字库（PingFang 没这个字形，见 convert_font.py），
    // 所以用「亲」字 + 数字，等 pixelart 的 HEART 点阵接进来再换。
    snprintf(buf, sizeof(buf), "亲%u", nurture_pct(s_w.pet.intimacy));
    int w = render_text_width(buf);
    render_text(SCR_W - 8 - w, Y(4), buf, ink);

    hline(Y(24), 0, SCR_W, mid);

    // -- 精灵 ----------------------------------------------------------
    const uint8_t *spr = assets_back_sprite(s_pet.species);
    if (spr) {
        uint16_t pal[4];
        load_palette(sp.palette, pal);
        // 32×32 @scale3 = 96px，水平垂直都居中。呼吸只改 y。
        //
        // 垂直位置 = 分隔线(24) 与第一条轴(180) 之间居中：
        //   24 + (156 - 96) / 2 = 54
        // 第一版写死 44，实测截图上精灵贴着状态栏 —— 那是我按
        // 「y=40 起」的草稿数字写的，没按页面文档的「居中」算。
        render_sprite_2bpp((SCR_W - 96) / 2, Y(SPRITE_Y + breath * 3),
                           spr, 32, 3, pal);
    }

    // -- 三条轴 + 行程 -------------------------------------------------
    //
    // 前三条来自 nurture.c，真的会随时间衰减。
    //
    // 第四条「今日行程」来自 S1 的移动量累积
    // （docs/04-gameplay.md#48：加权 Jaccard 距离攒成抽象刻度）。
    // 满格标定见 world.c 的 PROGRESS_FULL_Q10 —— 那个 20 是用
    // data/raw 的三份实测算出来的，不是拍脑袋。
    static const char *AXIS[4] = {"饱食", "心情", "体能", "今日行程"};
    const uint8_t VAL[4] = {
        nurture_pct(s_w.pet.satiety),
        nurture_pct(s_w.pet.mood),
        nurture_pct(s_w.pet.stamina),
        s_w.progress,                // S1 的移动量累积（F9-① 接上了）
    };
    for (int i = 0; i < 4; i++) {
        int y = 180 + i * 24;
        render_text(8, Y(y), AXIS[i], ink);
        // 前三条标签 2 字 = 32px，第四条 4 字 = 64px
        int lx = (i == 3) ? 80 : 48;
        draw_bar(lx, Y(y + 3), SCR_W - lx - 8, 10, VAL[i]);
    }

    // -- 心情文案 --------------------------------------------------------
    //
    // 页面文档的 `mood` 文案：愉快 / 平静 / 低落 / 消沉。
    // 光有进度条读不出「消沉」—— 那是任一轴低于 25 触发的**状态**，
    // 不是心情轴本身的高低（心情 90 但饿肚子也是消沉）。
    //
    // y=160 而不是 156：**不能跨横带边界**。带 1 是 80~159、
    // 带 2 是 160~239，跨界的字会被两条带各画一半，
    // 而这两条带的重画频率不同（带 1 每拍、带 2 每 8 拍），
    // 上下两半会不同步 —— 屏幕上是撕裂的字。
    // 160 让它完整落在带 2 内，与三条轴同频重画。
    static const char *MOOD[4] = {"愉快", "平静", "低落", "消沉"};
    const char *mood_s = MOOD[nurture_mood(&s_w.pet)];
    render_text(SCR_W - 8 - render_text_width(mood_s), Y(160), mood_s, ink);

    // -- 三键提示 ------------------------------------------------------
    //
    // 这一行是 P1-③ 规格冲突的落点：ASCII 半宽让它 184px 放得下。
    // 按定长 16px 算会是 272px，溢出 40px。
    hline(Y(292), 0, SCR_W, mid);
    int hx = render_text(8, Y(298), "[A]照料 [B]图鉴 [C]遭遇", ink);

    // 待处理遭遇的角标。页面文档：「C 键在有待处理遭遇时显示角标数字
    // 并闪烁 —— 角标是 P1 唯一的动态元素（除了呼吸动效），
    // 它承担『掏出设备看一眼』的全部信息量。」
    //
    // 闪烁用呼吸相位的后半段，不另起定时器 —— 多一个定时器就多一份
    // 与 exit 的竞态（上游 AGENTS.md：先停定时器再删屏）。
    if (s_w.pending && s_breath_i < BREATH_FRAMES / 2) {
        snprintf(buf, sizeof(buf), "%u", s_w.pending);
        render_text(hx + 4, Y(298), buf, ink);
    }

    #undef Y

    screen_push_band(band_y);

    // 推屏。字节序（ST7789 要大端）由 screen.c 处理 ——
    // 我第一版直接调 esp_lcd_panel_draw_bitmap 漏了这一步，
    // 整屏颜色错乱（GB 绿变紫白 + 亮绿）。
}

static void draw_all(int8_t breath)
{
    for (int y = 0; y < SCR_H; y += BAND_H) draw_band(y, breath);
}

// 截图用的重画 —— screen_dump 会调它，每条带 push 时被吐到串口。
static void redraw_for_dump(void)
{
    draw_all(BREATH[s_breath_i]);
}

// lv_timer 回调签名的包装
static void screen_dump_timer_cb(lv_timer_t *t)
{
    (void)t;
    screen_dump();
}

// 呼吸只影响精灵所在的带。精灵占 y=54~150（含向上浮动 6px），
// 落在第 0 条带（0~79）与第 1 条带（80~159）——
// 页面文档说「状态栏与三条轴是静态的，不参与逐帧重绘」。
static void draw_sprite_bands(int8_t breath)
{
    draw_band(0, breath);
    draw_band(BAND_H, breath);
}

static void tick(lv_timer_t *t)
{
    (void)t;

    // 刷快照。**养成结算不在这里** —— 它挪进了 world 任务，
    // 因为页面不在前台时 lv_timer 根本不跑，宠物的时间不该因此停住。
    // 这里只是把后台算好的值取一份出来画。
    world_snapshot(&s_w);

    s_breath_i = (uint8_t)((s_breath_i + 1) % BREATH_FRAMES);

    // 精灵带每拍都画（呼吸）。
    draw_sprite_bands(BREATH[s_breath_i]);

    // 底部带（240~319）也每拍画 —— 遭遇角标要闪，
    // 它的相位跟着 s_breath_i 走（见 draw_band 里那段）。
    // 没有待处理遭遇时这一带是静态的，但每拍重画 37.5KB 的代价
    // 与精灵带同量级，不值得为省它加一层判断。
    draw_band(BAND_H * 3, BREATH[s_breath_i]);

    // 三条轴那一带（160~239）每 8 拍（2 秒）画一次。
    // 衰减速率 4/小时，2 秒内变化 0.002，屏幕上一格都不动。
    static uint8_t n;
    if (++n >= 8) {
        n = 0;
        draw_band(BAND_H * 2, BREATH[s_breath_i]);
    }

    // 每 2 分钟打一行三条轴 —— **长跑观测用**。
    //
    // 为什么不用截图观测：截图靠开机 1 秒后那次自动触发，
    // 而要再截一张就得复位，复位就 nurture_init 了 ——
    // 把要测的状态本身清掉。日志没这个问题，设备自己跑就行。
    //
    // 2 分钟的间隔够看出变化：饱食 4/小时 = 0.13/2分钟，
    // 一小时后累计 4 格，用 tools/device/decay.py 拟合斜率。
    static uint16_t log_n;
    if (++log_n >= 480) {                // 480 × 250ms = 2 分钟
        log_n = 0;
        ESP_LOGI(TAG, "@@AXES %lld %u %u %u %u",
                 (long long)esp_timer_get_time(),
                 nurture_pct(s_w.pet.satiety), nurture_pct(s_w.pet.mood),
                 nurture_pct(s_w.pet.stamina), nurture_pct(s_w.pet.intimacy));
    }
}

void play_idle_enter(void)
{
    // 空屏 + 一张横带画布。不用 ui_pixel_screen_create ——
    // 那会加一个 LVGL 标题栏，而我们整页自己画。
    s_scr = lv_obj_create(NULL);
    lv_obj_set_style_bg_color(s_scr, lv_color_hex(C_BG), 0);
    lv_obj_set_style_pad_all(s_scr, 0, 0);
    lv_obj_set_style_border_width(s_scr, 0, 0);

    lv_screen_load(s_scr);

    s_breath_i = 0;
    world_snapshot(&s_w);          // 先取一份，别用零值画第一帧
    screen_set_redraw(redraw_for_dump);
    draw_all(0);
    s_tick = lv_timer_create(tick, 250, NULL);   // 4 fps

    // 进页面 1 秒后自动截一张 —— 让 PC 侧不用等人按键就能看到画面。
    //
    // 渲染类问题必须看屏幕，而拍照要人在场。自动截图让这个环节
    // 完全自助：烧写 → 等 10 秒 → screenshot.py 收图 → 我自己判断。
    // 一次性的（lv_timer_create 后立刻 set_repeat_count 1）。
    // **5 秒而不是 1 秒**：第一次扫描在开机约 3 秒完成，
    // 而遭遇是扫描的产物 —— 1 秒时截图，队列还是空的，
    // 角标画不出来而我会以为角标坏了（第一版就误判了一轮）。
    // 5 秒让第一批遭遇先落进队列。
    lv_timer_t *shot = lv_timer_create(screen_dump_timer_cb, 5000, NULL);
    lv_timer_set_repeat_count(shot, 1);

    ESP_LOGI(TAG, "P1：#%u Lv%u  提示行 %d px  横带 %dx%d×%d 条",
             s_pet.species, s_pet.level,
             render_text_width("[A]照料 [B]图鉴 [C]遭遇"),
             SCR_W, BAND_H, SCR_H / BAND_H);
}

void play_idle_exit(void)
{
    // 先停定时器再删屏 —— 反过来 tick 会访问野指针（上游 AGENTS.md）
    if (s_tick) { lv_timer_delete(s_tick); s_tick = NULL; }
    if (s_scr) { lv_obj_delete(s_scr); s_scr = NULL; }
}

void play_idle_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    // B 长按 = 截图。**渲染类问题必须看屏幕**，而拍照效率太低
    // 且有反光偏色 —— 这条通道让 PC 侧拿到像素级准确的画面。
    // 收图：python3 tools/device/screenshot.py
    if (btn == BSP_BTN_DOWN && ev == BSP_BTN_LONG) {
        screen_dump();
        return;
    }
    if (ev != BSP_BTN_CLICK) return;

    switch (btn) {
    case BSP_BTN_UP:                       // A 照料
        // 走 world 而不是自己改 —— **状态的唯一所有者是 world**，
        // 页面直接改快照的话，下一次 world_snapshot 就把它覆盖了。
        world_feed();
        world_snapshot(&s_w);
        draw_all(BREATH[s_breath_i]);
        ESP_LOGI(TAG, "照料 → 饱食 %u 心情 %u",
                 nurture_pct(s_w.pet.satiety), nurture_pct(s_w.pet.mood));
        break;
    case BSP_BTN_DOWN:                     // B 图鉴
        ESP_LOGI(TAG, "图鉴（P6 未实现）");
        break;
    case BSP_BTN_OK:                       // C 遭遇
        ESP_LOGI(TAG, "遭遇 %u 条待处理（P2 未实现）", s_w.pending);
        break;
    default:
        break;
    }
}
