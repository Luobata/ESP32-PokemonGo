#!/usr/bin/env python3
"""Exercise real page clocks, not only constants in presentation helpers."""
import json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build
exe,version=build()
r=Renderer(exe)
checks=0
def cmd(line):
    global checks
    f=r.command(line)
    assert r.command('check')['mismatch']==0,line
    checks+=1
    return f
try:
    cmd('boot 13 25 30 74 3 123 0 0 1')
    cmd('key 2 1')
    for _ in range(100):
        if r.inspect()['challenge']['mode']==2:break
        cmd('tick 45')
    assert r.inspect()['challenge']['mode']==2
    elapsed=0
    while r.inspect()['challenge']['mode']==2 and elapsed<6000:
        cmd('tick 45');elapsed+=45
    assert r.inspect()['challenge']['mode']==3
    assert 3135<=elapsed<=3225,elapsed
    sendout=elapsed
    # Force only our replacement: this previously took the shortened 900 ms
    # branch because there is no opponent front animation to wait for.
    cmd('challenge_hp_fixture 0 0 0')
    for _ in range(500):
        if r.inspect()['challenge']['mode']==4:break
        cmd('tick 45')
    assert r.inspect()['challenge']['mode']==4
    cmd('key 1 1');cmd('key 2 1')
    assert r.inspect()['challenge']['mode']==2
    assert r.inspect()['challenge']['sendout_mask']==1
    elapsed=0
    while r.inspect()['challenge']['mode']==2 and elapsed<6000:
        cmd('tick 45');elapsed+=45
    assert 3135<=elapsed<=3225,elapsed
    print(json.dumps(dict(build=version,initial_sendout_ms=sendout,
                          player_only_sendout_ms=elapsed,pixel_checks=checks)))
finally:r.close()
