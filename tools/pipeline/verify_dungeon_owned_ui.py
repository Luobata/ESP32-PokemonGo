#!/usr/bin/env python3
"""Native selection checks: sole partner, six rows, shiny duplicates and cancel."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'inspector'))
from native import Renderer,build,png
exe,_=build()
out=Path('reports/evidence/dungeon-owned-2026-09-13');out.mkdir(parents=True,exist_ok=True)
for full in (False,True):
 r=Renderer(exe)
 try:
  r.command('boot 16 2 16 74 3 1 0 0 0')
  if full:
   for species,level,shiny in ((2,18,1),(7,12,0),(4,15,0),(25,11,0),(133,13,0)):
    r.command(f'party_add {species} {level} 30 0 {shiny}')
  initial=r.inspect()
  def key(k):return r.command(f'key {k} 1')
  key(1);key(2)
  key(2);key(2) # select then cancel leader; neither operation spends stamina
  assert initial['nurture']==r.inspect()['nurture']
  if full:key(1)
  key(2)
  f=r.command('check');assert not f['mismatch']
  (out/('six-members-shiny.png' if full else 'solo-selected.png')).write_bytes(png(f['pixels']))
  for _ in range(5 if full else 1):key(1)
  f=key(2);assert f['page']=='P13'
  state=r.inspect();selected=state['dungeon_team']
  assert len(selected)==1 and selected[0]['species']==2
  assert selected[0]['level']==(18 if full else 16)
  assert selected[0]['shiny']==int(full)
  assert selected[0]['slot']==int(full)
  r.command('tick 4000')
  f=r.command('check');assert not f['mismatch']
  (out/('shiny-sendout.png' if full else 'solo-battle.png')).write_bytes(png(f['pixels']))
  print('PASS', 'six-owned-members/shiny' if full else 'single-owned-partner', selected)
 finally:r.close()
