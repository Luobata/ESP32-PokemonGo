#!/usr/bin/env python3
"""Fault-inject the production codec lifecycle, including failed resume and retry."""
import json,subprocess,tempfile
from pathlib import Path
import verify_silent_boot as base
ROOT=base.ROOT
D=base.DRIVER[:base.DRIVER.index('static void assert_blocked')]
D=D.replace('static unsigned last_level;', '''static unsigned last_level;
static int init_step, fail_step, live, fail_disable, fail_enable, fail_open, fail_read, fail_close;
static bool tx_running,rx_running;
static bool acquire(void){init_step++;if(init_step==fail_step)return false;live++;return true;}
''')
D=D.replace('assert(writes<256);memcpy(transactions[writes],data,2);writes++;', 'if(writes==256)writes=0;memcpy(transactions[writes],data,2);writes++;')
D=D.replace('(void)cfg; i2s++;*tx=(void *)3;*rx=(void *)4;return 0;', '(void)cfg;i2s++;if(!acquire())return ESP_FAIL;live++;*tx=(void *)3;*rx=(void *)4;return 0;')
D=D.replace('(void)ch;(void)cfg;i2s++;return 0;', '(void)ch;(void)cfg;i2s++;return ++init_step==fail_step?ESP_FAIL:0;')
D=D.replace('(void)ch;i2s++;return 0;', 'i2s++;if(fail_enable&&ch==(void*)4)return ESP_FAIL;if(ch==(void*)3)tx_running=true;else rx_running=true;return 0;')
D=D.replace('(void)cfg;codec++;return &dummy;', '(void)cfg;codec++;return acquire()?&dummy:NULL;')
D=D.replace('codec++;return &dummy;', 'codec++;return acquire()?&dummy:NULL;')
D=D.replace('(void)cfg;codec++;return (void *)5;', '(void)cfg;codec++;return acquire()?(void *)5:NULL;')
D=D.replace('(void)ch;return 0;}\nesp_err_t i2s_del_channel', 'if(ch==(void*)3)tx_running=false;else {if(fail_disable)return ESP_FAIL;rx_running=false;}return 0;}\nesp_err_t i2s_del_channel',1)
D=D.replace('esp_err_t i2s_del_channel(void *ch){(void)ch;return 0;}', 'esp_err_t i2s_del_channel(void *ch){(void)ch;live--;return 0;}')
for name,typ in [('codec','audio_codec_if_t'),('ctrl','audio_codec_ctrl_if_t'),('data','audio_codec_data_if_t'),('gpio','audio_codec_gpio_if_t')]:
 D=D.replace(f'void audio_codec_delete_{name}_if(const {typ} *p){{(void)p;}}',f'void audio_codec_delete_{name}_if(const {typ} *p){{assert(p);live--;}}')
D=D.replace('void esp_codec_dev_delete(void *p){(void)p;}','void esp_codec_dev_delete(void *p){assert(p);live--;}')
D=D.replace('(void)d;(void)fs;formats++;return 0;', '(void)d;(void)fs;formats++;assert(tx_running&&rx_running);return fail_open?ESP_FAIL:0;')
D=D.replace('int esp_codec_dev_close(void *d) { (void)d;return 0; }','int esp_codec_dev_close(void *d) { (void)d;if(fail_close)return ESP_FAIL;tx_running=rx_running=false;return 0; }')
D=D.replace('*(uint8_t*)out=r==0x0e?(v&0x7f):v;return 0;', '*(uint8_t*)out=r==0x0e?(v&0x7f):v;return fail_read?ESP_FAIL:0;')
# Main lives in the same translation unit to assert ownership after init rollback.
D += r'''
#include "bsp_audio.c"
int main(void){
 unsigned checks=0;
 for(int stage=1;stage<=8;stage++){
  init_step=0;fail_step=stage;
  assert(bsp_audio_init()!=ESP_OK);assert(!live&&!s_dev&&!s_ctrl&&!s_data&&!s_gpio&&!s_codec&&!s_tx&&!s_rx);checks++;
 }
 fail_step=0;init_step=0;
 assert(bsp_audio_boot_quiet()==ESP_OK);assert(bsp_audio_init()==ESP_OK);assert(live==7);
 assert(!tx_running&&!rx_running);checks++;
 int16_t pcm[4]={0};assert(bsp_audio_write(pcm,sizeof(pcm))==ESP_ERR_INVALID_STATE);checks++;
 for(int i=0;i<20;i++){
  assert(bsp_audio_set_format(i%2?16000:22050,16,1)==ESP_OK&&tx_running&&rx_running);
  assert(bsp_audio_write(pcm,sizeof(pcm))==ESP_OK);
  assert(bsp_audio_suspend()==ESP_OK&&!tx_running&&!rx_running);
  assert(bsp_audio_read(pcm,sizeof(pcm))==ESP_ERR_INVALID_STATE);checks++;
 }
 // A failed sleep remains retryable, while independent shutdown still runs.
 assert(bsp_audio_set_format(22050,16,1)==ESP_OK);fail_read=1;
 assert(bsp_audio_suspend()!=ESP_OK&&!tx_running&&!rx_running&&!s_quiet);checks++;
 fail_read=0;assert(bsp_audio_suspend()==ESP_OK&&s_quiet);checks++;
 assert(bsp_audio_set_format(22050,16,1)==ESP_OK);fail_disable=1;
 assert(bsp_audio_suspend()!=ESP_OK&&!s_quiet);fail_disable=0;
 assert(bsp_audio_suspend()==ESP_OK&&!tx_running&&!rx_running);checks++;
 fail_enable=1;assert(bsp_audio_set_format(22050,16,1)!=ESP_OK&&!tx_running&&!rx_running);
 fail_enable=0;assert(bsp_audio_set_format(22050,16,1)==ESP_OK);checks++;
 assert(bsp_audio_suspend()==ESP_OK);fail_open=1;
 assert(bsp_audio_set_format(22050,16,1)!=ESP_OK&&!tx_running&&!rx_running&&!s_opened);
 fail_open=0;assert(bsp_audio_set_format(22050,16,1)==ESP_OK);checks++;
 fail_close=1;assert(bsp_audio_suspend()!=ESP_OK&&s_close_pending);
 assert(bsp_audio_set_format(22050,16,1)!=ESP_OK&&!tx_running&&!rx_running);checks++;
 fail_close=0;assert(bsp_audio_set_format(22050,16,1)==ESP_OK&&!s_close_pending);checks++;
 assert(bsp_audio_suspend()==ESP_OK);audio_cleanup();assert(live==0);checks++;
 printf("{\"checks\":%u,\"resume_cycles\":20,\"init_failure_stages\":8,\"partial_failures_retry\":true}\n",checks);
}
'''
with tempfile.TemporaryDirectory(prefix='pw-power-audio-') as d:
 p=Path(d);(p/'platform.h').write_text(base.PLATFORM)
 for name in ['sdkconfig.h','driver/gpio.h','driver/i2c_master.h','driver/i2s_std.h','esp_log.h','esp_err.h','esp_codec_dev.h','esp_codec_dev_defaults.h','es8311_codec.h','freertos/FreeRTOS.h','freertos/task.h','freertos/queue.h']:
  f=p/name;f.parent.mkdir(parents=True,exist_ok=True);f.write_text('#include "platform.h"\n')
 pins='\n'.join(line for line in (base.BSP/'include/bsp_pins.h').read_text().splitlines() if not line.startswith('#include'))
 pins=pins.replace('I2S_NUM_0','0').replace('I2C_NUM_0','0')
 (p/'bsp_pins.h').write_text(pins)
 (p/'probe.c').write_text(D)
 r=subprocess.run(['cc','-std=c11','-Werror','-Wno-unused-function','-Wno-unused-variable','-fsanitize=address,undefined','-DCONFIG_POKEWALK_SILENT_BOOT=0','-DTEST_PA=-1','-I',str(p),'-I',str(base.BSP/'include'),'-I',str(base.BSP/'src'),'-I',str(base.MAIN),str(p/'probe.c'),str(base.BSP/'src/bsp_es8311_sleep_check.c'),'-o',str(p/'probe')],capture_output=True,text=True)
 assert r.returncode==0,r.stderr
 r=subprocess.run([str(p/'probe')],capture_output=True,text=True);assert r.returncode==0,r.stderr
 print(json.dumps(json.loads(r.stdout),indent=2))
