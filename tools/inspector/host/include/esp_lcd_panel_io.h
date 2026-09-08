#pragma once
#include <stddef.h>
typedef void *esp_lcd_panel_io_handle_t;
int esp_lcd_panel_io_tx_param(esp_lcd_panel_io_handle_t io, int cmd, const void *data, size_t size);
