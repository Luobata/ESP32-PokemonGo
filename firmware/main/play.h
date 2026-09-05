// main/play.h —— 本项目玩法的入口声明。
//
// 与 demo.h 分开：demo.h 是上游 BSP 参考示例的接口，
// 跟着上游走；play.h 是我们自己的东西。混在一起的话
// 下次同步上游会冲突。
#pragma once

#include "bsp_button.h"

// WiFi 指纹采集器（play_collect.c）。
//
// 先做采集而不是游戏，因为两件事卡在缺数据上：
// 野外 biome 死代码需要真实户外采集、口袋 RSSI 基线未标定。
// 详见 play_collect.c 顶部。
void play_collect_enter(void);
void play_collect_exit(void);
void play_collect_key(bsp_btn_t btn, bsp_btn_ev_t ev);

// P1 待机页（play_idle.c）—— roadmap 的 F8「最小可玩闭环」。
// 主宠 back sprite + 呼吸动效 + 三条轴 + 三键提示。
void play_idle_enter(void);
void play_idle_exit(void);
void play_idle_key(bsp_btn_t btn, bsp_btn_ev_t ev);

// P2 遭遇列表（play_enc.c）—— 队列的出口。
// 遭遇是后台攒的，这一页让玩家先扫一眼稀有度再决定处理顺序。
void play_enc_enter(void);
void play_enc_exit(void);
void play_enc_key(bsp_btn_t btn, bsp_btn_ev_t ev);

// P3 战斗（play_battle.c）—— 自动战斗，逐回合播放。
// 它是决策点不是走廊：打残了捕获窗口才宽（「先打再抓」的策略性）。
void play_battle_enter(void);
void play_battle_exit(void);
void play_battle_key(bsp_btn_t btn, bsp_btn_ev_t ev);

// P4 捕获（play_capture.c）—— 时机判定。
// 四个乘数（种族/心情/球种/打残）在这一页汇合。
void play_capture_enter(void);
void play_capture_exit(void);
void play_capture_key(bsp_btn_t btn, bsp_btn_ev_t ev);

// P6 图鉴（play_dex.c）—— 收集的展示面。未捕获画剪影。
void play_dex_enter(void);
void play_dex_exit(void);
void play_dex_key(bsp_btn_t btn, bsp_btn_ev_t ev);
