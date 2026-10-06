#!/usr/bin/env python3
"""Exercise care details, visitor cards and special outcomes using firmware UI C."""
from pathlib import Path
import json,struct,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,png
OUT=ROOT/'reports/evidence/exploration-events-2026-10-06/ui'

def mix(x):
 x&=0xffffffff;x^=x>>16;x=x*0x7feb352d&0xffffffff;x^=x>>15;x=x*0x846ca68b&0xffffffff;return x^(x>>16)
def run():
 OUT.mkdir(parents=True,exist_ok=True);exe,version=build();checks=0
 def cmd(r,c):
  nonlocal checks
  f=r.command(c);assert r.command('check')['mismatch']==0,c;checks+=1;return f
 def snap(r,name):
  f=cmd(r,'check');(OUT/(name+'.png')).write_bytes(png(f['pixels']))
 r=Renderer(exe)
 try:
  cmd(r,'boot 5 25 40 74 3 812 0 0 1');cmd(r,'nurture_fixture 100 100 100 100')
  cmd(r,'key 1 1');cmd(r,'key 1 1');before=r.inspect();cmd(r,'key 2 1');snap(r,'care-bonuses');assert r.inspect()==before
  cmd(r,'key 2 1');snap(r,'care-main');assert r.inspect()['page']==5
  cmd(r,'key 2 1');cmd(r,'key 1 3');assert r.inspect()['page']==5
  cmd(r,'page 3');cmd(r,'tick 6000');snap(r,'battle')
 finally:r.close()
 widths=[]
 for intimacy in (0,100):
  r=Renderer(exe)
  try:
   cmd(r,'boot 5 25 30 133 4 812 0 0 0');cmd(r,f'nurture_fixture 80 50 100 {intimacy}');f=cmd(r,'page 4')
   blue=struct.unpack_from('>H',f['pixels'],2*(217*240+120))[0]
   width=sum(struct.unpack_from('>H',f['pixels'],2*(217*240+x))[0]==blue for x in range(20,221));widths.append(width);snap(r,f'capture-bond-{intimacy}')
  finally:r.close()
 assert widths[1]>widths[0]*1.4,(widths)
 r=Renderer(exe);seen=set()
 try:
  cmd(r,'boot 15 25 40 74 3 812 0 0 1');cmd(r,'challenge_unlock 16383');cmd(r,'region_fixture 4 1')
  for step in range(1,121):
   # Keep the test encounter queue outside this habitat. Pending duplicates
   # intentionally block exploration and are separately covered by game tests.
   for sid in (1,4,25,133,143):cmd(r,f'spawn {sid} 3 {2000+step}')
   cmd(r,'nurture_fixture 100 100 100 100');cmd(r,'page 15');before=r.inspect();cmd(r,'key 2 1')
   if step in (1,13):snap(r,f'visitors-{step}')
   cmd(r,'key 2 1');cmd(r,'tick 1200');after=r.inspect()
   for _ in range(30):
    if not r.inspect()['growth']:break
    cmd(r,'key 1 3');cmd(r,'tick 500')
   new=[e for e in after['queue'] if e['uid'] not in {e['uid'] for e in before['queue']}]
   seed=mix(step^(4*0x9e3779b9)^0x714e35bd)
   if seed%100<32:
    kind='training' if mix(seed^0x87ab31)&1 else 'sparkle'
    if not new:kind='supply'
    if kind not in seen:snap(r,'event-'+kind);seen.add(kind)
   assert before['nurture']['stamina']-after['nurture']['stamina']==5,(step,before['nurture'],after['nurture'])
   if len(seen)==3 and step>=13:break
  assert seen=={'training','sparkle','supply'},seen
 finally:r.close()
 report={'passed':True,'build':version,'checks':checks,'pixel_band_mismatches':0,'capture_window_widths':widths,'special_outcomes':sorted(seen)}
 (OUT/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':run()
