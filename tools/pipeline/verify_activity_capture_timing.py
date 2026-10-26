#!/usr/bin/env python3
"""Bug survey: judge actual LCD pixels, physical gestures and delayed saves.

Uses the production page, navigation, capture resolver and activity transaction.
Host timings are fault fixtures, not a claim of physical LCD FPS or NVS latency.
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
parser.add_argument('--baseline', type=Path, help='Optional pre-fix native executable')
args = parser.parse_args()
OUT = Path(os.environ.get('POKEWALK_EVIDENCE_DIR',
                         ROOT / 'reports/evidence/bug-survey-capture-2026-10-25'))
OUT.mkdir(parents=True, exist_ok=True)
exe, version = build()


def pixel(frame, x, y):
    return struct.unpack_from('>H', frame['pixels'], 2 * (240 * y + x))[0]


def pointer(frame, y=217):
    points = [x for x in range(20, 221) if pixel(frame, x, y) == 0]
    assert len(points) == 1, points
    return points[0]


def setup(binary=exe, seed=0, ball=0, habitat=0):
    r = Renderer(binary)
    r.command('boot 1 145 95 74 3 81 0 0 0')
    r.command(f'tick {seed}')
    r.command('johto_fixture 8 0')
    r.command('page 18')
    for button in (2, 2, 1, 2, 1, 2):
        r.command(f'key {button} 1')
    for _ in range(habitat):
        r.command('key 1 1')
    r.command('key 2 1')
    assert r.inspect()['activity']['phase'] == 1
    r.command(f'inventory {ball} 1')
    if ball:
        r.command('key 1 1')
        for _ in range(ball):
            r.command('key 2 1')
        r.command('key 0 1')
    reference = r.command('tick 300')
    blue = [x for x in range(20, 221) if pixel(reference, x, 217) == (0x247f if binary == exe else 0x249f)]
    window = (min(blue), max(blue))
    r.command('page 18')  # Resume the same persisted found partner, reset bar.
    return r, window


def pixels_match(r):
    assert r.command('check')['mismatch'] == 0


cases = hits = misses = between_frames = 0
species = set()
for seed in (0, 17):
    for ball in range(8):
        for elapsed in (0, 89, 99, 149, 299, 319, 509, 549, 599, 899, 1049, 1199):
            for delay in (0, 180, 400):
                for event in (0, 1):  # Physical PRESS and preview CLICK.
                    r, (left, right) = setup(seed=seed, ball=ball)
                    try:
                        f = r.command(f'tick {elapsed}')
                        p = pointer(f)
                        assert pointer(f, 232) == p  # Both 20-row LCD strips.
                        expected = left <= p <= right
                        before = r.inspect()
                        species.add(before['activity']['found'])
                        # Screenshot replay must not advance the displayed sample.
                        pixels_match(r)
                        r.command(f'save_delay {delay}')
                        thrown = r.command(f'key 2 {event}')
                        immediate = r.inspect()
                        assert thrown['ms'] == f['ms'], 'input waited for Flash'
                        assert immediate['display']['busy']
                        assert immediate['activity'] == before['activity']
                        assert immediate['inventory'] == before['inventory']
                        r.command('tick 900')  # Commit in the open-ball hold.
                        after = r.inspect()
                        assert after['activity']['attempts'] == 1
                        assert (after['activity']['phase'] == 2) == expected, (
                            seed, ball, elapsed, delay, event, left, right, p)
                        assert after['inventory'][ball] == before['inventory'][ball] - 1
                        assert after['display']['busy']
                        if event == 0:
                            r.command('tick 180')
                            for followup in (4, 1, 5):
                                r.command(f'key 2 {followup}')
                            assert r.inspect()['activity'] == after['activity']
                            assert r.inspect()['inventory'] == after['inventory']
                        pixels_match(r)
                        hits += expected
                        misses += not expected
                        between_frames += elapsed % 50 != 0
                        cases += 1
                    finally:
                        r.close()

# Exercise the exact inclusive blue endpoints (not merely its center).
edges = 0
for seed, habitat in ((0, 0), (17, 1)):
    for ball in range(8):
        r, (left, right) = setup(seed=seed, habitat=habitat, ball=ball)
        species.add(r.inspect()['activity']['found'])
        r.close()
        for x in (left - 1, left, right, right + 1):
            if not 20 <= x <= 220:
                continue
            r, _ = setup(seed=seed, habitat=habitat, ball=ball)
            try:
                f = r.command(f'stall {(x - 20) * 3}')
                assert pointer(f) == x
                r.command('key 2 0')
                r.command('tick 900')
                assert (r.inspect()['activity']['phase'] == 2) == (left <= x <= right)
                edges += 1
            finally:
                r.close()

# Save rejection cannot spend a ball/attempt or silently retry on release/click.
for delay in (0, 400, 2000):
    r, _ = setup()
    try:
        r.command('tick 300')
        before = r.inspect()
        r.command('save_fail 1')
        r.command(f'save_delay {delay}')
        r.command('key 2 0')
        r.command('tick 900')
        for e in (4, 1, 5):
            r.command(f'key 2 {e}')
        after = r.inspect()
        assert after['activity'] == before['activity']
        assert after['inventory'] == before['inventory']
        assert not after['display']['busy']
        r.command('key 2 0')  # A fresh physical press can retry.
        r.command('tick 900')
        assert r.inspect()['activity']['attempts'] == 1
        assert r.inspect()['inventory'][0] == before['inventory'][0] - 1
        pixels_match(r)
    finally:
        r.close()

# Real LCD submissions, not a formula inferred from the implementation. Also
# compare every dirty render to a complete replay throughout a pointer cycle.
r, _ = setup()
try:
    bands = []
    for _ in range(48):
        before = r.inspect()['display']['submitted_bands']
        f = r.command('tick 40')
        bands.append(r.inspect()['display']['submitted_bands'] - before)
        pixels_match(r)
    assert set(bands) == {2}, bands
    (OUT / 'pointer.png').write_bytes(png(f['pixels']))
finally:
    r.close()

# Blocking NVS must not eat the beginning or shorten the capture animation.
timelines = []
for delay in (0, 180, 400, 2000):
    r, _ = setup()
    try:
        r.command('tick 300')
        r.command(f'save_delay {delay}')
        thrown = r.command('key 2 0')
        r.command('tick 900')
        committed = r.inspect()
        elapsed = 0
        reveal = None
        while r.inspect()['display']['busy'] and elapsed < 14000 + delay:
            f = r.command('tick 50')
            elapsed = f['ms'] - thrown['ms']
            pixels_match(r)
            now = r.inspect()
            assert now['inventory'] == committed['inventory']
            assert now['activity'] == committed['activity']
            if now['music'] == 16 and reveal is None:
                reveal = elapsed
        assert reveal is not None and 9117 + delay <= reveal <= 9217 + delay, (delay, reveal)
        assert 13121 + delay <= elapsed <= 13221 + delay, (delay, elapsed)
        timelines.append(dict(save_delay_ms=delay, result_ms=reveal, exit_ms=elapsed))
    finally:
        r.close()

# The normal hardware CLICK arrives during flight, before persistence. It must
# neither throw again nor change the visible judgment latched on PRESS.
r, _ = setup()
try:
    r.command('tick 300')
    original = r.inspect()
    r.command('key 2 0')
    r.command('tick 180')
    for e in (4, 1, 5):
        r.command(f'key 2 {e}')
    assert r.inspect()['activity'] == original['activity']
    assert r.inspect()['inventory'] == original['inventory']
    r.command('tick 720')
    assert r.inspect()['activity']['attempts'] == 1
    assert r.inspect()['activity']['phase'] == 2
    assert r.inspect()['inventory'][0] == original['inventory'][0] - 1
finally:
    r.close()

# Interrupted pre-commit presentation has not awarded/spent anything. Forced
# page entry models abandoning the process; ordinary navigation is busy-locked.
r, _ = setup()
try:
    original = r.inspect()
    r.command('key 2 0');r.command('tick 200')
    r.command('page 0');r.command('tick 1000');r.command('page 18')
    assert r.inspect()['activity'] == original['activity']
    assert r.inspect()['inventory'] == original['inventory']
    assert not r.inspect()['display']['busy']
finally:
    r.close()

baseline = None
if args.baseline:
    r, _ = setup(binary=args.baseline)
    try:
        r.command('tick 300')
        r.command('key 2 0')
        baseline = dict(attempts_after_press=r.inspect()['activity']['attempts'],
                        animation_after_press=r.inspect()['display']['busy'])
        assert baseline['attempts_after_press'] == 0  # Reproduces the old defect.
        assert not baseline['animation_after_press']
    finally:
        r.close()
    r, (left, right) = setup(binary=args.baseline)
    try:
        f = r.command('tick 549')
        # Old page draws a two-pixel pointer; the whole visible mark is blue.
        mark = [x for x in range(20, 221) if pixel(f, x, 217) == 0]
        assert mark and all(left <= x <= right for x in mark)
        r.command('key 2 1')
        baseline['visible_hit_rejected'] = r.inspect()['activity']['phase'] == 1
        assert baseline['visible_hit_rejected']
    finally:
        r.close()
assert hits and misses and between_frames
report = dict(build=version, cases=cases, visible_hits=hits, visible_misses=misses,
              between_frames=between_frames, species=sorted(species), edge_cases=edges,
              bands_per_pointer_frame=sorted(set(bands)), timelines=timelines,
              baseline=baseline, physical_device_fps_measured=False, passed=True)
(OUT / 'timing.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
