#include "sfx.h"

#include <inttypes.h>

#include "bsp_audio.h"
#include "esp_heap_caps.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"

#define SFX_QUEUE_DEPTH 8
#define SFX_CHUNK_SAMPLES 480

static const char *TAG = "sfx";
static QueueHandle_t s_queue;
static volatile uint32_t s_drops;
static int16_t s_pcm[SFX_CHUNK_SAMPLES];

static uint32_t dma_largest(void)
{
    return (uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_DMA);
}

static void play_one(sfx_id_t id)
{
    uint32_t total = audio_sfx_samples(id);
    uint32_t written = 0;
    uint32_t write_errors = 0;
    uint32_t underruns = 0;
    uint32_t pcm_peak = 0;
    uint32_t pcm_clip = 0;

    while (written < total) {
        uint32_t count = total - written;
        if (count > SFX_CHUNK_SAMPLES) count = SFX_CHUNK_SAMPLES;
        int64_t render_started_us = esp_timer_get_time();
        count = audio_render(id, written, count, s_pcm);
        if (count == 0) break;

        for (uint32_t i = 0; i < count; i++) {
            int32_t sample = s_pcm[i];
            uint32_t magnitude = (uint32_t)(sample < 0 ? -sample : sample);
            if (magnitude > pcm_peak) pcm_peak = magnitude;
            if (magnitude >= 32767u) pcm_clip++;
        }

        /* The codec API exposes no hardware underrun counter. A chunk whose
         * synthesis exceeds its own playback time would starve the writer. */
        if (written > 0 &&
            esp_timer_get_time() - render_started_us >
                (int64_t)count * 1000000 / AUDIO_SAMPLE_RATE) {
            underruns++;
        }
        if (bsp_audio_write(s_pcm, count * sizeof(s_pcm[0])) != ESP_OK) {
            write_errors++;
        }
        written += count;
    }

    ESP_LOGI(TAG, "@@SFX id=%u samples=%" PRIu32
             " i2s_underrun=%" PRIu32 " write_errors=%" PRIu32
             " pcm_peak=%" PRIu32 " pcm_clip=%" PRIu32
             " queue_drops=%" PRIu32 " heap=%" PRIu32
             " dma_largest=%" PRIu32,
             (unsigned)id, written, underruns, write_errors,
             pcm_peak, pcm_clip,
             __atomic_load_n(&s_drops, __ATOMIC_RELAXED),
             (uint32_t)esp_get_free_heap_size(), dma_largest());
}

static void sfx_task(void *arg)
{
    (void)arg;
    esp_err_t err = bsp_audio_set_format(AUDIO_SAMPLE_RATE, 16, 1);
    if (err == ESP_OK) bsp_audio_set_volume(SFX_VOLUME_PERCENT);
    ESP_LOGI(TAG, "@@SFX prewarm=%s volume=%u heap=%" PRIu32
             " dma_largest=%" PRIu32,
             esp_err_to_name(err), err == ESP_OK ? SFX_VOLUME_PERCENT : 0,
             (uint32_t)esp_get_free_heap_size(), dma_largest());

    for (;;) {
        sfx_id_t id;
        if (xQueueReceive(s_queue, &id, portMAX_DELAY) == pdTRUE) {
            if (err == ESP_OK) play_one(id);
            else ESP_LOGE(TAG, "丢弃音效 %u：codec 格式预热失败", (unsigned)id);
        }
    }
}

void sfx_start(void)
{
    if (s_queue) return;
    s_queue = xQueueCreate(SFX_QUEUE_DEPTH, sizeof(sfx_id_t));
    if (!s_queue) {
        ESP_LOGE(TAG, "音效队列创建失败");
        return;
    }
    if (xTaskCreate(sfx_task, "sfx", 4096, NULL, 5, NULL) != pdPASS) {
        vQueueDelete(s_queue);
        s_queue = NULL;
        ESP_LOGE(TAG, "音效任务创建失败");
    }
}

void sfx_play(sfx_id_t id)
{
    if ((unsigned)id >= SFX_COUNT || !s_queue ||
        xQueueSend(s_queue, &id, 0) != pdTRUE) {
        uint32_t drops = __atomic_add_fetch(&s_drops, 1, __ATOMIC_RELAXED);
        ESP_LOGW(TAG, "音效请求丢弃 id=%u queue_drops=%" PRIu32,
                 (unsigned)id, drops);
    }
}
