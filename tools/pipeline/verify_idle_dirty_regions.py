#!/usr/bin/env python3
"""Compare complete animation cycles and every party row with full redraws."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build

parser = argparse.ArgumentParser()
parser.add_argument('--baseline', type=Path, required=True)
args = parser.parse_args()
exe, version = build()
old = new = None
checks = 0


def command(value):
    global old, new, checks
    if value.startswith('boot '):
        if old:
            old.close()
            new.close()
        old, new = Renderer(args.baseline), Renderer(exe)
    expected, actual = old.command(value), new.command(value)
    assert expected['pixels'] == actual['pixels'], (checks, value)
    assert new.command('check')['mismatch'] == 0, (checks, value, 'dirty region')
    checks += 1


def animate(count=50):
    for _ in range(count):
        command('tick 80')


try:
    for species in (1, 25, 115, 130, 143, 201, 235, 249, 251):
        command(f'boot 5 {species} 60 130 4 81 1 0 1')
        animate(100)
        command('key 1 1'); command('key 1 1'); command('key 2 1')
        animate()  # Benefits page contains no animated sprite.
        command(f'boot 12 {species} 60 130 4 81 1 0 1')
        for row in range(6):
            animate()
            command('key 2 1')
            animate()
            command('key 1 3')
            command('key 1 1')
    print(json.dumps({'passed': True, 'checks': checks, 'renderer': version,
                      'scope': 'care cycles/benefits, six party rows/details, before-after pixels and full-redraw oracle'}))
finally:
    if old:
        old.close()
        new.close()
