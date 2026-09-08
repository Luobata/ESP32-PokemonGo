#!/usr/bin/env python3
"""Exercise production menu/party/navigation C and their rendered LCD frames.

The host inventory/save boundary is a fixture. verify_world_party.py separately
checks real world/save transactions; this gate checks the user's visible flow.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png
from server import page_value


class Flow:
    def __init__(self, executable, page=1, team=1, pet=25, names=0, wild=74, rarity=3):
        self.r = Renderer(executable)
        self.checks = 0
        self.frame = self.r.command(f'boot {page} {pet} 12 {wild} {rarity} 1 0 {names} {team}')
        self.check()

    def close(self): self.r.close()
    def state(self): return self.r.inspect()
    def check(self):
        self.frame = self.r.command('check')
        assert self.frame['mismatch'] == 0, self.frame['mismatch']
        self.checks += 1
    def cmd(self, value):
        self.frame = self.r.command(value)
        self.check()
    def key(self, key, hold=False): self.cmd(f'key {"ABC".index(key)} {3 if hold else 1}')
    def shot(self, out, name): (out / f'{name}.png').write_bytes(png(self.frame['pixels']))
    def select_menu(self, index):
        for _ in range(6):
            if self.state()['menu_view']['selected'] == index: return
            self.key('B')
        raise AssertionError('menu item unreachable')


def font_check():
    blob = (ROOT / 'assets/font16.bin').read_bytes()
    magic, _, size, stride, count = struct.unpack_from('<4sHHHI', blob)
    assert magic == b'FNT1' and size == 16
    codes = struct.unpack_from(f'<{count}H', blob, 14)
    required = set()
    for name in ('play_menu.c', 'play_party.c'):
        source = (ROOT / 'firmware/main' / name).read_text()
        source = re.sub(r'//[^\n]*|/\*.*?\*/', '', source, flags=re.S)
        for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', source):
            required.update(c for c in literal if ord(c) > 127)
    missing = required - {chr(c) for c in codes}
    assert not missing, ''.join(sorted(missing))
    for char in required:
        offset = 14 + count * 2 + codes.index(ord(char)) * stride
        assert any(blob[offset:offset + stride]), f'empty glyph {char}'
    return len(required)


def menu_routes(exe, out):
    f = Flow(exe)
    try:
        f.shot(out, 'idle-menu-entry')
        f.key('B'); assert f.state()['page'] == 11
        f.shot(out, 'menu')
        for index, page in ((0, 6), (1, 12), (2, 10), (3, 5)):
            f.select_menu(index); f.key('A')
            assert f.state()['page'] == page, (index, f.state())
            f.key('C'); assert f.state()['page'] == 11
            assert f.state()['menu_view']['selected'] == index
        # The nested care -> bag path must unwind through care and menu.
        f.select_menu(3); f.key('A')
        for _ in range(3): f.key('B')
        f.key('A'); assert f.state()['page'] == 10
        f.key('C'); assert f.state()['page'] == 5
        f.key('C'); assert f.state()['page'] == 11
        # Settings are discoverable and return to their own menu item.
        f.select_menu(4); f.key('A')
        assert f.state()['menu_view']['options']
        names = f.state()['names']; f.key('A')
        assert f.state()['names'] != names
        f.shot(out, 'options')
        f.key('C'); assert not f.state()['menu_view']['options']
        assert f.state()['menu_view']['selected'] == 4
        f.select_menu(0); f.key('B', True)
        assert f.state()['menu_view']['selected'] == 5
        f.key('A'); assert f.state()['page'] == 1
        # The existing idle shortcuts remain usable.
        f.key('A'); assert f.state()['page'] == 5
        f.key('C'); assert f.state()['page'] == 1
        f.key('C'); assert f.state()['page'] == 2
        return f.checks
    finally: f.close()


def party_flow(exe, out):
    f = Flow(exe)
    try:
        f.cmd('care_progress 77 123'); f.cmd('nurture 7 8 9')
        f.key('B'); f.select_menu(1); f.key('A')
        f.shot(out, 'party-six')
        first = f.state(); members = first['party']; assert len(members) == 6
        for index in range(6):
            assert f.state()['party_view']['selected'] == index
            f.key('A'); assert f.state()['party_view']['details']
            assert f.state()['party_view']['species'] == members[index]['species']
            if index == 4: f.shot(out, 'party-member')
            f.key('C'); assert not f.state()['party_view']['details']
            f.key('B')
        assert f.state()['party_view']['selected'] == 0
        f.key('B', True); assert f.state()['party_view']['selected'] == 5
        f.key('A')
        f.key('B'); assert f.state()['page'] == 12, 'bag must not silently change the leader'
        assert f.state()['pet'] == members[0]['species']
        f.cmd('save_fail 1'); f.key('A')
        failed = f.state()
        assert failed['party'] == members and failed['pet'] == first['pet']
        assert failed['nurture'] == first['nurture']
        assert failed['party_view']['feedback']
        f.shot(out, 'party-save-failed')
        f.key('A'); changed = f.state()
        assert changed['party'] == [members[-1], *members[:-1]], changed['party']
        assert changed['pet'] == members[-1]['species']
        assert changed['level'] == members[-1]['level'] and changed['exp'] == members[-1]['exp']
        assert changed['nurture']['intimacy'] == members[-1]['intimacy']
        for axis in ('satiety', 'mood', 'stamina'):
            assert changed['nurture'][axis] == first['nurture'][axis]
        f.shot(out, 'party-new-leader')
        # Details -> bag -> details -> list -> menu -> idle keeps the return path.
        f.key('B'); assert f.state()['page'] == 10
        f.key('B', True); assert f.state()['bag_selected'] == 18
        f.key('B'); assert f.state()['bag_selected'] == 0
        f.key('C'); assert f.state()['page'] == 12 and f.state()['party_view']['details']
        assert f.state()['party_view']['species'] == changed['pet']
        f.key('C'); assert not f.state()['party_view']['details']
        f.key('C'); assert f.state()['page'] == 11 and f.state()['menu_view']['selected'] == 1
        f.key('C'); assert f.state()['page'] == 1 and f.state()['pet'] == changed['pet']
        f.shot(out, 'idle-new-leader')
        f.key('A'); assert f.state()['page'] == 5 and f.state()['pet'] == changed['pet']
        f.key('C'); f.key('C'); f.key('A')
        for _ in range(180):
            state = f.state()
            if state['page'] == 3 and state['presentation']['phase'] == 'choice': break
            f.cmd('tick 60')
        else: raise AssertionError('new leader never reached battle choices')
        assert f.state()['presentation']['visible_level'] == changed['level']
        f.shot(out, 'battle-new-leader')
        return f.checks
    finally: f.close()


def single_and_capacity(exe, out):
    f = Flow(exe, page=12, team=0, pet=122, names=1)
    try:
        f.shot(out, 'party-single')
        f.key('B'); f.key('B', True)
        assert f.state()['party_view']['selected'] == 0
        f.key('A'); before = f.state(); f.key('A')
        assert f.state()['party'] == before['party']
        f.shot(out, 'party-already-leader')
        f.key('C')
        for sid in (29, 32, 83, 149, 151, 150): f.cmd(f'party_add {sid} 100 85 500 1')
        f.cmd('tick 500')
        assert f.state()['party_count'] == 6 and f.state()['box_count'] == 1
        f.shot(out, 'party-full-with-reserve')
        for _ in range(6):
            f.key('A'); f.key('C'); f.key('B')
        # New-game fixtures never inherit a synthetic team.
        return f.checks
    finally: f.close()


def shiny_leader(exe, out):
    frames, checks = {}, 0
    for shiny in (0, 1):
        f = Flow(exe, page=12, team=0)
        try:
            f.cmd(f'party_add 147 13 48 32 {shiny}'); f.cmd('tick 500')
            f.key('B'); f.key('A'); f.key('A')
            assert f.state()['pet'] == 147 and f.state()['party'][0]['flags'] == shiny
            f.key('C'); f.key('C'); f.key('C')
            assert f.state()['page'] == 1
            frames[(shiny, 1)] = f.frame['pixels']
            f.shot(out, f'leader-{shiny}-idle')
            f.key('A'); assert f.state()['page'] == 5
            frames[(shiny, 5)] = f.frame['pixels']
            f.shot(out, f'leader-{shiny}-care')
            f.key('C'); f.key('C'); f.key('A')
            for _ in range(180):
                state = f.state()
                if state['page'] == 3 and state['presentation']['phase'] == 'choice': break
                f.cmd('tick 60')
            else: raise AssertionError('shiny leader entry did not finish')
            frames[(shiny, 3)] = f.frame['pixels']
            f.shot(out, f'leader-{shiny}-battle')
            checks += f.checks
        finally: f.close()
    for page in (1, 5, 3):
        assert frames[(0, page)] != frames[(1, page)], f'P{page} lost the selected shiny palette'
    return checks


def legacy_capture_exp(exe, out):
    f = Flow(exe, page=12, team=0, wild=10, rarity=1)
    try:
        f.cmd('party_add 17 12 0 0 0'); f.cmd('party_exp 1 0'); f.cmd('tick 500')
        f.key('B'); f.key('A')
        f.cmd('save_fail 1'); f.key('A')
        assert f.state()['pet'] == 25 and f.state()['party'][1]['exp'] == 0
        f.key('A'); assert f.state()['pet'] == 17
        assert f.state()['level'] == 12 and f.state()['exp'] == 4320
        f.shot(out, 'legacy-level-exp-repaired')
        f.key('C'); f.key('C'); f.key('C'); f.key('C'); f.key('A')
        for _ in range(180):
            state = f.state()
            if state['page'] == 3 and state['presentation']['phase'] == 'choice': break
            f.cmd('tick 60')
        else: raise AssertionError('legacy member could not enter battle')
        f.key('B')
        for _ in range(600):
            state = f.state()
            assert state['level'] >= 12 and state['presentation']['visible_level'] >= 12, 'legacy capture dropped levels'
            if state['presentation']['phase'] == 'result': break
            f.cmd('tick 60')
        else: raise AssertionError('legacy member battle did not settle')
        state = f.state()
        assert state['active']['won'] and state['exp'] > 4320 and state['level'] >= 12
        f.shot(out, 'legacy-level-victory')
        return f.checks
    finally: f.close()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--out', type=Path, default=ROOT / 'reports/evidence/team-menu-2026-09-08')
    args = ap.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    exe, version = build()
    result = {'status': 'PASS', 'build': version, 'font_characters': font_check()}
    result['menu_checks'] = menu_routes(exe, args.out)
    result['party_checks'] = party_flow(exe, args.out)
    result['capacity_checks'] = single_and_capacity(exe, args.out)
    result['shiny_checks'] = shiny_leader(exe, args.out)
    result['legacy_exp_checks'] = legacy_capture_exp(exe, args.out)
    for page in (11, 12): assert page_value({'page': page}) == page
    for page in (7, 8, 13, True):
        try: page_value({'page': page})
        except ValueError: pass
        else: raise AssertionError(f'invalid page accepted: {page}')
    for page in (0, 9):
        f = Flow(exe, page=page, team=1)
        try: assert f.state()['party_count'] == 0 and f.state()['needs_starter']
        finally: f.close()
    result['dirty_full_checks'] = sum(result[k] for k in ('menu_checks', 'party_checks', 'capacity_checks', 'shiny_checks', 'legacy_exp_checks'))
    result['scope'] = 'Actual C pages/assets/nav; fixture world/save; real world/save checked separately.'
    (args.out / 'ui-flows.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__': main()
