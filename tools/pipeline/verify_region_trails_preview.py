#!/usr/bin/env python3
"""Drive the real C trail UI and check preview encounter levels and navigation."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png

OUT = ROOT / 'reports/evidence/region-trails-2026-10-05'
RANGES = [(35, 45), (42, 55), (38, 50), (45, 58),
          (48, 60), (50, 65), (60, 75), (65, 85)]
SEEN = [(86, 90, 116, 120, 117), (92, 96, 104, 93, 97),
        (29, 32, 102, 44, 70), (81, 100, 137, 111, 82),
        (37, 58, 77, 4, 5), (116, 111, 117, 75, 73),
        (137, 132, 63, 64, 82), (86, 90, 117, 80, 75)]
checks = 0


def command(renderer, text):
    global checks
    frame = renderer.command(text)
    assert renderer.command('check')['mismatch'] == 0, text
    checks += 1
    return frame


def key(renderer, button):
    return command(renderer, f'key {button} 1')


def progress(renderer):
    state = renderer.inspect()
    return {key: state[key] for key in
            ('region', 'queue', 'inventory', 'nurture', 'exp')}


def boot(renderer, region, level=40):
    command(renderer, f'boot 15 25 {level} 74 3 812 0 0 1')
    command(renderer, 'challenge_unlock 16383')
    command(renderer, f'region_fixture {region} 1')


def run():
    exe, version = build()
    OUT.mkdir(parents=True, exist_ok=True)
    results = []
    for region in range(4, 12):
        for deep in (False, True):
            renderer = Renderer(exe)
            try:
                boot(renderer, region)
                if deep:
                    for n, species in enumerate(SEEN[region - 4]):
                        command(renderer, f'spawn {species} 3 {1000 + n}')
                    key(renderer, 1)
                    key(renderer, 1)
                    key(renderer, 2)  # Activities.
                    for _ in range(4):
                        key(renderer, 1)
                    key(renderer, 2)  # Toggle deep exploration through real UI.
                    assert renderer.inspect()['region']['deep'] == 1
                    command(renderer, 'page 15')
                before = progress(renderer)
                key(renderer, 2)  # Open trail choices.
                for direction in range(3):
                    frame = command(renderer, 'check')
                    # Each choice has a visible frame; invalid tile dimensions
                    # silently skip drawing, even when band/full pixels agree.
                    for row in range(3):
                        black = sum(frame['pixels'][(y * 240 + x) * 2:(y * 240 + x) * 2 + 2] == b'\0\0'
                                    for y in range(96 + row * 64, 120 + row * 64)
                                    for x in range(8, 16))
                        assert black > 20, 'Missing trail frame'
                    if direction == 0:
                        path = OUT / f'trails-{region}-{"deep" if deep else "normal"}.png'
                        path.write_bytes(png(frame['pixels']))
                    key(renderer, 1)
                assert progress(renderer) == before, 'Choosing a cursor rerolled or charged progress'
                command(renderer, 'key 1 3')
                assert progress(renderer) == before, 'Cancelling consumed progress'
            finally:
                renderer.close()
        baseline = None
        for level in (10, 40, 100):
            renderer = Renderer(exe)
            try:
                boot(renderer, region, level)
                before = renderer.inspect()
                key(renderer, 2)
                key(renderer, 2)  # First habitat, one actual discovery.
                after = renderer.inspect()
                uids = {entry['uid'] for entry in before['queue']}
                discovered = [entry for entry in after['queue'] if entry['uid'] not in uids]
                assert len(discovered) == 1
                encounter = discovered[0]
                assert RANGES[region - 4][0] <= encounter['level'] <= RANGES[region - 4][1]
                assert before['nurture']['stamina'] - after['nurture']['stamina'] == 5
                value = (encounter['species'], encounter['rarity'], encounter['level'])
                if baseline is None:
                    baseline = value
                else:
                    assert value == baseline, 'Preview still scales new regions to leader level'
                command(renderer, 'page 1')
                command(renderer, 'page 15')
                assert renderer.inspect()['queue'] == after['queue'], 'Redraw changed an existing encounter'
                results.append(dict(region=region, leader=level, species=value[0], level=value[2]))
            finally:
                renderer.close()
    result = dict(build=version, checks=checks, maps=8, paths=24,
                  normal_and_deep_ui=True, pixel_band_mismatches=0,
                  navigation_preserves_progress=True, encounter_levels=results)
    (OUT / 'preview.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    run()
