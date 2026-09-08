#!/usr/bin/env python3
"""Compile the real BSP/SFX in silent and audible configurations, without devices.

Mocks record GPIO, I2C shutdown writes, codec/I2S and queue/task calls. Tests
include transport failures and compilable negative controls. No serial module,
esptool invocation, reset, audio playback or physical device access is used.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BSP = ROOT / 'firmware/components/bsp'
MAIN = ROOT / 'firmware/main'

PLATFORM = r'''
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_NOT_SUPPORTED 0x106
void test_log(const char *tag, const char *format, ...);
#define ESP_LOGI(...) test_log(__VA_ARGS__)
#define ESP_LOGW(...) test_log(__VA_ARGS__)
#define ESP_LOGE(...) test_log(__VA_ARGS__)
const char *esp_err_to_name(esp_err_t e);
typedef struct { uint64_t pin_bit_mask; int mode, pull_up_en, pull_down_en, intr_type; } gpio_config_t;
#define GPIO_MODE_OUTPUT 1
#define GPIO_PULLUP_DISABLE 0
#define GPIO_PULLDOWN_ENABLE 1
#define GPIO_INTR_DISABLE 0
esp_err_t gpio_set_level(int pin, unsigned level);
esp_err_t gpio_config(const gpio_config_t *cfg);
typedef void *i2c_master_bus_handle_t;
typedef void *i2c_master_dev_handle_t;
typedef struct { int dev_addr_length, device_address, scl_speed_hz; } i2c_device_config_t;
#define I2C_ADDR_BIT_LEN_7 0
esp_err_t i2c_master_bus_add_device(void *bus, const i2c_device_config_t *cfg, void **out);
esp_err_t i2c_master_transmit(void *dev, const void *data, size_t bytes, int timeout);
esp_err_t i2c_master_bus_rm_device(void *dev);
typedef void *esp_codec_dev_handle_t;
typedef void *i2s_chan_handle_t;
typedef struct { int id, role, dma_desc_num, dma_frame_num, auto_clear_after_cb, auto_clear_before_cb, intr_priority; } i2s_chan_config_t;
typedef struct {
 struct { int sample_rate_hz, clk_src, ext_clk_freq_hz, mclk_multiple; } clk_cfg;
 struct { int data_bit_width, slot_bit_width, slot_mode, slot_mask, ws_width, ws_pol, bit_shift, left_align, big_endian, bit_order_lsb; } slot_cfg;
 struct { int mclk, bclk, ws, dout, din; struct { int mclk_inv, bclk_inv, ws_inv; } invert_flags; } gpio_cfg;
} i2s_std_config_t;
#define I2S_ROLE_MASTER 1
#define I2S_CLK_SRC_DEFAULT 0
#define I2S_MCLK_MULTIPLE_256 256
#define I2S_DATA_BIT_WIDTH_16BIT 16
#define I2S_SLOT_BIT_WIDTH_AUTO 0
#define I2S_SLOT_MODE_STEREO 2
#define I2S_STD_SLOT_BOTH 3
esp_err_t i2s_new_channel(const i2s_chan_config_t *cfg, void **tx, void **rx);
esp_err_t i2s_channel_init_std_mode(void *chan, const i2s_std_config_t *cfg);
esp_err_t i2s_channel_enable(void *chan);
typedef struct { int unused; } audio_codec_ctrl_if_t;
typedef audio_codec_ctrl_if_t audio_codec_data_if_t;
typedef audio_codec_ctrl_if_t audio_codec_if_t;
typedef struct { int port, addr; void *bus_handle; } audio_codec_i2c_cfg_t;
typedef struct { int port; void *tx_handle, *rx_handle; } audio_codec_i2s_cfg_t;
typedef struct {
 const audio_codec_ctrl_if_t *ctrl_if; void *gpio_if;
 int codec_mode, pa_pin, pa_reverted, master_mode, use_mclk;
 struct { float pa_voltage, codec_dac_voltage; } hw_gain;
 bool no_dac_ref;
} es8311_codec_cfg_t;
typedef struct { int dev_type; const audio_codec_if_t *codec_if; const audio_codec_data_if_t *data_if; } esp_codec_dev_cfg_t;
typedef struct { int bits_per_sample, channel, channel_mask, sample_rate, mclk_multiple; } esp_codec_dev_sample_info_t;
#define ESP_CODEC_DEV_WORK_MODE_BOTH 3
#define ESP_CODEC_DEV_TYPE_IN_OUT 3
#define ESP_CODEC_DEV_MAKE_CHANNEL_MASK(x) (1 << (x))
const audio_codec_ctrl_if_t *audio_codec_new_i2c_ctrl(const audio_codec_i2c_cfg_t *cfg);
const audio_codec_data_if_t *audio_codec_new_i2s_data(const audio_codec_i2s_cfg_t *cfg);
void *audio_codec_new_gpio(void);
const audio_codec_if_t *es8311_codec_new(const es8311_codec_cfg_t *cfg);
void *esp_codec_dev_new(const esp_codec_dev_cfg_t *cfg);
int esp_codec_dev_open(void *dev, const esp_codec_dev_sample_info_t *fs);
int esp_codec_dev_close(void *dev);
int esp_codec_dev_set_in_gain(void *dev, float gain);
int esp_codec_dev_write(void *dev, void *pcm, size_t size);
int esp_codec_dev_read(void *dev, void *pcm, size_t size);
int esp_codec_dev_set_out_vol(void *dev, unsigned volume);
typedef void *QueueHandle_t;
#define MALLOC_CAP_DMA 1
#define portMAX_DELAY 0xffffffffu
#define pdTRUE 1
#define pdPASS 1
size_t heap_caps_get_largest_free_block(unsigned caps);
size_t esp_get_free_heap_size(void);
int64_t esp_timer_get_time(void);
void *xQueueCreate(unsigned count, unsigned bytes);
int xQueueReceive(void *q, void *id, unsigned wait);
int xQueueSend(void *q, const void *id, unsigned wait);
void vQueueDelete(void *q);
#define pdMS_TO_TICKS(x) (x)
void vTaskDelay(unsigned ticks);
int xTaskCreate(void (*fn)(void *), const char *name, unsigned stack, void *arg, unsigned priority, void *handle);
'''

DRIVER = r'''
#include "platform.h"
#include "bsp_audio.h"
#include "bsp_i2c.h"
#include "bsp_pins.h"
#include "sfx.h"
#include "sound_mixer.h"
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
static int mode, levels, configured, writes, removed, added, buses, i2s, codec, formats, volumes, output, input, queues, tasks, sends;
static unsigned last_level;
static uint8_t transactions[64][2];
static const audio_codec_ctrl_if_t dummy = {0};
void test_log(const char *tag, const char *format, ...) { (void)tag;(void)format; }
const char *esp_err_to_name(esp_err_t e) { (void)e; return "test"; }
esp_err_t gpio_set_level(int pin, unsigned level) {
 assert(pin==BSP_I2S_PA_CTRL && pin>=0); levels++; last_level=level;
 assert(level==0); return mode==1 ? ESP_FAIL : ESP_OK;
}
esp_err_t gpio_config(const gpio_config_t *cfg) {
 assert(levels && !last_level);
 assert(TEST_PA>=0 && cfg->pin_bit_mask==(1ULL<<(TEST_PA>=0?TEST_PA:0)) && cfg->mode==GPIO_MODE_OUTPUT);
 assert(cfg->pull_up_en==GPIO_PULLUP_DISABLE && cfg->pull_down_en==GPIO_PULLDOWN_ENABLE);
 configured++;return mode==2 ? ESP_FAIL : ESP_OK;
}
esp_err_t bsp_i2c_init(void) { buses++;return mode==3 ? ESP_FAIL : ESP_OK; }
void *bsp_i2c_bus(void) { return (void *)1; }
esp_err_t i2c_master_bus_add_device(void *bus, const i2c_device_config_t *cfg, void **out) {
 assert(bus==(void *)1 && cfg->device_address==0x18 && cfg->dev_addr_length==I2C_ADDR_BIT_LEN_7);
 added++;*out=(void *)2;return mode==4 ? ESP_FAIL : ESP_OK;
}
esp_err_t i2c_master_transmit(void *dev, const void *data, size_t bytes, int timeout) {
 assert(dev==(void *)2 && bytes==2 && timeout>0 && timeout<=100);
 assert(writes<64);memcpy(transactions[writes],data,2);writes++;
 return mode==5 && writes==1 ? ESP_FAIL : ESP_OK;
}
esp_err_t i2c_master_bus_rm_device(void *dev) {
 assert(dev==(void *)2);removed++;return mode==6 ? ESP_FAIL : ESP_OK;
}
esp_err_t i2s_new_channel(const i2s_chan_config_t *cfg, void **tx, void **rx) { (void)cfg; i2s++;*tx=(void *)3;*rx=(void *)4;return 0; }
esp_err_t i2s_channel_init_std_mode(void *ch, const i2s_std_config_t *cfg) { (void)ch;(void)cfg;i2s++;return 0; }
esp_err_t i2s_channel_enable(void *ch) { (void)ch;i2s++;return 0; }
const audio_codec_ctrl_if_t *audio_codec_new_i2c_ctrl(const audio_codec_i2c_cfg_t *cfg) { (void)cfg;codec++;return &dummy; }
const audio_codec_data_if_t *audio_codec_new_i2s_data(const audio_codec_i2s_cfg_t *cfg) { (void)cfg;codec++;return &dummy; }
void *audio_codec_new_gpio(void) { codec++;return (void *)1; }
const audio_codec_if_t *es8311_codec_new(const es8311_codec_cfg_t *cfg) { (void)cfg;codec++;return &dummy; }
void *esp_codec_dev_new(const esp_codec_dev_cfg_t *cfg) { (void)cfg;codec++;return (void *)5; }
int esp_codec_dev_open(void *d, const esp_codec_dev_sample_info_t *fs) { (void)d;(void)fs;formats++;return 0; }
int esp_codec_dev_close(void *d) { (void)d;return 0; }
int esp_codec_dev_set_in_gain(void *d, float gain) { (void)d;(void)gain;return 0; }
int esp_codec_dev_write(void *d, void *pcm, size_t bytes) { (void)d;(void)pcm;(void)bytes;output++;return 0; }
int esp_codec_dev_read(void *d, void *pcm, size_t bytes) { (void)d;(void)pcm;(void)bytes;input++;return 0; }
int esp_codec_dev_set_out_vol(void *d, unsigned volume) { (void)d;(void)volume;volumes++;return 0; }
size_t heap_caps_get_largest_free_block(unsigned caps) { (void)caps;return 10000; }
size_t esp_get_free_heap_size(void) { return 10000; }
int64_t esp_timer_get_time(void) { return 0; }
void *xQueueCreate(unsigned count, unsigned bytes) { assert(count>0 && bytes>=sizeof(sfx_id_t));queues++;return (void *)6; }
int xQueueReceive(void *q, void *id, unsigned wait) { (void)q;(void)id;(void)wait;abort(); }
int xQueueSend(void *q, const void *id, unsigned wait) { (void)id;assert(q==(void *)6 && wait==0);sends++;return pdTRUE; }
void vQueueDelete(void *q) { (void)q; }
int xTaskCreate(void (*fn)(void *), const char *name, unsigned stack, void *arg, unsigned priority, void *handle) {
 (void)fn;(void)name;(void)stack;(void)arg;(void)priority;(void)handle;tasks++;return pdPASS;
}
uint32_t audio_sfx_samples(sfx_id_t id) { (void)id;return 4; }
uint32_t audio_render(sfx_id_t id, uint32_t from, uint32_t count, int16_t *out) {
 (void)id;(void)from;memset(out,0,count*sizeof(*out));return count;
}
void vTaskDelay(unsigned ticks) {(void)ticks;}
bool screen_idle_is_off(void) {return false;}
bool audio_settings_muted(void) {return false;}
uint8_t audio_settings_volume(void) {return 55;}
sfx_id_t audio_encounter_alert(uint8_t r,bool s){return s?SFX_SHINY:r>=4?SFX_RARE:SFX_ENCOUNTER;}
void sound_mixer_init(sound_mixer_t *m) {memset(m,0,sizeof(*m));}
void sound_mixer_effect(sound_mixer_t *m,sfx_id_t id) {(void)m;(void)id;}
void sound_mixer_move(sound_mixer_t *m,uint16_t id,uint8_t type,bool missed) {(void)m;(void)id;(void)type;(void)missed;}
void sound_mixer_music(sound_mixer_t *m,music_id_t id) {(void)m;(void)id;}
void sound_mixer_render(sound_mixer_t *m,uint32_t n,int16_t *out) {(void)m;memset(out,0,n*2);}
static void assert_blocked(void) {
 unsigned char pcm[8];memset(pcm,0xa5,sizeof(pcm));
 assert(bsp_audio_set_format(22050,16,1)==ESP_ERR_NOT_SUPPORTED);
 assert(bsp_audio_set_format(48000,24,2)==ESP_ERR_NOT_SUPPORTED);
 assert(bsp_audio_write(pcm,sizeof(pcm))==ESP_ERR_NOT_SUPPORTED);
 assert(bsp_audio_write(NULL,0)==ESP_ERR_NOT_SUPPORTED);
 assert(bsp_audio_read(pcm,sizeof(pcm))==ESP_ERR_NOT_SUPPORTED);
 assert(pcm[0]==0xa5 && pcm[7]==0xa5);
 for(unsigned i=0;i<256;i++)bsp_audio_set_volume(i);
 for(int i=0;i<3;i++)sfx_start();
 for(int i=-1;i<=SFX_COUNT;i++)sfx_play((sfx_id_t)i);
 for(int i=0;i<MUSIC_COUNT;i++)sfx_music_play((music_id_t)i);
 sfx_move(85,3,false);
 assert(i2s==0 && codec==0 && formats==0 && volumes==0 && output==0 && input==0);
 assert(queues==0 && tasks==0 && sends==0);
}
static void assert_shutdown(void) {
 assert(writes>=17 && writes%17==0);
 const uint8_t *first=transactions[writes-17], *last=transactions[writes-1];
 assert(first[0]==0x31 && (first[1]&0x60)==0x60);
 assert(last[0]==0x31 && (last[1]&0x60)==0x60);
 bool dac=false,clock=false,volume=false;
 for(int i=writes-17;i<writes;i++) {
  if(transactions[i][0]==0x12 && transactions[i][1]==0x02)dac=true;
  if(transactions[i][0]==0x01 && transactions[i][1]==0x00)clock=true;
  if(transactions[i][0]==0x32 && transactions[i][1]==0x00)volume=true;
 }
 assert(dac && clock && volume);
}
int main(int argc, char **argv) {
 mode=argc>1?atoi(argv[1]):0;
#if CONFIG_POKEWALK_SILENT_BOOT
 assert_blocked(); // Direct calls before initialization cannot start hardware.
 esp_err_t e=bsp_audio_boot_quiet();
 assert(e==(mode ? ESP_FAIL : ESP_OK));
 if(mode!=3 && mode!=4) { assert_shutdown();assert(removed==1); }
 if(mode==3 || mode==4)assert(writes==0);
 if(mode==1 || mode==2)assert(buses==1 && writes==17);
 assert_blocked();
 int prior=writes;mode=0;
 assert(bsp_audio_init()==ESP_OK);assert_shutdown();
 assert(bsp_audio_boot_quiet()==ESP_OK);
 assert(writes==(e==ESP_OK ? prior : prior+17)); // Errors are retried, success is idempotent.
 assert_blocked();
#else
 assert(mode==0 && bsp_audio_boot_quiet()==ESP_OK && !i2s && !codec && writes==17);
 assert(bsp_audio_init()==ESP_OK && i2s>0 && codec>0);
 assert(bsp_audio_set_format(22050,16,1)==ESP_OK);
 assert(bsp_audio_set_format(22050,16,1)==ESP_OK && formats==1);
 assert(bsp_audio_set_format(16000,16,1)==ESP_OK && formats==2);
 int16_t pcm[4]={0};bsp_audio_set_volume(80);
 assert(bsp_audio_write(pcm,sizeof(pcm))==ESP_OK && output==1);
 assert(bsp_audio_read(pcm,sizeof(pcm))==ESP_OK && input==1 && volumes==1);
 sfx_start();sfx_start();assert(queues==1 && tasks==1);
 for(int i=0;i<SFX_COUNT;i++)sfx_play((sfx_id_t)i);
 assert(sends==SFX_COUNT);
#endif
 assert(TEST_PA<0 ? levels==0 && configured==0 : levels>0);
 puts("PASS");return 0;
}
'''


def verify_boot_order(text: str) -> None:
    source = re.sub(r'//[^\n]*|/\*.*?\*/', '', text, flags=re.S)
    body = source.split('void app_main(void) {', 1)[1]
    assert re.match(r'\s*esp_err_t\s+quiet\s*=\s*bsp_audio_boot_quiet\(\);', body), \
        'shutdown must be the first app action'


def main() -> int:
    bsp = (BSP/'src/bsp_audio.c').read_text()
    sfx = (MAIN/'sfx.c').read_text()
    startup = (MAIN/'main.c').read_text()
    verify_boot_order(startup)
    assert 'config POKEWALK_SILENT_BOOT' in (MAIN/'Kconfig.projbuild').read_text()
    assert re.search(r'#define\s+BSP_I2S_PA_CTRL\s+\(-1\)', (BSP/'include/bsp_pins.h').read_text()), \
        'update the board-level acoustic boundary if the real PA wiring changes'

    tests, negatives = [], []
    with tempfile.TemporaryDirectory(prefix='pokewalk-silent-') as name:
        tmp = Path(name)
        (tmp/'platform.h').write_text(PLATFORM)
        (tmp/'driver.c').write_text(DRIVER)
        headers = ['esp_err.h', 'sdkconfig.h', 'driver/gpio.h', 'driver/i2c_master.h',
                   'driver/i2s_std.h', 'esp_codec_dev.h', 'esp_codec_dev_defaults.h',
                   'es8311_codec.h', 'esp_log.h', 'esp_heap_caps.h', 'esp_system.h',
                   'esp_timer.h', 'freertos/FreeRTOS.h', 'freertos/queue.h', 'freertos/task.h']
        for header in headers:
            p = tmp/header;p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('#include "platform.h"\n')
        (tmp/'bsp_pins.h').write_text('''#include "platform.h"
#define BSP_I2S_PA_CTRL TEST_PA
#define BSP_I2C_ES8311_ADDR 0x18
#define BSP_I2C_PORT 0
#define BSP_I2C_SDA 10
#define BSP_I2C_SCL 7
#define BSP_I2S_PORT 0
#define BSP_I2S_MCLK 6
#define BSP_I2S_BCLK 5
#define BSP_I2S_WS 3
#define BSP_I2S_DOUT 2
#define BSP_I2S_DIN 4
''')

        def compile_case(silent: int, pin: int, audio_source=bsp, sfx_source=sfx) -> Path:
            (tmp/'bsp_audio.c').write_text(audio_source)
            (tmp/'sfx.c').write_text(sfx_source)
            exe = tmp/'probe'
            result = subprocess.run(['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-function', '-Wno-unused-variable',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                f'-DCONFIG_POKEWALK_SILENT_BOOT={silent}', f'-DTEST_PA={pin}',
                '-I', str(tmp), '-I', str(BSP/'include'), '-I', str(MAIN),
                str(tmp/'bsp_audio.c'), str(tmp/'sfx.c'), str(tmp/'driver.c'), '-o', str(exe)],
                capture_output=True, text=True)
            assert result.returncode == 0, result.stderr
            return exe

        def run(exe: Path, mode: int, reject=False) -> None:
            result = subprocess.run([str(exe), str(mode)], capture_output=True, text=True)
            if reject:
                assert result.returncode != 0 and 'Assertion failed' in result.stderr, result.stderr
            else:
                assert result.returncode == 0 and result.stdout.strip() == 'PASS', result.stderr

        for silent in (1, 0):
            for pin in (-1, 12):
                exe = compile_case(silent, pin)
                modes = [0, 3, 4, 5, 6] + ([1, 2] if pin>=0 else []) if silent else [0]
                for mode in modes:
                    run(exe, mode)
                    tests.append({'silent':bool(silent), 'pa_pin':pin, 'injected_failure':mode})

        mutants = [
            ('PA accidentally driven high', bsp.replace('gpio_set_level(BSP_I2S_PA_CTRL, 0)',
                                                       'gpio_set_level(BSP_I2S_PA_CTRL, 1)', 1), sfx),
            ('codec DAC shutdown omitted', bsp.replace('{0x12, 0x02}', '{0x12, 0x00}', 1), sfx),
            ('I2C error incorrectly cached as success', bsp.replace('s_quiet = e == ESP_OK;', 's_quiet = true;', 1), sfx),
            ('SFX queue still starts in silent build', bsp, sfx.replace('#if CONFIG_POKEWALK_SILENT_BOOT', '#if 0', 1)),
        ]
        for label, audio_source, sfx_source in mutants:
            run(compile_case(1, 12, audio_source, sfx_source), 5 if 'cached' in label else 0, reject=True)
            negatives.append(label)
        try:
            verify_boot_order(startup.replace('esp_err_t quiet = bsp_audio_boot_quiet();',
                                             'bsp_i2c_scan(); esp_err_t quiet = bsp_audio_boot_quiet();', 1))
        except AssertionError:
            negatives.append('scan inserted before early shutdown')
        else:
            raise AssertionError('boot order negative accepted')

    files = [BSP/'src/bsp_audio.c', BSP/'include/bsp_audio.h', MAIN/'sfx.c', MAIN/'sfx.h',
             MAIN/'main.c', MAIN/'Kconfig.projbuild', ROOT/'firmware/sdkconfig.defaults']
    result = {'status':'PASS', 'host_cases':tests, 'negative_controls':negatives,
              'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
              'scope':'Real BSP/SFX compiled under mocked platform, GPIO/I2C failures and silent-off recovery. No device access or acoustic/ROM/bootloader timing measurement.'}
    output = ROOT/'reports/evidence/silent-boot-2026-09-08/verification.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
