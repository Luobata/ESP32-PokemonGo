#!/usr/bin/env python3
"""Real vendored LVGL + production screen.c: reproduce late green flush, prevent it.
SPI is the only mocked display boundary. Gameplay timers must keep ticking.
"""
from pathlib import Path
import subprocess,shutil,json
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'.build/display-ownership';OUT.mkdir(parents=True,exist_ok=True)
inc=OUT/'include';inc.mkdir(exist_ok=True)
for p in (ROOT/'tools/inspector/host/include').glob('*.h'):
 if p.name!='lvgl.h':shutil.copyfile(p,inc/p.name)
shutil.copyfile(ROOT/'firmware/components/bsp/include/bsp_button.h',inc/'bsp_button.h')
(inc/'lv_conf.h').write_text('''#define LV_CONF_H
#define LV_COLOR_DEPTH 16
#define LV_USE_OS 0
#define LV_USE_STDLIB_MALLOC LV_STDLIB_CLIB
#define LV_USE_STDLIB_STRING LV_STDLIB_CLIB
#define LV_USE_STDLIB_SPRINTF LV_STDLIB_CLIB
#define LV_USE_LOG 0
#define LV_USE_THORVG_INTERNAL 0
''')
(OUT/'probe.c').write_text(r'''
#include "lvgl.h"
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include "screen.c"
static unsigned flushes,ticks,green_pixels;
static uint16_t buffer[240*20];
static void flush(lv_display_t *d,const lv_area_t *a,uint8_t *p){
 flushes++;unsigned n=(a->x2-a->x1+1)*(a->y2-a->y1+1);
 for(unsigned i=0;i<n;i++)if(((uint16_t *)p)[i]!=0xffff)green_pixels++;
 lv_display_flush_ready(d);
}
static void gameplay(lv_timer_t *t){(void)t;ticks++;}
static void advance(void){for(unsigned i=0;i<30;i++){lv_tick_inc(35);lv_timer_handler();}}
int main(void){
 lv_init();lv_display_t *d=lv_display_create(240,320);
 lv_display_set_color_format(d,LV_COLOR_FORMAT_RGB565);
 lv_display_set_buffers(d,buffer,NULL,sizeof(buffer),LV_DISPLAY_RENDER_MODE_PARTIAL);
 lv_display_set_flush_cb(d,flush);
 // Original implementation: loading an empty green screen is not ownership.
 lv_obj_t *old=lv_obj_create(NULL);lv_obj_set_style_bg_color(old,lv_color_hex(0x9bbc0f),0);lv_screen_load(old);
 flushes=green_pixels=0;advance();assert(flushes>=16&&green_pixels>0);
 unsigned before=flushes;
 // Production fix, exactly where startup claims the screen before nav_start.
 screen_own_display();flushes=0;lv_timer_create(gameplay,35,NULL);
 advance();assert(flushes==0&&ticks>=20);
 // A later accidental invalidation must not restart LVGL panel output.
 lv_obj_invalidate(lv_screen_active());advance();assert(flushes==0&&ticks>=40);
 printf("{\"original_late_flushes\":%u,\"fixed_late_flushes\":%u,\"gameplay_timer_ticks\":%u,\"real_lvgl\":true}\n",before,flushes,ticks);
 return 0;
}
''')
# A negative control removes the two ownership operations from the actual source.
negative=(ROOT/'firmware/main/screen.c').read_text().replace('lv_display_enable_invalidation(display, false);','').replace('if (refresh) lv_timer_pause(refresh);','')
(OUT/'screen_negative.c').write_text(negative)
(OUT/'probe_negative.c').write_text((OUT/'probe.c').read_text().replace('#include "screen.c"','#include "screen_negative.c"').replace('assert(flushes==0&&ticks>=20);','if(flushes>0)return 42;assert(ticks>=20);'))
(OUT/'CMakeLists.txt').write_text(f'''cmake_minimum_required(VERSION 3.20)
project(display_ownership C CXX ASM)
set(CONFIG_LV_BUILD_DEMOS OFF CACHE BOOL "" FORCE)
set(CONFIG_LV_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
set(CONFIG_LV_USE_THORVG_INTERNAL OFF CACHE BOOL "" FORCE)
set(LV_BUILD_CONF_PATH "{inc/'lv_conf.h'}" CACHE PATH "" FORCE)
add_subdirectory("{ROOT/'firmware/managed_components/lvgl__lvgl'}" lvgl)
add_executable(probe probe.c)
target_include_directories(probe PRIVATE "{inc}" "{ROOT/'firmware/main'}")
target_compile_options(probe PRIVATE -ffunction-sections -fdata-sections)
target_link_options(probe PRIVATE -Wl,-dead_strip)
target_link_libraries(probe PRIVATE lvgl)
add_executable(probe_negative probe_negative.c)
target_include_directories(probe_negative PRIVATE "{inc}" "{ROOT/'firmware/main'}")
target_compile_options(probe_negative PRIVATE -ffunction-sections -fdata-sections)
target_link_options(probe_negative PRIVATE -Wl,-dead_strip)
target_link_libraries(probe_negative PRIVATE lvgl)
''')
for cmd in [['cmake','-S',str(OUT),'-B',str(OUT/'build')],['cmake','--build',str(OUT/'build'),'-j','8']]:
 r=subprocess.run(cmd,capture_output=True,text=True)
 if r.returncode:raise RuntimeError(r.stdout[-2000:]+r.stderr[-4000:])
r=subprocess.run([str(OUT/'build/probe')],capture_output=True,text=True);assert r.returncode==0,r.stdout+r.stderr
negative=subprocess.run([str(OUT/'build/probe_negative')],capture_output=True,text=True)
assert negative.returncode==42,negative.stdout+negative.stderr
result=json.loads(r.stdout);result['negative_control_detected']=True;print(json.dumps(result))
