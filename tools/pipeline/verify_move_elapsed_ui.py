#!/usr/bin/env python3
"""A delayed actual trainer callback must land on the same visual sample."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build
exe,version=build()
def render(delayed):
 r=Renderer(exe)
 try:
  r.command('boot 13 25 12 74 3 123 0 0 0')
  for e in (0,4,1,5):r.command(f'key 2 {e}')
  for i in range(300):
   if r.inspect()['challenge']['mode']==3:break
   r.command('tick 45')
  else:raise AssertionError('no attack')
  f=r.command(('stall' if delayed else 'tick')+' 270')
  assert r.command('check')['mismatch']==0
  return f['pixels'],r.inspect()['challenge']['turns']
 finally:r.close()
a=render(False);b=render(True);assert a==b,'late rendering must catch up to the same attack frame without advancing combat again'
print(json.dumps(dict(build=version,passed=True,delay_ms=270,same_pixels=True,same_turn=True)))
