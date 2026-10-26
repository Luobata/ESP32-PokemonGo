#!/usr/bin/env python3
"""Continuous bug-survey windows: first LCD frame, next target, balls and retry.

No screenshot/replay command is allowed to repair the LCD before checking it.
Widths are calculated from the committed species asset, independently of UI C.
"""
import argparse
import json
import os
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png

parser = argparse.ArgumentParser()
parser.add_argument('--binary', type=Path)
args = parser.parse_args()
exe, version = (args.binary, 'external') if args.binary else build()
out = Path(os.environ.get('POKEWALK_EVIDENCE_DIR',
                         ROOT / 'reports/evidence/bug-survey-capture-2026-10-26'))
out.mkdir(parents=True, exist_ok=True)
asset = (ROOT / 'assets/gen1.bin').read_bytes()
record_size = struct.unpack_from('<H', asset, 6)[0]
checks = changes = retries = 0
species = set()
yanma = []


def pixel(f, x, y):
    return struct.unpack_from('>H', f['pixels'], 2 * (240 * y + x))[0]


def width(sid, ball):
    # Entry fixture: Lv95, intimacy 0; all bug-survey targets are Lv50.
    p = 16 + (sid - 1) * record_size
    rate, speed = asset[p + 6], asset[p + 14]
    weight = struct.unpack_from('<H', asset, p + 18)[0]
    factor = {1: 1500, 2: 2000, 6: 1500}.get(ball, 1000)
    if ball == 3:
        return 200
    if ball == 4 and speed >= 100:
        factor = 4000
    if ball == 5:
        factor = 3000 if weight >= 2000 else 2000 if weight >= 1000 else 1000
    return min(200, max(3, (rate * 550 * factor + 500000) // 1000000))


def verify_bar(f, sid, ball):
    global checks
    w = width(sid, ball)
    start = 20 + (200 - w) // 2
    # First row of the blue region has no arrow pixels in either renderer.
    for y in (217, 222 if args.binary else 232):
        mark = [x for x in range(20, 221) if pixel(f, x, y) == 0]
        assert len(mark) == 1, (sid, ball, y, mark)
        for x in range(20, 221):
            if x == mark[0]:
                continue
            assert (pixel(f, x, y) == (0x249f if args.binary else 0x247f)) == (start <= x <= start + w), (
                'stale window', sid, ball, w, x, y, pixel(f, x, y))
    checks += 1
    return w


for seed in range(24):
    r = Renderer(exe)
    def key(i):
        return r.command(f'key {i} 1')
    try:
        r.command('boot 1 145 95 74 3 81 0 0 0')
        r.command(f'tick {seed}')
        r.command('johto_fixture 8 0')
        for ball in range(8):
            r.command(f'inventory {ball} {20 if ball == 0 else 1}')
        r.command('page 18')
        for i in (2, 2, 1, 2, 1, 2):
            key(i)
        current_ball = 0
        previous = None
        for node in range(6):
            for _ in range((node + seed) % 3):
                key(1)
            f = key(2)  # First frame of the NEW target; no tick or replay first.
            state = r.inspect()['activity']
            assert state['phase'] == 1 and state['node'] == node + 1
            sid = state['found']
            species.add(sid)
            w = verify_bar(f, sid, current_ball)
            if previous is not None and previous != w:
                changes += 1
            if sid == 193:
                yanma.append(dict(seed=seed, node=node + 1, ball=current_ball, width=w))
                if current_ball == 0:
                    (out / 'yanma-first-frame.png').write_bytes(png(f['pixels']))
            key(1)  # Change ball: wide -> narrow and narrow -> wide in place.
            for _ in range(8):
                f = key(2)
                current_ball = (current_ball + 1) % 8
                verify_bar(f, sid, current_ball)
            key(0)
            # For Yanma specifically: miss at the outer endpoint, then verify
            # that retry still has exactly the same width, on the same page.
            if sid == 193 and state['attempts'] < 3:
                for _ in range(60):
                    f = r.command('tick 40')
                    mark = [x for x in range(20, 221) if pixel(f, x, 217) == 0][0]
                    if mark < 35:
                        break
                verify_bar(f, sid, current_ball)
                r.command('key 2 0')
                r.command('tick 180')
                for event in (4, 1, 5):
                    r.command(f'key 2 {event}')
                r.command('tick 14000')
                assert r.inspect()['activity']['phase'] == 1
                f = r.command('tick 0')
                verify_bar(f, sid, current_ball)
                (out / 'yanma-after-miss.png').write_bytes(png(f['pixels']))
                retries += 1
            # Ordinary pause/resume must reconstruct this target, not candidate.
            r.command('key 1 3')
            f = key(2)
            verify_bar(f, sid, current_ball)
            key(1); key(1); key(2)  # Skip -> next habitat choice.
            previous = w
        assert r.inspect()['activity']['phase'] == 3
    finally:
        r.close()

if not args.binary:
    # Exhausted balls/attempts must not start a fake throw and later redraw the
    # previous bar. A fresh press after replenishment/change still works.
    for exhausted_balls in (False, True):
        r = Renderer(exe)
        try:
            r.command('boot 1 145 95 74 3 81 0 0 0')
            r.command('johto_fixture 8 0'); r.command('page 18')
            for i in (2, 2, 1, 2, 1, 2, 2):
                r.command(f'key {i} 1')
            if exhausted_balls:
                r.command('inventory 0 0'); r.command('page 18')
            else:
                for attempt in range(3):
                    # A miss at the first visible endpoint, then another try.
                    r.command('page 18'); r.command('key 2 0')
                    r.command('tick 180')
                    for event in (4, 1, 5):
                        r.command(f'key 2 {event}')
                    r.command('tick 14000')
                    assert r.inspect()['activity']['attempts'] == attempt + 1
            before = r.inspect()
            r.command('key 2 0')
            assert not r.inspect()['display']['busy']
            f = r.command('tick 1000')
            assert r.inspect()['activity'] == before['activity']
            assert r.inspect()['inventory'] == before['inventory']
            assert not any(pixel(f, x, 217) == 0x247f for x in range(20, 221))
        finally:
            r.close()

assert len(species) == 15 and changes and retries and yanma
report = dict(build=version, pixel_checks=checks, changed_target_windows=changes,
              species=sorted(species), yanma_retries=retries, yanma=yanma,
              hardware=False, passed=True)
(out / 'continuous-windows.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps({k: v for k, v in report.items() if k != 'yanma'}))
