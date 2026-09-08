#pragma once
#include <stdio.h>
/* Keep diagnostics off the binary frame protocol. */
#define ESP_LOGI(tag, ...) ((void)(tag))
#define ESP_LOGW(tag, ...) ((void)(tag))
#define ESP_LOGE(tag, ...) ((void)(tag))
