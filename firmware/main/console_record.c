#include "console_record.h"
#if defined(ESP_PLATFORM) && !defined(HOST_BUILD)
#include "freertos/FreeRTOS.h"
#include "freertos/semphr.h"

static StaticSemaphore_t s_record_storage;
static SemaphoreHandle_t s_record_lock;
_Static_assert(sizeof(s_record_storage) + sizeof(s_record_lock) <= 128,
               "Console record lock exceeds its static RAM budget");

// Called once in app_main before starting the scan, UI or debug tasks. Static
// allocation avoids a new failure/allocation point during USB save import.
void console_record_init(void)
{
    s_record_lock = xSemaphoreCreateMutexStatic(&s_record_storage);
    configASSERT(s_record_lock);
}

void console_record_begin(void)
{
    configASSERT(s_record_lock);
    BaseType_t ok = xSemaphoreTake(s_record_lock, portMAX_DELAY);
    configASSERT(ok == pdTRUE);
    (void)ok;
}

void console_record_end(void)
{
    BaseType_t ok = xSemaphoreGive(s_record_lock);
    configASSERT(ok == pdTRUE);
    (void)ok;
}
#endif
