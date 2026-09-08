#!/usr/bin/env python3
"""Crystal capture ball art and colors from one fixed original source.

All three ball kinds share the source shape; BallColors selects red/blue/yellow.
The full closed 16x16 PNG frame and original top/bottom open halves are kept at
integer 2x. Open halves are joined as in the source sheet for this static UI
entry; this does not implement the original capture animation's timing/motion.

    python3 tools/pipeline/fetch_balls.py [--check]
    python3 tools/pipeline/convert_ui.py
"""
from __future__ import annotations

import argparse
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
COMMIT = '7a7881d0d62e0ddbd82dcf10e7116807487ac651'
SOURCE_HASHES = {
    'gfx/battle_anims/pokeball.png': '08ff3eac18e420c5735eaa030bba9ae59ae53a6607407533fd3e89b95603f67b',
    'gfx/battle_anims/battle_anims.pal': 'a50a2b3d717f33c3a2c5fa690099406c6dd8182bb45fe90d265ace06ccd240d3',
    'data/battle_anims/ball_colors.asm': '60110c0d270ea1a576d289db4b627f8b0e9f15ae28ef6627a57be8683ec30437',
    'data/battle_anims/oam.asm': '3760169d375966da1c0b0b097201d384e358ad3aa6b0b0fda42d9e55877d3782',
    'data/battle_anims/framesets.asm': 'cb98a82f1d50e86f0c78bff3afa14001f0f865ac9c7324a28775365eb260dbe9',
    'engine/battle_anims/functions.asm': 'f79ffa3db232dfd21a81d9d8ad108d2c45217f52f876799eedec7de05ac227bf',
    'data/moves/animations.asm': '3e8c0e82a8807342862970304fb879bf7c4ad2364675c3af2f5af356b11d07e3',
    'constants/battle_anim_constants.asm': 'b8f6bba84ac6a9e636cfe5f00596b42421da9a48c2a697ff423fc870c5fe99ce',
    'Makefile': '3416a95d328172fc7fc5b4e991510383d9e15761bc6ccc59af52700adad3695e',
    'tools/gfx.c': '2a55def1b32c90d4de6886df1b469ff084a135c1d838fe7eb0049b90b14c00f8',
    'tools/common.h': '276f4932f978ab9f1091f4279a05dac5709d36516036d264329176b1f0dee3f5',
}
BALL_NAMES = ('ball_24', 'ball_great', 'ball_ultra', 'ball_master',
              'ball_fast', 'ball_heavy', 'ball_level', 'ball_friend')
BALL_SOURCE_IDS = ('POKE_BALL', 'GREAT_BALL', 'ULTRA_BALL', 'MASTER_BALL',
                   'FAST_BALL', 'HEAVY_BALL', 'LEVEL_BALL', 'FRIEND_BALL')
BALL_COLORS = ('red', 'blue', 'yellow', 'green', 'blue', 'gray', 'brown', 'yellow')
# Original battle object RGB5 palettes, reversed into engine shade order.
BALL_RGB5 = (
    ((0, 0, 0), (30, 10, 6), (31, 19, 24), (31, 31, 31)),
    ((0, 0, 0), (1, 4, 31), (8, 12, 31), (31, 31, 31)),
    ((0, 0, 0), (31, 16, 1), (31, 31, 7), (31, 31, 31)),
    ((0, 0, 0), (5, 14, 0), (12, 25, 1), (31, 31, 31)),
    ((0, 0, 0), (1, 4, 31), (8, 12, 31), (31, 31, 31)),
    ((0, 0, 0), (13, 13, 13), (25, 25, 25), (31, 31, 31)),
    ((0, 0, 0), (20, 15, 3), (24, 18, 7), (31, 31, 31)),
    ((0, 0, 0), (31, 16, 1), (31, 31, 7), (31, 31, 31)),
)


def rgb565(c):
    r, g, b = c
    return (r << 11) | (((g << 1) | (g >> 4)) << 5) | b


def display_hex(v):
    r, g, b = v >> 11, (v >> 5) & 63, v & 31
    return f'#{((r << 3) | (r >> 2)):02x}{((g << 2) | (g >> 4)):02x}{((b << 3) | (b >> 2)):02x}'


BALL_PALETTES_RGB565 = tuple(tuple(rgb565(c) for c in pal) for pal in BALL_RGB5)
# UIA1 contains the three legacy keys plus the opened ball. New capture kinds
# reuse ball_24's identical source pixels with the eight-kind C palette table.
BALL_PALETTES = {name: [display_hex(v) for v in pal]
                 for name, pal in zip(BALL_NAMES[:3], BALL_PALETTES_RGB565)}
BALL_PALETTES['ball_open'] = BALL_PALETTES['ball_24']


@lru_cache(maxsize=None)
def source_path(name: str) -> Path:
    expected = SOURCE_HASHES[name]
    local = Path('/tmp/pokecrystal') / name
    if local.exists():
        data = local.read_bytes()
        path = local
    else:
        path = Path('/tmp/crystal-balls') / COMMIT / name
        if path.exists():
            data = path.read_bytes()
        else:
            url = f'https://raw.githubusercontent.com/pret/pokecrystal/{COMMIT}/{name}'
            req = urllib.request.Request(url, headers={'User-Agent': 'ESP32-PokemonGo/fetch_balls'})
            with urllib.request.urlopen(req, timeout=30) as response:
                data = response.read()
            if hashlib.sha256(data).hexdigest() != expected:
                raise ValueError(f'Downloaded Crystal source differs: {name}')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'Crystal source differs from pinned commit: {name}')
    return path


@lru_cache(maxsize=None)
def _frames():
    import convert_sprites as cs
    w, h, rows, _, _ = cs.read_png_full(str(source_path('gfx/battle_anims/pokeball.png')))
    if (w, h) != (16, 56):
        raise ValueError(f'Unexpected original ball sheet: {w}x{h}')
    if any(p[0] != p[1] or p[1] != p[2] or p[0] not in (0,85,170,255) for row in rows for p in row):
        raise ValueError('Original ball sheet is not four source shades')
    # PNG rows 0..15 are the exact mirrored OAMSET_0A composite. The open
    # image contains OAMSET_0C/0D at y=0/8; no source pixels are redrawn.
    native = tuple([[p[0] // 85 for p in row] for row in rows[y:y+16]] for y in (0,32))
    return tuple([[v for v in row for _ in range(2)] for row in grid for _ in range(2)] for grid in native)


def ball_grid(name: str):
    if name not in (*BALL_NAMES, 'ball_open'):
        raise ValueError(f'Unknown ball UI entry: {name}')
    return _frames()[name == 'ball_open']


def visible_bounds(grid):
    pixels = [(x,y) for y,row in enumerate(grid) for x,v in enumerate(row) if v != 3]
    left, top = min(x for x,y in pixels), min(y for x,y in pixels)
    return [left,top,max(x for x,y in pixels)-left+1,max(y for x,y in pixels)-top+1]


def generated():
    for name in SOURCE_HASHES:
        source_path(name)
    palettes = source_path('gfx/battle_anims/battle_anims.pal').read_text()
    matches = re.findall(r'; (\w+)\s*\n(.*?)(?=;|\Z)', palettes, re.S)
    source_pals = {color: [tuple(map(int, v)) for v in re.findall(r'RGB\s+(\d+),\s*(\d+),\s*(\d+)', body)]
                   for color, body in matches}
    color_map = source_path('data/battle_anims/ball_colors.asm').read_text()
    for name, color, pal in zip(BALL_SOURCE_IDS, BALL_COLORS, BALL_RGB5):
        if not re.search(r'\b'+name+r',\s*PAL_BATTLE_OB_'+color.upper()+r'\b', color_map):
            raise ValueError('Original ball/color mapping changed')
        if list(reversed(source_pals[color])) != list(pal):
            raise ValueError('Original ball palette changed')
    closed, opened = map(visible_bounds, _frames())
    header = [
        '// Generated by tools/pipeline/fetch_balls.py; do not edit.',
        f'// Crystal {COMMIT}: pokeball.png, BallColors, battle_anims.pal.',
        '// Source shape is shared by all kinds; 3 is transparent. UI art is already 2x.',
        '#pragma once', '#include <stdbool.h>', '#include <stdint.h>',
        'typedef struct { uint8_t x, y, w, h; } ball_asset_bounds_t;',
        'enum { BALL_ASSET_WIDTH = 32, BALL_ASSET_HEIGHT = 32, BALL_ASSET_KINDS = 8 };',
        '// kind order matches the eight CAP_BALL / ITEM ball enum values.',
        'static inline const uint16_t *ball_assets_palette(uint8_t kind)', '{',
        '    static const uint16_t palettes[8][4] = {',
    ]
    header.extend('        {'+', '.join(f'0x{v:04x}' for v in pal)+'},' for pal in BALL_PALETTES_RGB565)
    header.extend(['    };', '    return palettes[kind < 8 ? kind : 0];', '}',
        'static inline ball_asset_bounds_t ball_assets_visible(bool opened)', '{',
        '    return opened ? (ball_asset_bounds_t){'+', '.join(map(str,opened))+'}',
        '                  : (ball_asset_bounds_t){'+', '.join(map(str,closed))+'};', '}', ''])
    import pixelart as pa
    manifest = dict(repository='https://github.com/pret/pokecrystal',commit=COMMIT,sources=SOURCE_HASHES,
        source_closed='PNG [0,0,16,16] / Frameset_PokeBall4 / OAMSET_0A',
        source_open='PNG [0,32,16,48] / original OAMSET_0C top + OAMSET_0D bottom at y=0/8',
        scale=2,format='UIA1 unchanged; 32x32 full canvas; shade 3 transparent',
        palettes_rgb5=BALL_RGB5,palettes_rgb565=BALL_PALETTES_RGB565,
        capture_kind_sources=dict(zip(BALL_SOURCE_IDS, BALL_COLORS)),
        entries={name:dict(width=32,height=32,visible_bounds=visible_bounds(ball_grid(name)),
            sha256=hashlib.sha256(pa.to_2bpp(ball_grid(name))).hexdigest())
            for name in (*BALL_NAMES[:3],'ball_open')},
        limit='Static original art/colors; open halves joined as in source sheet. Original capture timing/motion is not emulated.')
    return '\n'.join(header), json.dumps(manifest,indent=2)+'\n'


def write_metadata(check=False):
    header, manifest = generated()
    for path, data in ((ROOT/'firmware/main/ball_assets.h',header),(ROOT/'assets/ball_sources.json',manifest)):
        if check:
            if path.read_text() != data:
                raise ValueError(f'Ball metadata needs regeneration: {path}')
        else:
            path.write_text(data)


def main():
    import sys
    sys.path.insert(0,str(ROOT/'sim'))
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--check',action='store_true')
    args=ap.parse_args()
    write_metadata(args.check)
    print('verified' if args.check else 'generated', 'Crystal ball palette/bounds header and source manifest')


if __name__ == '__main__':
    main()
