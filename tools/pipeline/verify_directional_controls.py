#!/usr/bin/env python3
"""Exercise new controls through production C, including return boundaries."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png

OUT = ROOT / 'reports/evidence/controls-growth-2026-09-10'
OUT.mkdir(parents=True, exist_ok=True)
exe, version = build()
checks = 0
passed = []

class Flow:
    def __init__(self, page=1, team=1, pet=25, wild=74, level=30):
        self.r = Renderer(exe)
        self.cmd(f'boot {page} {pet} {level} {wild} 3 123 0 0 {team}')
    def cmd(self, cmd):
        global checks
        self.frame = self.r.command(cmd)
        assert self.r.command('check')['mismatch'] == 0, cmd
        checks += 1
        return self.state()
    def state(self): return self.r.inspect()
    def key(self, key):
        for event in (0, 4, 1, 5): self.cmd(f'key {key} {event}')
        return self.state()
    def back(self):
        for event in (0, 3, 4, 5): self.cmd(f'key 1 {event}')
        return self.state()
    def until(self, predicate, ms=60000):
        for _ in range(ms // 120):
            if predicate(self.state()): return self.state()
            self.cmd('tick 120')
        raise AssertionError(('timeout', self.state()))
    def shot(self, name): (OUT / f'{name}.png').write_bytes(png(self.frame['pixels']))
    def growth(self):
        for _ in range(80):
            self.cmd('tick 120')
            if not self.state()['growth']: return
            self.key(2)
        raise AssertionError('growth notices did not finish')
    def close(self): self.r.close()

def check(name, run):
    run()
    passed.append(name)
    print('PASS', name, flush=True)

def home_and_lists():
    f = Flow()
    try:
        f.key(0); f.key(1); assert f.state()['page'] == 1
        f.key(2); assert f.state()['page'] == 5
        f.back(); f.key(1); assert f.state()['page'] == 1
        f.key(2); assert f.state()['page'] == 11
        assert f.key(0)['menu_view']['selected'] == 8
        assert f.key(1)['menu_view']['selected'] == 0
        f.shot('menu')
        for index, page in [(0,6),(1,12),(2,10),(3,5),(4,13),(6,14),(7,15)]:
            while f.state()['menu_view']['selected'] != index: f.key(1)
            assert f.key(2)['page'] == page, index
            if page not in (13,15): f.key(0); f.key(1)
            assert f.back()['page'] == 11, (index, f.state())
            assert f.state()['menu_view']['selected'] == index
        f.back(); f.shot('home'); assert f.state()['page'] == 1
        f.back(); assert f.state()['page'] == 1
    finally: f.close()

def settings_and_wake():
    f = Flow(11)
    try:
        for _ in range(5): f.key(1)
        f.key(2); assert f.state()['menu_view']['options']
        for _ in range(3): f.key(1)
        f.key(2); old = f.state()['volume']
        f.key(0); assert f.state()['volume'] == min(100,old+5)
        f.key(1); assert f.state()['volume'] == old
        f.back(); assert f.state()['menu_view']['options']
        f.shot('settings')
        f.back(); assert not f.state()['menu_view']['options']
        f.cmd('tick 60000'); assert f.state()['display']['off']
        before=f.state()['menu_view']['selected']
        f.back(); assert not f.state()['display']['off'] and f.state()['page'] == 11
        assert f.state()['menu_view']['selected'] == before
        f.back(); assert f.state()['page'] == 1
    finally: f.close()

def party_and_box():
    f = Flow(12)
    try:
        f.cmd('party_add 150 40 90 0 1')
        f.key(1); assert f.state()['party_view']['selected'] == 1
        f.key(2); assert f.state()['party_view']['details']
        f.shot('party-details')
        f.key(1); f.key(1); f.key(2); assert f.state()['party_view']['skills']
        f.key(0); f.key(1); f.back(); assert not f.state()['party_view']['skills']
        f.key(1); f.key(2); assert f.state()['party_view']['box']
        f.shot('warehouse')
        f.key(2); assert f.state()['party_view']['details']
        f.key(1); f.key(2); assert f.state()['party_view']['skills']
        f.back()
        before=f.state()['party'][1]['species']
        f.cmd('save_fail 1'); f.key(0); f.key(2)
        assert f.state()['party'][1]['species'] == before
        f.key(2); assert f.state()['party'][1]['species'] == 150
        assert not f.state()['party_view']['box']
        f.back(); assert not f.state()['party_view']['details']
    finally: f.close()

def exploration():
    f = Flow(15)
    try:
        energy=f.state()['exploration']['energy']
        f.key(1); f.key(2); f.key(0); f.key(2)
        assert f.state()['exploration']['route'] == 3
        assert f.state()['exploration']['energy'] == energy
        f.key(0); f.key(2); f.shot('exploration-activities')
        f.key(1); f.key(2); f.shot('research'); f.back()
        f.key(1); f.key(2); f.key(0); f.key(1); f.key(2)
        assert f.state()['page']==15
        f.back(); f.back(); f.key(1); f.key(2)
        assert f.state()['exploration']['energy'] == energy-1
        f.until(lambda s:not s['display']['busy'])
        f.growth()
        f.back(); f.back(); assert f.state()['page'] == 11
    finally:f.close()

def starter():
    f = Flow(9, team=0)
    try:
        f.cmd('tick 2000'); f.key(0); f.key(2)
        assert f.state()['pet'] == 25 and not f.state()['needs_starter']
        assert f.state()['page'] == 1
    finally:f.close()
    f = Flow(9, team=0)
    try:
        f.cmd('tick 2000'); f.back(); assert f.state()['page'] == 0
        f.back(); f.until(lambda s:s['page']==9); f.shot('starter')
    finally:f.close()

def capture_and_counter():
    f = Flow(4, team=0)
    try:
        before=f.state()['inventory']
        f.key(1); f.back()
        assert f.state()['page']==3 and f.state()['inventory']==before
        f.until(lambda s:not s['display']['busy'])
        f.key(2); assert f.state()['page']==4
        f.shot('capture')
        before=f.state()['inventory'][0]
        f.cmd('key 2 0')
        assert f.state()['inventory'][0]==before-1, 'throw must happen on PRESS'
        f.cmd('key 2 4'); f.cmd('key 2 1'); f.cmd('key 2 5')
        assert f.state()['inventory'][0]==before-1, 'release must not throw twice'
        f.back(); assert f.state()['page']==4, 'capture animation cannot be bypassed'
        s=f.until(lambda s:s['page']==3 and not s['display']['busy'])
        assert s['active']['attacks']==1 and not s['active']['auto_battle']
        f.key(2); assert f.state()['page']==4, 'failed capture restores capture choice'
    finally:f.close()

def wild_escape_and_fight():
    f=Flow(3,pet=1,wild=150,level=20)
    try:
        f.until(lambda s:not s['display']['busy'])
        f.shot('wild-choice')
        before=f.state()['active']
        f.back();f.shot('escape-confirm');f.back()
        assert f.state()['active']==before
        f.back();f.key(2);assert f.state()['active']==before, 'C confirms default continue'
        f.key(1);f.key(2);assert f.state()['active']['auto_battle']
        f.back();assert f.state()['page']==3, 'return must not abandon battle'
        f.key(1);f.key(2)
        f.cmd('tick 12000')
        s=f.state();assert s['page'] in (2,3)
        if s['page']==3: assert s['active']['attacks']>0
    finally:f.close()

def trainer():
    f=Flow(13,level=60)
    try:
        f.cmd('challenge_unlock 1');f.key(2)
        assert f.state()['challenge']['active']
        f.key(2);f.until(lambda s:s['challenge']['mode']==7)
        f.shot('trainer-tactics')
        f.key(1);f.key(2);assert f.state()['challenge']['mode']==9
        f.key(0);f.key(1);f.back();assert f.state()['challenge']['mode']==7
        f.key(1);f.key(2);assert f.state()['challenge']['mode']==4
        f.key(1);f.key(2);assert f.state()['challenge']['sendout_mask']==1
        f.back();f.until(lambda s:s['challenge']['mode']==6)
        f.key(2);assert f.state()['challenge']['active'] and f.state()['challenge']['mode']==7
        for _ in range(4):f.key(1)
        f.key(2);f.key(1);f.key(2)
        assert f.state()['challenge']['mode']==5
        f.cmd('tick 1000');f.key(2);assert f.state()['challenge']['mode']==0
    finally:f.close()

def care_stamina():
    for stamina in (0, 4, 5, 6):
        f=Flow(5)
        try:
            f.cmd(f'nurture_fixture 40 20 {stamina} 10')
            f.key(1); before=f.state()['nurture'].copy(); inventory=f.state()['inventory']
            f.key(2); after=f.state()['nurture']
            if stamina<5: assert after==before
            else:
                assert after==dict(before,mood=35,stamina=stamina-5,intimacy=11)
            assert f.state()['inventory']==inventory
            if stamina==0:
                f.shot('care-no-stamina'); f.key(0); f.key(2)
                assert f.state()['nurture']['satiety']==70 and f.state()['nurture']['stamina']==0
                assert f.state()['inventory'][15]==inventory[15]-1
        finally:f.close()

def adaptive_party():
    f=Flow(12,team=0)
    try:
        f.key(2); assert f.state()['party_view']['details']
        f.back(); f.cmd('party_add 1 12 100 0 0'); f.cmd('party_add 7 12 100 0 0'); f.cmd('tick 80')
        f.shot('party-three'); f.key(1); f.key(1); f.key(2)
        assert f.state()['party_view']['details'] and f.state()['party_view']['species']==7
        f.back(); f.cmd('party_add 4 12 100 0 0'); f.cmd('tick 80')
        f.key(0); assert not f.state()['party_view']['details'] and f.state()['party_view']['selected']==1
        f.shot('party-four'); f.key(2); assert f.state()['party_view']['details']
    finally:f.close()

for name,run in [('home-and-lists',home_and_lists),('settings-and-wake',settings_and_wake),
                 ('party-and-box',party_and_box),('exploration',exploration),('starter',starter),
                 ('capture-and-counter',capture_and_counter),('wild-escape-and-fight',wild_escape_and_fight),('trainer',trainer),('care-stamina',care_stamina),('adaptive-party',adaptive_party)]:
    check(name,run)
report={'build':version,'passed':passed,'dirty_vs_full_redraw_checks':checks,
        'scope':'production game C with host world/save fixtures; physical ADC gestures checked separately'}
(OUT/'navigation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
