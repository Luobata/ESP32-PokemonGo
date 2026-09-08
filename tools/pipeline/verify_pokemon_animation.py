#!/usr/bin/env python3
"""Verify original per-species front frames/timing and real C LCD rendering.

Pillow + pinned upstream gbcpal + an independent tick VM supply expected data.
The driver links production assets/render/screen/animation code under ASan/UBSan.
--negative additionally proves three compilable sampling/decoding defects fail.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from pokemon_animation_oracle import COMMIT, OriginalMotion, load_original, rgb565

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / 'firmware/main'
ASSETS = ('gen1.bin', 'gen1_front.bin', 'gen1_back.bin', 'palettes.bin', 'font16.bin', 'moves.bin', 'ui.bin')
ROI = 112

DRIVER = r'''
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "assets.h"
#include "pokemon_animation.h"
#include "render.h"
#include "screen.h"
#include "bsp_display.h"

// Pixel oracle keeps the display lit; wake/timeout routing has its own production-core gate.
bool screen_idle_is_off(void) { return false; }
static unsigned char lcd[SCREEN_W * SCREEN_H * 2];
static const void *pending;
static int pending_y;
int esp_lcd_panel_draw_bitmap(esp_lcd_panel_handle_t p, int x0, int y0,
                              int x1, int y1, const void *pixels) {
    (void)p;
    if (pending || x0 || x1 != SCREEN_W || y0 < 0 || y1 > SCREEN_H || y1-y0 != SCREEN_BAND_H) exit(3);
    pending = pixels; pending_y = y0; return 0;
}
int esp_lcd_panel_io_tx_param(esp_lcd_panel_io_handle_t io, int cmd, const void *data, size_t size) {
    (void)io; (void)cmd; (void)data; (void)size;
    if (pending) {
        memcpy(lcd + pending_y * SCREEN_W * 2, pending, SCREEN_W * SCREEN_BAND_H * 2);
        pending = NULL;
    }
    return 0;
}
static void sample(unsigned sid, uint32_t ms) {
    pokemon_anim_sample_t pose = pokemon_anim_sample(sid, ms);
    printf("TIME %u %lu %u %u\n", sid, (unsigned long)ms, pose.frame, pose.finished);
}
int main(void) {
    if (!assets_init() || !render_init()) return 2;
    for (unsigned sid = 1; sid <= 151; sid++) {
        pokemon_anim_info_t info;
        species_t species;
        if (!pokemon_anim_info(sid, &info) || !assets_species(sid, &species)) return 4;
        printf("INFO %u %u %u %u %u %u %u %u\n", sid, info.size, info.frame_count,
               info.duration_ticks, info.x, info.y, info.w, info.h);
        for (unsigned tick = 0; tick <= info.duration_ticks + 2u; tick++) {
            uint32_t ms = (tick * 1000u + 59u) / 60u;
            sample(sid, ms);
            if (ms) sample(sid, ms-1u);
        }
        sample(sid, UINT32_MAX);
        sample(sid, 0); // Revisit after unrelated end/large samples.
        for (unsigned frame = 0; frame < info.frame_count; frame++) {
            unsigned char guarded[POKEMON_ANIM_BUFFER_BYTES + 16];
            memset(guarded, 0xa5, sizeof guarded);
            sprite_asset_t image;
            if (!pokemon_anim_decode(sid, frame, guarded + 8, POKEMON_ANIM_BUFFER_BYTES, &image)) return 5;
            if (image.data != guarded+8 || image.w != info.size || image.h != info.size) return 6;
            size_t bytes = (size_t)image.w * image.h / 4;
            for (unsigned i = 0; i < sizeof guarded; i++)
                if ((i < 8 || i >= bytes+8) && guarded[i] != 0xa5) return 7;
            printf("ART %u %u %u\n", sid, frame, info.size);
            fwrite(image.data, 1, bytes, stdout);
            for (unsigned shiny = 0; shiny < 2; shiny++) {
                uint16_t palette[4]; assets_palette_variant(species.palette, shiny != 0, palette);
                for (int band = 0; band < SCREEN_H; band += SCREEN_BAND_H) {
                    screen_band_clear(0xffff);
                    render_sprite_2bpp_wh(64, 64-band, image.data, image.w, image.h, 2, palette);
                    screen_push_band(band);
                }
                if (pending) return 8;
                fwrite(palette, 2, 4, stdout);
                for (int y = 64; y < 64+112; y++) fwrite(lcd+(y*SCREEN_W+64)*2, 2, 112, stdout);
            }
            // A one-byte-short destination must fail and clear the descriptor.
            image = (sprite_asset_t){guarded, 9, 9};
            if (pokemon_anim_decode(sid, frame, guarded+8, bytes-1, &image) || image.data || image.w || image.h) return 9;
        }
        unsigned char buffer[POKEMON_ANIM_BUFFER_BYTES]; sprite_asset_t invalid;
        if (pokemon_anim_decode(sid, info.frame_count, buffer, sizeof buffer, &invalid) || invalid.data) return 10;
    }
    for (unsigned invalid_id = 0; invalid_id <= 65535; invalid_id += 65535) {
        pokemon_anim_info_t info = {1,1,1,1,1,1,1};
        pokemon_anim_sample_t pose = pokemon_anim_sample(invalid_id, 0);
        unsigned char buffer[POKEMON_ANIM_BUFFER_BYTES]; sprite_asset_t image = {buffer,1,1};
        if (pokemon_anim_info(invalid_id, &info) || info.size || info.frame_count || info.duration_ticks ||
            info.x || info.y || info.w || info.h || !pose.finished || pose.frame ||
            pokemon_anim_decode(invalid_id, 0, buffer, sizeof buffer, &image) || image.data || image.w || image.h) return 11;
    }
    return 0;
}
'''


def build_driver(directory: Path, source: Path) -> Path:
    (directory / 'driver.c').write_text(DRIVER)
    assembly = []
    for name in ASSETS:
        symbol = '_binary_' + name.replace('.', '_')
        path = str(ROOT / 'assets' / name).replace('\\', '\\\\').replace('"', '\\"')
        assembly += ['.balign 4', f'.global {symbol}_start', f'.global {symbol}_end',
                     f'{symbol}_start:', f'.incbin "{path}"', f'{symbol}_end:']
    (directory / 'assets.S').write_text('\n'.join(assembly) + '\n')
    executable = directory / 'driver'
    subprocess.run(['cc', '-O1', '-std=gnu11', '-DHOST_BUILD=1', '-Wall', '-Wextra', '-Werror',
                    '-Wno-unused-parameter', '-Wno-unused-function', '-Wno-unused-variable',
                    '-Wno-unused-but-set-variable', '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    '-I', str(MAIN), '-I', str(ROOT / 'tools/inspector/host/include'),
                    '-I', str(ROOT / 'firmware/components/bsp/include'),
                    str(directory / 'driver.c'), str(source), str(MAIN / 'assets.c'),
                    str(MAIN / 'pokemon_names.c'), str(MAIN / 'render.c'), str(MAIN / 'screen.c'),
                    str(directory / 'assets.S'), '-lz', '-o', str(executable)],
                   check=True, capture_output=True, text=True)
    return executable


def pixels(motion: OriginalMotion, frame: int, shiny: bool) -> tuple[tuple[int, ...], bytes]:
    palette_gbc = motion.shiny_gbc if shiny else motion.normal_gbc
    palette = tuple(rgb565(color) for color in reversed(palette_gbc))
    result = bytearray(b'\xff\xff' * (ROI*ROI))
    for y in range(motion.size):
        colors = motion.frames[frame][y*motion.size:(y+1)*motion.size]
        row = b''.join(struct.pack('>H', palette[3-motion.normal_gbc.index(color)])*2 for color in colors)
        for dy in (0, 1):
            start = (y*2+dy)*ROI*2
            result[start:start+len(row)] = row
    return palette, bytes(result)


def check(executable: Path, directory: Path, motions: dict[int, OriginalMotion]) -> Counter:
    output = directory / 'renders.bin'
    with output.open('wb') as stream:
        subprocess.run([str(executable)], stdout=stream, check=True, timeout=60)
    stats = Counter()
    with output.open('rb') as stream:
        for sid, motion in motions.items():
            fields = stream.readline().decode().split()
            expected = (sid, motion.size, len(motion.frames), len(motion.ticks),
                        motion.bbox[0], motion.bbox[1], motion.bbox[2]-motion.bbox[0], motion.bbox[3]-motion.bbox[1])
            assert fields[0] == 'INFO' and tuple(map(int, fields[1:])) == expected, f'#{sid}: metadata/union differs from original'
            stats['species'] += 1
            milliseconds = []
            for tick in range(len(motion.ticks)+3):
                ms = (tick*1000+59)//60
                milliseconds.append(ms)
                if ms:
                    milliseconds.append(ms-1)
            milliseconds += [0xFFFFFFFF, 0]
            for ms in milliseconds:
                fields = stream.readline().decode().split()
                tick = ms*60//1000
                finished = tick >= len(motion.ticks)
                expected = (sid, ms, 0 if finished else motion.ticks[tick], int(finished))
                assert fields[0] == 'TIME' and tuple(map(int, fields[1:])) == expected, f'#{sid}: original timing differs at {ms} ms'
                stats['timing_samples'] += 1
            for frame in range(len(motion.frames)):
                fields = stream.readline().decode().split()
                assert fields == ['ART', str(sid), str(frame), str(motion.size)], f'#{sid}: C frame lookup mismatch'
                packed = stream.read(motion.size*motion.size//4)
                assert packed == motion.packed(frame), f'#{sid} frame {frame}: decoded 2bpp differs from original PNG'
                stats['decoded_frames'] += 1
                for shiny in (False, True):
                    palette, expected_pixels = pixels(motion, frame, shiny)
                    assert struct.unpack('<4H', stream.read(8)) == palette, f'#{sid}: original palette mismatch'
                    actual = stream.read(ROI*ROI*2)
                    assert actual == expected_pixels, f'#{sid} frame {frame} shiny={shiny}: actual C LCD pixels differ'
                    stats['c_renders'] += 1
                    stats['rgb565_pixels'] += ROI*ROI
        assert not stream.read(1), 'unexpected extra C output'
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', type=Path, default=Path('/tmp/pokecrystal'))
    parser.add_argument('--report', type=Path, default=ROOT / 'reports/pokemon-animation-verification-2026-09-08.json')
    parser.add_argument('--negative', action='store_true')
    args = parser.parse_args()
    motions, hashes = load_original(args.src)
    negatives = []
    with tempfile.TemporaryDirectory(prefix='verify-pokemon-animation-') as name:
        directory = Path(name)
        source = MAIN / 'pokemon_animation.c'
        stats = check(build_driver(directory, source), directory, motions)
        print(f'PASS original front animations: {dict(stats)}')
        if args.negative:
            original = source.read_text()
            mutations = {
                'wrong patch row': ('source + row * 2u', 'source + 0u'),
                'half-speed source timing': ('* 60u / 1000u', '* 30u / 1000u'),
                'ending keeps a moving frame': ('return (pokemon_anim_sample_t){0, true};',
                                                'return (pokemon_anim_sample_t){r ? 1 : 0, true};'),
            }
            for label, (old, new) in mutations.items():
                assert original.count(old) == 1, f'negative anchor changed: {label}'
                mutant = directory / 'pokemon_animation.c'
                mutant.write_text(original.replace(old, new))
                executable = build_driver(directory, mutant)
                try:
                    check(executable, directory, motions)
                except AssertionError:
                    negatives.append(label)
                    print(f'PASS negative: {label}')
                else:
                    raise AssertionError(f'broken animation escaped: {label}')
    result = {'status': 'PASS', 'commit': COMMIT, 'stats': dict(stats), 'source_sha256': hashes,
              'source_frames_range': [min(len(m.frames) for m in motions.values()), max(len(m.frames) for m in motions.values())],
              'duration_ticks_range': [min(len(m.ticks) for m in motions.values()), max(len(m.ticks) for m in motions.values())],
              'negatives_rejected': negatives, 'sanitizers': 'address,undefined',
              'scope': '151 original front scripts, all 789 PNG frames, original normal/shiny palettes and 2x C LCD rendering; back static'}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
