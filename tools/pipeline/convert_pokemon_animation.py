#!/usr/bin/env python3
"""Compile pinned Crystal front.png + anim.asm into compact C tile patches.

Only original normal-speed entrance scripts are imported. Back pictures have
no corresponding frame scripts and stay static. Requires matching FRNT bases.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import struct

from convert_pokemon_art import COMMIT, REPOSITORY, PinnedTree, pack, sha256
from convert_sprites import read_png_full

ROOT = Path(__file__).resolve().parents[2]
WHITE, BLACK = (31, 31, 31), (0, 0, 0)


def number(value: str) -> int:
    return int(value[1:], 16) if value.startswith('$') else int(value, 10)


def commands(text: str) -> list[tuple[str, ...]]:
    result = []
    for raw in text.splitlines():
        line = raw.split(';', 1)[0].strip()
        if not line:
            continue
        fields = re.split(r'[\s,]+', line)
        op, args = fields[0], tuple(number(v) for v in fields[1:])
        arity = {'frame': 2, 'setrepeat': 1, 'dorepeat': 1, 'endanim': 0}
        if op not in arity or len(args) != arity[op] or any(not 0 <= n <= 255 for n in args):
            raise ValueError(f'unsupported animation command: {raw}')
        result.append((op, *args))
    if not result or result[-1] != ('endanim',):
        raise ValueError('animation must terminate with endanim')
    return result


def timeline(script: list[tuple], frame_count: int) -> list[tuple[int, int]]:
    """Return exclusive end_tick/frame pairs, including exhausted-loop holds.

    PokeAnim_RunAnim processes setrepeat/taken dorepeat in the same tick.
    An exhausted dorepeat returns without a new frame, holding it one tick.
    frame decrements its wait counter immediately, so duration N is N ticks.
    """
    pc = repeat = clock = frame = 0
    result = []

    def hold(ticks: int) -> None:
        nonlocal clock
        clock += ticks
        if clock > 65535:
            raise ValueError('animation duration exceeds uint16 ticks')
        if result and result[-1][1] == frame:
            result[-1] = (clock, frame)
        else:
            result.append((clock, frame))

    for _ in range(10000):
        if not 0 <= pc < len(script):
            raise ValueError('animation branch is outside script')
        op, *args = script[pc]
        pc += 1
        if op == 'endanim':
            return result
        if op == 'frame':
            frame, ticks = args
            if frame >= frame_count or ticks == 0:
                raise ValueError('invalid source frame or zero duration')
            hold(ticks)
        elif op == 'setrepeat':
            repeat = args[0]
        else:
            if repeat:
                repeat -= 1
            if repeat:
                pc = args[0]
            else:
                hold(1)
    raise ValueError('animation does not terminate')


def read_front(blob: bytes) -> dict[int, tuple[int, bytes]]:
    magic, version, count = struct.unpack_from('<4sHH', blob)
    if magic != b'FRNT' or version != 1 or count != 3:
        raise ValueError('expected current FRNT format')
    body = 8 + count * 12
    frames = {}
    for i in range(count):
        size, length, records, offset = struct.unpack_from('<HHII', blob, 8 + i * 12)
        if size not in (40, 48, 56) or length != size * size // 4:
            raise ValueError('invalid FRNT segment')
        for index in range(records):
            start = body + offset + index * (length + 2)
            sid = struct.unpack_from('<H', blob, start)[0]
            frame = blob[start + 2:start + 2 + length]
            if sid in frames or not 1 <= sid <= 151 or len(frame) != length:
                raise ValueError('invalid FRNT record')
            frames[sid] = size, frame
    if len(frames) != 151:
        raise ValueError('FRNT does not contain all 151 bases')
    return frames


def byte_array(name: str, data: bytes) -> str:
    lines = [f'static const uint8_t {name}[] = {{']
    lines += ['    ' + ','.join(f'0x{b:02x}' for b in data[i:i + 24]) + ','
              for i in range(0, len(data), 24)]
    return '\n'.join(lines + ['};'])


def generate(src: Path, front: bytes) -> dict[str, bytes]:
    tree = PinnedTree(src)
    table = tree.read('data/pokemon/base_stats.asm').decode()
    names = re.findall(r'INCLUDE "data/pokemon/base_stats/([^/]+)\.asm"', table)[:151]
    if len(names) != 151 or len(set(names)) != 151:
        raise ValueError('invalid original species order')
    makefile = tree.read('Makefile').decode()
    reverse = set(re.findall(r'gfx/pokemon/([^/]+)/normal\.gbcpal: tools/gbcpal \+= --reverse', makefile))
    for path in ('tools/gbcpal.c', 'tools/common.h', 'tools/pokemon_animation_graphics.c',
                 'tools/pokemon_animation.c', 'macros/scripts/pic_anims.asm',
                 'engine/gfx/pic_animation.asm'):
        tree.read(path)
    bases = read_front(front)
    tiles, tile_ids, patches, frame_records, runs, species, details = [], {}, bytearray(), [], [], [], []
    raw_bytes = 0

    for sid, name in enumerate(names, 1):
        decoded, colors = {}, set()
        for view in ('front', 'back'):
            path = f'gfx/pokemon/{name}/{view}.png'
            tree.read(path)
            w, h, rows, palette, _indices = read_png_full(str(src / path))
            if w not in (40, 48, 56) or h % w or not palette:
                raise ValueError(f'{path}: invalid original dimensions')
            if any(pixel[3] != 255 for row in rows for pixel in row):
                raise ValueError(f'{path}: alpha is unsupported')
            colors.update(tuple(c >> 3 for c in rgb) for rgb in palette)
            decoded[view] = w, h, rows
        middle = colors - {WHITE, BLACK}
        if len(middle) != 2:
            raise ValueError(f'{name}: expected two original middle colors')
        normal = [WHITE, *sorted(middle, key=lambda c: 299*c[0] + 587*c[1] + 114*c[2],
                                reverse=name not in reverse), BLACK]
        w, h, pixels = decoded['front']
        shades = [[3 - normal.index(tuple(c >> 3 for c in p[:3])) for p in row] for row in pixels]
        squares = [shades[y:y + w] for y in range(0, h, w)]
        if bases[sid] != (w, pack(squares[0])):
            raise ValueError(f'#{sid}: FRNT base does not match pinned original source')
        script_path = f'gfx/pokemon/{name}/anim.asm'
        script = commands(tree.read(script_path).decode())
        sequence = timeline(script, len(squares))
        if not sequence or not any(frame for _end, frame in sequence):
            raise ValueError(f'#{sid}: missing original entrance motion')
        used_frames = {0, *(frame for _end, frame in sequence)}
        ink = [(x, y) for frame in used_frames for y, row in enumerate(squares[frame])
               for x, shade in enumerate(row) if shade != 3]
        left, top = min(x for x, _y in ink), min(y for _x, y in ink)
        right, bottom = max(x for x, _y in ink) + 1, max(y for _x, y in ink) + 1
        frame_start, run_start = len(frame_records), len(runs)
        base_tiles = None
        frame_details = []
        for frame_index, square in enumerate(squares):
            packed = pack(square)
            raw_bytes += len(packed)
            frame_tiles = [pack([row[x:x + 8] for row in square[y:y + 8]])
                           for y in range(0, w, 8) for x in range(0, w, 8)]
            if base_tiles is None:
                base_tiles = frame_tiles
            patch_start = len(patches) // 3
            for position, tile in enumerate(frame_tiles):
                if tile == base_tiles[position]:
                    continue
                if tile not in tile_ids:
                    tile_ids[tile] = len(tiles)
                    tiles.append(tile)
                patches += struct.pack('<BH', position, tile_ids[tile])
            patch_count = len(patches) // 3 - patch_start
            frame_records.append((patch_start, patch_count))
            frame_details.append({'frame': frame_index, 'sha256': sha256(packed),
                                  'patch_count': patch_count})
        runs.extend(sequence)
        species.append((frame_start, run_start, len(sequence), sequence[-1][0],
                        w, len(squares), left, top, right - left, bottom - top))
        details.append({'id': sid, 'name': name, 'size': w, 'frame_count': len(squares),
                        'duration_ticks': sequence[-1][0], 'union': [left, top, right - left, bottom - top],
                        'commands': script, 'timeline_end_tick_frame': sequence, 'frames': frame_details})

    if len(tiles) > 65535 or len(patches) // 3 > 65535 or len(runs) > 65535:
        raise ValueError('generated atlas exceeds uint16 offsets')
    header = ['// Generated by convert_pokemon_animation.py; do not edit.',
              f'// {REPOSITORY} @ {COMMIT}', '#pragma once', '#include <stdint.h>',
              '#define POKEMON_ANIM_SPECIES_COUNT 151u', f'#define POKEMON_ANIM_TILE_COUNT {len(tiles)}u',
              'typedef struct { uint16_t patch_start; uint8_t patch_count; } pokemon_anim_frame_record_t;',
              'typedef struct { uint16_t end_tick; uint8_t frame; } pokemon_anim_run_t;',
              'typedef struct {',
              '    uint16_t frame_start, run_start, run_count, duration_ticks;',
              '    uint8_t size, frame_count, x, y, w, h;',
              '} pokemon_anim_record_t;',
              byte_array('POKEMON_ANIM_TILES', b''.join(tiles)),
              byte_array('POKEMON_ANIM_PATCHES', bytes(patches)),
              'static const pokemon_anim_frame_record_t POKEMON_ANIM_FRAMES[] = {',
              *[f'    {{{offset},{count}}},' for offset, count in frame_records], '};',
              'static const pokemon_anim_run_t POKEMON_ANIM_RUNS[] = {',
              *[f'    {{{end},{frame}}},' for end, frame in runs], '};',
              'static const pokemon_anim_record_t POKEMON_ANIM_SPECIES[] = {',
              *['    {' + ','.join(str(n) for n in record) + '},' for record in species], '};', '']
    output = '\n'.join(header).encode()
    # C structs use 2-byte alignment: frame/run=4 bytes, species=14 bytes.
    flash = len(tiles) * 16 + len(patches) + len(frame_records) * 4 + len(runs) * 4 + len(species) * 14
    manifest = {'repository': REPOSITORY, 'commit': COMMIT,
                'mode': 'original per-species anim.asm, normal speed; back remains static',
                'timing': '60 Hz; exhausted dorepeat holds one tick; endanim restores frame 0',
                'codec': '8x8 packed-2bpp tile patches relative to current FRNT base, global tile dedup',
                'base_front_sha256': sha256(front), 'species_count': 151,
                'frame_count': len(frame_records), 'raw_frame_bytes': raw_bytes,
                'unique_patch_tiles': len(tiles), 'patch_count': len(patches) // 3,
                'compiled_atlas_bytes': flash, 'decode_buffer_bytes': 784,
                'inputs': tree.inputs, 'species': details,
                'outputs': {'pokemon_animation_assets.h': {'bytes': len(output), 'sha256': sha256(output)}}}
    return {'pokemon_animation_assets.h': output,
            'pokemon_animation_sources.json': (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', type=Path, default=Path('/tmp/pokecrystal'))
    parser.add_argument('--front', type=Path, default=ROOT / 'assets/gen1_front.bin')
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    products = generate(args.src, args.front.read_bytes())
    for name, data in products.items():
        path = ROOT / ('firmware/main' if name.endswith('.h') else 'assets') / name
        if args.check:
            if not path.is_file() or path.read_bytes() != data:
                raise ValueError(f'{path}: differs from pinned source')
        else:
            path.write_bytes(data)
    manifest = json.loads(products['pokemon_animation_sources.json'])
    print(f'{"verified" if args.check else "generated"} 151 original front scripts; '
          f'{manifest["frame_count"]} frames; {manifest["compiled_atlas_bytes"]} bytes flash, 784 bytes decode RAM')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
