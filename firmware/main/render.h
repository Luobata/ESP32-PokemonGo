// main/render.h —— 中文点阵与 2bpp sprite 绘制（F2 + F3）。
//
// 与 sim/strings.py 的排版模型保持一致：**汉字 16px，ASCII 半宽 8px**。
// 那是页面文档所有「184px / 232px」数字的依据，
// 而字库本身是定长 16×16 —— 半宽靠渲染时的步进实现，不改格式。
// 详见 render.c 顶部。
#pragma once

#include <stdbool.h>
#include <stdint.h>

// 不依赖 LVGL —— 直接写 screen.c 的横带缓冲。
// 这让渲染层能在 host 上编译测试（同 sensing.c）。

// 解析字库。失败时 render_text 静默不画 —— 调用方要看返回值。
bool render_init(void);

// 与 PC 侧逐项对账：码点升序、关键字存在、排版宽度。
bool render_selftest(void);

// 画一行字，返回结束时的 x。UTF-8 输入，字库没有的字跳过。
int render_text(int x, int y, const char *s, uint16_t fg);

// 排版宽度（像素）。必须与 sim/strings.py 的 text_px() 一致。
int render_text_width(const char *s);

// 单个码点的步进宽度。ASCII 8，汉字 16。
uint8_t render_char_advance(uint16_t cp);

// 画 2bpp sprite。color 3 = 透明（与 sim/effects.py 约定一致）。
// palette 是 4 个颜色，按色号索引。
void render_sprite_2bpp(int x, int y,
                        const uint8_t *data, int size, int scale,
                        const uint16_t *palette);
