#!/usr/bin/env python3
"""Compare band-rendered maps to an independent whole-scene pixel reference.

Checks original packed pixels, transparency, facing/mirroring, camera clipping,
and every target's collision route. This is not an LCD FPS measurement.
"""
import json
import os
from pathlib import Path
import re
import struct
import sys

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png

source = (ROOT / 'firmware/main/field_map_assets.h').read_text()
data = {n: json.loads(v.replace('{', '[').replace('}', ']'))
        for n, v in re.findall(r'static const \w+ (\w+)\[[^=]+ = (.+);', source)}
cfg = json.loads((ROOT / 'assets/field_maps.json').read_text())['maps']
out = Path(os.environ.get('POKEWALK_EVIDENCE_DIR', ROOT / 'reports/evidence/gold-field-ui-2026-10-25'))
out.mkdir(parents=True, exist_ok=True)


def unpack(packed, size, palette):
    shades = [(b >> shift) & 3 for b in packed for shift in (6, 4, 2, 0)]
    im = Image.new('I', (size, size)); im.putdata([palette[s] for s in shades])
    mask = Image.new('L', im.size); mask.putdata([255 if s != 3 else 0 for s in shades])
    return im, mask


def background(m):
    im = Image.new('I', (256, 224))
    for row, tiles in enumerate(data['FIELD_MAP_TILES'][m]):
        for col, tile in enumerate(tiles):
            pal = data['FIELD_BG_PAL'][int(m == 2)][data['FIELD_TILE_PAL'][m][tile]]
            im.paste(unpack(data['FIELD_TILES'][m][tile], 8, pal)[0], (col * 8, row * 8))
    return im


backgrounds = [background(m) for m in range(3)]


def reference(m, x, y, facing, pose):
    im = backgrounds[m].copy()
    people = [(y, x, 0, facing, pose)]
    for which, xx, yy in data['FIELD_MAP_NPCS'][m]:
        if which == 255: continue
        xx *= 16; yy *= 16
        direction = 0
        if abs(xx - x) + abs(yy - y) <= 32:
            direction = (2 if x < xx else 3) if abs(xx - x) > abs(yy - y) else (1 if y < yy else 0)
        people.append((yy, xx, which, direction, 0))
    # Same-foot-row NPC behind the player, matching the original overlap rule.
    for yy, xx, who, direction, p in sorted(people, key=lambda p: (p[0], p[2] == 0)):
        frame = min(direction, 2) + (3 if p % 2 else 0)
        sprite, mask = unpack(data['FIELD_PEOPLE'][who][frame], 16, data['FIELD_PERSON_PAL'][who])
        if direction == 3 or direction < 2 and p == 3:
            sprite = sprite.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
            mask = mask.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        im.paste(sprite, (xx, yy - 8), mask)
    cx = max(0, min(144, x + 8 - 56)); cy = max(0, min(132, y - 46))
    return im.crop((cx, cy, cx + 112, cy + 92)).resize((224, 184), Image.Resampling.NEAREST)


def compare(frame, m, x, y, facing, pose):
    actual = Image.new('I', (240, 320))
    actual.putdata([v[0] for v in struct.iter_unpack('>H', frame['pixels'])])
    actual = list(actual.crop((8, 32, 232, 216)).getdata())
    expected = list(reference(m, x, y, facing, pose).getdata())
    errors = [(i % 224, i // 224, a, e) for i, (a, e) in enumerate(zip(actual, expected)) if a != e]
    assert not errors, (m, x, y, facing, pose, len(errors), errors[:3])


exe, version = build()
checks = 0; directions = set(); poses = set(); r = None
try:
    for m in range(3):
        r = Renderer(exe)
        r.command('boot 22 25 60 74 3 81 0 0 0'); r.command('johto_fixture 8 0'); r.command('page 22')
        for _ in range(m): r.command('key 1 1')
        r.command('key 2 1')
        (out / f'map-{m}-entry.png').write_bytes(png(r.command('tick 0')['pixels']))
        # Return paths exercise all directions, turns and alternate camera edges.
        for target in (0, 2, 1, 3, 5, 4, 0):
            while r.inspect()['field']['point'] != target: r.command('key 1 1')
            s = r.inspect()['field']; cell = s['y'] // 16 * 16 + s['x'] // 16
            end = data['FIELD_MAP_TARGET'][m][target]
            route = [cell]
            while cell != end:
                nxt = data['FIELD_MAP_NEXT'][m][target][cell]
                assert nxt != 255 and abs(nxt % 16 - cell % 16) + abs(nxt // 16 - cell // 16) == 1
                assert nxt not in route
                route.append(nxt); cell = nxt
            if len(route) == 1: continue
            start_ms = r.command('key 2 1')['ms']
            while r.inspect()['field']['walking']:
                f = r.command('tick 50'); s = r.inspect()['field']; dt = f['ms'] - start_ms
                step = min(dt // 160, len(route) - 1); here = route[step]
                if s['walking']:
                    nxt = route[step + 1]; dx, dy = nxt % 16 - here % 16, nxt // 16 - here // 16
                    direction = (2 if dx < 0 else 3) if dx else (1 if dy < 0 else 0)
                    pose = (dt * 4194304 // (70224 * 1000 * 4)) % 4
                    assert s['x'] == here % 16 * 16 + dx * (dt // 10 % 16)
                    assert s['y'] == here // 16 * 16 + dy * (dt // 10 % 16)
                    directions.add(direction); poses.add((direction, pose))
                else:
                    direction = data['FIELD_MAP_FACING'][m][target]; pose = 0
                compare(f, m, s['x'], s['y'], direction, pose); checks += 1
                assert r.command('check')['mismatch'] == 0
            if target in (2, 3, 5):
                (out / f'map-{m}-point-{target}.png').write_bytes(png(f['pixels']))
        assert r.inspect()['field']['serial'] == 0, 'Walking/looking must not roll an encounter'
        r.close(); r = None
    assert directions == {0, 1, 2, 3} and len(poses) == 16, (directions, poses)
    report = dict(passed=True, build=version, full_reference_frames=checks, direction_pose_pairs=len(poses),
                  scope='Whole-scene Gold pixel reference vs real production band rendering; no hardware FPS claim')
    (out / 'art-check.json').write_text(json.dumps(report, indent=2) + '\n')
    print(report)
finally:
    if r: r.close()
