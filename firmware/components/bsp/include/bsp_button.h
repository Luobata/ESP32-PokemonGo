// components/bsp/include/bsp_button.h
// 三个按键共用一个 ADC 引脚,靠分压电阻区分。电压窗口见 bsp_pins.h。
#pragma once

#include "esp_err.h"
#include <stdbool.h>

// A/B 的网页按住阈值也使用 600 ms；硬件在去抖确认按下后计时。
#define BSP_BTN_LONG_PRESS_MS 600
#define BSP_BTN_SHORT_PRESS_MS 180
// C 长按会退出玩法，继续保留原来的较长门槛。
#define BSP_BTN_EXIT_PRESS_MS 1500

// 按键索引。数量用 bsp_pins.h 的 BSP_BTN_COUNT(硬件属性,归引脚表管),
// 这里不再定义尾项计数,避免出现 BSP_BTN_COUNT / BSP_BTN_COUNT_ 两个近似名字。
typedef enum {
    BSP_BTN_UP = 0,
    BSP_BTN_DOWN,
    BSP_BTN_OK,
} bsp_btn_t;

typedef enum {
    BSP_BTN_PRESS = 0,   // 按下瞬间(低延迟,适合游戏类即时响应)
    BSP_BTN_CLICK,       // 单击(按下并抬起)
    BSP_BTN_DOUBLE,      // 双击
    BSP_BTN_LONG,        // A/B 约 0.6 秒、C 约 1.5 秒；仅一次，松开不再触发单击
    BSP_BTN_RELEASE = 4, // 去抖确认松开；短按时先 RELEASE，双击窗口结束后才 CLICK
    BSP_BTN_GESTURE_END = 5, // 库已完成整组单/双/连按分类；此后才开始下一次独立手势
} bsp_btn_ev_t;

// 按键事件回调。运行于 button 组件的定时器任务,勿在其中阻塞或做重活。
typedef void (*bsp_btn_cb_t)(bsp_btn_t btn, bsp_btn_ev_t ev, void *user);

esp_err_t bsp_button_init(bsp_btn_cb_t cb, void *user);

// 读当前 ADC 原始电压(mV)。松开时约 3300;按住某键时约为该键的分压值。
// ★ 换了分压/上拉阻值后,用它测出自己的三档电压,再改 bsp_pins.h 的 BSP_BTN_MV_TABLE。
// 读取失败返回 -1。
int bsp_button_read_mv(void);

// Diagnostic observation: suppress game actions while preserving release/end
// cleanup. A gesture that starts during observation remains suppressed to END.
void bsp_button_observe_only(bool enabled);
