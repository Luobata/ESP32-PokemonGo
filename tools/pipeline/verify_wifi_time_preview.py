#!/usr/bin/env python3
"""Settings/Wi-Fi UI rendered by production band renderer, native network stub."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
out=ROOT/'reports/evidence/wifi-time-2026-09-15';out.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0

def cmd(line):
 global checks
 result=r.command(line);assert r.command('check')['mismatch']==0,line;checks+=1;return result

def key(n,ev=1):return cmd(f'key {n} {ev}')
def snap(name):(out/(name+'.png')).write_bytes(png(cmd('check')['pixels']))
try:
 cmd('boot 11 25 40 74 3 123 0 0 0')
 for _ in range(5):key(1)
 key(2)
 for _ in range(6):key(1)
 snap('settings-wifi');key(2);snap('wifi-unconfigured');initial=cmd('check')['pixels'];key(2);snap('wifi-setup');assert cmd('check')['pixels']!=initial
 key(1,3);snap('settings-return');key(2);snap('wifi-setup-closed');assert cmd('check')['pixels']==initial
finally:r.close()
result={'build':version,'band_checks':checks,'native_network_stub':True,'hardware_tested':False}
(out/'preview.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
