#include <stddef.h>
#include <stdatomic.h>
#include "screen_idle.h"
#include "bsp_display.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "lvgl.h"
#include "screen.h"

#define IDLE_MS 60000u
static lv_timer_t *s_timer;
static bool (*s_busy)(void);
static int64_t s_last_activity;
static atomic_bool s_off;
static uint8_t s_pressed, s_wake_gesture;
static atomic_uint s_cleanup;

void screen_idle_input_dropped(bsp_btn_t button, bsp_btn_ev_t event)
{
    if ((unsigned)button >= 3) return;
    unsigned bit = 1u << button;
    if (event == BSP_BTN_RELEASE) atomic_fetch_or(&s_cleanup, bit);
    else if (event == BSP_BTN_GESTURE_END) atomic_fetch_or(&s_cleanup, bit << 3);
}

static void apply_cleanup(void)
{
    unsigned pending = atomic_exchange(&s_cleanup, 0);
    s_pressed &= (uint8_t)~((pending & 7u) | (pending >> 3));
    s_wake_gesture &= (uint8_t)~(pending >> 3);
}

uint32_t screen_idle_timeout_ms(void) { return IDLE_MS; }
bool screen_idle_is_off(void) { return s_off; }
void screen_idle_note_activity(void) { s_last_activity = esp_timer_get_time(); }

void screen_idle_request_off(void)
{
    if (!s_timer || s_off) return;
    bsp_display_backlight(0);
    s_off = true;
    ESP_LOGI("screen_idle", "@@DISPLAY off timeout_ms=%u", IDLE_MS);
}

static void wake(void)
{
    s_off = false;
    // Repaint while the backlight is still dark, then reveal the current page.
    screen_redraw_current();
    bsp_display_backlight(100);
    screen_idle_note_activity();
    ESP_LOGI("screen_idle", "@@DISPLAY on");
}

static void tick(lv_timer_t *timer)
{
    (void)timer;
    apply_cleanup();
    if (s_off) return;
    int64_t now = esp_timer_get_time();
    if (s_pressed || (s_busy && s_busy())) s_last_activity = now;
    else if (now - s_last_activity >= (int64_t)IDLE_MS * 1000)
        screen_idle_request_off();
}

bool screen_idle_init(bool (*busy)(void))
{
    if (s_timer) return true;
    s_busy = busy;
    s_off = false;
    s_pressed = s_wake_gesture = 0;
    atomic_store(&s_cleanup, 0);
    screen_idle_note_activity();
    s_timer = lv_timer_create(tick, 100, NULL);
    return s_timer != NULL;
}

bool screen_idle_filter_key(bsp_btn_t button, bsp_btn_ev_t event)
{
    if (!s_timer || (unsigned)button >= 3) return false;
    apply_cleanup();
    uint8_t bit = (uint8_t)(1u << button);
    screen_idle_note_activity();
    if (event == BSP_BTN_PRESS) {
        s_pressed |= bit;
        if (s_off) { s_wake_gesture |= bit; wake(); }
        return (s_wake_gesture & bit) != 0;
    }
    if (event == BSP_BTN_RELEASE) {
        s_pressed &= (uint8_t)~bit;
        // CLICK/DOUBLE may arrive later. Keep the wake guard until the actual
        // classifier ends the gesture; a guessed timeout can leak late input.
        return true;
    }
    if (event == BSP_BTN_GESTURE_END) {
        s_pressed &= (uint8_t)~bit;
        s_wake_gesture &= (uint8_t)~bit;
        return true;
    }
    if (event != BSP_BTN_CLICK && event != BSP_BTN_DOUBLE && event != BSP_BTN_LONG)
        return false;
    // Serial/preview semantic inputs need no preceding physical PRESS event.
    if (s_off) { wake(); return true; }
    if (s_wake_gesture & bit) return true;
    if (button == BSP_BTN_OK && event == BSP_BTN_LONG) {
        screen_idle_request_off();
        return true;
    }
    return false;
}
