// main/nav.h —— 页面导航。
//
// ## 为什么不用 main.c 的 DEMOS 表
//
// 那张表是**菜单式**的：进一项、长按 OK 退回菜单。上游 demo 就该这样。
// 但玩法是**链式**的：P1 →C→ P2 →A→ P3 →A→ P4 →抓到→ P6，
// 每一步都要带参数（P3 要知道打哪一只，P4 要知道打残到什么程度）。
//
// 塞进 DEMOS 表要么给每页一个全局变量传参（下一个人看不出数据从哪来），
// 要么把跳转逻辑摊到各页的 key 回调里（改一条路径要动三个文件）。
// 这里用一张显式的页面表 + 一个 nav_go()，跳转关系集中在一处。
//
// ## 生命周期契约
//
// nav_go(P) 会：当前页 exit() → 切 s_cur → 新页 enter()。
// **exit 必须先停掉自己的 lv_timer 再删屏** —— 反过来定时器会访问
// 已删除的对象（上游 AGENTS.md 专门点了这条，P1 的 exit 有示范）。
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "bsp_button.h"
#include "encounter.h"

typedef enum {
    PAGE_IDLE = 0,      // P1 待机
    PAGE_ENCOUNTER,     // P2 遭遇列表
    PAGE_BATTLE,        // P3 战斗
    PAGE_CAPTURE,       // P4 捕获
    PAGE_DEX,           // P6 图鉴
    PAGE_COUNT,
} page_id_t;

// 切页。在 LVGL 任务里调（按键回调已经持锁，直接调即可）。
void nav_go(page_id_t p);
page_id_t nav_current(void);

// 分发按键给当前页
void nav_key(bsp_btn_t btn, bsp_btn_ev_t ev);

// 进 P1（开机用）
void nav_start(void);

// 退出当前页（要去 demo 菜单时用）—— 不进新页，只做清理。
void nav_exit_current(void);

// ---------------------------------------------------------------------------
// 页面间传参
//
// 用一个显式的「当前处理中的遭遇」而不是各页自己存 —— P3 打完把 HP
// 写回这里，P4 读它算捕获窗口。链路上只有一条，不需要栈。
// ---------------------------------------------------------------------------

typedef struct {
    encounter_t enc;        // 正在处理的这一只
    uint8_t queue_index;    // 它在队列里的下标（丢弃/取走要用）
    bool valid;

    // P3 打完留下的：给 P4 用
    bool battled;
    bool battle_won;
} nav_ctx_t;

nav_ctx_t *nav_ctx(void);
