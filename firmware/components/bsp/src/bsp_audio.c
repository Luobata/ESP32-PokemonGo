// components/bsp/src/bsp_audio.c
// 移植自 trae_card/components/platform/platform_esp32/src/audio_es8311.c
#include "bsp_audio.h"
#include "bsp_i2c.h"
#include "bsp_pins.h"
#include "sdkconfig.h"
#include "driver/gpio.h"
#include <stdbool.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "bsp_es8311_sleep_check.h"
#include "esp_log.h"

static esp_err_t pa_off(void) {
#if BSP_I2S_PA_CTRL >= 0
    // Load the low output latch before enabling the pin's output driver.
    esp_err_t e = gpio_set_level(BSP_I2S_PA_CTRL, 0);
    if (e != ESP_OK) return e;
    return gpio_config(&(gpio_config_t){
        .pin_bit_mask = 1ULL << BSP_I2S_PA_CTRL,
        .mode = GPIO_MODE_OUTPUT,
        .pull_up_en = GPIO_PULLUP_DISABLE,
        .pull_down_en = GPIO_PULLDOWN_ENABLE,
        .intr_type = GPIO_INTR_DISABLE,
    });
#else
    return ESP_OK;
#endif
}

static bool s_quiet;
static i2c_master_dev_handle_t s_quiet_device;

esp_err_t bsp_audio_boot_quiet(void) {
    esp_err_t pa = pa_off();
    if (s_quiet) return pa;
    // A GPIO failure must not prevent the independent codec shutdown attempt.
    esp_err_t e = bsp_i2c_init();
    if (e != ESP_OK) return pa != ESP_OK ? pa : e;
    i2c_master_dev_handle_t codec = s_quiet_device;
    if (!codec) {
    e = i2c_master_bus_add_device(bsp_i2c_bus(), &(i2c_device_config_t){
        .dev_addr_length = I2C_ADDR_BIT_LEN_7,
        .device_address = BSP_I2C_ES8311_ADDR,
        .scl_speed_hz = 100000,
    }, &codec);
    if (e != ESP_OK) return pa != ESP_OK ? pa : e;
    s_quiet_device = codec;
    }
    e = pa;

    // Mute first, then the installed esp_codec_dev ES8311 driver's suspend
    // sequence (device/es8311/es8311.c::es8311_suspend). This also stops a
    // codec left powered by a previous firmware after an MCU-only reset.
    // Do not create/open the codec: its enable path turns the PA/DAC on.
    static const uint8_t stop[][2] = {
        {0x31, 0x60}, {0x32, 0x00}, {0x17, 0x00}, {0x0e, 0xff},
        {0x12, 0x02}, {0x14, 0x00}, {0x0d, 0xfa}, {0x15, 0x00},
        {0x02, 0x10}, {0x00, 0x00}, {0x00, 0x1f}, {0x01, 0x30},
        {0x01, 0x00}, {0x45, 0x01}, {0x0d, 0xfc}, {0x02, 0x00},
        {0x31, 0x60},
    };
    // Force and verify even a codec left running by the previous firmware.
    // REG0E's reserved bit can read 0: compare only the documented mask.
    for (unsigned attempt = 0; attempt < 2; attempt++) {
        e = pa;
        for (size_t i = 0; i < sizeof(stop) / sizeof(stop[0]); i++) {
            esp_err_t write = i2c_master_transmit(codec, stop[i], sizeof(stop[i]), 50);
            if (e == ESP_OK && write != ESP_OK) e = write;
        }
        for (size_t i = 0; i < bsp_es8311_sleep_check_count; i++) {
            const bsp_es8311_reg_check_t *check = &bsp_es8311_sleep_checks[i];
            uint8_t actual = 0;
            esp_err_t read = i2c_master_transmit_receive(codec, &check->reg, 1, &actual, 1, 50);
            if (e == ESP_OK && (read != ESP_OK || !bsp_es8311_sleep_check_matches(check, actual)))
                e = read != ESP_OK ? read : ESP_FAIL;
        }
        if (e == ESP_OK) break;
        if (!attempt) vTaskDelay(pdMS_TO_TICKS(5));
    }
    esp_err_t removed = i2c_master_bus_rm_device(codec);
    if (removed == ESP_OK) s_quiet_device = NULL;
    if (e == ESP_OK) e = removed;
    s_quiet = e == ESP_OK;
    if (s_quiet) ESP_LOGI("bsp_audio", "Codec sleep verified (REG45 pull-ups disabled)");
    return e;
}

#if CONFIG_POKEWALK_SILENT_BOOT

esp_err_t bsp_audio_suspend(void) { return bsp_audio_boot_quiet(); }
esp_err_t bsp_audio_init(void) { return bsp_audio_boot_quiet(); }
esp_err_t bsp_audio_set_format(uint32_t hz, uint8_t bits, uint8_t ch) {
    (void)hz; (void)bits; (void)ch;
    return ESP_ERR_NOT_SUPPORTED;
}
esp_err_t bsp_audio_write(const void *pcm, size_t bytes) {
    (void)pcm; (void)bytes;
    return ESP_ERR_NOT_SUPPORTED;
}
esp_err_t bsp_audio_read(void *pcm, size_t bytes) {
    (void)pcm; (void)bytes;
    return ESP_ERR_NOT_SUPPORTED;
}
void bsp_audio_set_volume(uint8_t percent) { (void)percent; }

#else

#include "esp_codec_dev.h"
#include "esp_codec_dev_defaults.h"
#include "es8311_codec.h"
#include "driver/i2s_std.h"
#include "esp_log.h"

static const char *TAG = "bsp_audio";

static esp_codec_dev_handle_t s_dev;
static i2s_chan_handle_t      s_tx, s_rx;
// 记录当前已打开的格式,用于判断"要不要 close 重开"(见头文件里的坑说明)。
static uint32_t s_hz;
static uint8_t  s_bits, s_ch;
static bool     s_opened, s_close_pending;
static const audio_codec_ctrl_if_t *s_ctrl;
static const audio_codec_data_if_t *s_data;
static const audio_codec_if_t *s_codec;
static const audio_codec_gpio_if_t *s_gpio;


static esp_err_t audio_disable_i2s_channels(void) {
    esp_err_t result = ESP_OK;
    i2s_chan_handle_t channels[] = {s_tx, s_rx};
    for (unsigned i = 0; i < 2; i++) {
        if (!channels[i]) continue;
        esp_err_t e = i2s_channel_disable(channels[i]);
        if (e != ESP_OK && e != ESP_ERR_INVALID_STATE && result == ESP_OK) result = e;
    }
    return result;
}

esp_err_t bsp_audio_suspend(void) {
    esp_err_t result = pa_off();
    if (s_dev && (s_opened || s_close_pending)) {
        bsp_audio_set_volume(0);
        // Explicitly update codec state before close; next open must resume it.
        if (!s_codec || !s_codec->enable || s_codec->enable(s_codec, false) != 0)
            result = ESP_FAIL;
        if (esp_codec_dev_close(s_dev) != 0) result = ESP_FAIL;
        s_close_pending = result != ESP_OK;
        s_opened = false;
        s_quiet = false; // close may write the dependency's weaker REG45 value.
    }
    esp_err_t e = bsp_audio_boot_quiet();
    if (result == ESP_OK) result = e;
    // Stop both clocks even after a failed I2C write/read. Never re-enable here.
    e = audio_disable_i2s_channels();
    if (result == ESP_OK) result = e;
    if (result != ESP_OK) s_quiet = false; // A failed transition is retryable.
    return result;
}

static void audio_cleanup(void) {
    if (s_dev) {
        esp_codec_dev_delete(s_dev);
        s_dev = NULL;
    }
    if (s_codec) {
        audio_codec_delete_codec_if(s_codec);
        s_codec = NULL;
    }
    if (s_gpio) {
        audio_codec_delete_gpio_if(s_gpio);
        s_gpio = NULL;
    }
    if (s_data) {
        audio_codec_delete_data_if(s_data);
        s_data = NULL;
    }
    if (s_rx) {
        i2s_channel_disable(s_rx);
        esp_err_t e = i2s_del_channel(s_rx);
        if (e == ESP_OK) s_rx = NULL;
        else ESP_LOGE(TAG, "I2S RX 回滚失败: %s", esp_err_to_name(e));
    }
    if (s_tx) {
        i2s_channel_disable(s_tx);
        esp_err_t e = i2s_del_channel(s_tx);
        if (e == ESP_OK) s_tx = NULL;
        else ESP_LOGE(TAG, "I2S TX 回滚失败: %s", esp_err_to_name(e));
    }
    if (s_ctrl) {
        audio_codec_delete_ctrl_if(s_ctrl);
        s_ctrl = NULL;
    }
    s_opened = false;

    s_hz = 0;
    s_bits = 0;
    s_ch = 0;
}

static esp_err_t i2s_full_duplex_init(void) {
    i2s_chan_config_t chan = {
        .id = BSP_I2S_PORT,
        .role = I2S_ROLE_MASTER,
        .dma_desc_num = 6,
        .dma_frame_num = 240,
        .auto_clear_after_cb = true,
        .auto_clear_before_cb = false,
        .intr_priority = 0,
    };
    esp_err_t e = i2s_new_channel(&chan, &s_tx, &s_rx);
    if (e != ESP_OK) { ESP_LOGE(TAG, "i2s_new_channel 失败: %s", esp_err_to_name(e)); return e; }

    // 这里的采样率只用于建通道;实际速率由 esp_codec_dev_open() 按需重配。
    i2s_std_config_t std = {
        .clk_cfg = {
            .sample_rate_hz = 16000,
            .clk_src = I2S_CLK_SRC_DEFAULT,
            .ext_clk_freq_hz = 0,
            .mclk_multiple = I2S_MCLK_MULTIPLE_256,
        },
        .slot_cfg = {
            .data_bit_width = I2S_DATA_BIT_WIDTH_16BIT,
            .slot_bit_width = I2S_SLOT_BIT_WIDTH_AUTO,
            .slot_mode = I2S_SLOT_MODE_STEREO,
            .slot_mask = I2S_STD_SLOT_BOTH,
            .ws_width = I2S_DATA_BIT_WIDTH_16BIT,
            .ws_pol = false,
            .bit_shift = true,
            .left_align = true,
            .big_endian = false,
            .bit_order_lsb = false,
        },
        .gpio_cfg = {
            .mclk = BSP_I2S_MCLK, .bclk = BSP_I2S_BCLK, .ws = BSP_I2S_WS,
            .dout = BSP_I2S_DOUT, .din = BSP_I2S_DIN,
            .invert_flags = { .mclk_inv = false, .bclk_inv = false, .ws_inv = false },
        },
    };
    if ((e = i2s_channel_init_std_mode(s_tx, &std)) != ESP_OK) {
        ESP_LOGE(TAG, "i2s tx 初始化失败: %s", esp_err_to_name(e)); return e;
    }
    if ((e = i2s_channel_init_std_mode(s_rx, &std)) != ESP_OK) {
        ESP_LOGE(TAG, "i2s rx 初始化失败: %s", esp_err_to_name(e)); return e;
    }
    return ESP_OK;
}

esp_err_t bsp_audio_init(void) {
    if (s_dev) return ESP_OK;
    if (s_tx || s_rx || s_ctrl || s_data || s_codec || s_gpio) {
        audio_cleanup();
        if (s_tx || s_rx || s_ctrl || s_data || s_codec || s_gpio)
            return ESP_ERR_INVALID_STATE;
    }

    esp_err_t e = bsp_i2c_init();
    if (e != ESP_OK) return e;

    s_ctrl = audio_codec_new_i2c_ctrl(&(audio_codec_i2c_cfg_t){
        .port = BSP_I2C_PORT,
        .addr = BSP_I2C_ES8311_ADDR << 1,   // 该接口要 8 位地址形式
        .bus_handle = bsp_i2c_bus(),
    });
    if (!s_ctrl) {
        ESP_LOGE(TAG, "ES8311 控制口创建失败 —— 用 bsp_i2c_scan() 确认 0x%02X 是否应答;"
                      "检查 SDA=GPIO%d / SCL=GPIO%d 接线与 codec 供电",
                 BSP_I2C_ES8311_ADDR, BSP_I2C_SDA, BSP_I2C_SCL);
        return ESP_FAIL;
    }

    if ((e = i2s_full_duplex_init()) != ESP_OK) goto fail;

    s_data = audio_codec_new_i2s_data(&(audio_codec_i2s_cfg_t){
        .port = BSP_I2S_PORT, .tx_handle = s_tx, .rx_handle = s_rx,
    });
    if (!s_data) { ESP_LOGE(TAG, "I2S 数据口创建失败"); e = ESP_ERR_NO_MEM; goto fail; }

    s_gpio = audio_codec_new_gpio();
    if (!s_gpio) { ESP_LOGE(TAG, "codec GPIO 接口创建失败"); e = ESP_ERR_NO_MEM; goto fail; }

    s_quiet = false; // Constructing the driver can change codec registers.
    s_codec = es8311_codec_new(&(es8311_codec_cfg_t){
        .ctrl_if     = s_ctrl,
        .gpio_if     = s_gpio,
        .codec_mode  = ESP_CODEC_DEV_WORK_MODE_BOTH,
        .pa_pin      = BSP_I2S_PA_CTRL,
        .pa_reverted = false,
        .master_mode = false,          // MCU I2S 为 master,codec 为 slave
        .use_mclk    = true,
        .hw_gain     = { .pa_voltage = 5.0f, .codec_dac_voltage = 3.3f },
        // ⚠ 单声道纯麦克风录音必须为 true。false 会让驱动写 REG44=0x58 进入
        //   ADCL+DACR 参考模式,单声道读到的那一路是 DAC 参考 → 【录音恒为 0】。
        .no_dac_ref  = true,
    });
    if (!s_codec) { ESP_LOGE(TAG, "es8311_codec_new 失败"); e = ESP_ERR_NO_MEM; goto fail; }

    s_dev = esp_codec_dev_new(&(esp_codec_dev_cfg_t){
        .dev_type = ESP_CODEC_DEV_TYPE_IN_OUT,
        .codec_if = s_codec,
        .data_if  = s_data,
    });
    if (!s_dev) { ESP_LOGE(TAG, "esp_codec_dev_new 失败"); e = ESP_ERR_NO_MEM; goto fail; }

    ESP_LOGI(TAG, "ES8311 就绪");
    return ESP_OK;

fail:
    audio_cleanup();
    s_quiet = false;
    (void)bsp_audio_boot_quiet();
    return e;
}

esp_err_t bsp_audio_set_format(uint32_t hz, uint8_t bits, uint8_t ch) {
    if (!s_dev) return ESP_ERR_INVALID_STATE;
    if (s_opened && s_hz == hz && s_bits == bits && s_ch == ch) return ESP_OK;   // 同格式复用

    if ((s_opened || s_close_pending) && bsp_audio_suspend() != ESP_OK) return ESP_FAIL;
    // Reopen is the only place that starts I2S. Disable first so a partial
    // previous enable/open failure cannot leave TX/RX in different states.
    esp_err_t e = audio_disable_i2s_channels();
    if (e == ESP_OK) e = i2s_channel_enable(s_tx);
    if (e == ESP_OK) e = i2s_channel_enable(s_rx);
    if (e != ESP_OK) { (void)bsp_audio_suspend(); return e; }
    s_quiet = false;

    esp_codec_dev_sample_info_t fs = {
        .bits_per_sample = bits,
        .channel = ch,
        .channel_mask = ESP_CODEC_DEV_MAKE_CHANNEL_MASK(0),
        .sample_rate = hz,
        .mclk_multiple = 0,          // 0 → 驱动按默认 256xfs 取 MCLK
    };
    int r = esp_codec_dev_open(s_dev, &fs);
    if (r != 0) {
        // An unsuccessful open may already have powered up part of the codec.
        s_close_pending = true;
        (void)bsp_audio_suspend();
        ESP_LOGE(TAG, "esp_codec_dev_open 失败: %d", r);
        return ESP_FAIL;
    }

    // ⚠ open 之后【不要】手动覆写 ES8311 的时钟分频寄存器(REG01~06):
    //   驱动已按采样率与 MCLK 精确算好,覆写会导致 ADC/DAC 时序错乱、录音回放全是杂音。
    //   这里只设麦克风模拟 PGA 增益。
    esp_codec_dev_set_in_gain(s_dev, 30.0f);

    s_quiet = false;
    s_opened = true; s_hz = hz; s_bits = bits; s_ch = ch;
    ESP_LOGI(TAG, "codec 打开 %luHz/%ubit/%uch", (unsigned long)hz, bits, ch);
    return ESP_OK;
}

esp_err_t bsp_audio_write(const void *pcm, size_t bytes) {
    if (!s_dev || !s_opened) return ESP_ERR_INVALID_STATE;
    return esp_codec_dev_write(s_dev, (void *)pcm, bytes) == 0 ? ESP_OK : ESP_FAIL;
}

esp_err_t bsp_audio_read(void *pcm, size_t bytes) {
    if (!s_dev || !s_opened) return ESP_ERR_INVALID_STATE;
    return esp_codec_dev_read(s_dev, pcm, bytes) == 0 ? ESP_OK : ESP_FAIL;
}

void bsp_audio_set_volume(uint8_t percent) {
    if (s_dev && s_opened) esp_codec_dev_set_out_vol(s_dev, percent);
}

#endif // CONFIG_POKEWALK_SILENT_BOOT
