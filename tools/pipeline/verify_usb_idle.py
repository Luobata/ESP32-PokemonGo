#!/usr/bin/env python3
"""Keep a real USB import awake, and retain serial bytes across UI-lock retries."""
import json, os, subprocess, sys, tempfile, zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build

# Compile the exact function used by the device's debug receive loop.
source=(ROOT/'firmware/main/dbg.c').read_text()
helper='static bool feed_backup_byte(char c)'+source.split('static bool feed_backup_byte(char c)',1)[1].split('static void dbg_task',1)[0]
assert 'if (feed_backup_byte((char)c)) continue;' in source
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <string.h>
static unsigned failures,waits,calls,unlocks;
static char received[512];
#define pdMS_TO_TICKS(n) (n)
static bool bsp_lvgl_lock(unsigned n){assert(n==1000);if(failures){failures--;return false;}return true;}
static void bsp_lvgl_unlock(void){unlocks++;}
static void vTaskDelay(unsigned n){assert(n==1);waits++;}
static bool usb_backup_feed(char c){received[calls++]=c;return c!='x';}
'''
suffix=r'''
int main(void){
 const char *frame="!PWBACKUP RDATA 0123456789abcdef0123456789abcdef 1 31232 001122\n";
 for(unsigned i=0;i<strlen(frame);i++){failures=i%4;assert(feed_backup_byte(frame[i]));}
 failures=3;assert(!feed_backup_byte('x'));assert(waits>10);
 assert(calls==strlen(frame)+1&&unlocks==calls);assert(!memcmp(received,frame,strlen(frame)));
 assert(received[calls-1]=='x');return 0;
}
'''
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp);c=p/'test.c';exe=p/'test'
 for negative in (False,True):
  h=helper.replace('while (!bsp_lvgl_lock(1000)) vTaskDelay(pdMS_TO_TICKS(1));','if (!bsp_lvgl_lock(1000)) {vTaskDelay(pdMS_TO_TICKS(1));return true;}') if negative else helper
  c.write_text(prefix+h+suffix)
  subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
  result=subprocess.run([str(exe)],capture_output=True)
  assert (result.returncode!=0)==negative,(negative,result.stderr)

exe,version=build();r=Renderer(exe);checks=0;token='0123456789abcdef0123456789abcdef'
def cmd(s):
 global checks
 f=r.command(s)
 # Protocol input only changes state; the production menu refreshes it on its
 # 250 ms timer. Compare presented frames after keys/ticks, not before refresh.
 if not s.startswith(('usb_line ','usb_poll ')):
  assert r.command('check')['mismatch']==0,s;checks+=1
 return f

def key(n=2):return cmd(f'key {n} 1')
def wire(s):cmd('usb_line !PWBACKUP '+s+' '+token)
def packet(s):cmd('usb_line !PWBACKUP '+s)
try:
 cmd('boot 11 25 30 74 3 123 0 0 0');cmd('usb_init')
 for _ in range(5):key(1)
 key()
 for _ in range(5):key(1)
 key();wire('HELLO')
 crc=zlib.crc32(bytes(24576))
 packet(f'OFFER {token} 001122334455 '+('1'*64)+f' 22 24576 {crc:08x}')
 key(1);key();assert r.inspect()['display']['busy']
 elapsed=0
 # Export the mandatory pre-backup before authorizing the receiving phase.
 for _ in range(193):
  elapsed+=20;cmd(f'usb_poll {elapsed}')
 cmd('tick 4000')
 packet(f'ACK {token} 1');assert r.inspect()['display']['busy']
 # Slow real protocol chunks for 86 seconds: each advances both clocks and
 # renews the heartbeat. This exceeds the 60-second automatic screen timeout.
 for offset in range(0,24576,128):
  packet(f'PING {token}');packet(f'RDATA {token} 1 {offset} '+('00'*128))
  elapsed+=450;cmd('tick 450');cmd(f'usb_poll {elapsed}')
  assert r.inspect()['display']['busy'] and not r.inspect()['display']['off'],offset
 wire('BYE');assert not r.inspect()['display']['busy']
 cmd('tick 59800');assert not r.inspect()['display']['off']
 cmd('tick 300');assert r.inspect()['display']['off']
 result={'passed':True,'native_build':version,'pixel_checks':checks,'slow_import_ms':192*450,'retained_byte_lock_retries':True,'negative_control_rejected':True,'automatic_sleep_resumes_after_cancel':True,'scope':'Production protocol, UI and timer with simulated flash; not hardware throughput'}
 out=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',str(ROOT/'.build/usb-idle')));out.mkdir(parents=True,exist_ok=True);(out/'checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:r.close()
