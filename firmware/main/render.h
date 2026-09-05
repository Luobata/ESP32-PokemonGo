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

// 画 2bpp sprite（正方形）。color 3 = 透明（与 sim/effects.py 约定一致）。
// palette 是 4 个颜色，按色号索引。
void render_sprite_2bpp(int x, int y,
                        const uint8_t *data, int size, int scale,
                        const uint16_t *palette);

// 长方形版本 —— UI 点阵素材不是正方形（光标 5×9、心形 7×6）。
//
// 正方形版是它的特例（w == h）。**行字节数按 w 算**：
// 2bpp 每行 ceil(w/4) 字节，用 h 或用固定值都会错位 ——
// 错位的表现是图案斜着糊开，而不是报错。
void render_sprite_2bpp_wh(int x, int y,
                           const uint8_t *data, int w, int h, int scale,
                           const uint16_t *palette);

// ---------------------------------------------------------------------------
// 动效（S15 / sim/effects.py）
//
// 全是**整数序列**，逐值抄自 PC 侧 —— 那边的 shake_sequence 等函数
// 本来就没有浮点，为的就是能原样移植。
//
// 用法是「页面按帧取一个变换，画的时候套上去」，
// 而不是引一套动画框架 —— 三键设备上动效就这么几种，
// 框架的抽象成本比直接写高。
// ---------------------------------------------------------------------------

// 受击抖动：左右各 amplitude 像素，交替 frames 帧。
// 返回第 i 帧的 x 偏移。i 超出范围返回 0（动效结束 = 不偏移）。
int render_shake_dx(int i, int frames, int amplitude);

// 闪白：偶数帧把三档前景全映射到最亮（色号 2），奇数帧原样。
// 返回 true 表示这一帧该用「全白调色板」。
//
// **不是映射到色号 3** —— 那是透明，闪出来是背景色而不是白。
// sim 那边 shade_map 的 (3,3,3,3) 是在它自己的渲染约定下写的，
// 直接抄过来会闪成透明（踩过 sprite 内部高光那一次同源的坑）。
bool render_flash_on(int i, int frames);
