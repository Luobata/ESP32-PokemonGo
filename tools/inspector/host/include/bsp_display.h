#pragma once
#include <stdint.h>
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
static inline esp_lcd_panel_handle_t bsp_display_panel(void) { return (void *)1; }
static inline esp_lcd_panel_io_handle_t bsp_display_io(void) { return (void *)1; }
void bsp_display_backlight(uint8_t percent);
