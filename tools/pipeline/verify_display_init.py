#!/usr/bin/env python3
"""Inject failures at every initialization step of the actual display BSP."""
import json,re,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
STUB=r'''
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <assert.h>
typedef int esp_err_t;typedef void *esp_lcd_panel_handle_t;typedef void *esp_lcd_panel_io_handle_t;typedef void *esp_lcd_spi_bus_handle_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_INVALID_STATE -2
#define ESP_LOGE(...) ((void)0)
#define ESP_LOGI(...) ((void)0)
#define ESP_LOGW(...) ((void)0)
#define SPI_DMA_CH_AUTO 0
#define LCD_RGB_ELEMENT_ORDER_RGB 0
#define LEDC_AUTO_CLK 0
#define pdMS_TO_TICKS(n) (n)
#define BSP_LCD_SPI_HOST 2
#define BSP_LCD_MOSI 9
#define BSP_LCD_SCLK 8
#define BSP_LCD_CS 1
#define BSP_LCD_DC 20
#define BSP_LCD_RST -1
#define BSP_LCD_BL 21
#define BSP_LCD_W 240
#define BSP_LCD_H 320
#define BSP_LCD_PCLK_HZ 40000000
#define BSP_LCD_SPI_MODE 0
#define BSP_LCD_INVERT_COLOR 1
#define BSP_BL_LEDC_MODE 0
#define BSP_BL_LEDC_TIMER 0
#define BSP_BL_LEDC_RES 10
#define BSP_BL_LEDC_FREQ_HZ 5000
#define BSP_BL_LEDC_CHANNEL 0
typedef struct {int mosi_io_num,sclk_io_num,miso_io_num,quadwp_io_num,quadhd_io_num,max_transfer_sz;} spi_bus_config_t;
typedef struct {int cs_gpio_num,dc_gpio_num,pclk_hz,spi_mode,lcd_cmd_bits,lcd_param_bits,trans_queue_depth;} esp_lcd_panel_io_spi_config_t;
typedef struct {int reset_gpio_num,rgb_ele_order,bits_per_pixel;} esp_lcd_panel_dev_config_t;
typedef struct {int speed_mode,timer_num,duty_resolution,freq_hz,clk_cfg;} ledc_timer_config_t;
typedef struct {int gpio_num,speed_mode,channel,timer_sel,duty,hpoint;} ledc_channel_config_t;
static unsigned step,fail,live_bus,live_io,live_panel;static bool fail_delete;
static int next(void){return ++step==fail?-1:0;}
static int spi_bus_initialize(int h,const spi_bus_config_t*c,int dma){assert(!live_bus);int e=next();if(!e)live_bus++;return e;}
static int esp_lcd_new_panel_io_spi(void*b,const esp_lcd_panel_io_spi_config_t*c,void**out){assert(live_bus&&!live_io);int e=next();if(!e){live_io++;*out=(void*)2;}return e;}
static int esp_lcd_new_panel_st7789(void*io,const esp_lcd_panel_dev_config_t*c,void**out){assert(live_io&&!live_panel);int e=next();if(!e){live_panel++;*out=(void*)3;}return e;}
static int esp_lcd_panel_reset(void*p){return next();}
static int esp_lcd_panel_init(void*p){return next();}
static int esp_lcd_panel_io_tx_param(void*p,int c,const void*d,size_t n){return next();}
static int esp_lcd_panel_invert_color(void*p,bool v){return next();}
static int esp_lcd_panel_mirror(void*p,bool x,bool y){return next();}
static int esp_lcd_panel_set_gap(void*p,int x,int y){return next();}
static int esp_lcd_panel_disp_on_off(void*p,bool on){return next();}
static int esp_lcd_panel_disp_sleep(void*p,bool on){return 0;}
static int esp_lcd_panel_del(void*p){if(fail_delete)return -1;assert(live_panel);live_panel--;return 0;}
static int esp_lcd_panel_io_del(void*p){assert(!live_panel&&live_io);live_io--;return 0;}
static int spi_bus_free(int h){assert(!live_io&&live_bus);live_bus--;return 0;}
static int ledc_timer_config(const ledc_timer_config_t*c){return next();}
static int ledc_channel_config(const ledc_channel_config_t*c){return next();}
static int ledc_timer_rst(int a,int b){return 0;}
static int ledc_stop(int a,int b,int c){return 0;}
static int ledc_set_duty(int a,int b,unsigned c){return 0;}
static int ledc_update_duty(int a,int b){return 0;}
static unsigned ledc_get_duty(int a,int b){return 0;}
static void vTaskDelay(unsigned n){}
'''
CASES=r'''
int main(void){
 assert(bsp_display_init()==ESP_OK&&s_ready);unsigned total=step;assert(total>20);display_cleanup();
 for(unsigned i=1;i<=total;i++){
  fail=i;step=0;assert(bsp_display_init()!=ESP_OK&&!s_ready&&!s_panel&&!s_io&&!s_bus_ready&&!s_bl_ready);
  assert(!live_bus&&!live_io&&!live_panel);
  fail=step=0;assert(bsp_display_init()==ESP_OK&&s_ready);display_cleanup();
 }
 fail=4;step=0;fail_delete=true;assert(bsp_display_init()!=ESP_OK);assert(live_panel&&live_io&&live_bus);
 fail=step=0;assert(bsp_display_init()!=ESP_OK);fail_delete=false;assert(bsp_display_init()==ESP_OK&&s_ready);display_cleanup();
 printf("{\"failure_stages\":%u,\"retry_after_each_failure\":true,\"failed_cleanup_retains_ownership\":true}\n",total);
}
'''
with tempfile.TemporaryDirectory(prefix='pw-display-init-') as d:
 p=Path(d);source=(ROOT/'firmware/components/bsp/src/bsp_display.c').read_text();source=re.sub(r'^#include.*\n','',source,flags=re.M)
 (p/'probe.c').write_text(STUB+source+CASES)
 r=subprocess.run(['cc','-std=c11','-fsanitize=address,undefined',str(p/'probe.c'),'-o',str(p/'probe')],capture_output=True,text=True);assert not r.returncode,r.stderr
 r=subprocess.run([str(p/'probe')],capture_output=True,text=True);assert not r.returncode,r.stderr;print(json.dumps(json.loads(r.stdout),indent=2))
