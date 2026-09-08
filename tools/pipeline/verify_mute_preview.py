#!/usr/bin/env python3
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import build,Renderer,png
out=ROOT/'reports/evidence/runtime-mute-2026-09-08';out.mkdir(exist_ok=True,parents=True)
exe,v=build();r=Renderer(exe)
def cmd(c):
 f=r.command(c);assert r.command('check')['mismatch']==0;return f
try:
 cmd('boot 11 25 12 74 3 1 0 0 1');assert r.inspect()['muted'];assert not any(r.audio(11025))
 for _ in range(5):cmd('key 1 1')
 cmd('key 0 1')
 for _ in range(2):cmd('key 1 1')
 (out/'muted.png').write_bytes(png(cmd('check')['pixels']))
 cmd('key 0 1');assert not r.inspect()['muted'];before=r.inspect();assert any(r.audio(11025));assert r.inspect()==before
 (out/'sound-on.png').write_bytes(png(cmd('check')['pixels']))
 cmd('save_fail 1');cmd('key 0 1');assert not r.inspect()['muted']
 (out/'save-failed.png').write_bytes(png(cmd('check')['pixels']))
 cmd('key 0 1');assert r.inspect()['muted'];assert not any(r.audio(3528))
 cmd('key 1 3');cmd('key 0 1');assert r.inspect()['display']['off'];assert not any(r.audio(3528));cmd('key 2 1');assert r.inspect()['muted']
 print(json.dumps({'build':v,'default_muted':True,'toggle_pcm_gate':True,'write_failure_preserved':True,'sleep_silent':True,'dirty_full_equal':True}))
finally:r.close()
