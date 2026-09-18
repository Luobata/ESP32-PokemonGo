#!/usr/bin/env python3
import json
from verify_party_menu import ROOT,font_check
from native import Renderer,build,png
out=ROOT/'reports/evidence/usb-save-backup';out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe)
try:
 r.command('boot 11 25 30 74 3 123 0 0 0')
 for _ in range(5):r.command('key 1 1')
 r.command('key 2 1')
 for _ in range(4):r.command('key 1 1')
 assert r.inspect()['menu_view']['option_selected']==4
 for name in ['options','no-host']:
  if name=='no-host':r.command('key 2 1')
  frame=r.command('check');assert frame['mismatch']==0;(out/f'{name}.png').write_bytes(png(frame['pixels']))
 r.command('key 1 3')
 assert r.inspect()['menu_view']['options']
 r.command('key 1 1')
 assert r.inspect()['menu_view']['option_selected']==5
 r.command('key 2 1')
 frame=r.command('check');assert frame['mismatch']==0;(out/'import-wait.png').write_bytes(png(frame['pixels']))
 r.command('key 1 3')
 for _ in range(3):r.command('key 1 1')
 assert r.inspect()['menu_view']['option_selected']==8
 r.command('key 2 1')
 assert not r.inspect()['menu_view']['options']
 font_check()
 print(json.dumps({'passed':True,'renderer':version,'scope':'nine option rows, backup and import, long B return, bands, font'}))
finally:r.close()
