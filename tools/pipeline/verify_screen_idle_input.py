#!/usr/bin/env python3
"""Replay production screen-idle, BSP and installed ADC/button C together.

Only platform timing/voltage/display calls and downstream page actions are
stubbed. main.on_key and nav_key are extracted unchanged from production C,
so the C-long shell shortcut and ordinary nav filter take their real paths.
This opens no device, serial port or audio output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import verify_button_input as button

ROOT = button.ROOT
MAIN = ROOT / 'firmware/main'

LVGL = r'''
#pragma once
#include "platform.h"
typedef struct lv_timer_t { void (*callback)(struct lv_timer_t *); uint32_t period; uint64_t due; } lv_timer_t;
lv_timer_t *lv_timer_create(void (*callback)(lv_timer_t *), uint32_t period, void *user);
'''

ROUTING = r'''
#include "screen_idle.h"
#include "lvgl.h"
static lv_timer_t idle_timer;
static bool busy, fail_lv_timer, stall_button_task;
static int brightness=100, redraws, backlight_changes, locks;
static unsigned fail_events;
static int dispatch_event=-1;
static int actions, action_key[32], action_event[32], exits, menus, demo_calls;
static bool off_on_a_click;
static bool s_in_game=true, s_entered=true, s_ok[1]={true};
static int s_active=-1, s_sel, s_cur;
static void *s_menu_scr, *s_mascot;

lv_timer_t *lv_timer_create(void (*callback)(lv_timer_t *), uint32_t period, void *user) {
 assert(!user && period==100);
 if(fail_lv_timer)return NULL;
 idle_timer=(lv_timer_t){callback,period,(uint64_t)now_us+period*1000};return &idle_timer;
}
void bsp_display_backlight(uint8_t pct) {
 assert(pct==0 || pct==100);brightness=pct;backlight_changes++;
}
void screen_redraw_current(void) {
 assert(brightness==0 && "wake must redraw before revealing the backlight");redraws++;
}
static bool is_busy(void) { return busy; }
static bool bsp_lvgl_lock(int ms) {
 assert(ms==500 && !locks);
 if(dispatch_event>=0 && (fail_events & (1u<<dispatch_event)))return false;
 locks++;return true;
}
static void bsp_lvgl_unlock(void) { assert(locks==1);locks--; }
static bool world_needs_starter(void) { return false; }
static bool nav_can_leave(void) { return true; }
static void nav_exit_current(void) { exits++; }
static void enter_menu(void) { menus++;s_active=-1; }
static void menu_refresh(void) {}
static void ui_pixel_mascot_jump(void *obj) { (void)obj; }
static void lv_obj_delete(void *obj) { (void)obj; }
static void demo_enter(void) { demo_calls++; }
static void demo_exit(void) { demo_calls++; }
static void page_key(bsp_btn_t key, bsp_btn_ev_t event) {
 assert(event!=BSP_BTN_RELEASE && event!=BSP_BTN_GESTURE_END && "physical housekeeping leaked to a page");
 if(event!=BSP_BTN_CLICK && event!=BSP_BTN_DOUBLE && event!=BSP_BTN_LONG)return;
 assert(actions<32);action_key[actions]=key;action_event[actions++]=event;
 if(off_on_a_click && key==BSP_BTN_UP && event==BSP_BTN_CLICK)screen_idle_request_off();
}
static const struct { void (*key)(bsp_btn_t,bsp_btn_ev_t); } PAGES[]={{page_key}};
static const struct { void (*enter)(void);void (*exit)(void);void (*key)(bsp_btn_t,bsp_btn_ev_t); }
 DEMOS[]={{demo_enter,demo_exit,page_key}};
#define DEMO_COUNT 1
'''

CASES = r'''
static void deliver_key(bsp_btn_t key, bsp_btn_ev_t event, void *user) {
 assert(user==(void *)3 && count<2048);
 events[count].key=key;events[count].event=event;events[count++].ms=(int)(now_us/1000);
 dispatch_event=event;on_key(key,event,user);dispatch_event=-1;assert(!locks);
}
static void run(int mv, int ms) {
 assert(ms>=0 && ms%5==0);voltage=mv;
 for(int i=0;i<ms;i+=5) {
  now_us+=5000;
  if(!stall_button_task)for(unsigned j=0;j<16;j++)if(timers[j].used && timers[j].active && now_us>=timers[j].due) {
   struct timer *t=&timers[j];if(t->period)t->due+=t->period;else t->active=false;t->callback(t->arg);
  }
  if(idle_timer.callback && now_us>=idle_timer.due) {
   idle_timer.due=now_us+idle_timer.period*1000;idle_timer.callback(&idle_timer);
  }
 }
}
static void idle_at(int64_t us) { now_us=us;idle_timer.callback(&idle_timer); }
static void off(void) {
 screen_idle_request_off();assert(screen_idle_is_off() && brightness==0);
 int changes=backlight_changes;screen_idle_request_off();assert(changes==backlight_changes);
}
static void action(int n,int key,int event) {
 assert(actions==n && "wake leaked an action or next independent gesture was swallowed");
 assert(action_key[n-1]==key && action_event[n-1]==event);
}
static void click(int key) {
 const int mv[]={0,300,595};run(mv[key],80);run(3300,300);
}
static void next_click(int key) { int before=actions;click(key);action(before+1,key,BSP_BTN_CLICK); }
static void wake_clean(void) {
 assert(!screen_idle_is_off() && brightness==100 && redraws==1);
 assert(!actions && !exits && !menus && "waking gesture reached a page or shell action");
}
static void print_result(const char *name) {
 printf("{\"case\":\"%s\",\"actions\":%d,\"redraws\":%d,\"exits\":%d,\"raw\":[",name,actions,redraws,exits);
 for(int i=0;i<count;i++)printf("%s[%d,%d,%d]",i?",":"",events[i].key,events[i].event,events[i].ms);
 puts("]}");
}
int main(int argc,char **argv) {
 assert(argc==2);const char *name=argv[1];
 assert(screen_idle_timeout_ms()==60000);
 if(!strcmp(name,"init-retry")) {
  screen_idle_request_off();assert(!screen_idle_is_off() && !backlight_changes);
  assert(!screen_idle_filter_key(BSP_BTN_UP,BSP_BTN_CLICK));
  fail_lv_timer=true;assert(!screen_idle_init(is_busy));
  screen_idle_request_off();assert(!screen_idle_is_off());
  fail_lv_timer=false;
 }
 assert(screen_idle_init(is_busy));assert(screen_idle_init(is_busy));
 assert(bsp_button_init(deliver_key,(void *)3)==ESP_OK);
 if(!strcmp(name,"threshold") || !strcmp(name,"init-retry")) {
  idle_at(59999999);assert(!screen_idle_is_off() && brightness==100);
  idle_at(60000000);assert(screen_idle_is_off() && brightness==0 && "60 second threshold missed");
 } else if(!strcmp(name,"activity")) {
  idle_at(29000000);screen_idle_note_activity();
  idle_at(88999999);assert(!screen_idle_is_off());
  idle_at(89000000);assert(screen_idle_is_off());
 } else if(!strcmp(name,"held")) {
  run(300,61000);assert(!screen_idle_is_off() && "held button must defer automatic screen off");
  action(1,1,BSP_BTN_LONG);run(3300,300);int64_t end=events[count-1].ms*1000LL;
  idle_at(end+59999999);assert(!screen_idle_is_off());
  idle_at(end+60000000);assert(screen_idle_is_off());
 } else if(!strcmp(name,"busy")) {
  busy=true;run(3300,70000);assert(!screen_idle_is_off() && "busy page must defer automatic screen off");
  busy=false;idle_at(129999999);assert(!screen_idle_is_off());
  idle_at(130000000);assert(screen_idle_is_off());
 } else if(!strcmp(name,"c-long-main")) {
  off();run(595,2000);run(3300,300);wake_clean();assert(s_in_game);
  next_click(1);run(595,1800);run(3300,300);
  assert(s_in_game && exits==0 && menus==0 && screen_idle_is_off() && "deliberate C-long must sleep without leaving game");
 } else if(!strcmp(name,"demo-release")) {
  s_in_game=false;s_active=0;click(1);action(1,1,BSP_BTN_CLICK);
  off();run(595,2000);run(3300,300);
  assert(s_active==0 && menus==0 && demo_calls==0 && actions==1);
 } else if(!strcmp(name,"off-action")) {
  off_on_a_click=true;click(0);action(1,0,BSP_BTN_CLICK);assert(screen_idle_is_off());
  click(0);assert(!screen_idle_is_off() && actions==1 && "wake click immediately re-entered screen off");
  next_click(1);
 } else if(!strcmp(name,"cross-key")) {
  off();run(300,80);run(0,100);run(3300,300);
  action(1,0,BSP_BTN_CLICK);assert(redraws==1 && !screen_idle_is_off());
  next_click(1);
 } else if(!strcmp(name,"semantic")) {
  for(int event=BSP_BTN_CLICK;event<=BSP_BTN_LONG;event++) {
   int before=actions;off();on_key(BSP_BTN_DOWN,(bsp_btn_ev_t)event,NULL);assert(actions==before);
   on_key(BSP_BTN_DOWN,(bsp_btn_ev_t)event,NULL);action(before+1,1,event);
  }
 } else if(!strcmp(name,"delayed-classification")) {
  off();run(300,80);run(3300,10);assert(count==2 && events[1].event==BSP_BTN_RELEASE);
  stall_button_task=true;run(3300,1000);stall_button_task=false;
  run(3300,300);wake_clean();assert(events[count-2].event==BSP_BTN_CLICK && events[count-1].event==BSP_BTN_GESTURE_END);
  next_click(1);
 } else if(!strcmp(name,"dropped-release-end")) {
  off();fail_events=(1u<<BSP_BTN_RELEASE)|(1u<<BSP_BTN_GESTURE_END);
  run(300,900);run(3300,300);wake_clean();fail_events=0;
  next_click(1);int64_t end=events[count-1].ms*1000LL;
  idle_at(end+59999999);assert(!screen_idle_is_off());
  idle_at(end+60000000);assert(screen_idle_is_off() && "dropped release left a key held");
 } else if(!strcmp(name,"dropped-end-next-press")) {
  off();fail_events=1u<<BSP_BTN_GESTURE_END;
  run(300,900);run(3300,10);wake_clean();fail_events=0;
  // The next PRESS precedes the next 100 ms LVGL tick: filter must drain cleanup too.
  next_click(1);
 } else if(!strncmp(name,"triple-gap-",11)) {
  int gap=atoi(name+11);off();
  run(300,60);run(3300,60);run(300,60);run(3300,60);run(300,60);run(3300,gap);
  int before=count;run(300,60);run(3300,300);
  // Boundary oracle is the real library's END before the last PRESS, not a guessed time window.
  bool new_group=false;
  for(int i=0;i<before;i++)if(events[i].event==BSP_BTN_GESTURE_END)new_group=true;
  // An END may arrive in the debounce scans preceding this PRESS.
  for(int i=before;i<count && events[i].event!=BSP_BTN_PRESS;i++)if(events[i].event==BSP_BTN_GESTURE_END)new_group=true;
  assert(actions==(new_group ? 1 : 0) && "ADC repeat boundary disagrees with wake guard");
  assert(!screen_idle_is_off());next_click(1);
 } else if(!strncmp(name,"wake-",5)) {
  int key=name[strlen(name)-1]-'0';assert(key>=0 && key<3);
  const int mv[]={0,300,595};int threshold=key==2 ? 1500 : 600;off();
  if(!strncmp(name,"wake-short-",11))run(mv[key],80);
  else if(!strncmp(name,"wake-double-",12)) {run(mv[key],80);run(3300,60);run(mv[key],80);}
  else if(!strncmp(name,"wake-triple-",12)) {run(mv[key],60);run(3300,60);run(mv[key],60);run(3300,60);run(mv[key],60);}
  else if(!strncmp(name,"wake-long-",10))run(mv[key],threshold+1000);
  else if(!strncmp(name,"wake-taphold-",13)) {run(mv[key],80);run(3300,60);run(mv[key],threshold+100);}
  else if(!strncmp(name,"wake-medium-",12)) {run(mv[key],80);run(3300,60);run(mv[key],300);}
  else assert(!"unknown wake case");
  run(3300,300);wake_clean();
  assert(events[count-1].event==BSP_BTN_GESTURE_END && "even unclassified tap groups must end");
  next_click(key);
 } else assert(!"unknown case");
 assert(!locks);print_result(name);return 0;
}
'''


def c_function(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index('{', start)
    depth = 1
    for index in range(opening + 1, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError(f'unclosed C function: {signature}')


def setup(directory: Path, main_route: str, nav_route: str):
    (directory / 'platform.h').write_text(button.PLATFORM)
    headers = ('esp_err.h', 'esp_log.h', 'esp_check.h', 'esp_timer.h', 'esp_attr.h',
               'esp_idf_version.h', 'driver/gpio.h', 'driver/spi_master.h', 'driver/i2c_types.h',
               'hal/adc_types.h', 'soc/soc_caps.h', 'esp_adc/adc_oneshot.h', 'esp_adc/adc_cali.h',
               'esp_adc/adc_cali_scheme.h', 'freertos/FreeRTOS.h', 'freertos/task.h', 'freertos/timers.h')
    for name in headers:
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#include "platform.h"\n')
    selected = [line.split('=', 1) for line in (ROOT / 'firmware/sdkconfig').read_text().splitlines()
                if line.startswith(('CONFIG_BUTTON_', 'CONFIG_ADC_BUTTON_')) and '=' in line]
    (directory / 'sdkconfig.h').write_text('#pragma once\n#define CONFIG_IDF_TARGET_ESP32C3 1\n' +
        ''.join(f'#define {name} {value}\n' for name, value in selected))
    (directory / 'lvgl.h').write_text(LVGL)
    (directory / 'bsp_display.h').write_text('#include <stdint.h>\nvoid bsp_display_backlight(uint8_t pct);\n')
    (directory / 'adc_driver.c').write_text('#define iot_button_new_adc_device real_iot_button_new_adc_device\n'
                                         f'#include "{button.BUTTON / "button_adc.c"}"\n')
    platform_driver = button.DRIVER.split('static void on_key(')[0]
    (directory / 'driver.c').write_text(platform_driver + ROUTING + nav_route + main_route + CASES)


def compile_probe(directory: Path, source: str) -> Path:
    (directory / 'screen_idle.c').write_text(source)
    executable = directory / 'screen-idle-probe'
    result = subprocess.run([
        'cc', '-std=c11', '-g', '-O1', '-fsanitize=address,undefined',
        '-fno-omit-frame-pointer', '-Wno-pointer-to-int-cast',
        '-DBUTTON_VER_MAJOR=4', '-DBUTTON_VER_MINOR=1', '-DBUTTON_VER_PATCH=5',
        '-I' + str(directory), '-I' + str(MAIN), '-I' + str(button.BSP / 'include'),
        '-I' + str(button.BUTTON / 'include'), '-I' + str(button.BUTTON / 'interface'),
        str(button.BSP / 'src/bsp_button.c'), str(button.BUTTON / 'iot_button.c'),
        str(directory / 'adc_driver.c'), str(directory / 'screen_idle.c'),
        str(directory / 'driver.c'), '-o', str(executable),
    ], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path,
                        default=ROOT / 'reports/evidence/screen-idle-2026-09-08/input.json')
    args = parser.parse_args()
    source = (MAIN / 'screen_idle.c').read_text()
    main_route = c_function((MAIN / 'main.c').read_text(), 'static void on_key(')
    nav_route = c_function((MAIN / 'nav.c').read_text(), 'void nav_key(')
    cases = ['threshold', 'activity', 'held', 'busy', 'init-retry', 'c-long-main',
             'demo-release', 'off-action', 'cross-key', 'semantic', 'delayed-classification',
             'dropped-release-end', 'dropped-end-next-press']
    cases += [f'wake-{gesture}-{key}' for gesture in ('short', 'double', 'triple', 'long', 'taphold', 'medium')
              for key in range(3)]
    cases += [f'triple-gap-{gap}' for gap in (170, 175, 180, 185, 190, 195, 200, 205, 300)]
    evidence = {'cases': [], 'negative_caught': [], 'source_sha256': {}}
    for path in (MAIN / 'screen_idle.c', MAIN / 'screen_idle.h', MAIN / 'main.c', MAIN / 'nav.c',
                 button.BSP / 'src/bsp_button.c', button.BSP / 'include/bsp_button.h',
                 button.BUTTON / 'iot_button.c', button.BUTTON / 'button_adc.c'):
        evidence['source_sha256'][str(path.relative_to(ROOT))] = hashlib.sha256(path.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix='screen_idle_input_') as temp:
        directory = Path(temp)
        setup(directory, main_route, nav_route)
        executable = compile_probe(directory, source)
        for case in cases:
            result = subprocess.run([executable, case], capture_output=True, text=True)
            assert result.returncode == 0, (case, result.stderr)
            evidence['cases'].append(json.loads(result.stdout))
        controls = [
            ('60 second boundary delayed', 'else if (now - s_last_activity >=', 'else if (now - s_last_activity >', 'threshold', '60 second threshold missed'),
            ('held press forgotten', 'if (s_pressed || (s_busy && s_busy()))', 'if (s_busy && s_busy())', 'held', 'held button must defer'),
            ('busy deferral removed', 'if (s_pressed || (s_busy && s_busy()))', 'if (s_pressed)', 'busy', 'busy page must defer'),
            ('wake guard cleared at release', 'if (event == BSP_BTN_RELEASE) {', 'if (event == BSP_BTN_RELEASE) { s_wake_gesture &= (uint8_t)~bit;', 'wake-short-1', 'waking gesture reached'),
            ('gesture end failed to clear guard', 's_wake_gesture &= (uint8_t)~bit;', '/* negative: leave wake group pending */', 'wake-triple-1', 'next independent gesture was swallowed'),
            ('repeat press guard bypassed', 'if (s_wake_gesture & bit) return true;', '/* negative: bypass semantic wake guard */', 'wake-taphold-1', 'waking gesture reached'),
            ('backlight shown before redraw', 'screen_redraw_current();\n    bsp_display_backlight(100);', 'bsp_display_backlight(100);\n    screen_redraw_current();', 'wake-short-1', 'wake must redraw before'),
            ('dropped end cleanup forgotten', 's_wake_gesture &= (uint8_t)~(pending >> 3);', '/* negative: lost end is never applied */', 'dropped-end-next-press', 'next independent gesture was swallowed'),
        ]
        for name, before, after, case, expected in controls:
            assert before in source, f'missing mutation anchor: {name}'
            executable = compile_probe(directory, source.replace(before, after))
            result = subprocess.run([executable, case], capture_output=True, text=True)
            assert result.returncode and expected in result.stderr, (name, result.stderr[-2000:])
            evidence['negative_caught'].append(name)
        before = 'if (button == BSP_BTN_OK && event == BSP_BTN_LONG)'
        executable = compile_probe(directory, source.replace(before, 'if (false)'))
        result = subprocess.run([executable, 'c-long-main'], capture_output=True, text=True)
        assert result.returncode and 'deliberate C-long must sleep' in result.stderr, result.stderr
        evidence['negative_caught'].append('C-long sleep removed')
    evidence['scope'] = ('Production screen_idle + BSP + installed ADC/button state machine; exact main.on_key and '
                         'nav_key functions, ideal ADC voltages, controlled 5 ms ESP and 100 ms LVGL callbacks. '
                         'Pages, backlight electrical output and task lock contention are stubbed; no hardware was used.')
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': len(evidence['cases']), 'negative_caught': evidence['negative_caught'],
                      'evidence': str(args.evidence)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
