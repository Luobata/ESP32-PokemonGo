#!/usr/bin/env python3
"""Verify the actual C menu's screen-off entry, pixels, and wake-up return.

The screen-idle engine has a separate gate. This covers the product entry and
its integration with the real native menu and input dispatch.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png
from verify_menu_party_layout import crop, font


def text_pixels(text, glyphs, width, centered=False):
    points, pen = [], 0
    for char in text:
        assert char in glyphs and (char == ' ' or any(glyphs[char])), f'missing/blank glyph {char}'
        glyph = glyphs[char]
        for y in range(16):
            for x in range(16):
                if glyph[y * 2 + x // 8] & (128 >> (x % 8)):
                    points.append((pen + x - (4 if ord(char) < 128 else 0), y))
        pen += 8 if ord(char) < 128 else 16
    assert points
    dx = dy = 0
    if centered:
        left, top = min(x for x, _ in points), min(y for _, y in points)
        right, bottom = max(x for x, _ in points) + 1, max(y for _, y in points) + 1
        dx, dy = (width - (right - left)) // 2 - left, (16 - (bottom - top)) // 2 - top
    pixels = [0xffff] * (width * 16)
    for x, y in points:
        x, y = x + dx, y + dy
        assert 0 <= x < width and 0 <= y < 16, f'text escapes its reserved line: {text}'
        pixels[y * width + x] = 0
    return pixels


def assert_text(frame, box, text, glyphs, color=0, centered=False):
    expected = text_pixels(text, glyphs, box[2], centered)
    expected = [color if pixel == 0 else pixel for pixel in expected]
    assert crop(frame['pixels'], *box) == struct.pack(f'>{len(expected)}H', *expected), f'incomplete/misaligned visible text: {text}'


def verify(executable, evidence):
    r = Renderer(executable)
    dirty = 0
    def command(line):
        nonlocal dirty
        frame = r.command(line)
        assert r.command('check')['mismatch'] == 0, 'screen-off menu left stale horizontal bands'
        dirty += 1
        return frame
    def key(button, hold=False): return command(f'key {"ABC".index(button)} {3 if hold else 1}')
    def selected(index):
        view = r.inspect()['menu_view']
        assert view['options'] and view['option_selected'] == index, view
    try:
        frame = command('boot 11 25 12 74 3 1 0 0 0')
        for _ in range(4): key('B')
        frame = key('A'); selected(0)
        glyphs = font()
        for y, label in ((80, '译名'), (112, '立即熄屏'), (144, '返回菜单')):
            assert_text(frame, (40, y, 116, 16), label, glyphs)
        # All three indices wrap in both directions; return is no longer index1.
        key('B', True); selected(2)
        key('B'); selected(0)
        key('B'); selected(1)
        key('B'); selected(2)
        key('B', True); selected(1)
        frame = command('check')
        muted = ((0x68 & 0xf8) << 8) | ((0x68 & 0xfc) << 3) | (0x68 >> 3)
        assert_text(frame, (12, 196, 216, 16), '60秒无操作自动熄屏', glyphs, muted, True)
        assert_text(frame, (12, 224, 216, 16), '任意键亮屏', glyphs, 0, True)
        assert_text(frame, (12, 248, 216, 16), '按A立即熄屏', glyphs, muted, True)
        (evidence / 'P11-screen-off-option.png').write_bytes(png(frame['pixels']))
        before = r.inspect()
        off_frame = key('A')
        after = r.inspect()
        assert after['display']['off'], 'A on the visible entry did not request screen off'
        assert after['display']['timeout_ms'] == 60000 and after['display']['backlight'] == 0
        assert off_frame['pixels'] == bytes(240 * 320 * 2), 'off display still exposes lit preview pixels'
        assert after['menu_view'] == before['menu_view'], 'screen-off changed the selected page/item'
        assert after['names'] == before['names'] and after['party'] == before['party']
        # Waking with A must consume that key, otherwise the same selected entry
        # immediately switches the screen off again and cannot be exited.
        awake_frame = key('A')
        assert not r.inspect()['display']['off'], 'wake-up A was re-dispatched and switched the screen off again'
        assert r.inspect()['display']['backlight'] == 100
        assert awake_frame['pixels'] == frame['pixels'], 'wake-up did not restore the same option screen'
        selected(1)
        key('B'); selected(2)
        key('A'); assert not r.inspect()['menu_view']['options']
        key('A'); selected(0)
        previous = r.inspect()['names']; key('A')
        assert r.inspect()['names'] != previous, 'name preference no longer works'
        key('C'); assert not r.inspect()['menu_view']['options']
        key('C'); assert r.inspect()['page'] == 1
        return {'three_rows': True, 'bidirectional_wrap': True, 'original_names_preserved': True,
                'manual_off': True, 'wake_key_consumed': True, 'same_selection_after_wake': True,
                'text_pixel_checks': 6, 'dirty_checks': dirty}
    finally: r.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=ROOT / 'reports/evidence/screen-idle-2026-09-08')
    args = parser.parse_args(); args.evidence.mkdir(parents=True, exist_ok=True)
    executable, version = build()
    result = {'build': version, **verify(executable, args.evidence)}
    (args.evidence / 'menu.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
