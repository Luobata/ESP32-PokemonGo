#!/usr/bin/env python3
"""Application record framing with real emitters and the target mutex code.

Two FILE objects sharing a serial sink expose the FILE-only guard's limitation;
the explicit record mutex must work both with shared and distinct FILE streams.
This models an output concurrency hazard, not proof of task FILE identities on
hardware. Actual wire interleaving is recorded separately in hardware evidence.
"""
from pathlib import Path
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
world = (ROOT / 'firmware/main/world.c').read_text()
scan = 'static void emit_ndjson(uint16_t n)' + world.split('static void emit_ndjson(uint16_t n)', 1)[1].split('// Debug-only encounter injection', 1)[0]
device = (ROOT / 'firmware/main/usb_backup_device.c').read_text()
emit = next(line for line in device.splitlines() if line.startswith('static void emit('))
main = (ROOT / 'firmware/main/main.c').read_text().split('void app_main(void)', 1)[1]
assert main.index('console_record_init();') < main.index('world_start(')
assert '"console_record.c"' in (ROOT / 'firmware/main/CMakeLists.txt').read_text()

prefix = r'''
#define _DEFAULT_SOURCE
#include <stdint.h>
#include <inttypes.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <pthread.h>
#include <unistd.h>
#include "console_record.h"
static _Thread_local FILE *task_stdout;
static FILE *shared_stdout;
#undef stdout
#define stdout task_stdout

typedef struct {uint8_t ssid[33],bssid[6],primary,authmode;int rssi;} wifi_ap_record_t;
static wifi_ap_record_t s_recs[8];
static int64_t esp_timer_get_time(void){return 1000000;}
static int bsp_battery_soc(void){return 100;}
static const char *auth_name(int mode){(void)mode;return "open";}
static void json_escape(const char *in,char *out,size_t n){snprintf(out,n,"%s",in);}
static int slow_printf(const char *fmt,...){va_list a;va_start(a,fmt);int n=vfprintf(stdout,fmt,a);va_end(a);usleep(30);return n;}
#define printf slow_printf
'''
suffix = r'''
static void *scanner(void *arg){task_stdout=arg;for(int i=0;i<100;i++)emit_ndjson(8);return NULL;}
static void *protocol(void *arg){task_stdout=arg;for(int i=0;i<1000;i++){emit("!PWBACKUP NEXT 1 128\n");usleep(30);}return NULL;}
int main(int argc,char **argv){
 (void)argv;console_record_init();shared_stdout=fdopen(dup(STDOUT_FILENO),"w");assert(shared_stdout);
 FILE *other=argc>1?fdopen(dup(STDOUT_FILENO),"w"):shared_stdout;assert(other);
 assert(!setvbuf(shared_stdout,NULL,_IONBF,0));if(other!=shared_stdout)assert(!setvbuf(other,NULL,_IONBF,0));
 pthread_t a,b;assert(!pthread_create(&a,NULL,scanner,shared_stdout));assert(!pthread_create(&b,NULL,protocol,other));
 assert(!pthread_join(a,NULL));assert(!pthread_join(b,NULL));
 if(other!=shared_stdout)fclose(other);fclose(shared_stdout);return 0;
}
'''
sem = r'''
#pragma once
#include <assert.h>
#include <stdint.h>
#include <pthread.h>
typedef int BaseType_t;
typedef pthread_mutex_t StaticSemaphore_t;
typedef StaticSemaphore_t *SemaphoreHandle_t;
#define pdTRUE 1
#define portMAX_DELAY UINT32_MAX
#define configASSERT(x) assert(x)
static inline SemaphoreHandle_t xSemaphoreCreateMutexStatic(StaticSemaphore_t *s){assert(!pthread_mutex_init(s,NULL));return s;}
static inline BaseType_t xSemaphoreTake(SemaphoreHandle_t s,uint32_t timeout){assert(timeout==portMAX_DELAY);assert(!pthread_mutex_lock(s));return pdTRUE;}
static inline BaseType_t xSemaphoreGive(SemaphoreHandle_t s){assert(!pthread_mutex_unlock(s));return pdTRUE;}
'''

def valid_lines(text):
    rows = text.splitlines()
    assert len(rows) == 1100, len(rows)
    scan_count = usb_count = 0
    for row in rows:
        if row == '!PWBACKUP NEXT 1 128':
            usb_count += 1
        else:
            data = json.loads(row)
            assert len(data['aps']) == 8 and data['bat'] == 100
            scan_count += 1
    assert (scan_count, usb_count) == (100, 1000)

with tempfile.TemporaryDirectory() as folder:
    tmp = Path(folder)
    (tmp / 'freertos').mkdir()
    (tmp / 'freertos/FreeRTOS.h').write_text(sem)
    (tmp / 'freertos/semphr.h').write_text('#include "FreeRTOS.h"\n')
    for negative in (False, True):
        code = emit + '\n' + scan
        if negative:
            code = code.replace('console_record_begin();', '').replace('console_record_end();', '')
        src, exe = tmp / 'console.c', tmp / 'console'
        src.write_text(prefix + code + suffix)
        subprocess.run(['cc', '-std=c11', '-DESP_PLATFORM', '-pthread', '-fsanitize=address,undefined', '-fno-sanitize-recover=all', '-I', str(tmp), '-I', str(ROOT/'firmware/main'), str(src), str(ROOT/'firmware/main/console_record.c'), '-o', str(exe)], check=True)
        for separate in (False, True):
            result = subprocess.run([str(exe)] + (['separate'] if separate else []), capture_output=True, text=True, check=True)
            try:
                valid_lines(result.stdout)
            except (AssertionError, ValueError):
                assert negative and separate
            else:
                assert not (negative and separate), 'FILE-only negative control did not reproduce interleaving'
print(json.dumps(dict(passed=True, wifi_records_per_case=100, usb_records_per_case=1000, shared_and_separate_streams=True, target_static_mutex_code=True, file_only_negative_control_detected=True)))
