// main/screen.c —— 帧缓冲、推屏、截图。
//
// ## 为什么需要这一层
//
// 直接 esp_lcd_panel_draw_bitmap 有个坑：**ST7789 走 SPI 要大端
// RGB565，而我们内存里是小端**。BSP 的 LVGL 路径靠 `swap_bytes = true`
// 让 esp_lvgl_port 代劳，绕过 LVGL 自己推屏就漏了这一步 ——
// 实测表现是整屏颜色错乱（GB 绿变成紫白 + 亮绿）。
//
// ## 截图：让调试不再靠拍照
//
// 渲染问题拍照看效率极低：拍一张、传一张、我猜一轮。
// `screen_dump()` 把帧缓冲 base64 打到串口，
// `tools/device/screenshot.py` 收下来存成 PNG —— 我自己就能看。
//
// 240×320×2 = 150KB → base64 后 200KB，115200 波特下约 18 秒。
// 慢，但比来回拍照快得多，而且**像素级准确**：
// 照片有反光、偏色、摩尔纹，截图没有。

#include <string.h>

#include "esp_lcd_panel_ops.h"
#include "esp_log.h"

#include "bsp_display.h"
#include "screen.h"

static const char *TAG = "screen";

// 一条横带的帧缓冲。240×80×2 = 37.5KB。
//
// 不开整屏（150KB）：可用堆 231KB，WiFi 栈与 LVGL 还要用。
// 这也正是 docs/01-constitution.md 那条「无法整帧缓冲，必须分块
// 横带渲染」的落地 —— 那条约束一直写在纸上，到这里才真的执行。
static uint16_t s_band[SCREEN_W * SCREEN_BAND_H];

// 截图**不缓存整屏**。
//
// 第一版开了 240×320×2 = 150KB 的 static 缓冲，直接 DRAM 溢出
// 32624 字节链接失败 —— 可用堆 231KB 是运行时的数字，
// 而 static 数据要在链接期挤进 dram0_0_seg，那里更紧。
//
// 改成**回调式**：dump 时让页面重画一遍，每画完一条带就把它
// base64 吐出去。代价是 dump 期间画面会闪一下（重画），
// 换来零常驻内存。
static screen_redraw_cb_t s_redraw;
static bool s_dumping;

uint16_t *screen_band(void) { return s_band; }

void screen_band_clear(uint16_t rgb565)
{
    for (int i = 0; i < SCREEN_W * SCREEN_BAND_H; i++) s_band[i] = rgb565;
}

void screen_px(int x, int y, uint16_t rgb565)
{
    if (x < 0 || x >= SCREEN_W || y < 0 || y >= SCREEN_BAND_H) return;
    s_band[y * SCREEN_W + x] = rgb565;
}

void screen_push_band(int band_y)
{
    esp_lcd_panel_handle_t panel = bsp_display_panel();
    if (!panel) return;

    // dump 模式：在字节交换**之前**吐出去 —— 输出的是逻辑颜色
    // （小端 RGB565），PC 侧解码不用猜硬件字节序。
    if (s_dumping) {
        screen_emit_band(band_y);
    }

    // 小端 → 大端。ST7789 走 SPI 要大端 RGB565，
    // 而 C 里的 uint16_t 在 RISC-V 上是小端。
    //
    // 原地交换：交换后这块缓冲就不能再当逻辑颜色读了，
    // 但下一帧会重新填，无所谓。
    for (int i = 0; i < SCREEN_W * SCREEN_BAND_H; i++) {
        uint16_t v = s_band[i];
        s_band[i] = (uint16_t)((v >> 8) | (v << 8));
    }

    esp_lcd_panel_draw_bitmap(panel, 0, band_y, SCREEN_W,
                              band_y + SCREEN_BAND_H, s_band);
}

// ---------------------------------------------------------------------------
// 截图
// ---------------------------------------------------------------------------

static const char B64[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

void screen_set_redraw(screen_redraw_cb_t cb) { s_redraw = cb; }

// 把当前横带 base64 吐到串口。由 screen_push_band 在 dump 模式下调用。
void screen_emit_band(int band_y)
{
    const uint8_t *p = (const uint8_t *)s_band;
    size_t n = (size_t)SCREEN_W * SCREEN_BAND_H * 2;

    printf("@@BAND %d\n", band_y);

    // 每行 76 个 base64 字符（57 字节原始）。不用太长：
    // 串口缓冲有限，长行容易丢。
    char line[80];
    size_t li = 0;
    for (size_t i = 0; i < n; i += 3) {
        uint32_t v = (uint32_t)p[i] << 16;
        if (i + 1 < n) v |= (uint32_t)p[i + 1] << 8;
        if (i + 2 < n) v |= p[i + 2];

        line[li++] = B64[(v >> 18) & 0x3F];
        line[li++] = B64[(v >> 12) & 0x3F];
        line[li++] = (i + 1 < n) ? B64[(v >> 6) & 0x3F] : '=';
        line[li++] = (i + 2 < n) ? B64[v & 0x3F] : '=';

        if (li >= 76) {
            line[li] = '\0';
            printf("%s\n", line);
            fflush(stdout);
            li = 0;
        }
    }
    if (li) { line[li] = '\0'; printf("%s\n", line); }
}

void screen_dump(void)
{
    if (!s_redraw) {
        ESP_LOGW(TAG, "没注册重画回调 —— 页面要调 screen_set_redraw()");
        return;
    }
    printf("\n@@SHOT %d %d rgb565le %d\n", SCREEN_W, SCREEN_H, SCREEN_BAND_H);
    fflush(stdout);

    // 让页面重画一遍。每条带在 push 时会被 emit 出去。
    s_dumping = true;
    s_redraw();
    s_dumping = false;

    printf("@@SHOTEND\n");
    fflush(stdout);
    ESP_LOGI(TAG, "截图已输出（%d×%d）", SCREEN_W, SCREEN_H);
}
