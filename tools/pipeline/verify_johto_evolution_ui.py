#!/usr/bin/env python3
"""Production C UI, button navigation, cancellation and warehouse evolution."""
import sys,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
OUT=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',str(ROOT/'reports/evidence/johto-evolution-2026-10-17')));OUT.mkdir(parents=True,exist_ok=True)
exe,version=build();r=Renderer(exe);checks=0
def cmd(s):
 global checks
 f=r.command(s);assert not r.command('check')['mismatch'],s;checks+=1;return f
def key(i):cmd(f'key {i} 1')
def shot(n):(OUT/(n+'.png')).write_bytes(png(cmd('tick 0')['pixels']))
def evolution_menu():
 cmd('page 12');key(2)
 for _ in range(4):key(1)
 key(2)
try:
 cmd('boot 12 95 40 74 3 123 0 0 0');cmd('inventory 20 1');evolution_menu();shot('onix-conditions')
 key(2);shot('onix-confirm');key(2) # default Cancel
 assert not r.inspect()['evolution_ui']['active'] and r.inspect()['party'][0]['species']==95
 key(2);key(1);key(2);cmd('tick 16000');shot('steelix-evolved')
 assert r.inspect()['party'][0]['species']==208 and r.inspect()['inventory'][20]==0
 key(2);cmd('page 1');cmd('party_add 133 50 80 7 1');cmd('johto_fixture 3 0')
 cmd('page 12');key(1);key(2)
 for _ in range(4):key(1)
 key(2);shot('eevee-five-branches')
 for _ in range(4):key(1)
 key(2);key(1);key(2);cmd('tick 16000')
 assert r.inspect()['party'][1]['species']==197 and r.inspect()['party'][1]['flags']&1
 key(2);cmd('page 1')
 for sid in (1,4,7,25):cmd(f'party_add {sid} 30 20 0 0')
 cmd('party_add 123 60 42 13 1');cmd('inventory 20 1');cmd('page 12');key(2)
 for _ in range(3):key(1)
 key(2);key(2)
 for _ in range(3):key(1)
 key(2);shot('warehouse-evolution');key(2);key(1);key(2);cmd('tick 16000')
 assert r.inspect()['party_view']['species']==212
 key(2)
 for _ in range(3):key(0)
 key(2);assert r.inspect()['party'][0]['species']==212 and r.inspect()['party'][0]['flags']&1
 cmd('johto_fixture 8 12');cmd('page 17');cmd('tick 1000')
 for _ in range(5):key(1)
 key(2);shot('research-rewards');key(2);shot('research-claimed')
 assert r.inspect()['inventory'][19]==1
 cmd('page 14')
 for _ in range(16):key(1)
 shot('johto-achievements')
 result=dict(build=version,checks=checks,passed=True);(OUT/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:r.close()
