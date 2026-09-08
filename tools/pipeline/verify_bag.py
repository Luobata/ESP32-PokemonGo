#!/usr/bin/env python3
"""Drive actual P5/P10 C pages; item persistence is verified separately."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png
from server import page_value


def crop(pixels, x, y, w, h):
    return b''.join(pixels[((y + row) * 240 + x) * 2:((y + row) * 240 + x + w) * 2] for row in range(h))


class Flow:
    def __init__(self, executable, page=10, pet=25, level=12):
        self.renderer = Renderer(executable)
        self.checks = 0
        self.frame = self.renderer.command(f'boot {page} {pet} {level} 74 3 1 0')
        self.check()

    def close(self): self.renderer.close()
    def state(self): return self.renderer.inspect()

    def check(self):
        frame = self.renderer.command('check')
        assert frame['mismatch'] == 0, f'stale band pixels on {frame["page"]}: {frame["mismatch"]}'
        self.frame = frame
        self.checks += 1

    def command(self, command):
        self.frame = self.renderer.command(command)
        self.check()
        return self.frame

    def key(self, key, long=False):
        return self.command(f'key {"ABC".index(key)} {3 if long else 1}')

    def select(self, item):
        for _ in range(19):
            if self.state()['bag_selected'] == item: return
            self.key('B')
        raise AssertionError('selected item never became reachable')

    def stock(self, item, quantity):
        self.command(f'inventory {item} {quantity}')
        self.command('tick 500')


def verify_font():
    blob = (ROOT / 'assets/font16.bin').read_bytes()
    magic, version, size, per, count = struct.unpack_from('<4sHHHI', blob)
    assert magic == b'FNT1' and size == 16 and per == 32
    codes = struct.unpack_from(f'<{count}H', blob, 14)
    required = set()
    for filename in ('play_bag.c', 'play_care.c', 'items.c'):
        source = (ROOT / 'firmware/main' / filename).read_text()
        source = re.sub(r'//[^\n]*|/\*.*?\*/', '', source, flags=re.S)
        source = re.sub(r'ESP_LOG[EWIDV]\([^;]*;', '', source, flags=re.S)
        for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', source):
            required.update(char for char in literal if ord(char) > 127)
    missing = required - {chr(code) for code in codes}
    assert not missing, 'new bag/care font characters missing: ' + ''.join(sorted(missing))
    for char in required:
        start = 14 + count * 2 + codes.index(ord(char)) * per
        assert any(blob[start:start + per]), f'empty glyph: {char}'
    return len(required)


def browse(executable, evidence=None):
    f = Flow(executable)
    try:
        for item in range(19): f.command(f'inventory {item} 0')
        f.command('tick 500')
        first = f.frame['pixels']
        frames = []
        for selected in range(19):
            assert f.state()['bag_selected'] == selected, 'B must advance exactly one item'
            assert f.state()['inventory'] == [0] * 19
            page_start = 0 if selected < 8 else 8 if selected < 15 else 15
            page_end = 8 if selected < 8 else 15 if selected < 15 else 19
            first_item = page_start + (selected - page_start) // 4 * 4
            row_count = min(4, page_end - first_item)
            for row in range(row_count):
                region = crop(f.frame['pixels'], 56, 64 + row * 24, 136, 16)
                assert region != b'\xff' * len(region), f'zero-stock item row hidden #{first_item + row}'
            if row_count == 3:
                empty = crop(f.frame['pixels'], 8, 132, 224, 24)
                assert empty == b'\xff' * len(empty), 'short pocket page retained its previous fourth row'
            frames.append(hashlib.sha256(f.frame['pixels']).hexdigest())
            if evidence and selected in (0, 4, 8, 12, 15):
                (evidence / f'P10-zero-{selected:02d}.png').write_bytes(png(f.frame['pixels']))
            f.key('B')
        assert f.frame['pixels'] == first, '19 forward steps must return to the same display'
        assert len(set(frames)) == 19
        f.key('B', long=True)
        assert f.state()['bag_selected'] == 18, 'long B must wrap backward to the last item'
        f.key('B'); assert f.state()['bag_selected'] == 0
        before = f.state(); f.key('A')
        assert f.state() == before, 'ball A must only explain capture-page use'
        f.select(2)
        before_pixels = f.frame['pixels']
        f.command('inventory 2 1')
        f.command('tick 500')
        assert f.frame['pixels'] != before_pixels, 'background stock update never reached the displayed quantity'
        # Only the high ball count changes; the list, description and header stay stable.
        changed = [(i // 2 % 240, i // 2 // 240) for i in range(0, len(before_pixels), 2)
                   if f.frame['pixels'][i:i+2] != before_pixels[i:i+2]]
        assert changed and all(196 <= x < 228 and 112 <= y < 128 for x, y in changed)
        f.key('C'); assert f.state()['page'] == 5
        for _ in range(3): f.key('B')
        f.key('A'); assert f.state()['page'] == 10, 'P5 must expose the bag as its fourth menu action'
        return {'items': 19, 'pocket_pages': 5, 'zero_stock_visible': True,
                'reverse_wrap': True, 'live_quantity_refresh': True, 'dirty_checks': f.checks}
    finally: f.close()


def care_food(executable, evidence=None):
    f = Flow(executable, page=5)
    try:
        f.command('nurture 20 20 20'); f.stock(15, 2)
        before = f.state(); f.key('A'); fed = f.state()
        assert fed['inventory'][15] == 1, 'P5 feeding must consume one berry'
        assert fed['nurture']['satiety'] == 50 and fed['nurture']['mood'] == 25
        assert fed['nurture']['stamina'] == before['nurture']['stamina']
        if evidence: (evidence / 'P5-fed.png').write_bytes(png(f.frame['pixels']))
        f.stock(15, 0); before = f.state(); f.key('A')
        assert f.state() == before, 'empty-stock feeding changed nurture or inventory'
        if evidence: (evidence / 'P5-empty.png').write_bytes(png(f.frame['pixels']))
        f.stock(15, 1); before = f.state(); f.command('save_fail 1'); f.key('A')
        assert f.state() == before, 'failed feed save published its effect or consumption'
        if evidence: (evidence / 'P5-save-failed.png').write_bytes(png(f.frame['pixels']))
        f.key('A'); assert f.state()['inventory'][15] == 0
        stock = f.state()['inventory']; f.key('B'); f.key('A')
        assert f.state()['inventory'] == stock, 'free play consumed an item'
        f.key('B'); f.key('A')
        assert f.state()['inventory'] == stock, 'free rest consumed an item'
        return {'feed_consumes_berry': True, 'empty_and_failed_save_unchanged': True,
                'free_play_rest_preserved': True, 'dirty_checks': f.checks}
    finally: f.close()


def usable_items(executable, evidence=None):
    checks, evolutions = 0, []
    for item, species, level, target in (
        (8, 37, 12, 38), (9, 61, 12, 62), (10, 25, 12, 26),
        (11, 44, 12, 45), (12, 35, 12, 36), (13, 64, 12, 65),
        (14, 1, 16, 2), (8, 133, 12, 136), (9, 133, 12, 134), (10, 133, 12, 135),
    ):
        f = Flow(executable, pet=species, level=level)
        try:
            f.stock(item, 1); f.select(item); before = f.state(); f.key('A'); after = f.state()
            assert after['pet'] == target and after['party'][0]['species'] == target
            assert after['inventory'][item] == 0 and after['exp'] == before['exp'] and after['level'] == before['level']
            if evidence and item in (10, 13, 14) and species != 133:
                (evidence / f'P10-used-{item:02d}.png').write_bytes(png(f.frame['pixels']))
            f.key('A'); assert f.state() == after, 'empty evolution item was usable again'
            evolutions.append([item, species, target]); checks += f.checks
        finally: f.close()
    expected = {15: (50, 25, 20, 0), 16: (20, 15, 90, 0),
                17: (40, 20, 45, 0), 18: (20, 45, 20, 2)}
    for item in range(15, 19):
        f = Flow(executable)
        try:
            f.command('nurture 20 20 20'); f.stock(item, 1); f.select(item); f.key('A')
            state = f.state(); n = state['nurture']
            assert tuple(n[key] for key in ('satiety', 'mood', 'stamina', 'intimacy')) == expected[item]
            assert state['inventory'][item] == 0
            if evidence: (evidence / f'P10-used-{item:02d}.png').write_bytes(png(f.frame['pixels']))
            checks += f.checks
        finally: f.close()
    return {'evolutions': evolutions, 'care_items': 4, 'dirty_checks': checks}


def failures(executable, evidence=None):
    f = Flow(executable, pet=1, level=15)
    try:
        for item in (10, 14):
            f.stock(item, 1); f.select(item); before = f.state(); f.key('A')
            assert f.state() == before, 'incompatible or under-level item changed game state'
        if evidence: (evidence / 'P10-level-too-low.png').write_bytes(png(f.frame['pixels']))
        f.select(15); f.stock(15, 1); f.command('nurture 20 20 20')
        before = f.state(); f.command('save_fail 1'); f.key('A')
        assert f.state() == before, 'failed item save changed game state'
        if evidence: (evidence / 'P10-save-failed.png').write_bytes(png(f.frame['pixels']))
        f.key('A'); assert f.state()['inventory'][15] == 0
        f.stock(15, 1); f.command('nurture 100 100 100'); before = f.state(); f.key('A')
        assert f.state() == before, 'food without a benefit was consumed'
        return {'wrong_target': True, 'level_gate': True, 'save_failure_retry': True,
                'full_axes_no_consumption': True, 'dirty_checks': f.checks}
    finally: f.close()


def natural_evolution(executable, evidence=None):
    checks = 0
    for species in (25, 64):
        f = Flow(executable, page=5, pet=species)
        try:
            f.command('care_progress 100 65535')
            row = crop(f.frame['pixels'], 8, 160, 104, 16)
            assert row == b'\xff' * len(row), 'stone/trade species exposed a free evolution action'
            for _ in range(4): f.key('B')
            before = f.state(); f.key('A')
            assert f.state()['pet'] == species, 'stone/trade species evolved without its item'
            assert f.state()['inventory'][15] == before['inventory'][15] - 1
            checks += f.checks
        finally: f.close()
    f = Flow(executable, page=5, pet=1, level=12)
    try:
        f.command('care_progress 100 65535')
        for _ in range(4): f.key('B')
        before = f.state()
        if evidence: (evidence / 'P5-natural-ready.png').write_bytes(png(f.frame['pixels']))
        f.command('save_fail 1'); f.key('A'); f.command('tick 450')
        assert f.state() == before, 'failed natural evolution changed the partner or inventory'
        if evidence: (evidence / 'P5-natural-save-failed.png').write_bytes(png(f.frame['pixels']))
        f.key('A'); f.command('tick 450')
        after = f.state()
        assert after['pet'] == 2 and after['inventory'] == before['inventory'], 'natural LEVEL evolution was removed or spent a machine'
        assert after['level'] == before['level'] and after['exp'] == before['exp']
        checks += f.checks
        return {'level_natural_path': True, 'stone_trade_require_items': True,
                'save_failure_retry': True, 'dirty_checks': checks}
    finally: f.close()


def negative_probes():
    tests = [
        ('B skips items', 'play_bag.c', '(ev == BSP_BTN_LONG ? -1 : 1)', '(ev == BSP_BTN_LONG ? -1 : 2)',
         browse, 'B must advance exactly one item'),
        ('missing berry transaction', 'play_care.c',
         'item_use_status_t status = world_item_use(s_w.species, ITEM_BERRY, &result);',
         'item_use_status_t status = ITEM_USE_OK;', care_food, 'P5 feeding must consume one berry'),
    ]
    detected = []
    for label, filename, before, after, run, expected in tests:
        with tempfile.TemporaryDirectory(prefix='bag_negative_') as directory:
            private = Path(directory)
            for relative in ('firmware/main', 'firmware/components/bsp/include', 'tools/inspector/host'):
                shutil.copytree(ROOT / relative, private / relative)
            shutil.copy2(ROOT / 'tools/inspector/native.py', private / 'tools/inspector/native.py')
            (private / 'assets').symlink_to(ROOT / 'assets', target_is_directory=True)
            target = private / 'firmware/main' / filename
            source = target.read_text(); assert source.count(before) == 1
            target.write_text(source.replace(before, after))
            spec = importlib.util.spec_from_file_location('bag_negative_native', private / 'tools/inspector/native.py')
            module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
            executable, _ = module.build()
            try: run(executable)
            except AssertionError as error:
                assert expected in str(error), f'{label} failed for an unrelated reason: {error}'
                detected.append(label)
            else: raise AssertionError(f'negative regression was not detected: {label}')
    return detected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--evidence', type=Path, default=ROOT / 'reports/evidence/bag-2026-09-08')
    args = parser.parse_args(); args.evidence.mkdir(parents=True, exist_ok=True)
    assert page_value({'page': 10}) == 10
    for value in (7, 8, 13):
        try: page_value({'page': value})
        except ValueError: pass
        else: raise AssertionError('unsupported preview page accepted')
    executable, version = build()
    result = {'build': version, 'font_characters': verify_font(),
              'browse': browse(executable, args.evidence), 'care': care_food(executable, args.evidence),
              'use': usable_items(executable, args.evidence), 'failures': failures(executable, args.evidence),
              'natural': natural_evolution(executable, args.evidence)}
    if args.negative: result['negative_caught'] = negative_probes()
    result['scope'] = 'Actual P5/P10/nav/render C with runtime inventory/NVS fixtures; real world/save transactions have separate gates.'
    (args.evidence / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
