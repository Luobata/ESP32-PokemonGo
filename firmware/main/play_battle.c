// main/play_battle.c —— P3 遭遇详情 / 战斗。
//
// 对应 docs/pages/P3-battle.md。
//
// ## 不做招式选择，张力从哪来
//
// 战斗是自动的（用户定的）。页面文档列了三处制造张力的地方：
//   1. **属性相克可见** —— 「效果绝佳」让玩家看到自己属性选择的因果
//   2. **HP 逐回合扣减**而非瞬间结算
//   3. **削弱机制** —— 战后野怪 HP 降低使捕获窗口加宽
//
// 第 3 点是关键：它让「先打再抓」成为**真策略**，而不是可跳过的动画。
// 战斗页因此不是通往捕获的走廊，而是一个决策点。
//
// ## 为什么先算完再逐帧播
//
// battle_run() 一次算完整场（40 回合上限），页面按定时器逐条播放。
// 反过来（每帧算一回合）看似更自然，但那样**结果依赖帧率** ——
// 页面被 WiFi 扫描挤掉几帧就少打几回合。先算完就没这问题，
// 而且能提前知道总回合数用来分配播放节奏。

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
#include "world.h"

static const char *TAG = "p3";

#define BAND_H SCREEN_BAND_H
#define SCR_W SCREEN_W
#define SCR_H SCREEN_H

#define C_BG    RGB_HEX(0x9bbc0f)
#define C_INK   RGB_HEX(0x0f380f)
#define C_MID   RGB_HEX(0x306230)
#define C_LIGHT RGB_HEX(0x8bac0f)

// 布局（不跨横带边界 y=80/160/240）
//   y=4    野怪名 Lv20        ★★★☆☆      带 0
//   y=28   野怪 HP 条                      带 0
//   y=48   [ 野怪 front sprite 居中 ]      带 0~1
//   y=168  主宠名 Lv12                     带 2
//   y=192  主宠 HP 条                      带 2
//   y=216  回合文字（招名 + 效果）          带 2
//   y=292  ────────────────────
//   y=298  [A]捕获 [B]战斗 [C]逃跑          带 3
#define WILD_BAR_Y 28
#define PET_BAR_Y 192
#define MSG_Y 216

static lv_timer_t *s_tick;

static battle_result_t s_res;
static uint8_t s_play_i;         // 播到第几回合
static bool s_playing;
static bool s_done;

// 受击抖动。**挨打的那一方抖**，不是攻击方 ——
// 页面文档把「HP 逐回合扣减 + shake」列为三处张力之一。
//
// 每回合播放时先抖 SHAKE_FRAMES 帧再停，所以 tick 要比回合快：
// 回合 600ms，抖动 4 帧 × 60ms = 240ms，剩下 360ms 静止让人看清数字。
#define SHAKE_FRAMES 4
#define SHAKE_AMP 3
static uint8_t s_shake_i = SHAKE_FRAMES;   // >= FRAMES 表示不抖

// 主宠。等级与物种还是固定值（S14 队伍没移植）——
// 与 P1 同一份假设，接上队伍时两处一起改。
#define PET_SPECIES 25
#define PET_LEVEL 12

static void hline_at(int y)
{
    for (int x = 0; x < SCR_W; x++) screen_px(x, y, C_MID);
}

static void draw_bar(int x, int y, int w, int h, uint16_t cur, uint16_t max)
{
    int fw = max ? (int)((uint32_t)w * cur / max) : 0;
    for (int dy = 0; dy < h; dy++) {
        for (int dx = 0; dx < w; dx++) {
            bool border = (dy == 0 || dy == h - 1 || dx == 0 || dx == w - 1);
            uint16_t c = border ? C_INK : (dx < fw ? C_MID : C_LIGHT);
            screen_px(x + dx, y + dy, c);
        }
    }
}

static void draw_band(int band_y)
{
    screen_band_clear(C_BG);
    #define Y(v) ((v) - band_y)

    const nav_ctx_t *c = nav_ctx();
    char buf[64];
    species_t wild_sp, pet_sp;
    bool has_wild = assets_species(c->enc.species_id, &wild_sp);
    bool has_pet = assets_species(PET_SPECIES, &pet_sp);

    uint8_t wlv = battle_wild_level(c->enc.rarity);

    // 当前 HP —— 播放到第几回合就显示那一回合的值
    uint16_t p_hp = s_res.pet_hp_max, w_hp = s_res.wild_hp_max;
    if (s_play_i > 0 && s_play_i <= s_res.round_count) {
        p_hp = s_res.rounds[s_play_i - 1].pet_hp;
        w_hp = s_res.rounds[s_play_i - 1].wild_hp;
    }

    // -- 野怪 ------------------------------------------------------------
    if (has_wild) {
        snprintf(buf, sizeof(buf), "%.*s Lv%u",
                 wild_sp.name_zh_len, wild_sp.name_zh, wlv);
    } else {
        snprintf(buf, sizeof(buf), "#%03u Lv%u", c->enc.species_id, wlv);
    }
    render_text(8, Y(4), buf, C_INK);

    // 稀有度星，右上
    {
        char st[32];
        int n = 0;
        for (int i = 0; i < 5; i++) {
            memcpy(st + n, (i < c->enc.rarity) ? "★" : "☆", 3);
            n += 3;
        }
        st[n] = '\0';
        render_text(SCR_W - 8 - render_text_width(st), Y(4), st, C_INK);
    }
    draw_bar(8, Y(WILD_BAR_Y), SCR_W - 16, 10, w_hp, s_res.wild_hp_max);

    // -- 野怪 sprite（用 back 凑合）--------------------------------------
    //
    // 本该用 front（面朝玩家）—— 但 front 是分尺寸档的图集
    // （40/56/72 三档，见 convert_gen1.py），assets.c 现在只解了 back。
    // 先用 back @scale2 把页面跑通，front 的读取留到第 4 步。
    // **标出来而不是假装它对**：屏幕上野怪会背对玩家，那是暂时的。
    const uint8_t *spr = assets_back_sprite(c->enc.species_id);
    if (spr && has_wild) {
        uint16_t pal[4];
        assets_palette(wild_sp.palette, pal);
        // 野怪挨打时抖它，主宠挨打时不抖野怪
        int dx = 0;
        if (s_play_i > 0 && s_play_i <= s_res.round_count &&
            s_res.rounds[s_play_i - 1].by_pet) {
            dx = render_shake_dx(s_shake_i, SHAKE_FRAMES, SHAKE_AMP);
        }
        render_sprite_2bpp((SCR_W - 64) / 2 + dx, Y(52), spr, 32, 2, pal);
    }

    // -- 主宠 ------------------------------------------------------------
    if (has_pet) {
        snprintf(buf, sizeof(buf), "%.*s Lv%u",
                 pet_sp.name_zh_len, pet_sp.name_zh, PET_LEVEL);
        render_text(8, Y(168), buf, C_INK);
    }
    draw_bar(8, Y(PET_BAR_Y), SCR_W - 16, 10, p_hp, s_res.pet_hp_max);

    // -- 回合文字 --------------------------------------------------------
    if (s_play_i > 0 && s_play_i <= s_res.round_count) {
        const battle_round_t *r = &s_res.rounds[s_play_i - 1];
        const char *who = r->by_pet ? "我方" : "对方";
        if (r->missed) {
            snprintf(buf, sizeof(buf), "%s %.*s 没打中",
                     who, r->move_zh_len, r->move_zh ? r->move_zh : "");
        } else {
            snprintf(buf, sizeof(buf), "%s %.*s", who,
                     r->move_zh_len, r->move_zh ? r->move_zh : "");
        }
        render_text(8, Y(MSG_Y), buf, C_INK);

        // 效果提示 —— **100 倍率不显示**（页面文档：只在有反差时说话，
        // 每回合都弹「效果一般」会把「效果绝佳」的分量冲掉）
        const char *lbl = battle_eff_label(r->mult);
        if (lbl) render_text(8, Y(MSG_Y + 22), lbl, C_INK);
    } else if (s_done) {
        render_text(8, Y(MSG_Y), s_res.won ? "胜" : "败", C_INK);
        snprintf(buf, sizeof(buf), "经验 +%u", s_res.exp);
        render_text(8, Y(MSG_Y + 22), buf, C_MID);
        if (s_res.won) render_text(96, Y(MSG_Y + 22), "看起来虚弱了", C_MID);
    }

    // -- 三键 --------------------------------------------------------------
    hline_at(Y(292));
    render_text(8, Y(298), "[A]捕获 [B]战斗 [C]逃跑", C_INK);

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
    (void)t;
    if (!s_playing) return;

    // 抖动阶段：只重画野怪那两条带，不整屏 —— 60ms 一帧整屏画不完
    // （四条带 30.7ms，加上文字渲染会掉帧）。
    if (s_shake_i < SHAKE_FRAMES) {
        s_shake_i++;
        draw_band(0);
        draw_band(BAND_H);
        return;
    }

    // 回合间隔：抖完还要停一会儿让人看清 —— 用 tick 计数凑够 600ms
    static uint8_t hold;
    if (++hold < 6) return;      // 6 × 60ms = 360ms
    hold = 0;

    if (s_play_i < s_res.round_count) {
        s_play_i++;
        s_shake_i = 0;           // 新回合，重新抖
        draw_all();
        return;
    }

    // 播完
    s_playing = false;
    s_done = true;
    nav_ctx_t *c = nav_ctx();
    c->battled = true;
    c->battle_won = s_res.won;
    // 打残的程度写回队列 —— **这是「先打再抓」成为真策略的落点**
    c->enc.hp_ratio = s_res.wild_hp_ratio;
    world_update_hp_uid(c->uid, s_res.wild_hp_ratio);

    ESP_LOGI(TAG, "战斗结束：%s %u 回合，野怪剩 %u%%",
             s_res.won ? "胜" : "败", s_res.round_count, s_res.wild_hp_ratio);
    draw_all();
}

void play_battle_enter(void)
{

    memset(&s_res, 0, sizeof(s_res));
    s_play_i = 0;
    s_playing = false;
    s_done = false;
    s_shake_i = SHAKE_FRAMES;

    // 进来先不打 —— 玩家可以直接 A 捕获（不打就抓，窗口窄但省时间）
    // 或 B 开打。这正是页面文档说的「战斗页是决策点不是走廊」。
    const nav_ctx_t *c = nav_ctx();
    species_t sp;
    if (assets_species(c->enc.species_id, &sp)) {
        uint8_t wlv = battle_wild_level(c->enc.rarity);
        // 先算一遍只为拿到 HP 上限（画满血条用），不播放
        battle_run(PET_SPECIES, PET_LEVEL, c->enc.species_id, wlv,
                   1024, c->enc.ts ? c->enc.ts : 1, &s_res);
        uint8_t saved_rounds = s_res.round_count;
        (void)saved_rounds;
        s_play_i = 0;    // 回到第 0 回合 = 双方满血
    }

    screen_set_redraw(redraw_for_dump);
    draw_all();
    // 60ms 一拍：抖动要这个频率才顺，回合节奏靠 tick 里数拍子凑
    // （抖 4 拍 + 停 6 拍 = 600ms/回合）。
    s_tick = lv_timer_create(tick, 60, NULL);

    // **不做自动截图** —— P1 那个是在只有一页时加的，
    // 现在有了 dbg.c 的按键注入，截图由 walk.py 显式发 's' 触发。
    // 页面自己再截一张只会与之交错，让 PC 侧收到半张（踩过一次）。
}

void play_battle_exit(void)
{
    // 先停定时器再删屏 —— 反过来 tick 会访问野指针（上游 AGENTS.md）
    if (s_tick) { lv_timer_delete(s_tick); s_tick = NULL; }
}

void play_battle_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    if (btn == BSP_BTN_DOWN && ev == BSP_BTN_LONG) { screen_dump(); return; }
    if (ev != BSP_BTN_CLICK) return;

    switch (btn) {
    case BSP_BTN_UP:                       // A 捕获 → P4
        nav_go(PAGE_CAPTURE);
        break;

    case BSP_BTN_DOWN:                     // B 战斗（开始播放）
        if (!s_playing && !s_done) {
            s_playing = true;
            ESP_LOGI(TAG, "开打：%u 回合", s_res.round_count);
        }
        break;

    case BSP_BTN_OK:                       // C 逃跑 → 回 P2
        nav_go(PAGE_ENCOUNTER);
        break;

    default:
        break;
    }
}
