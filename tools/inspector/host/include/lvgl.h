#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef struct lv_timer_t lv_timer_t;
struct lv_timer_t {
    void (*callback)(lv_timer_t *);
    uint64_t due;
    uint32_t period;
    void *user_data;
    bool active;
};
lv_timer_t *lv_timer_create(void (*callback)(lv_timer_t *), uint32_t period, void *data);
void lv_timer_delete(lv_timer_t *timer);
typedef int lv_obj_t;
static inline lv_obj_t *lv_obj_create(void *parent) { (void)parent; static int obj; return &obj; }
static inline void lv_obj_set_style_pad_all(lv_obj_t *o, int a, int b) { (void)o; (void)a; (void)b; }
static inline void lv_obj_set_style_border_width(lv_obj_t *o, int a, int b) { (void)o; (void)a; (void)b; }
static inline void lv_obj_set_style_bg_color(lv_obj_t *o, int a, int b) { (void)o; (void)a; (void)b; }
static inline int lv_color_hex(int color) { return color; }
static inline void lv_screen_load(lv_obj_t *o) { (void)o; }
/* Native preview has no LVGL pixel renderer or refresh timer. Production
 * display ownership is exercised with real LVGL by verify_display_ownership. */
typedef int lv_display_t;
static inline lv_display_t *lv_obj_get_display(lv_obj_t *o) { (void)o; static int display; return &display; }
static inline void lv_display_enable_invalidation(lv_display_t *d, bool enabled) { (void)d; (void)enabled; }
static inline lv_timer_t *lv_display_get_refr_timer(lv_display_t *d) { (void)d; return NULL; }
static inline void lv_timer_pause(lv_timer_t *timer) { if (timer) timer->active = false; }
