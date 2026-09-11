#!/usr/bin/env python3
"""Check scene audio order and cancellation without playing a speaker."""
import sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build
exe,version=build();r=Renderer(exe)
def key(k):
 for e in (0,4,1,5):r.command(f'key {k} {e}')
try:
 r.command('boot 5 1 16 74 3 123 1 0 0');r.command('care_progress 0 0');key(0);key(2)
 assert r.inspect()['music']==0
 observed=[0]
 for _ in range(600):
  r.command('tick 33');s=r.inspect()
  if observed[-1]!=s['music']:observed.append(s['music'])
  assert r.command('check')['mismatch']==0
 assert observed==[0,14,17,0,16],observed
 assert s['evolution_ui']['active'] and s['party'][0]['species']==2
 key(2);assert not r.inspect()['evolution_ui']['active'] and r.inspect()['music']==4
 result=dict(build=version,music_sequence=observed,passed=True)
 (ROOT/'reports/evidence/evolution-scene-2026-09-11/audio-sequence.json').write_text(json.dumps(result,indent=2)+'\n');print(result)
finally:r.close()
