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
