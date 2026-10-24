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
#include <stdio.h>
#ifndef HOST_BUILD
#include "driver/usb_serial_jtag_vfs.h"
#endif

#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_log.h"
#include "esp_timer.h"

#include "lvgl.h"

#include "bsp_display.h"
#include "screen.h"
#include "screen_idle.h"

static const char *TAG = "screen";

// 一条横带的帧缓冲。240×20×2 = 9,600 B。
//
// 不开整屏（150KB）：可用堆 231KB，WiFi 栈与 LVGL 还要用。
// 这也正是 docs/01-constitution.md 那条「无法整帧缓冲，必须分块
// 横带渲染」的落地 —— 那条约束一直写在纸上，到这里才真的执行。
static uint16_t s_band[SCREEN_W * SCREEN_BAND_H];
static uint16_t *s_draw = s_band, *s_spare;
static bool s_dma_pending;
static void wait_dma_done(void);

void screen_flush(void)
{
    if (!s_dma_pending) return;
    wait_dma_done();
    s_dma_pending = false;
}

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
static bool s_fap_capture;
static bool s_profiling;
static uint32_t s_profile_bands;
static int64_t s_profile_push_us;

// Bounded diagnostic: 2 x 64 x uint16_t histogram bins (8 ms resolution).
// Rendering completion is measured after all queued band transfers of
// a timer callback, not once per band. Intentional idle holds remain visible
// as fewer presented frames; callback cadence is reported separately.
static struct {
    bool enabled, inside;
    unsigned period, ticks, frames, bands, current_bands, late;
    int64_t started, tick_started, previous_tick, previous_frame, last_frame;
    uint64_t render_us;
    uint32_t max_tick_us, max_frame_us, max_render_us;
    uint16_t tick_hist[64], frame_hist[64];
} s_cadence;

static void cadence_interval(uint16_t *hist, uint32_t us)
{
    unsigned bin = us ? (us - 1) / 8000 : 0;
    if (bin > 63) bin = 63;
    if (hist[bin] < UINT16_MAX) hist[bin]++;
}

static unsigned cadence_percentile(const uint16_t *hist, unsigned percentile)
{
    unsigned n = 0, sum = 0;
    for (unsigned i = 0; i < 64; i++) n += hist[i];
    if (!n) return 0;
    unsigned target = (n * percentile + 99) / 100;
    for (unsigned i = 0; i < 64; i++) {
        sum += hist[i];
        if (sum >= target) return i == 63 ? UINT32_MAX : (i + 1) * 8;
    }
    return 0;
}

void screen_cadence_start(void)
{
    memset(&s_cadence, 0, sizeof(s_cadence));
    s_cadence.started = esp_timer_get_time();
    s_cadence.enabled = true;
    ESP_LOGI(TAG, "@@CADENCE_START");
}

void screen_cadence_begin(unsigned period_ms)
{
    if (!s_cadence.enabled || s_profiling || s_dumping || s_fap_capture) return;
    if (screen_idle_is_off()) { s_cadence.enabled = false; return; }
    int64_t now = esp_timer_get_time();
    if (now - s_cadence.started > 30000000) { s_cadence.enabled = false; return; }
    s_cadence.inside = true;
    s_cadence.current_bands = 0;
    s_cadence.period = period_ms;
    s_cadence.tick_started = now;
    if (s_cadence.previous_tick) {
        uint32_t gap = now - s_cadence.previous_tick;
        cadence_interval(s_cadence.tick_hist, gap);
        if (gap > s_cadence.max_tick_us) s_cadence.max_tick_us = gap;
        if (gap > period_ms * 1000u) s_cadence.late++;
    }
    s_cadence.previous_tick = now;
    s_cadence.ticks++;
}

void screen_cadence_end(void)
{
    screen_flush();
    if (!s_cadence.inside) return;
    s_cadence.inside = false;
    if (!s_cadence.current_bands) return;
    int64_t now = esp_timer_get_time();
    uint32_t duration = now - s_cadence.tick_started;
    if (s_cadence.previous_frame) {
        uint32_t gap = now - s_cadence.previous_frame;
        cadence_interval(s_cadence.frame_hist, gap);
        if (gap > s_cadence.max_frame_us) s_cadence.max_frame_us = gap;
    }
    s_cadence.previous_frame = s_cadence.last_frame = now;
    s_cadence.render_us += duration;
    if (duration > s_cadence.max_render_us) s_cadence.max_render_us = duration;
    s_cadence.bands += s_cadence.current_bands;
    s_cadence.frames++;
}

void screen_cadence_report(void)
{
    s_cadence.enabled = false;
    ESP_LOGI(TAG, "@@CADENCE period_ms=%u ticks=%u frames=%u bands=%u window_us=%lld render_us=%llu render_max_us=%lu tick_p50_ms=%u tick_p95_ms=%u tick_max_us=%lu late=%u frame_p50_ms=%u frame_p95_ms=%u frame_max_us=%lu bytes=%u",
             s_cadence.period, s_cadence.ticks, s_cadence.frames, s_cadence.bands,
             (long long)(s_cadence.last_frame ? s_cadence.last_frame - s_cadence.started : 0),
             (unsigned long long)s_cadence.render_us, (unsigned long)s_cadence.max_render_us,
             cadence_percentile(s_cadence.tick_hist, 50), cadence_percentile(s_cadence.tick_hist, 95),
             (unsigned long)s_cadence.max_tick_us, s_cadence.late,
             cadence_percentile(s_cadence.frame_hist, 50), cadence_percentile(s_cadence.frame_hist, 95),
             (unsigned long)s_cadence.max_frame_us, (unsigned)sizeof(s_cadence));
}

// 唯一的那张 LVGL 屏。**只建一次**，之后页面切换不碰它 ——
// 见 screen.h 里那段「让 LVGL 闭嘴」。
static lv_obj_t *s_lv_scr;

void screen_own_display(void)
{
    if (s_lv_scr) return;
    s_lv_scr = lv_obj_create(NULL);
    lv_obj_set_style_pad_all(s_lv_scr, 0, 0);
    lv_obj_set_style_border_width(s_lv_scr, 0, 0);
    lv_obj_set_style_bg_color(s_lv_scr, lv_color_hex(0xffffff), 0);
    lv_screen_load(s_lv_scr);
    // Loading an empty screen queues a full LVGL refresh. If it runs after
    // nav_start draws the game, its background overwrites the game bands.
    // Idle animation redraws only selected bands, leaving a persistent stripe.
    // Own pixel output exclusively; keep the LVGL task and gameplay timers alive.
    // Called while holding bsp_lvgl_lock, before the first game frame.
    lv_display_t *display = lv_obj_get_display(s_lv_scr);
    lv_display_enable_invalidation(display, false);
    lv_timer_t *refresh = lv_display_get_refr_timer(display);
    if (refresh) lv_timer_pause(refresh);
    // The refresh timer is paused before borrowing its existing DMA buffer.
    // LVGL retains ownership/lifetime; never free or resize it while borrowed.
    // This overlaps 20-row rendering and DMA without another allocation.
    lv_draw_buf_t *buffer = lv_display_get_buf_active(display);
    if (buffer && buffer->data && buffer->data_size >= sizeof(s_band) &&
        ((uintptr_t)buffer->data % 4u) == 0) s_spare = (uint16_t *)buffer->data;
    ESP_LOGI(TAG, "Game owns panel; LVGL refresh paused; pipeline=%d", s_spare != NULL);
}

uint16_t *screen_band(void) { return s_draw; }

void screen_band_clear(uint16_t rgb565)
{
    for (int i = 0; i < SCREEN_W * SCREEN_BAND_H; i++) s_draw[i] = rgb565;
}

void screen_px(int x, int y, uint16_t rgb565)
{
    if (x < 0 || x >= SCREEN_W || y < 0 || y >= SCREEN_BAND_H) return;
    s_draw[y * SCREEN_W + x] = rgb565;
}

// Rendering uses the inactive buffer while SPI owns the previous one. Before
// queueing it, a polling NOP drains the existing transfer. Do not replace the
// esp_lvgl_port completion callback: it owns the panel's sole IRQ callback.
// Without an eligible paused LVGL buffer, push stays synchronous and uses the
// original 9,600-byte band only. Neither path allocates more frame memory.
static void wait_dma_done(void)
{
    esp_lcd_panel_io_handle_t io = bsp_display_io();
    if (io) esp_lcd_panel_io_tx_param(io, 0x00, NULL, 0);   // NOP
}

static void (*s_overlay)(int);
void screen_set_overlay(void (*draw_band)(int)) { s_overlay = draw_band; }

void screen_push_band(int band_y)
{
    int64_t start = s_profiling ? esp_timer_get_time() : 0;
    if (s_overlay) s_overlay(band_y);
    if (s_fap_capture) {
        // Logical RGB565 in the existing little-endian band buffer. No extra
        // 150 KiB framebuffer and no panel/backlight writes during capture.
        fwrite(s_draw, 1, sizeof(s_band), stdout);
        return;
    }
    if (screen_idle_is_off() && !s_dumping) return;
    esp_lcd_panel_handle_t panel = bsp_display_panel();
    if (!panel) return;

    // 小端 → 大端。ST7789 走 SPI 要大端 RGB565，
    // 而 C 里的 uint16_t 在 RISC-V 上是小端。
    //
    // 原地交换：交换后这块缓冲就不能再当逻辑颜色读了 ——
    // 所以截图要在交换**之后**做（见下面那段）。
    for (int i = 0; i < SCREEN_W * SCREEN_BAND_H; i++) {
        uint16_t v = s_draw[i];
        s_draw[i] = (uint16_t)((v >> 8) | (v << 8));
    }

    // dump 模式：吐**交换之后**的字节，也就是屏幕真正收到的东西。
    //
    // 第一版在交换前吐，理由是「输出逻辑颜色，PC 侧不用猜字节序」——
    // 那正好让截图**看不见字节序类的错误**。屏幕紫的时候截图还是绿的，
    // 我据此以为渲染没问题，用户看到的才是真相。
    // 观测手段必须能看见故障，否则它只是在确认我的预期。
    if (s_dumping) screen_emit_band(band_y);

    // Finish the previous buffer only after drawing the next one. The active
    // DMA buffer is never modified; the panel and LVGL keep their existing IRQ.
    screen_flush();
    esp_err_t result = esp_lcd_panel_draw_bitmap(panel, 0, band_y, SCREEN_W,
                              band_y + SCREEN_BAND_H, s_draw);
    if (result == ESP_OK) s_dma_pending = true;
    if (s_spare) s_draw = s_draw == s_band ? s_spare : s_band;
    else screen_flush(); // Safe single-buffer fallback.
    if (s_dumping) screen_flush();
    if (s_cadence.inside) s_cadence.current_bands++;
    if (s_profiling) {
        s_profile_push_us += esp_timer_get_time() - start;
        s_profile_bands++;
    }
}

// ---------------------------------------------------------------------------
// 截图
// ---------------------------------------------------------------------------

static const char B64[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

void screen_set_redraw(screen_redraw_cb_t cb) { s_redraw = cb; }
void screen_redraw_current(void) { if (s_redraw) s_redraw(); screen_flush(); }

// The caller holds the LVGL lock. Replay only: no ticks, input, save or large
// buffer allocation. Push time is CPU submission plus exposed DMA wait;
// overlapped wire time is not counted twice. Total includes the final drain.
void screen_profile_current(void)
{
    if (!s_redraw || s_dumping || s_fap_capture || screen_idle_is_off()) return;
    screen_flush();
    for (unsigned i = 0; i < 3; i++) {
        s_profile_bands = 0; s_profile_push_us = 0; s_profiling = true;
        int64_t start = esp_timer_get_time();
        s_redraw();
        int64_t drain_start = esp_timer_get_time();
        screen_flush();
        s_profile_push_us += esp_timer_get_time() - drain_start;
        int64_t total = esp_timer_get_time() - start;
        s_profiling = false;
        ESP_LOGI(TAG, "@@RENDER_PROFILE sample=%u bands=%lu total_us=%lld draw_us=%lld push_us=%lld",
                 i, (unsigned long)s_profile_bands, (long long)total,
                 (long long)(total - s_profile_push_us), (long long)s_profile_push_us);
    }
}

// 把当前横带 base64 吐到串口。由 screen_push_band 在 dump 模式下调用。
void screen_emit_band(int band_y)
{
    const uint8_t *p = (const uint8_t *)s_draw;
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
    printf("\n@@SHOT %d %d rgb565be %d\n", SCREEN_W, SCREEN_H, SCREEN_BAND_H);
    fflush(stdout);

    // 让页面重画一遍。每条带在 push 时会被 emit 出去。
    s_dumping = true;
    s_redraw();
    s_dumping = false;

    printf("@@SHOTEND\n");
    fflush(stdout);
    ESP_LOGI(TAG, "截图已输出（%d×%d）", SCREEN_W, SCREEN_H);
}

#ifndef HOST_BUILD
static int capture_discard_log(const char *format, va_list args)
{
    (void)format; (void)args; return 0;
}
#endif

void screen_dump_fap(void)
{
    if (!s_redraw || s_fap_capture) return;
#ifndef HOST_BUILD
    vprintf_like_t previous = esp_log_set_vprintf(capture_discard_log);
#endif
    // Keep background telemetry out of the binary payload. Rendering is frozen
    // by the caller's LVGL lock; this callback only replays the current frame.
    flockfile(stdout);
    fflush(stdout);
#ifndef HOST_BUILD
    usb_serial_jtag_vfs_set_tx_line_endings(ESP_LINE_ENDINGS_LF);
#endif
    printf("\nFAP_SCREENSHOT_V1 %d %d RGB565LE %d\n", SCREEN_W, SCREEN_H,
           SCREEN_W * SCREEN_H * 2);
    s_fap_capture = true;
    s_redraw();
    s_fap_capture = false;
    fflush(stdout);
#ifndef HOST_BUILD
#if CONFIG_LIBC_STDOUT_LINE_ENDING_CRLF
    usb_serial_jtag_vfs_set_tx_line_endings(ESP_LINE_ENDINGS_CRLF);
#elif CONFIG_LIBC_STDOUT_LINE_ENDING_CR
    usb_serial_jtag_vfs_set_tx_line_endings(ESP_LINE_ENDINGS_CR);
#else
    usb_serial_jtag_vfs_set_tx_line_endings(ESP_LINE_ENDINGS_LF);
#endif
#endif
    funlockfile(stdout);
#ifndef HOST_BUILD
    esp_log_set_vprintf(previous);
#endif
}
