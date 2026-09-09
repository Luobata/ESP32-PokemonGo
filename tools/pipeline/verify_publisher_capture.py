#!/usr/bin/env python3
"""Official serial screenshot bytes, read-only page replay, and command isolation."""
from pathlib import Path
import json, subprocess, sys, tempfile, time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import Renderer, build

with tempfile.TemporaryDirectory() as directory:
    source = Path(directory)/'parser.c'
    source.write_text(r'''
#include <assert.h>
#include "serial_capture.h"
int main(void) {
 const char *lines[]={"FAP_SCREENSHOT_V1\n", "FAP_SCREENSHOT_V1\r\n",
 "FAP_SCREENSHOT_V1_extraABC\n", "FOOABC\n", "FAP\n", "FAP_SCREENSHOT_V2\n"};
 for(unsigned i=0;i<6;i++) {
  serial_capture_parser_t parser={0};unsigned ready=0;
  for(const char *p=lines[i];*p;p++) {
   int result=serial_capture_feed(&parser,*p);
   if(*p!='\n'&&*p!='\r')assert(result!=SERIAL_CAPTURE_OTHER);
   ready+=result==SERIAL_CAPTURE_READY;
  }
  assert(ready==(i<2));assert(!parser.active);
  assert(serial_capture_feed(&parser,'a')==SERIAL_CAPTURE_OTHER);
 }
 serial_capture_parser_t parser={0};serial_capture_feed(&parser,'F');
 for(unsigned i=0;i<100000;i++)assert(serial_capture_feed(&parser,'A')==SERIAL_CAPTURE_CONSUMED);
 assert(serial_capture_feed(&parser,'\n')==SERIAL_CAPTURE_CONSUMED);
 return 0;
}
''')
    exe = Path(directory)/'parser'
    subprocess.run(['cc','-std=c11','-fsanitize=address,undefined','-I',str(ROOT/'firmware/main'),str(source),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)

exe,version=build()
def capture(r):
    r.process.stdin.write(b'FAP_SCREENSHOT_V1\n');r.process.stdin.flush()
    assert r.process.stdout.readline()==b'\n'
    assert r.process.stdout.readline()==b'FAP_SCREENSHOT_V1 240 320 RGB565LE 153600\n'
    raw=r._read(153600,time.monotonic()+15)
    wire=bytearray(raw);wire[::2],wire[1::2]=raw[1::2],raw[::2]
    return bytes(wire)

pages=(1,2,3,4,5,6,9,10,11,12,13,14,15)
for page in pages:
    r=Renderer(exe)
    try:
        r.command(f'boot {page} 25 20 74 3 123 0 0 0');r.command('tick 750')
        frame=r.command('check')['pixels'];before=r.inspect()
        assert capture(r)==frame, page
        assert r.inspect()==before and r.command('check')['pixels']==frame, page
    finally:r.close()
r=Renderer(exe)
try:
    r.command('boot 1 25 20 74 3 123 0 0 0');r.command('tick 60000');r.command('tick 1000')
    before=r.inspect();assert before['display']['off']
    assert any(capture(r)), 'sleeping display still has a logical game frame'
    assert r.inspect()==before and not any(r.command('check')['pixels'])
finally:r.close()
print(json.dumps({'status':'PASS','renderer':version,'pages':len(pages),'compared_pixels':len(pages)*76800,'game_state_unchanged':True,'panel_unchanged':True,'sleep_preserved':True,'malformed_commands_isolated':True}))
