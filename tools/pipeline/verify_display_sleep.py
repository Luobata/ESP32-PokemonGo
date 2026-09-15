#!/usr/bin/env python3
"""Exercise unchanged production BSP power functions with a LEDC/panel boundary."""
import json,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
SOURCE=ROOT/'firmware/components/bsp/src/bsp_display.c'
STUB=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_ERR_INVALID_STATE -1
#define BSP_BL_LEDC_RES 10
#define BSP_BL_LEDC_MODE 0
#define BSP_BL_LEDC_CHANNEL 0
#define ESP_LOGE(...) ((void)0)
#define pdMS_TO_TICKS(n) (n)
static bool s_bl_ready=true,enabled=true;static void *s_panel=(void*)1;
static unsigned duty,stops,idle_level=1;
static int events[16],count,fail_event;
static int record(int e){events[count++]=e;return fail_event==e?-2:0;}
static int ledc_set_duty(int m,int c,unsigned d){duty=d;return 0;}
static int ledc_update_duty(int m,int c){enabled=true;return 0;}
static int ledc_stop(int m,int c,unsigned idle){enabled=false;idle_level=idle;stops++;return 0;}
static unsigned ledc_get_duty(int m,int c){return duty;}
static int esp_lcd_panel_disp_on_off(void*p,bool on){assert(p);return record(on?4:1);}
static int esp_lcd_panel_disp_sleep(void*p,bool sleep){assert(p);return record(sleep?2:3);}
static void vTaskDelay(unsigned ticks){assert(ticks==20);record(5);}
'''
CASES=r'''
int main(void){
 bsp_display_backlight(100);assert(enabled&&duty==1023&&bsp_display_get_backlight()==100);
 bsp_display_backlight(0);assert(!enabled&&!idle_level&&!duty&&stops==1&&bsp_display_get_backlight()==0);
 bsp_display_backlight(50);assert(enabled&&duty==511);bsp_display_backlight(255);assert(duty==1023);
 bsp_display_backlight(0);assert(bsp_display_sleep(true)==0&&count==2&&events[0]==1&&events[1]==2);
 count=0;assert(bsp_display_sleep(false)==0&&count==3&&events[0]==3&&events[1]==5&&events[2]==4&&!enabled);
 count=0;fail_event=1;assert(bsp_display_sleep(true)==-2&&count==1);
 count=0;fail_event=3;assert(bsp_display_sleep(false)==-2&&count==1);
 count=0;fail_event=2;assert(bsp_display_sleep(true)==-2&&count==2);
 count=0;s_panel=NULL;assert(bsp_display_sleep(true)==ESP_ERR_INVALID_STATE&&!count);
 puts("{\"checks\":9,\"pwm_stopped_low\":true,\"pwm_wake_reenabled\":true,\"panel_off_sleep_order\":true,\"panel_wake_delay_order\":true,\"error_propagation\":true,\"physical_light_measured\":false}");
}
'''
with tempfile.TemporaryDirectory(prefix='display-sleep-') as temp:
 p=Path(temp);s=SOURCE.read_text();s=s[s.index('void bsp_display_backlight('):]
 (p/'probe.c').write_text(STUB+s+CASES)
 subprocess.run(['cc','-std=c11','-Wall','-Werror','-fsanitize=address,undefined',str(p/'probe.c'),'-o',str(p/'probe')],check=True)
 r=subprocess.run([str(p/'probe')],capture_output=True,text=True);assert r.returncode==0,r.stderr
 print(json.dumps(json.loads(r.stdout),indent=2))
