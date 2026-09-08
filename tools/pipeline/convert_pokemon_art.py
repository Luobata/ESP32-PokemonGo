#!/usr/bin/env python3
"""Import 151 static Crystal fronts/backs and original normal/shiny palettes.

Uses a pinned pret/pokecrystal tree. Preserves all four source shades, including
white; display index 3 is transparent only under the white-page contract.
No gameplay fields are regenerated: gen1.bin byte 23 is the only changed field.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

from convert_sprites import read_png_full

ROOT = Path(__file__).resolve().parents[2]
COMMIT = '7a7881d0d62e0ddbd82dcf10e7116807487ac651'
REPOSITORY = 'https://github.com/pret/pokecrystal'
WHITE, BLACK = (31, 31, 31), (0, 0, 0)
SIZES = (40, 48, 56)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class PinnedTree:
    def __init__(self, root: Path):
        self.root, self.inputs = root, {}
        listing = subprocess.check_output(['git', '-C', str(root), 'ls-tree', '-r', COMMIT], text=True)
        self.blobs = {line.split('\t', 1)[1]: line.split()[2] for line in listing.splitlines()}

    def read(self, path: str) -> bytes:
        data = (self.root / path).read_bytes()
        blob_id = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        if self.blobs.get(path) != blob_id:
            raise ValueError(f'{path}: working file differs from pinned commit {COMMIT}')
        self.inputs[path] = {'git_blob': blob_id, 'sha256': sha256(data)}
        return data


def rgb565(rgb5: tuple[int, int, int]) -> int:
    r, g, b = rgb5
    return (r << 11) | (((g << 1) | (g >> 4)) << 5) | b


def pack(rows: list[list[int]]) -> bytes:
    return bytes(sum(row[x + k] << (6 - 2*k) for k in range(4))
                 for row in rows for x in range(0, len(row), 4))


def gameplay_hash(data: bytes) -> str:
    # Zero only presentation byte 23. Flags, stats, moves-related reserved bytes
    # and both string pools remain part of this immutable gameplay fingerprint.
    magic, ver, stride, count, pool = struct.unpack_from('<4sHHII', data)
    if (magic, ver, stride, count) != (b'GEN1', 1, 32, 151) or len(data) != 16 + stride*count + pool:
        raise ValueError('unsupported gen1.bin')
    copy = bytearray(data)
    for sid in range(count):
        copy[16 + sid*stride + 23] = 0
    return sha256(copy)


def generate(src: Path, current_data: bytes) -> dict[str, bytes]:
    tree = PinnedTree(src)
    palette_table = tree.read('data/pokemon/palettes.asm').decode()
    names = re.findall(r'INCBIN "gfx/pokemon/([^/]+)/normal\.gbcpal", middle_colors', palette_table)[:151]
    base_names = re.findall(r'INCLUDE "data/pokemon/base_stats/([^/]+)\.asm"',
                            tree.read('data/pokemon/base_stats.asm').decode())[:151]
    if len(names) != 151 or names != base_names:
        raise ValueError('source species order differs between palette and base-stat tables')
    makefile = tree.read('Makefile').decode()
    reverse = set(re.findall(r'gfx/pokemon/([^/]+)/normal\.gbcpal: tools/gbcpal \+= --reverse', makefile))
    tree.read('tools/gbcpal.c')
    tree.read('tools/common.h')
    before = gameplay_hash(current_data)
    data = bytearray(current_data)
    pool_start = 16 + 151*32
    fronts, backs, pairs, pair_ids, details = {}, {}, [], {}, []
    white_pixels = 0

    for sid, name in enumerate(names, 1):
        record = data[16 + (sid-1)*32:16 + sid*32]
        off, length = struct.unpack_from('<H', record)[0], record[2]
        slug = data[pool_start+off:pool_start+off+length].decode()
        if re.sub(r'[^a-z0-9]', '', slug) != re.sub(r'[^a-z0-9]', '', name):
            raise ValueError(f'#{sid}: source name {name} does not match existing gameplay ID {slug}')
        decoded = {}
        colors = set()
        for view in ('front', 'back'):
            relative = f'gfx/pokemon/{name}/{view}.png'
            tree.read(relative)
            w, h, rows, palette, _indices = read_png_full(str(src / relative))
            if not palette or w not in (40, 48, 56) or (view == 'front' and h % w) or (view == 'back' and (w, h) != (48, 48)):
                raise ValueError(f'{relative}: invalid source canvas {w}x{h}')
            if any(pixel[3] != 255 for row in rows for pixel in row):
                raise ValueError(f'{relative}: unexpected alpha channel')
            # RGBDS extracts PNG colors in RGB5 before tools/gbcpal combines
            # front/back colors. Black and white are forced palette endpoints.
            colors.update(tuple(c >> 3 for c in rgb) for rgb in palette)
            decoded[view] = (w, [[tuple(c >> 3 for c in pixel[:3]) for pixel in row]
                                for row in rows[:w]])
        middle = colors - {WHITE, BLACK}
        if len(middle) != 2:
            raise ValueError(f'#{sid}: expected two distinct source middle colors')
        # Matches pinned tools/gbcpal.c (RGB5 luminance, optional --reverse).
        ordered = sorted(middle, key=lambda c: 299*c[0] + 587*c[1] + 114*c[2],
                         reverse=name not in reverse)
        normal_gbc = [WHITE, *ordered, BLACK]
        shiny_file = f'gfx/pokemon/{name}/shiny.pal'
        shiny_text = tree.read(shiny_file).decode()
        shiny_mid = [tuple(map(int, match)) for match in
                     re.findall(r'\bRGB\s+(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', shiny_text)]
        if len(shiny_mid) != 2 or any(c > 31 for color in shiny_mid for c in color):
            raise ValueError(f'{shiny_file}: invalid RGB5 palette')
        shiny_gbc = [WHITE, *shiny_mid, BLACK]
        normal = tuple(rgb565(c) for c in reversed(normal_gbc))
        shiny = tuple(rgb565(c) for c in reversed(shiny_gbc))
        pair = (normal, shiny)
        if pair not in pair_ids:
            pair_ids[pair] = len(pairs)
            pairs.append(pair)
        index = pair_ids[pair]
        data[16 + (sid-1)*32 + 23] = index
        entry = {'id': sid, 'source_name': name, 'palette_pair': index,
                 'reverse_middle_order': name in reverse,
                 'normal_rgb5_gbc_order': normal_gbc, 'shiny_rgb5_gbc_order': shiny_gbc}
        for view, (w, rows) in decoded.items():
            shades = [[3 - normal_gbc.index(rgb) for rgb in row] for row in rows]
            blob = pack(shades)
            (fronts if view == 'front' else backs)[sid] = (w, blob)
            count_white = sum(shade == 3 for row in shades for shade in row)
            white_pixels += count_white
            entry[view] = {'width': w, 'height': w, 'packed_sha256': sha256(blob),
                           'source_white_pixels_preserved': count_white}
        details.append(entry)

    directory, body = bytearray(), bytearray()
    for size in SIZES:
        entries = [(sid, blob) for sid, (width, blob) in fronts.items() if width == size]
        directory += struct.pack('<HHII', size, size*size//4, len(entries), len(body))
        for sid, blob in entries:
            body += struct.pack('<H', sid) + blob
    front = struct.pack('<4sHH', b'FRNT', 1, len(SIZES)) + directory + body
    back = struct.pack('<4sHHHHI', b'BACK', 1, 48, 48, 576, 151) + b''.join(backs[sid][1] for sid in range(1, 152))
    palette_body = b''.join(struct.pack('<4H', *pair[variant])
                            for variant in (0, 1) for pair in pairs)
    mapping = bytes(data[16 + (sid-1)*32 + 23] for sid in range(1, 152))
    palette_blob = struct.pack('<4sHHHH', b'PALS', 1, len(pairs), 4, 151) + palette_body + mapping
    if gameplay_hash(data) != before:
        raise ValueError('conversion modified gameplay bytes')
    products = {'gen1_front.bin': bytes(front), 'gen1_back.bin': back,
                'palettes.bin': palette_blob, 'gen1.bin': bytes(data)}
    manifest = {'repository': REPOSITORY, 'commit': COMMIT,
                'source_mode': 'Crystal front first square frame and 48x48 back; four original shades',
                'palette_rule': 'pinned Makefile + tools/gbcpal.c; original shiny.pal, paired deduplication',
                'white_contract': 'index 3 remains source white; transparent rendering requires white page background',
                'gameplay_sha256_except_palette_byte_23': before,
                'front_size_counts': dict(sorted(Counter(w for w, _ in fronts.values()).items())),
                'palette_pair_count': len(pairs), 'source_white_pixels_preserved': white_pixels,
                'inputs': tree.inputs, 'species': details,
                'outputs': {name: {'bytes': len(blob), 'sha256': sha256(blob)} for name, blob in products.items()}}
    products['pokemon_art_sources.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2) + '\n').encode()
    return products


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--src', type=Path, default=Path('/tmp/pokecrystal'))
    ap.add_argument('--out', type=Path, default=ROOT / 'assets')
    ap.add_argument('--data', type=Path, default=ROOT / 'assets/gen1.bin')
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    products = generate(args.src, args.data.read_bytes())
    for name, blob in products.items():
        target = args.out / name
        if args.check:
            if not target.is_file() or target.read_bytes() != blob:
                raise ValueError(f'{target}: differs from pinned source conversion')
        else:
            args.out.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
    print(f'{"verified" if args.check else "generated"} 302 Crystal images + original normal/shiny palettes; {COMMIT}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
