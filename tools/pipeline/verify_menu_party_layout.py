#!/usr/bin/env python3
"""Compare P11/P12 pixels with independent original front/font asset decoding.

This is the artwork/layout gate. Navigation and world/save transactions are
covered separately; this script runs the real page/render/screen C sources.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png
from verify_battle_layout import read_fronts, read_species


def crop(pixels, x, y, width, height):
    return b''.join(pixels[((y + dy) * 240 + x) * 2:((y + dy) * 240 + x + width) * 2]
                    for dy in range(height))


def palettes():
    blob = (ROOT / 'assets/palettes.bin').read_bytes()
    magic, version, sets, colors, count = struct.unpack_from('<4sHHHH', blob)
    assert magic == b'PALS' and version == 1 and colors == 4 and count == 151
    return [[struct.unpack_from('<4H', blob, 12 + (style * sets + index) * 8)
             for index in range(sets)] for style in range(2)]


def font():
    blob = (ROOT / 'assets/font16.bin').read_bytes()
    magic, version, size, per, count = struct.unpack_from('<4sHHHI', blob)
    assert magic == b'FNT1' and size == 16 and per == 32
    codes = struct.unpack_from(f'<{count}H', blob, 14)
    glyphs = {chr(code): blob[14 + count * 2 + index * per:14 + count * 2 + (index + 1) * per]
              for index, code in enumerate(codes)}
    return glyphs


def verify_font(glyphs):
    required = set()
    for filename in ('play_menu.c', 'play_party.c'):
        source = (ROOT / 'firmware/main' / filename).read_text()
        source = re.sub(r'//[^\n]*|/\*.*?\*/', '', source, flags=re.S)
        for literal in re.findall(r'"((?:[^"\\]|\\.)*)"', source):
            required.update(char for char in literal if ord(char) > 127)
    assert not required - glyphs.keys(), 'missing visible UI glyphs: ' + ''.join(sorted(required - glyphs.keys()))
    assert all(any(glyphs[char]) for char in required), 'empty visible UI glyph'
    return len(required)


def sprite_oracle(size, packed, palette, width, height, *, scale=None, dest=None):
    source = [[(packed[(y * size + x) // 4] >> (6 - 2 * (x % 4))) & 3
               for x in range(size)] for y in range(size)]
    if scale is not None:
        rows = [[shade for shade in row for _ in range(scale)] for row in source for _ in range(scale)]
    else:
        # Pixel-center nearest neighbor, applied to the full source before trim.
        rows = [[source[(2 * y + 1) * size // (2 * dest)][(2 * x + 1) * size // (2 * dest)]
                 for x in range(dest)] for y in range(dest)]
    points = [(x, y) for y, row in enumerate(rows) for x, shade in enumerate(row) if shade != 3]
    assert points, 'original front is blank'
    left, top = min(x for x, _ in points), min(y for _, y in points)
    right, bottom = max(x for x, _ in points) + 1, max(y for _, y in points) + 1
    assert right - left <= width and bottom - top <= height, 'visible original artwork exceeds the display box'
    dx, dy = (width - (right - left)) // 2 - left, (height - (bottom - top)) // 2 - top
    result = [0xffff] * (width * height)
    for x, y in points:
        assert 0 <= x + dx < width and 0 <= y + dy < height, 'opaque source pixel would be clipped'
        result[(y + dy) * width + x + dx] = palette[rows[y][x]]
    assert any(color != 0xffff for color in result), 'front became invisible in original palette'
    return struct.pack(f'>{len(result)}H', *result), [right - left, bottom - top]


def text_oracle(text, glyphs, width=116):
    result = [0xffff] * (width * 16)
    pen, ink_right = 0, 0
    for char in text:
        assert char in glyphs, f'name glyph missing: {char}'
        glyph = glyphs[char]
        bearing = -4 if ord(char) < 128 else 0
        for y in range(16):
            for x in range(16):
                if not (glyph[y * 2 + x // 8] & (128 >> (x % 8))): continue
                px = pen + bearing + x
                assert 0 <= px < width, f'name escapes its reserved width: {text!r} at x={px}'
                ink_right = max(ink_right, px + 1)
                result[y * width + px] = 0
        pen += 8 if ord(char) < 128 else 16
    assert pen <= 104, f'name too wide for P11 left column: {text!r}'
    # Lv100 begins at x188. Party names start at 64; preserve visible separation.
    assert 188 - (64 + ink_right) >= 12, f'name touches level label: {text!r}'
    return struct.pack(f'>{len(result)}H', *result), ink_right


def compare(frame, box, expected, label):
    actual = crop(frame['pixels'], *box)
    assert actual == expected, f'{label}: {sum(a != b for a, b in zip(actual, expected))} mismatching RGB565 bytes'
    assert actual != b'\xff' * len(actual), f'{label}: blank content'


def verify_all(executable, evidence):
    species = read_species((ROOT / 'assets/gen1.bin').read_bytes())
    fronts = read_fronts((ROOT / 'assets/gen1_front.bin').read_bytes())
    legacy = {record['id']: record['name'] for record in json.loads((ROOT / 'data/pokemon_names/gs_legacy.json').read_text())['records']}
    pal = palettes()
    glyphs = font()
    font_count = verify_font(glyphs)
    count, dirty, max_ink, rows_seen = 0, 0, 0, set()
    for sid in range(1, 152):
        for style in range(2):
            # Both translations and both original palette variants for every
            # species; distribute the target among all six visible row slots.
            index = sid % 6 if style == 0 else 1 + sid % 5
            r = Renderer(executable)
            try:
                frame = r.command(f'boot 12 {sid if index == 0 else 25} 100 74 3 1 0 {style} 0')
                for filler in range(1, index): r.command(f'party_add {filler} 12 30 80 0')
                if index: r.command(f'party_add {sid} 100 100 65535 {style}')
                r.command('tick 500')
                # Artwork oracle compares the resting pose; animated selected frames
                # are independently covered by verify_comfort_motion.py.
                frame = r.command('page 12')
                state = r.inspect()
                assert state['party'][index]['species'] == sid and state['party'][index]['flags'] == style
                size, packed = fronts[sid]
                palette = pal[style][species[sid]['palette']]
                expected, _ = sprite_oracle(size, packed, palette, 32, 32, dest=32)
                y = 38 + index * 36
                compare(frame, (24, y, 32, 32), expected, f'P12 row{index + 1} #{sid} style{style}')
                name = legacy[sid] if style else species[sid]['name']
                expected_name, ink = text_oracle(name, glyphs)
                compare(frame, (64, y, 116, 16), expected_name, f'P12 complete name #{sid} style{style}')
                max_ink = max(max_ink, ink)
                rows_seen.add(index)
                assert r.command('check')['mismatch'] == 0; dirty += 1
                for _ in range(index): r.command('key 1 1')
                frame = r.command('key 0 1')
                expected, _ = sprite_oracle(size, packed, palette, 112, 112, scale=2)
                compare(frame, (64, 64, 112, 112), expected, f'P12 detail #{sid} style{style}')
                assert r.command('check')['mismatch'] == 0; dirty += 1
                r.command('key 0 1')  # Make this member the explicit leader for P11.
                assert r.inspect()['pet'] == sid
                frame = r.command('page 11')
                expected, _ = sprite_oracle(size, packed, palette, 104, 96, scale=1)
                compare(frame, (8, 88, 104, 96), expected, f'P11 visible original front #{sid} style{style}')
                assert r.command('check')['mismatch'] == 0; dirty += 1
                if sid in (25, 83, 122, 149, 150) and style == 0:
                    (evidence / f'P11-{sid:03d}.png').write_bytes(png(frame['pixels']))
                if sid == 149 and style == 1:
                    (evidence / 'P11-shiny-legacy-149.png').write_bytes(png(frame['pixels']))
                    r.command('page 12'); frame = r.command('key 0 1')
                    (evidence / 'P12-shiny-legacy-149.png').write_bytes(png(frame['pixels']))
                count += 1
            finally: r.close()
    assert rows_seen == set(range(6)), 'one of the six rows was not exercised'
    return {'species': 151, 'cases': count, 'sprite_pixel_comparisons': count * 3,
            'complete_name_comparisons': count, 'dirty_checks': dirty,
            'font_characters': font_count, 'rows_exercised': sorted(rows_seen),
            'max_name_ink_width': max_ink, 'minimum_name_level_gap': 188 - 64 - max_ink}


def negative_blank_menu():
    # Reproduce the rejected enlargement call: the lower-level thumbnail API
    # only supports reductions and silently returns for a destination of 80.
    with tempfile.TemporaryDirectory(prefix='menu_party_negative_') as directory:
        private = Path(directory)
        for relative in ('firmware/main', 'firmware/components/bsp/include', 'tools/inspector/host'):
            shutil.copytree(ROOT / relative, private / relative)
        shutil.copy2(ROOT / 'tools/inspector/native.py', private / 'tools/inspector/native.py')
        (private / 'assets').symlink_to(ROOT / 'assets', target_is_directory=True)
        target = private / 'firmware/main/play_menu.c'
        source = target.read_text()
        correct = 'game_ui_sprite_centered(band_y, 8, 88, 104, 96, front, size, size, 1, palette);'
        assert source.count(correct) == 1
        target.write_text(source.replace(correct, 'game_ui_thumbnail_centered(band_y, 8, 88, 104, 96, front, size, 80, palette);'))
        spec = importlib.util.spec_from_file_location('menu_party_negative_native', private / 'tools/inspector/native.py')
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        executable, _ = module.build()
        r = Renderer(executable)
        try:
            frame = r.command('boot 11 25 12 74 3 1 0')
            assert crop(frame['pixels'], 8, 88, 104, 96) == b'\xff' * (104 * 96 * 2), 'negative must reproduce the blank original portrait'
            size, packed = read_fronts((ROOT / 'assets/gen1_front.bin').read_bytes())[25]
            palette_index = read_species((ROOT / 'assets/gen1.bin').read_bytes())[25]['palette']
            expected, _ = sprite_oracle(size, packed, palettes()[0][palette_index], 104, 96, scale=1)
            try: compare(frame, (8, 88, 104, 96), expected, 'blank-menu negative')
            except AssertionError as error:
                assert 'mismatching RGB565 bytes' in str(error)
            else: raise AssertionError('blank-menu regression was not detected')
        finally: r.close()
    return 'Unsupported 80px enlargement produces blank P11; positive pixel oracle rejects it.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--evidence', type=Path, default=ROOT / 'reports/evidence/menu-party-2026-09-08')
    args = parser.parse_args(); args.evidence.mkdir(parents=True, exist_ok=True)
    executable, version = build()
    result = {'build': version, **verify_all(executable, args.evidence)}
    if args.negative: result['negative'] = negative_blank_menu()
    (args.evidence / 'layout.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
