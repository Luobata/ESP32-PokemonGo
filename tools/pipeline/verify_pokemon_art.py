#!/usr/bin/env python3
"""Independent Crystal source oracle plus 604 actual C sprite renders.

Pillow decodes pinned upstream PNGs independently of the converter's PNG reader.
The upstream gbcpal.c itself orders normal palettes, including Makefile reverse
exceptions; shiny colors come from original .pal files. Then actual assets.c,
render.c and screen.c load/draw all normal/shiny front/back images at integer 2x.
No page-layout code or project conversion functions supply expected pixels.
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
import tempfile

from PIL import Image
from verify_battle_layout import read_fronts, require

ROOT = Path(__file__).resolve().parents[2]
COMMIT = '7a7881d0d62e0ddbd82dcf10e7116807487ac651'
WHITE, BLACK = (31, 31, 31), (0, 0, 0)
FILES = ('gen1.bin', 'gen1_front.bin', 'gen1_back.bin', 'palettes.bin')

C_DRIVER = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "assets.h"
#include "render.h"
#include "screen.h"
#include "bsp_display.h"
static unsigned char lcd[SCREEN_W * SCREEN_H * 2]; // Host fixture only.
static const void *pending;
static int pending_y;
int esp_lcd_panel_draw_bitmap(esp_lcd_panel_handle_t panel, int x0, int y0,
                              int x1, int y1, const void *pixels) {
    (void)panel;
    if (pending || x0 || x1 != SCREEN_W || y0 < 0 || y1 > SCREEN_H || y1-y0 != SCREEN_BAND_H) exit(3);
    pending = pixels; pending_y = y0; return 0;
}
int esp_lcd_panel_io_tx_param(esp_lcd_panel_io_handle_t io, int cmd,
                             const void *data, size_t size) {
    (void)io; (void)cmd; (void)data; (void)size;
    if (pending) {
        memcpy(lcd + pending_y * SCREEN_W * 2, pending, SCREEN_W * SCREEN_BAND_H * 2);
        pending = NULL;
    }
    return 0;
}
int main(void) {
    if (!assets_init() || !render_init()) return 2;
    for (unsigned sid = 1; sid <= 151; sid++) {
        species_t sp; sprite_asset_t back; uint8_t front_size = 0;
        const uint8_t *front = assets_front_sprite(sid, &front_size);
        if (!assets_species(sid, &sp) || !assets_back_sprite_info(sid, &back) ||
            !front || !front_size || back.w != 48 || back.h != 48 || assets_back_sprite(sid)) return 4;
        uint16_t plain[4], normal[4];
        assets_palette(sp.palette, plain);
        assets_palette_variant(sp.palette, false, normal);
        if (memcmp(plain, normal, sizeof plain)) return 5;
        for (unsigned view = 0; view < 2; view++) for (unsigned shiny = 0; shiny < 2; shiny++) {
            const uint8_t *source = view ? back.data : front;
            int w = view ? back.w : front_size, h = view ? back.h : front_size;
            uint16_t pal[4]; assets_palette_variant(sp.palette, shiny != 0, pal);
            for (int band = 0; band < SCREEN_H; band += SCREEN_BAND_H) {
                screen_band_clear(0xffff);
                render_sprite_2bpp_wh(32, 70-band, source, w, h, 2, pal);
                screen_push_band(band);
            }
            if (pending) return 6;
            printf("ART %u %u %u %d %d %u\n", sid, view, shiny, w, h, sp.palette);
            fwrite(pal, sizeof(uint16_t), 4, stdout);
            fwrite(lcd, 1, sizeof lcd, stdout);
        }
    }
    // The white index is intentionally transparent: it preserves a white
    // background, and does not become another body color on a different one.
    const uint8_t white_pixels[1] = {0xff};
    const uint16_t pal[4] = {0, 1, 2, 0xffff};
    screen_band_clear(0x1234);
    render_sprite_2bpp_wh(8, 8, white_pixels, 4, 1, 1, pal);
    for (int x = 8; x < 12; x++) if (screen_band()[8 * SCREEN_W + x] != 0x1234) return 7;
    uint16_t invalid[4]; assets_palette_variant(255, true, invalid);
    if (invalid[0] || invalid[1] || invalid[2] || invalid[3] != 0xffff) return 8;
    return 0;
}
'''


def rgb565(c):
    return (c[0] << 11) | (((c[1] << 1) | (c[1] >> 4)) << 5) | c[2]


def rgb5(value):
    return value & 31, (value >> 5) & 31, (value >> 10) & 31


def packed_rgb5(c):
    return c[0] | (c[1] << 5) | (c[2] << 10)


def unpack_shades(data):
    return [b >> shift & 3 for b in data for shift in (6, 4, 2, 0)]


def gameplay_bytes(data):
    data = bytearray(data)
    require(struct.unpack_from('<4sHHI', data) == (b'GEN1', 1, 32, 151), 'invalid gameplay header')
    for sid in range(151): data[16 + sid * 32 + 23] = 0
    return bytes(data)


def check(src: Path, assets: Path, reference: Path | None):
    tree_text = subprocess.check_output(['git', '-C', str(src), 'ls-tree', '-r', COMMIT], text=True)
    tree = {line.split('\t', 1)[1]: line.split()[2] for line in tree_text.splitlines()}
    source_hashes = {}
    def pinned(path):
        data = (src / path).read_bytes()
        digest = hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()
        require(tree.get(path) == digest, f'upstream source changed: {path}')
        source_hashes[path] = hashlib.sha256(data).hexdigest()
        return data
    make = pinned('Makefile').decode()
    reverse = set(re.findall(r'gfx/pokemon/([^/]+)/normal\.gbcpal: tools/gbcpal \+= --reverse', make))
    table = pinned('data/pokemon/palettes.asm').decode()
    names = re.findall(r'INCBIN "gfx/pokemon/([^/]+)/normal\.gbcpal", middle_colors', table)[:151]
    require(len(names) == 151, 'source species table is incomplete')
    blobs = {n: (assets / n).read_bytes() for n in FILES}
    fronts = read_fronts(blobs['gen1_front.bin'])
    back_blob = blobs['gen1_back.bin']
    magic, ver, bw, bh, per, count = struct.unpack_from('<4sHHHHI', back_blob)
    require((magic, ver, bw, bh, per, count) == (b'BACK', 1, 48, 48, 576, 151), 'back schema is not original Crystal 48x48')
    require(len(back_blob) == 16 + per * count, 'invalid back length')
    backs = {sid: (48, back_blob[16+(sid-1)*per:16+sid*per]) for sid in range(1, 152)}
    p = blobs['palettes.bin']
    magic, ver, pairs, colors, count = struct.unpack_from('<4sHHHH', p)
    require(magic == b'PALS' and ver == 1 and colors == 4 and count == 151 and 1 <= pairs <= 151, 'invalid palette header')
    require(len(p) == 12 + pairs * 16 + 151, 'invalid paired palette length')
    palettes = [struct.unpack_from('<4H', p, 12 + n * 8) for n in range(pairs * 2)]
    indices = p[12 + pairs * 16:]
    require(all(i < pairs for i in indices), 'invalid per-species palette index')
    require(indices == bytes(blobs['gen1.bin'][16+n*32+23] for n in range(151)), 'gameplay palette bytes disagree')
    if reference:
        require(gameplay_bytes(reference.read_bytes()) == gameplay_bytes(blobs['gen1.bin']),
                'gameplay bytes changed outside palette byte 23')
    expected = {}
    stats = Counter()
    size_counts = Counter()
    with tempfile.TemporaryDirectory(prefix='verify_pokemon_art_') as temporary:
        temp = Path(temporary)
        for name in ('gbcpal.c', 'common.h'):
            (temp / name).write_bytes(pinned('tools/' + name))
        subprocess.run(['cc', '-O2', '-std=c17', str(temp/'gbcpal.c'), '-o', str(temp/'gbcpal')], check=True)
        for sid, name in enumerate(names, 1):
            images, input_pals = {}, []
            for view in ('front', 'back'):
                path = f'gfx/pokemon/{name}/{view}.png'; pinned(path)
                with Image.open(src/path) as image:
                    width, height = image.size
                    require(width in (40, 48, 56) and height >= width, f'#{sid} invalid source dimensions')
                    rgba = image.convert('RGBA')
                    require(all(c[3] == 255 for c in rgba.get_flattened_data()), f'#{sid} source contains unexpected alpha')
                    all_colors = {tuple(v >> 3 for v in color[:3]) for color in rgba.get_flattened_data()}
                    raw = temp/f'{view}.gbcpal'
                    raw.write_bytes(b''.join(struct.pack('<H', packed_rgb5(c)) for c in sorted(all_colors)))
                    input_pals.append(raw)
                    first = rgba.crop((0, 0, width, width)).convert('RGB')
                    images[view] = (width, [tuple(v >> 3 for v in color) for color in first.get_flattened_data()])
            output = temp/'normal.gbcpal'
            subprocess.run([str(temp/'gbcpal'), *(['--reverse'] if name in reverse else []),
                            str(output), *map(str, input_pals)], check=True)
            normal_gbc = [rgb5(v) for v in struct.unpack('<4H', output.read_bytes())]
            shiny_text = pinned(f'gfx/pokemon/{name}/shiny.pal').decode()
            middle = [tuple(map(int, row)) for row in re.findall(r'\bRGB\s+(\d+)\s*,\s*(\d+)\s*,\s*(\d+)', shiny_text)]
            require(len(middle) == 2, f'#{sid} invalid shiny palette')
            shiny_gbc = [WHITE, *middle, BLACK]
            for shiny, source_pal in enumerate((normal_gbc, shiny_gbc)):
                actual_pal = palettes[indices[sid-1] + shiny*pairs]
                oracle_pal = tuple(rgb565(c) for c in reversed(source_pal))
                require(actual_pal == oracle_pal, f'#{sid} {"shiny" if shiny else "normal"} palette differs from upstream')
            for view, atlas in (('front', fronts), ('back', backs)):
                size, packed = atlas[sid]
                source_size, source_pixels = images[view]
                actual = unpack_shades(packed)
                require(size == source_size and len(actual) == len(source_pixels), f'#{sid} {view} source canvas changed')
                oracle_shades = [3-normal_gbc.index(c) for c in source_pixels]
                errors = sum(a != b for a, b in zip(actual, oracle_shades))
                require(errors == 0, f'#{sid} {view}: {errors} source shade mismatches')
                stats['source_images'] += 1
                stats['source_pixels'] += len(actual)
                stats['source_white_pixels_preserved'] += actual.count(3)
                if view == 'front': size_counts[size] += 1
                for shiny, source_pal in enumerate((normal_gbc, shiny_gbc)):
                    expected[sid, view, shiny] = (size, [rgb565(source_pal[3-shade]) for shade in oracle_shades],
                                                 tuple(rgb565(c) for c in reversed(source_pal)))

        # Build only the actual asset/render/screen path and minimal LCD sink.
        (temp/'driver.c').write_text(C_DRIVER)
        asm = []
        for name in (*FILES, 'moves.bin', 'ui.bin', 'font16.bin'):
            path = (assets/name if name in FILES else ROOT/'assets'/name).resolve()
            symbol = '_binary_' + name.replace('.', '_')
            quoted = str(path).replace('\\', '\\\\').replace('"', '\\"')
            asm += ['.balign 4', f'.global {symbol}_start', f'.global {symbol}_end',
                    f'{symbol}_start:', f'.incbin "{quoted}"', f'{symbol}_end:']
        (temp/'assets.S').write_text('\n'.join(asm)+'\n')
        main, host = ROOT/'firmware/main', ROOT/'tools/inspector/host/include'
        subprocess.run(['cc', '-std=gnu11', '-O2', '-DHOST_BUILD=1', '-Wall', '-Wextra',
                        '-Wno-unused-variable', '-Wno-unused-but-set-variable', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                        '-I', str(main), '-I', str(host), str(temp/'driver.c'),
                        str(main/'assets.c'), str(main/'pokemon_names.c'),
                        str(main/'render.c'), str(main/'screen.c'),
                        str(temp/'assets.S'), '-lz', '-o', str(temp/'driver')], check=True)
        with (temp/'renders.bin').open('wb') as stream:
            subprocess.run([str(temp/'driver')], stdout=stream, check=True)
        with (temp/'renders.bin').open('rb') as stream:
            for _ in range(604):
                fields = stream.readline().decode().split()
                require(len(fields) == 7 and fields[0] == 'ART', 'C render protocol differs')
                sid, view_index, shiny, w, h, pal_index = map(int, fields[1:])
                view = ('front', 'back')[view_index]
                size, colors, palette = expected[sid, view, shiny]
                require((w, h, pal_index) == (size, size, indices[sid-1]), f'#{sid}: actual C lookup geometry/index differs')
                require(struct.unpack('<4H', stream.read(8)) == palette, f'#{sid}: actual C palette lookup differs')
                pixels = stream.read(240 * 320 * 2)
                require(len(pixels) == 240 * 320 * 2, 'truncated C render')
                oracle = bytearray(b'\xff\xff' * (240 * 320))
                for y in range(size):
                    row = b''.join(struct.pack('>H', color) * 2 for color in colors[y*size:(y+1)*size])
                    for dy in (0, 1):
                        offset = ((70 + y*2 + dy) * 240 + 32) * 2
                        oracle[offset:offset+len(row)] = row
                require(pixels == oracle, f'#{sid} {view} shiny={shiny}: actual C output differs from source pixels')
                stats['c_renders'] += 1
                stats['compared_c_screen_pixels'] += 240 * 320
            require(not stream.read(1), 'extra C render output')
    require(stats['source_images'] == 302 and stats['c_renders'] == 604, 'incomplete image/variant coverage')
    require(all((assets/name).read_bytes() == blob for name, blob in blobs.items()), 'assets changed during verification')
    return {'status': 'PASS', 'repository': 'https://github.com/pret/pokecrystal', 'commit': COMMIT,
            'stats': dict(stats), 'front_size_counts': dict(sorted(size_counts.items())), 'back_size': [48, 48],
            'palette_pairs': pairs, 'maximum_combined_palette_index': max(indices)+pairs,
            'reverse_kanto_species': [n for n in names if n in reverse],
            'source_index_mismatches': 0, 'normal_palette_mismatches': 0, 'shiny_palette_mismatches': 0,
            'actual_c_pixel_mismatches': 0,
            'gameplay_sha256_except_palette_byte_23': hashlib.sha256(gameplay_bytes(blobs['gen1.bin'])).hexdigest(),
            'gameplay_reference_checked': str(reference) if reference else None,
            'source_inputs_sha256': source_hashes,
            'asset_sha256': {name: hashlib.sha256(blob).hexdigest() for name, blob in blobs.items()},
            'scope': 'static Crystal first front frame and back; integer 2x normal/shiny C rendering on white',
            'limits': 'Index 3 stays original white but is transparent in renderer; white page background required. P6 nearest-neighbor 32px thumbnails are reduced representations, not source-pixel 1:1.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--src', type=Path, default=Path('/tmp/pokecrystal'))
    ap.add_argument('--assets', type=Path, default=ROOT/'assets')
    ap.add_argument('--gameplay-reference', type=Path)
    ap.add_argument('--report', type=Path, default=ROOT/'reports/pokemon-art-verification-2026-09-07.json')
    args = ap.parse_args()
    result = check(args.src, args.assets, args.gameplay_reference)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('source_inputs_sha256',)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
