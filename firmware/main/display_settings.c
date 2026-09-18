#include "display_settings.h"
#include "bsp_display.h"
#include "screen_idle.h"
#include "nvs.h"
#include <stdatomic.h>

static atomic_uchar s_brightness = DISPLAY_BRIGHTNESS_DEFAULT;

void display_settings_init(void)
{
    uint8_t value = DISPLAY_BRIGHTNESS_DEFAULT;
    nvs_handle_t handle;
    if (nvs_open("pokewalk", NVS_READONLY, &handle) == ESP_OK) {
        if (nvs_get_u8(handle, "brightness", &value) != ESP_OK ||
            value < DISPLAY_BRIGHTNESS_MIN || value > 100)
            value = DISPLAY_BRIGHTNESS_DEFAULT;
        nvs_close(handle);
    }
    atomic_store(&s_brightness, value);
}

uint8_t display_settings_brightness(void) { return atomic_load(&s_brightness); }

bool display_settings_set_brightness(uint8_t percent)
{
    if (percent < DISPLAY_BRIGHTNESS_MIN || percent > 100) return false;
    if (percent == display_settings_brightness()) return true;
    nvs_handle_t handle;
    if (nvs_open("pokewalk", NVS_READWRITE, &handle) != ESP_OK) return false;
    esp_err_t result = nvs_set_u8(handle, "brightness", percent);
    if (result == ESP_OK) result = nvs_commit(handle);
    nvs_close(handle);
    if (result != ESP_OK) return false;
    atomic_store(&s_brightness, percent);
    if (!screen_idle_is_off()) bsp_display_backlight(percent);
    return true;
}
