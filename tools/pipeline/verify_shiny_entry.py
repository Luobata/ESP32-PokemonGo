#!/usr/bin/env python3
"""Actual C shiny send-out integration, with independent pixel/lifecycle checks."""
import io
import json
from pathlib import Path
import sys
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import build, Renderer, png

OUT = ROOT/'reports/evidence/shiny-entry-2026-10-07'
OUT.mkdir(parents=True, exist_ok=True)
exe, version = build()
checks = 0
cases = []

def command(r, text):
    global checks
    f = r.command(text)
    assert not r.command('check')['mismatch'], text
    checks += 1
    return f

def until(r, predicate, limit=500):
    for _ in range(limit):
        if predicate(r.inspect()):
            return
        command(r, 'tick 45')
    raise AssertionError(r.inspect())

def wild(pet, enemy):
    r = Renderer(exe)
    try:
        command(r, f'boot 3 25 40 130 4 123 {enemy} 0 0 {pet}')
        before = r.inspect()
        frames, sides = [], []
        for _ in range(350):
            s = r.inspect()
            if s['presentation']['phase'] == 'choice':
                break
            if s['presentation']['phase'] == 'shiny-entry':
                sides.append(s['presentation']['shiny_side'])
                f = command(r, 'check')
                frames.append(Image.open(io.BytesIO(png(f['pixels']))).convert('RGB'))
                # Even long-return and confirm cannot skip entry to capture/attack.
                for key in ('key 2 1', 'key 1 3'):
                    command(r, key)
                assert r.inspect()['page'] == 3
                assert r.inspect()['presentation']['phase'] == 'shiny-entry'
            command(r, 'tick 45')
        else:
            raise AssertionError('entry did not finish')
        after = r.inspect()
        assert sides == sorted(sides, reverse=True)  # enemy before player
        assert set(sides) == ({1} if pet else set()) | ({2} if enemy else set())
        assert 22*(pet+enemy) <= len(sides) <= 23*(pet+enemy)
        for key in ('exp', 'party', 'queue'):
            assert before[key] == after[key], key
        if frames:
            assert len({f.tobytes() for f in frames}) > 7
            frames[min(6,len(frames)-1)].save(OUT/f'wild-p{pet}-e{enemy}.png')
            frames[0].save(OUT/f'wild-p{pet}-e{enemy}.gif', save_all=True,
                           append_images=frames[1:]+[Image.open(io.BytesIO(png(command(r,'check')['pixels']))).convert('RGB')],
                           duration=[45]*len(frames)+[700], loop=0)
        # A cancelled capture returns to this encounter without replaying entry.
        command(r,'key 2 1'); assert r.inspect()['page'] == 4
        command(r,'key 1 3'); assert r.inspect()['page'] == 3
        assert r.inspect()['presentation']['phase'] == 'choice'
        command(r,'tick 1500'); assert r.inspect()['presentation']['phase'] == 'choice'
        assert r.audio(1000) == bytes(2000)  # preview remains muted
        cases.append(f'wild: player={pet}, enemy={enemy}, {len(sides)} sparkle frames; no state mutation/replay')
    finally:
        r.close()

def trainer():
    r = Renderer(exe)
    try:
        command(r,'boot 13 25 20 74 3 123 0 0 0 1')
        command(r,'party_add 6 20 80 0 1')
        command(r,'key 2 1')
        until(r,lambda s:s['shiny_entry_side']==1)
        assert r.inspect()['challenge']['sendout_mask']==3
        before = r.inspect()['challenge']
        for i in range(23):
            if i==6:(OUT/'trainer.png').write_bytes(png(command(r,'check')['pixels']))
            if r.inspect()['shiny_entry_side']:
                assert r.inspect()['challenge']==before
            command(r,'tick 45')
        # Ask for tactics, then switch to the other shiny owned partner.
        command(r,'key 2 1');until(r,lambda s:s['challenge']['mode']==7)
        command(r,'key 1 1');command(r,'key 1 1');command(r,'key 2 1')
        command(r,'key 1 1');command(r,'key 2 1')
        assert r.inspect()['challenge']['sendout_mask']==1
        until(r,lambda s:s['shiny_entry_side']==1)
        command(r,'tick 1100');assert not r.inspect()['shiny_entry_side']
        # An enemy replacement must not replay our existing shiny's sparkle.
        command(r,'challenge_hp_fixture 1 0 0')
        until(r,lambda s:s['challenge']['sendout_mask']==2)
        for _ in range(80):
            assert not r.inspect()['shiny_entry_side']
            command(r,'tick 45')
            if r.inspect()['challenge']['mode']!=2:break
        cases.append('trainer: initial and player-only replacement sparkle; enemy-only replacement does not replay player')
    finally:
        r.close()

def dungeon():
    r = Renderer(exe)
    try:
        command(r,'boot 16 2 16 74 3 1 0 0 0 1')
        for key in (1,2,2,2,2,1,2):command(r,f'key {key} 1')
        assert r.inspect()['page']==13
        assert r.inspect()['dungeon_team'][0]['shiny']==1
        until(r,lambda s:s['shiny_entry_side']==1)
        command(r,'tick 270');(OUT/'dungeon.png').write_bytes(png(command(r,'check')['pixels']))
        command(r,'tick 800');assert not r.inspect()['shiny_entry_side']
        cases.append('dungeon: selected owned shiny retains palette and entry effect')
    finally:
        r.close()

for pet in (0,1):
    for enemy in (0,1):wild(pet,enemy)
trainer()
dungeon()
result=dict(passed=True,version=version,checks=checks,cases=cases)
(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
