#pragma once

// Shared inline battery widget for the menu and care identity rows.
// right/y are logical screen coordinates; drawing never polls the hardware.
void battery_ui_draw(int band_y, int right, int y);
void battery_ui_start(void);
void battery_ui_stop(void);
