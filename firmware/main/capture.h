// main/capture.h —— S2 捕获判定。
//
// PC 侧 sim/systems.py。这一整块是**确定性的**（除逃跑判定），
// 所以能与 sim 逐值对账，不像战斗那样只能对统计分布。
#pragma once

#include <stdbool.h>
#include <stdint.h>

#define CAP_BAR_WIDTH 200          // 判定条像素宽（240 屏留边距）
#define CAP_POINTER_PERIOD_MS 1200 // 指针一个往复
#define CAP_WINDOW_MIN 3           // 下界 —— 极稀有种也不是数学上不可能
#define CAP_WINDOW_MAX 200         // 上界 —— 防止条被填满导致「必中」

typedef enum {
    CAP_BALL_POKE = 0,
    CAP_BALL_GREAT,
    CAP_BALL_ULTRA,
    CAP_BALL_COUNT,
} cap_ball_t;

typedef struct {
    bool caught;
    bool fled;
    uint16_t pointer;
    uint16_t window_start, window_end, window_w;
    cap_ball_t ball;
} cap_result_t;

const char *cap_ball_name(cap_ball_t b);

// 判定窗口宽度（像素）。四个乘数对应四条玩家能动性 —— 见 capture.c。
// mood_bonus_q10 来自 PetState.catch_window_bonus，1024 = 1.0。
uint16_t cap_window_width(uint8_t capture_rate, uint16_t mood_bonus_q10,
                          cap_ball_t ball, uint8_t hp_ratio);

// 指针位置 —— 三角波往复，整数运算。
uint16_t cap_pointer_position(uint32_t elapsed_ms);

// 投一次球。命中是确定性的；只有「失败后逃不逃」用 seed。
void cap_attempt(uint8_t capture_rate, uint16_t mood_bonus_q10,
                 cap_ball_t ball, uint8_t hp_ratio, uint8_t rarity,
                 uint32_t elapsed_ms, uint32_t seed,
                 cap_result_t *out);
