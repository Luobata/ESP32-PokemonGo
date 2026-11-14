#include "language.h"
#include "nvs.h"

void language_settings_init(void) {
    uint8_t value=LANGUAGE_ZH_HANS;nvs_handle_t handle;
    if(nvs_open("pokewalk",NVS_READONLY,&handle)==ESP_OK) {
        if(nvs_get_u8(handle,"language",&value)!=ESP_OK || value>=LANGUAGE_COUNT)value=LANGUAGE_ZH_HANS;
        nvs_close(handle);
    }
    language_set_runtime(value);
}
bool language_settings_set(language_t language) {
    if((unsigned)language>=LANGUAGE_COUNT)return false;
    if(language==language_get())return true;
    nvs_handle_t handle;
    if(nvs_open("pokewalk",NVS_READWRITE,&handle)!=ESP_OK)return false;
    esp_err_t err=nvs_set_u8(handle,"language",language);
    if(err==ESP_OK)err=nvs_commit(handle);
    nvs_close(handle);
    if(err!=ESP_OK)return false;
    return language_set_runtime(language);
}
