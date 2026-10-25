#!/usr/bin/env python3
"""Pack original Gold overworld pixels/palettes and bounded, collision-safe routes.

The three compact layouts are PokeWalk adaptations, not original map copies.
No image resampling, palette approximation or runtime pathfinding workspace.
"""
import argparse
from collections import deque
import hashlib
import json
from pathlib import Path
import re

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
REV = '656583c939d30f920a316177311a502dd222b57c'
HEADER = ROOT / 'firmware/main/field_map_assets.h'
MANIFEST = ROOT / 'assets/field_map_sources.json'
CONFIG = ROOT / 'assets/field_maps.json'
NAMES = ['GRAY', 'RED', 'GREEN', 'WATER', 'YELLOW', 'BROWN', 'ROOF', 'TEXT']
WALKABLE = {'FLOOR', 'TALL_GRASS', 'LONG_GRASS', 'LADDER', 'CAVE', 'DOOR', 'WARP_CARPET_DOWN'}
COLS, ROWS = 16, 14


def generate(src):
    sources = {}

    def source(path):
        p = src / path
        sources[path] = hashlib.sha256(p.read_bytes()).hexdigest()
        return p

    def palettes(path):
        out = []
        for line in source(path).read_text().splitlines():
            if line.lstrip().startswith('RGB'):
                v = list(map(int, re.findall(r'\d+', line.split(';')[0])))
                assert len(v) == 12
                # GBC RGB555 -> LCD RGB565. Keep source colour order for audit.
                out.append([(r << 11) | (((g << 1) | (g >> 4)) << 5) | b
                            for r, g, b in zip(v[::3], v[1::3], v[2::3])])
        return out

    def pack(im):
        assert set(im.getdata()) <= {0, 85, 170, 255}
        v = list(im.getdata())
        return [sum((v[i + k] // 85) << (6 - k * 2) for k in range(4))
                for i in range(0, len(v), 4)]

    def arr(name, data, typ='uint8_t'):
        def c(v):
            return '{' + ','.join(c(n) if isinstance(n, list) else str(n) for n in v) + '}'
        dims = []
        d = data
        while isinstance(d, list):
            dims.append(len(d))
            d = d[0]
        return 'static const %s %s%s = %s;\n' % (typ, name, ''.join('[%d]' % d for d in dims), c(data))

    bg = palettes('gfx/tilesets/bg_tiles.pal')
    npc = palettes('gfx/overworld/npc_sprites.pal')
    config = json.loads(CONFIG.read_text())['maps']
    tiles, color_map, grids, routes, targets, faces, spawns, people, occupancy = ([] for _ in range(9))
    distance = []
    for m in config:
        name = m['tileset']
        im = Image.open(source(f'gfx/tilesets/{name}.png')).convert('L')
        assert im.size == (128, 48)
        tiles.append([pack(im.crop((i % 16 * 8, i // 16 * 8, i % 16 * 8 + 8, i // 16 * 8 + 8))) for i in range(96)])
        pm = []
        for line in source(f'gfx/tilesets/{name}_palette_map.asm').read_text().splitlines():
            if 'tilepal' in line:
                assert line.strip().startswith('tilepal 0,')
                pm.extend(NAMES.index(s.strip()) for s in line.split(',', 1)[1].split(','))
        assert len(pm) == 96
        color_map.append(pm)
        meta = source(f'data/tilesets/{name}_metatiles.bin').read_bytes()
        coll = []
        for line in source(f'data/tilesets/{name}_collision.asm').read_text().splitlines():
            if 'tilecoll' in line:
                coll.append(line.split(';')[0].split('tilecoll')[1].strip().split(', '))
        blocks = [[int(t, 16) for t in row.split()] for row in m['blocks']]
        assert len(blocks) == ROWS // 2 and all(len(r) == COLS // 2 for r in blocks)
        grid = [[meta[blocks[y // 4][x // 4] * 16 + y % 4 * 4 + x % 4]
                 for x in range(COLS * 2)] for y in range(ROWS * 2)]
        assert all(0 <= t < 96 for row in grid for t in row)
        grids.append(grid)
        walk = [coll[blocks[y // 2][x // 2]][y % 2 * 2 + x % 2] in WALKABLE
                for y in range(ROWS) for x in range(COLS)]
        ns = []
        for p in m['npcs']:
            x, y = p['cell']; cell = y * COLS + x
            assert walk[cell], (name, 'NPC on obstruction', p)
            walk[cell] = False
            ns.append([p['sprite'], x, y])
        while len(ns) < 2:
            ns.append([255, 0, 0])
        people.append(ns)
        occupancy.append([int(v) for v in walk])
        ts = [y * COLS + x for x, y in m['targets']]
        spawn = m['spawn'][1] * COLS + m['spawn'][0]
        assert all(walk[t] for t in ts + [spawn]), (name, 'Blocked target/spawn', ts)
        targets.append(ts); spawns.append(spawn); faces.append(m['facing'])
        mr = []
        max_length = 0
        for target in ts:
            nxt = [255] * (COLS * ROWS); nxt[target] = target
            q = deque([target])
            while q:
                current = q.popleft(); x, y = current % COLS, current // COLS
                for xx, yy in ((x, y + 1), (x, y - 1), (x - 1, y), (x + 1, y)):
                    if not (0 <= xx < COLS and 0 <= yy < ROWS): continue
                    n = yy * COLS + xx
                    if walk[n] and nxt[n] == 255:
                        nxt[n] = current; q.append(n)
            for start in ts + [spawn]:
                assert nxt[start] != 255, (name, 'Unreachable', start, target)
                n, steps = start, 0
                while n != target:
                    n = nxt[n]; steps += 1
                    assert steps < COLS * ROWS
                max_length = max(max_length, steps)
            mr.append(nxt)
        routes.append(mr); distance.append(max_length)
    sprites = []
    for n in ['chris', 'scientist', 'bug_catcher']:
        im = Image.open(source(f'gfx/sprites/{n}.png')).convert('L')
        assert im.size == (16, 96)
        sprites.append([pack(im.crop((0, i * 16, 16, i * 16 + 16))) for i in range(6)])
    # Preserve provenance for facing/mirror semantics and palette selection.
    for f in ('data/sprites/facings.asm', 'data/sprites/sprites.asm',
              'data/maps/environment_colors.asm', 'engine/overworld/map_object_action.asm'):
        source(f)
    header = '// Generated by compile_field_maps.py. Gold ' + REV + '\n#pragma once\n#include <stdint.h>\n'
    header += 'enum { FIELD_MAP_COLS=16, FIELD_MAP_ROWS=14 };\n'
    for name, data in [('FIELD_TILES', tiles), ('FIELD_TILE_PAL', color_map), ('FIELD_MAP_TILES', grids),
                       ('FIELD_MAP_NEXT', routes), ('FIELD_MAP_TARGET', targets), ('FIELD_MAP_FACING', faces),
                       ('FIELD_MAP_SPAWN', spawns), ('FIELD_MAP_NPCS', people), ('FIELD_PEOPLE', sprites)]:
        header += arr(name, data)
    # Source shade 0 is dark, 3 is light/transparent; reverse GBC palette.
    header += arr('FIELD_BG_PAL', [[list(reversed(bg[40 if p == 3 and env == 0 else 8 + p]))
                                  for p in range(8)] for env in range(2)], 'uint16_t')
    header += arr('FIELD_PERSON_PAL', [list(reversed(npc[8 + p])) for p in (0, 1, 1)], 'uint16_t')
    manifest = dict(upstream='https://github.com/pret/pokegold', commit=REV, source_sha256=sources,
                    layout_sha256=hashlib.sha256(CONFIG.read_bytes()).hexdigest(),
                    generated_sha256=hashlib.sha256(header.encode()).hexdigest(),
                    map_cells=[COLS, ROWS], longest_route_cells=distance,
                    adaptation='Compact custom layouts; original 8px tiles, day palettes, Chris/NPC sprites and facing/mirror frames. Integer 2x display with camera follow. No overworld ROM/emulator.')
    return header, json.dumps(manifest, indent=2) + '\n'


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--src', type=Path, default=ROOT / '.build/sources/pokegold-656583c')
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    if a.check and not a.src.exists():
        meta = json.loads(MANIFEST.read_text())
        assert hashlib.sha256(HEADER.read_bytes()).hexdigest() == meta['generated_sha256']
        assert hashlib.sha256(CONFIG.read_bytes()).hexdigest() == meta['layout_sha256']
        print('Committed map asset/layout hashes match; source byte audit requires --src.')
        return
    header, manifest = generate(a.src)
    if a.check:
        assert HEADER.read_text() == header and MANIFEST.read_text() == manifest
    else:
        HEADER.write_text(header); MANIFEST.write_text(manifest)
    print('Gold map assets, palettes, directional frames and every target route verified.')


if __name__ == '__main__': main()
