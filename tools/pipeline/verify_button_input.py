#!/usr/bin/env python3
"""Run the real BSP + installed ADC/button state machines with simulated voltages.

Only ESP platform calls are stubbed. No serial port, device or audio is opened.
The resulting B events are also replayed through actual native nav/P10 code.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BSP = ROOT / 'firmware/components/bsp'
BUTTON = ROOT / 'firmware/managed_components/espressif__button'

PLATFORM = r'''
#pragma once
#include "sdkconfig.h"
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <stdlib.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_INVALID_ARG 0x102
#define ESP_ERR_INVALID_STATE 0x103
#define ESP_ERR_NOT_FOUND 0x105
#define ESP_ERR_NOT_SUPPORTED 0x106
const char *esp_err_to_name(esp_err_t error);
void test_log(const char *tag, const char *format, ...);
#define ESP_LOGI(...) test_log(__VA_ARGS__)
#define ESP_LOGD(...) test_log(__VA_ARGS__)
#define ESP_LOGW(...) test_log(__VA_ARGS__)
#define ESP_LOGE(...) test_log(__VA_ARGS__)
#define ESP_RETURN_ON_FALSE(a,e,...) do { if (!(a)) return (e); } while(0)
#define ESP_GOTO_ON_FALSE(a,e,label,...) do { if (!(a)) { ret=(e); goto label; } } while(0)
#define __containerof(p,t,f) ((t *)((char *)(p)-offsetof(t,f)))
#define IRAM_ATTR
typedef int portMUX_TYPE;
#define portMUX_INITIALIZER_UNLOCKED 0
#define portENTER_CRITICAL(p) ((void)(p))
#define portEXIT_CRITICAL(p) ((void)(p))
#define portENTER_CRITICAL_ISR(p) ((void)(p))
#define portEXIT_CRITICAL_ISR(p) ((void)(p))
typedef void *esp_timer_handle_t;
typedef struct { void (*callback)(void *); void *arg; int dispatch_method; const char *name; } esp_timer_create_args_t;
#define ESP_TIMER_TASK 0
esp_err_t esp_timer_create(const esp_timer_create_args_t *args, esp_timer_handle_t *out);
esp_err_t esp_timer_start_periodic(esp_timer_handle_t timer, uint64_t us);
esp_err_t esp_timer_start_once(esp_timer_handle_t timer, uint64_t us);
esp_err_t esp_timer_stop(esp_timer_handle_t timer);
esp_err_t esp_timer_delete(esp_timer_handle_t timer);
int64_t esp_timer_get_time(void);
void gpio_intr_disable(int pin);
typedef int adc_unit_t;
typedef int adc_atten_t;
typedef void *adc_oneshot_unit_handle_t;
typedef void *adc_cali_handle_t;
typedef struct { int unit_id; } adc_oneshot_unit_init_cfg_t;
typedef struct { int atten, bitwidth; } adc_oneshot_chan_cfg_t;
typedef struct { int unit_id, chan, atten, bitwidth; } adc_cali_curve_fitting_config_t;
#define ADC_UNIT_1 0
#define ADC_CHANNEL_0 0
#define ADC_ATTEN_DB_0 0
#define ADC_ATTEN_DB_6 2
#define ADC_ATTEN_DB_12 3
#define ADC_BITWIDTH_DEFAULT 0
#define ADC_CALI_SCHEME_CURVE_FITTING_SUPPORTED 1
#define ADC_CALI_SCHEME_LINE_FITTING_SUPPORTED 0
#define SOC_ADC_ATTEN_NUM 4
#define SOC_ADC_DIGI_MAX_BITWIDTH 12
#define SOC_ADC_CHANNEL_NUM(unit) 5
#define SOC_ADC_PERIPH_NUM 2
esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *cfg, void **out);
esp_err_t adc_oneshot_del_unit(void *adc);
esp_err_t adc_oneshot_config_channel(void *adc, int channel, const adc_oneshot_chan_cfg_t *cfg);
esp_err_t adc_oneshot_read(void *adc, int channel, int *raw);
esp_err_t adc_cali_create_scheme_curve_fitting(const adc_cali_curve_fitting_config_t *cfg, void **out);
esp_err_t adc_cali_delete_scheme_curve_fitting(void *cali);
esp_err_t adc_cali_raw_to_voltage(void *cali, int raw, int *mv);
'''

DRIVER = r'''
#include "platform.h"
#include "bsp_button.h"
#include "button_adc.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
_Static_assert(BSP_BTN_PRESS==0 && BSP_BTN_CLICK==1 && BSP_BTN_DOUBLE==2 &&
               BSP_BTN_LONG==3 && BSP_BTN_RELEASE==4 && BSP_BTN_GESTURE_END==5,
               "button event wire values changed");
static int voltage=3300, adc_units, adc_channels, adc_deleted, mode, devices, hold_created;
static int64_t now_us;
static struct timer { void (*callback)(void *); void *arg; bool used, active; uint64_t due, period; } timers[16];
static struct { int key, event, ms; } events[2048];
static int count;
static void run(int mv, int ms);
void test_log(const char *tag, const char *format, ...) { (void)tag; (void)format; }
const char *esp_err_to_name(esp_err_t error) { (void)error; return "test"; }
esp_err_t esp_timer_create(const esp_timer_create_args_t *args, void **out) {
 if(!strcmp(args->name,"bsp_btn_hold") && ++hold_created==2 && (mode==1 || mode==2 || mode==6)) {
  *out=NULL; return mode==2 ? ESP_OK : ESP_ERR_NO_MEM;
 }
 for(unsigned i=0;i<16;i++)if(!timers[i].used) {
  timers[i]=(struct timer){.callback=args->callback,.arg=args->arg,.used=true};*out=&timers[i];return 0;
 }
 return ESP_ERR_NO_MEM;
}
esp_err_t esp_timer_start_periodic(void *timer, uint64_t us) {
 assert(timer && us==5000);struct timer *t=timer;assert(t->used);t->active=true;t->due=now_us+us;t->period=us;return 0;
}
esp_err_t esp_timer_start_once(void *timer, uint64_t us) {
 assert(timer);struct timer *t=timer;assert(t->used && !t->active && (us==600000 || us==1500000));
 if(mode==5)return ESP_FAIL;
 t->active=true;t->due=now_us+us;t->period=0;return 0;
}
esp_err_t esp_timer_stop(void *timer) { assert(timer);struct timer *t=timer;assert(t->used);t->active=false;return 0; }
esp_err_t esp_timer_delete(void *timer) {
 assert(timer);struct timer *t=timer;assert(t->used && !t->active);
 // Exercise an ADC callback interleaving with failed initialization cleanup.
 if(mode==6 && !t->period) { run(0,20);assert(!t->active && "partial init armed a hold timer"); }
 t->used=false;
 if(mode==6 && !t->period) run(3300,20);
 return 0;
}
int64_t esp_timer_get_time(void) { return now_us; }
void gpio_intr_disable(int pin) { (void)pin; }
esp_err_t adc_oneshot_new_unit(const adc_oneshot_unit_init_cfg_t *cfg, void **out) {
 assert(cfg->unit_id==0); adc_units++; *out=(void *)1; return 0;
}
esp_err_t adc_oneshot_del_unit(void *adc) { assert(adc);adc_deleted++;return 0; }
esp_err_t adc_oneshot_config_channel(void *adc, int channel, const adc_oneshot_chan_cfg_t *cfg) {
 assert(adc && channel==0 && cfg->atten==3); adc_channels++; return 0;
}
esp_err_t adc_oneshot_read(void *adc, int channel, int *raw) { assert(adc && channel==0); *raw=voltage; return 0; }
esp_err_t adc_cali_create_scheme_curve_fitting(const adc_cali_curve_fitting_config_t *cfg, void **out) {
 assert(cfg->unit_id==0 && cfg->atten==3); *out=(void *)2; return 0;
}
esp_err_t adc_cali_delete_scheme_curve_fitting(void *cali) { (void)cali; return 0; }
esp_err_t adc_cali_raw_to_voltage(void *cali, int raw, int *mv) { assert(cali); *mv=raw; return 0; }
esp_err_t real_iot_button_new_adc_device(const button_config_t *,const button_adc_config_t *,button_handle_t *);
esp_err_t iot_button_new_adc_device(const button_config_t *button,const button_adc_config_t *adc,button_handle_t *out) {
 if(++devices==2 && (mode==3 || mode==4)) { *out=NULL;return mode==3 ? ESP_FAIL : ESP_OK; }
 return real_iot_button_new_adc_device(button,adc,out);
}
static void on_key(bsp_btn_t key, bsp_btn_ev_t event, void *user) {
 assert(user==(void *)3 && count<2048);
 events[count].key=key; events[count].event=event; events[count++].ms=(int)(now_us/1000);
}
static void run(int mv, int ms) {
 voltage=mv;
 for(int i=0;i<ms;i+=5) {
  now_us+=5000;
  for(unsigned j=0;j<16;j++)if(timers[j].used && timers[j].active && now_us>=timers[j].due) {
   struct timer *t=&timers[j];if(t->period)t->due+=t->period;else t->active=false;t->callback(t->arg);
  }
 }
}
static void expect(int begin, int key, const int *sequence, int n) {
 assert(count-begin==n && "unexpected extra/missing button event");
 for(int i=0;i<n;i++) assert(events[begin+i].key==key && events[begin+i].event==sequence[i]);
}
int main(int argc, char **argv) {
 if(argc>1 && !strncmp(argv[1],"fail",4)) {
  mode=atoi(argv[1]+4);
  assert(bsp_button_init(NULL,NULL)==ESP_ERR_INVALID_ARG && !adc_units);
  assert(bsp_button_init(on_key,(void *)3)!=ESP_OK && adc_deleted==1);
  for(unsigned i=0;i<16;i++)assert(!timers[i].used && "partial init left a live timer");
  run(300,1000);assert(count==0 && bsp_button_read_mv()==-1);
  mode=0;adc_units=adc_channels=devices=hold_created=0;
 }
 assert(bsp_button_init(on_key,(void *)3)==0);
 assert(bsp_button_init(on_key,(void *)3)==ESP_ERR_INVALID_STATE);
 assert(adc_units==1 && adc_channels==1 && "BSP and ADC keys must share ADC1");
 run(3300,300); assert(count==0 && bsp_button_read_mv()==3300);
 if(argc>1 && !strcmp(argv[1],"observe")) {
  bsp_button_observe_only(true);
  run(300,700);bsp_button_observe_only(false);run(3300,500);
  const int cleanup[]={BSP_BTN_RELEASE,BSP_BTN_GESTURE_END};expect(0,1,cleanup,2);
  int begin=count;run(300,100);run(3300,300);
  const int click[]={BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_CLICK,BSP_BTN_GESTURE_END};expect(begin,1,click,4);
  begin=count;run(595,100);bsp_button_observe_only(true);run(3300,300);bsp_button_observe_only(false);
  const int started[]={BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_GESTURE_END};expect(begin,2,started,3);
  puts("{\"observation_suppresses_actions\":true,\"gesture_finishes_after_probe\":true}");return 0;
 }
 if(argc>1 && !strcmp(argv[1],"hold")) {
  run(300,3000); run(3300,500);
  printf("{\"events\":[");
  for(int i=0;i<count;i++) printf("%s[%d,%d,%d]",i?",":"",events[i].key,events[i].event,events[i].ms);
  puts("]}"); return 0;
 }
 if(argc>1 && !strcmp(argv[1],"start-fail")) {
  mode=5;run(300,1000);run(3300,300);
  const int failed[]={BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_GESTURE_END};expect(0,1,failed,3);
  mode=0;run(300,700);run(3300,300);assert(count==7 && events[4].event==BSP_BTN_LONG && events[5].event==BSP_BTN_RELEASE && events[6].event==BSP_BTN_GESTURE_END);
  puts("{\"timer_start_failure_recovers\":true}");return 0;
 }
 const int mv[]={0,300,595}, click[]={BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_CLICK,BSP_BTN_GESTURE_END};
 const int twice[]={BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_DOUBLE,BSP_BTN_GESTURE_END};
 const int hold[]={BSP_BTN_PRESS,BSP_BTN_LONG,BSP_BTN_RELEASE,BSP_BTN_GESTURE_END};
 for(int key=0;key<3;key++) {
  int begin=count; run(mv[key],100); assert(count==begin+1 && "held button emitted early release");
  run(3300,10); expect(begin,key,click,2); // Release is immediate after two ADC scans.
  run(3300,240); expect(begin,key,click,4); // Click then END waits for the repeat window.
  assert(events[begin+1].ms<events[begin+2].ms);
  begin=count; run(mv[key],80); run(3300,60); run(mv[key],80); run(3300,250); expect(begin,key,twice,6);
  int threshold=key==BSP_BTN_OK ? BSP_BTN_EXIT_PRESS_MS : BSP_BTN_LONG_PRESS_MS;
  begin=count; run(mv[key],threshold-20); assert(count==begin+1 && "hold fired too early");
  run(mv[key],120); assert(count>=begin+2 && "long press must be available by 700 ms");
  run(mv[key],2000); run(3300,500); expect(begin,key,hold,4);
  int delay=events[begin+1].ms-events[begin].ms;
  assert(delay>=threshold && delay<=threshold+30);
  begin=count; run(mv[key],100); run(3300,250); expect(begin,key,click,4);
  // Bounce shorter than the actual two-scan debounce must not become a key.
  begin=count; run(mv[key],5); run(3300,250); assert(count==begin);
  // A released click followed immediately by a hold lands in the library's
  // repeat branch, where it never emits START/HOLD. BSP must still time it.
  begin=count; run(mv[key],80);run(3300,60);run(mv[key],threshold+100);run(3300,300);
  const int tap_hold[]={BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_PRESS,BSP_BTN_LONG,BSP_BTN_RELEASE,BSP_BTN_GESTURE_END};expect(begin,key,tap_hold,6);
  // Three taps have no CLICK/DOUBLE classification, but must still end the group.
  begin=count;run(mv[key],60);run(3300,60);run(mv[key],60);run(3300,60);run(mv[key],60);run(3300,300);
  const int triple[]={BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_PRESS,BSP_BTN_RELEASE,BSP_BTN_GESTURE_END};
  expect(begin,key,triple,7);
  // Release just before the timer (after 10 ms ADC debounce) must click once.
  begin=count;run(mv[key],threshold);run(3300,300);expect(begin,key,click,4);
  begin=count;run(mv[key],threshold+15);run(3300,300);expect(begin,key,hold,4);
 }
 // Switch from B to A before B's timer fires: never deliver a stale B LONG.
 int begin=count;run(300,600);run(0,700);run(3300,300);
 assert(count==begin+8 && events[begin].key==1 && events[begin].event==BSP_BTN_PRESS);
 assert(events[begin+1].key==1 && events[begin+1].event==BSP_BTN_RELEASE);
 assert(events[begin+2].key==0 && events[begin+2].event==BSP_BTN_PRESS);
 assert(events[begin+3].key==1 && events[begin+3].event==BSP_BTN_CLICK);
 assert(events[begin+4].key==1 && events[begin+4].event==BSP_BTN_GESTURE_END);
 assert(events[begin+5].key==0 && events[begin+5].event==BSP_BTN_LONG);
 assert(events[begin+6].key==0 && events[begin+6].event==BSP_BTN_RELEASE);
 assert(events[begin+7].key==0 && events[begin+7].event==BSP_BTN_GESTURE_END);
 puts("{\"keys\":3,\"clicks\":9,\"double_clicks\":3,\"triple_click_ends\":3,\"long_holds\":6,\"tap_then_hold\":3,\"threshold_edges\":6,\"switch_key\":1,\"press_release_order\":3,\"release_clicks_after_hold\":0,\"bounce_rejected\":3}");
}
'''


def compile_probe(directory: Path, text: str):
    source = directory / 'bsp_button.c'
    source.write_text(text)
    executable = directory / 'button-probe'
    compiled = subprocess.run([
        'cc', '-std=c11', '-g', '-O1', '-fsanitize=address,undefined',
        '-fno-omit-frame-pointer', '-Wno-pointer-to-int-cast',
        '-DBUTTON_VER_MAJOR=4', '-DBUTTON_VER_MINOR=1', '-DBUTTON_VER_PATCH=5',
        '-I' + str(directory), '-I' + str(BSP / 'include'),
        '-I' + str(BUTTON / 'include'), '-I' + str(BUTTON / 'interface'),
        str(source), str(BUTTON / 'iot_button.c'), str(directory / 'adc_driver.c'),
        str(directory / 'driver.c'), '-o', str(executable),
    ], capture_output=True, text=True)
    assert compiled.returncode == 0, compiled.stderr
    return executable


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--native', action='store_true', help='also replay voltage-produced events through native P10')
    parser.add_argument('--evidence', type=Path)
    args = parser.parse_args()
    original = (BSP / 'src/bsp_button.c').read_text()
    with tempfile.TemporaryDirectory(prefix='button_input_') as temp:
        directory = Path(temp)
        (directory / 'platform.h').write_text(PLATFORM)
        headers = ('esp_err.h', 'esp_log.h', 'esp_check.h', 'esp_timer.h', 'esp_attr.h',
                   'esp_idf_version.h', 'driver/gpio.h', 'driver/spi_master.h', 'driver/i2c_types.h',
                   'hal/adc_types.h', 'soc/soc_caps.h', 'esp_adc/adc_oneshot.h', 'esp_adc/adc_cali.h',
                   'esp_adc/adc_cali_scheme.h', 'freertos/FreeRTOS.h', 'freertos/task.h', 'freertos/timers.h')
        for name in headers:
            path = directory / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "platform.h"\n')
        # Read installed sdkconfig, rather than assuming the ADC scan settings.
        config = (ROOT / 'firmware/sdkconfig').read_text().splitlines()
        selected = [line.split('=', 1) for line in config
                    if line.startswith(('CONFIG_BUTTON_', 'CONFIG_ADC_BUTTON_')) and '=' in line]
        (directory / 'sdkconfig.h').write_text('#pragma once\n#define CONFIG_IDF_TARGET_ESP32C3 1\n' +
            ''.join(f'#define {name} {value}\n' for name, value in selected))
        (directory / 'driver.c').write_text(DRIVER)
        (directory / 'adc_driver.c').write_text('#define iot_button_new_adc_device real_iot_button_new_adc_device\n'
                                             f'#include "{BUTTON / "button_adc.c"}"\n')
        executable = compile_probe(directory, original)
        result = subprocess.run([executable], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        evidence = {'bsp_sha256': hashlib.sha256(original.encode()).hexdigest(),
                    'managed_sha256': {name: hashlib.sha256((BUTTON / name).read_bytes()).hexdigest()
                                       for name in ('iot_button.c', 'button_adc.c')},
                    'bsp_adc_and_state_machine': json.loads(result.stdout)}
        hold = json.loads(subprocess.check_output([executable, 'hold'], text=True))['events']
        assert [event[:2] for event in hold] == [[1, 0], [1, 3], [1, 4], [1, 5]]
        evidence['three_second_B_hold_events'] = hold
        evidence['observation'] = json.loads(subprocess.check_output([executable, 'observe'], text=True))
        evidence['failure_recovery'] = []
        for mode, label in (
            ('fail1', 'timer creation error: clean partial init and retry'),
            ('fail2', 'timer creation returned NULL: clean partial init and retry'),
            ('fail3', 'button creation error: clean partial init and retry'),
            ('fail4', 'button creation returned NULL: clean partial init and retry'),
            ('fail6', 'ADC callbacks during partial cleanup cannot use deleted hold timers'),
            ('start-fail', 'timer start error: no fabricated action; next press recovers'),
        ):
            result = subprocess.run([executable,mode], capture_output=True, text=True)
            assert result.returncode == 0, (mode,result.stderr)
            evidence['failure_recovery'].append(label)
        controls = [
            ('original START callback overrun', 'const button_event_t events[] = { BUTTON_PRESS_DOWN, BUTTON_PRESS_UP,',
             'const button_event_t events[] = { BUTTON_PRESS_DOWN, BUTTON_LONG_PRESS_START,', 'hold', 'AddressSanitizer: heap-buffer-overflow'),
            ('release no longer cancels timer', 'esp_timer_stop(s_hold[(intptr_t)u]);',
             '/* negative: keep release timer */', '', 'unexpected extra/missing button event'),
            ('release event missing', 'on_event(a, u, BSP_BTN_RELEASE);',
             '/* negative: no release notification */', '', 'unexpected extra/missing button event'),
            ('gesture end event missing', 'on_event(a, u, BSP_BTN_GESTURE_END);',
             '/* negative: no classification end notification */', '', 'unexpected extra/missing button event'),
            ('default 1500ms threshold restored', 'const uint32_t ms = i == BSP_BTN_OK ? BSP_BTN_EXIT_PRESS_MS : BSP_BTN_LONG_PRESS_MS;',
             'const uint32_t ms = BSP_BTN_EXIT_PRESS_MS;', '', 'long press must be available by 700 ms'),
            ('press callback active during init', 'static void cb_press(void *a, void *u) {\n    if (!s_cb) return;',
             'static void cb_press(void *a, void *u) {', 'fail6', 'partial init armed a hold timer'),
            ('release callback active during cleanup', 'static void cb_release(void *a, void *u) {\n    (void)a;\n    if (!s_cb) return;',
             'static void cb_release(void *a, void *u) {\n    (void)a;', 'fail6', 't->used'),
        ]
        evidence['negative_caught'] = []
        for name, before, after, mode, expected in controls:
            assert original.count(before) == 1, f'changed mutation anchor: {name}'
            executable = compile_probe(directory, original.replace(before, after))
            failed = subprocess.run([executable] + ([mode] if mode else []), capture_output=True, text=True)
            assert failed.returncode and expected in failed.stderr, (name, failed.stdout, failed.stderr[-2000:])
            evidence['negative_caught'].append(name)
        if args.native:
            sys.path.insert(0, str(ROOT / 'tools/inspector'))
            from native import Renderer, build
            executable, version = build()
            renderer = Renderer(executable)
            try:
                renderer.command('boot 10 25 12 74 3 1 0')
                assert renderer.inspect()['bag_selected'] == 0
                for key, event, _ in hold:
                    if event in (0, 4, 5):  # This replay tests the completed P10 gesture, not physical edges.
                        continue
                    renderer.command(f'key {key} {event}')
                    assert renderer.command('check')['mismatch'] == 0
                assert renderer.inspect()['page'] == 5, 'real DOWN hold did not return to care'
                renderer.command('tick 1000')
                assert renderer.inspect()['page'] == 5, 'release/timer changed the returned page'
                renderer.command('key 1 1')
                assert renderer.inspect()['page'] == 5, 'click after hold must select on care without navigation'
                evidence['native_P10'] = {'build': version, 'after_hold_and_release_page': 5, 'after_next_click_page': 5}
            finally:
                renderer.close()
        evidence['scope'] = 'Actual BSP + installed ADC/button C with ideal voltages and timer ticks; hardware voltage noise/LVGL task timing not measured.'
        if args.evidence:
            args.evidence.parent.mkdir(parents=True, exist_ok=True)
            args.evidence.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
