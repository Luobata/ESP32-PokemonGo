#!/usr/bin/env python3
"""Drive the actual menu renderer and input routing, with desktop NVS/display stubs."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import Renderer, build, png

out = ROOT/'reports/evidence/settings-fixes-2026-09-19'
out.mkdir(parents=True, exist_ok=True)
exe, version = build()
r = Renderer(exe)
checks = 0


def cmd(line):
    global checks
    result = r.command(line)
    assert r.command('check')['mismatch'] == 0, line
    checks += 1
    return result


def key(n, event=1):
    return cmd(f'key {n} {event}')


def screenshot(name):
    (out/f'{name}.png').write_bytes(png(cmd('check')['pixels']))


try:
    cmd('boot 11 25 40 74 3 123 0 0 0')
    for _ in range(5):
        key(1)
    key(2)
    for _ in range(7):
        key(1)
    assert r.inspect()['menu_view']['option_selected'] == 7
    key(2)
    for _ in range(6):
        key(1)
    assert r.inspect()['display']['backlight'] == 40
    screenshot('brightness-40')
    cmd('save_fail 1')
    key(1)
    assert r.inspect()['display']['backlight'] == 40
    screenshot('brightness-save-error')
    key(1)
    assert r.inspect()['display']['backlight'] == 30
    key(0)
    key(2)  # complete edit, remain in options
    key(2, 3)  # long C sleeps even inside options
    assert r.inspect()['display']['off']
    assert r.inspect()['display']['backlight'] == 0
    key(2)  # wake must not enter editing
    assert r.inspect()['display']['backlight'] == 40
    key(1)
    assert r.inspect()['menu_view']['option_selected'] == 8
    screenshot('options-return')
    key(0)
    key(2)
    for _ in range(12):
        key(1)
    assert r.inspect()['display']['backlight'] == 10
    screenshot('brightness-minimum')
    for _ in range(12):
        key(0)
    assert r.inspect()['display']['backlight'] == 100
    key(1, 3)  # exit edit before leaving options
    assert r.inspect()['menu_view']['options']
    key(0)
    assert r.inspect()['menu_view']['option_selected'] == 6
    key(2)
    screenshot('wifi-unconfigured')
    key(2)
    screenshot('wifi-setup')
    key(1, 3)
    for _ in range(2):
        key(1)
    key(2)
    assert not r.inspect()['menu_view']['options']
finally:
    r.close()

result = {'build': version, 'band_checks': checks, 'brightness_bounds': [10, 100],
          'wake_restores_brightness': True, 'save_failure_preserves_brightness': True,
          'hardware_tested': False}
(out/'preview.json').write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
