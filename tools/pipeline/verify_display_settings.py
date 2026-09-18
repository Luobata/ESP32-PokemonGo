#!/usr/bin/env python3
"""Exercise production brightness persistence without connecting a device."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
NVS = '''#include <stdint.h>
typedef int esp_err_t;typedef int nvs_handle_t;
#define ESP_OK 0
#define NVS_READONLY 0
#define NVS_READWRITE 1
int nvs_open(const char*,int,int*);int nvs_get_u8(int,const char*,uint8_t*);
int nvs_set_u8(int,const char*,uint8_t);int nvs_commit(int);void nvs_close(int);
'''
DRIVER = r'''
#include "nvs.h"
#include "display_settings.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int disk=-1,stage,fail,writes,backlight=100;
static bool off;
int nvs_open(const char*n,int mode,int*h){assert(!strcmp(n,"pokewalk"));(void)mode;*h=1;stage=disk;return fail==1?-1:0;}
int nvs_get_u8(int h,const char*k,uint8_t*v){(void)h;assert(!strcmp(k,"brightness"));if(disk<0||fail==4)return -1;*v=disk;return 0;}
int nvs_set_u8(int h,const char*k,uint8_t v){(void)h;assert(!strcmp(k,"brightness"));writes++;if(fail==2)return -1;stage=v;return 0;}
int nvs_commit(int h){(void)h;if(fail==3)return -1;disk=stage;return 0;}
void nvs_close(int h){(void)h;}
bool screen_idle_is_off(void){return off;}
void bsp_display_backlight(uint8_t v){assert(!off);backlight=v;}
int main(void){
 display_settings_init();assert(display_settings_brightness()==100);
 assert(display_settings_set_brightness(100)&&writes==0);
 for(fail=1;fail<=3;fail++){
  assert(!display_settings_set_brightness(40));
  assert(display_settings_brightness()==100&&disk==-1&&backlight==100);
 }
 fail=0;assert(display_settings_set_brightness(40));assert(backlight==40);
 display_settings_init();assert(display_settings_brightness()==40);
 assert(!display_settings_set_brightness(0)&&!display_settings_set_brightness(9)&&!display_settings_set_brightness(101));
 assert(display_settings_brightness()==40&&backlight==40);
 assert(display_settings_set_brightness(10)&&backlight==10);
 off=true;backlight=0;assert(display_settings_set_brightness(70)&&backlight==0);
 display_settings_init();assert(display_settings_brightness()==70&&backlight==0);
 for(int value=0;value<=255;value+=255){disk=value;display_settings_init();assert(display_settings_brightness()==100);}
 disk=40;fail=4;display_settings_init();assert(display_settings_brightness()==100);
 puts("PASS: brightness bounds, defaults, restart, NVS failures, sleeping panel stays dark");
}
'''

with tempfile.TemporaryDirectory(prefix='brightness-') as tmp:
    p = Path(tmp)
    (p/'nvs.h').write_text(NVS)
    (p/'bsp_button.h').write_text('typedef int bsp_btn_t;typedef int bsp_btn_ev_t;\n')
    (p/'bsp_display.h').write_text('#include <stdint.h>\nvoid bsp_display_backlight(uint8_t);\n')
    (p/'probe.c').write_text(DRIVER)
    result = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                             '-fsanitize=address,undefined', '-I', str(p),
                             '-I', str(ROOT/'firmware/main'),
                             str(ROOT/'firmware/main/display_settings.c'), str(p/'probe.c'),
                             '-o', str(p/'probe')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    result = subprocess.run([str(p/'probe')], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    print(result.stdout.strip())
