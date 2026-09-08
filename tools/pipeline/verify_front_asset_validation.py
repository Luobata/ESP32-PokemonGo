#!/usr/bin/env python3
"""Exercise actual assets.c FRNT rejection and failed-reload invalidation.

Only the host fixture's embedded header is writable. Repository assets remain
untouched; the supported 40/48/56 images come from the current production atlas.
"""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ('gen1.bin', 'gen1_front.bin', 'gen1_back.bin', 'palettes.bin',
          'moves.bin', 'ui.bin', 'font16.bin')

DRIVER = r'''
#include <stdio.h>
#include <string.h>
#include "assets.h"
extern uint8_t front[] asm("_binary_gen1_front_bin_start");

static void put16(uint8_t *p, unsigned n) { p[0] = n; p[1] = n >> 8; }
static void put32(uint8_t *p, unsigned n) {
    put16(p, n); put16(p + 2, n >> 16);
}
static int valid(void) {
    if (!assets_init()) return 1;
    unsigned sizes = 0;
    for (unsigned sid = 1; sid <= 151; sid++) {
        uint8_t size = 0;
        if (!assets_front_sprite(sid, &size)) return 2;
        if (size == 40) sizes |= 1;
        else if (size == 48) sizes |= 2;
        else if (size == 56) sizes |= 4;
        else return 3;
    }
    return sizes == 7 ? 0 : 4;
}
static int rejected(const char *label) {
    uint8_t size = 255;
    if (assets_init()) { fprintf(stderr, "%s: invalid atlas accepted\n", label); return 5; }
    if (assets_front_sprite(1, &size) || size) {
        fprintf(stderr, "%s: stale front remained available\n", label); return 6;
    }
    return 0;
}
int main(void) {
    int error = valid(); if (error) return error;
    uint8_t original[44]; memcpy(original, front, sizeof original);
    const unsigned invalid_sizes[] = {41, 256};
    for (unsigned i = 0; i < 2; i++) {
        unsigned size = invalid_sizes[i];
        put16(front + 8, size);
        put16(front + 10, (size * size + 3) / 4);
        put32(front + 12, 1); // Keep the bad record within the valid blob length.
        error = rejected(size == 41 ? "row stride 41" : "uint8 width 256");
        if (error) return error;
        memcpy(front, original, sizeof original);
        error = valid(); if (error) return error;
    }
    front[0] = 'X';
    error = rejected("failed reload"); if (error) return error;
    memcpy(front, original, sizeof original);
    error = valid(); if (error) return error;
    puts("PASS: 151 production fronts at 40/48/56; reject 41/256; failed reload clears lookup; recovery succeeds");
    return 0;
}
'''


def check(asset_source: Path = ROOT / 'firmware/main/assets.c') -> str:
    with tempfile.TemporaryDirectory(prefix='verify_front_assets_') as directory:
        temp = Path(directory)
        (temp / 'probe.c').write_text(DRIVER)
        assembly = ['.data']
        for name in ASSETS:
            symbol = '_binary_' + name.replace('.', '_')
            path = str(ROOT / 'assets' / name).replace('\\', '\\\\').replace('"', '\\"')
            assembly += ['.balign 4', f'.global {symbol}_start', f'.global {symbol}_end',
                         f'{symbol}_start:', f'.incbin "{path}"', f'{symbol}_end:']
        (temp / 'assets.S').write_text('\n'.join(assembly) + '\n')
        subprocess.run(['cc', '-std=gnu11', '-O2', '-DHOST_BUILD=1',
                        '-I', str(ROOT / 'firmware/main'),
                        '-I', str(ROOT / 'tools/inspector/host/include'),
                        str(temp / 'probe.c'), str(asset_source),
                        str(ROOT / 'firmware/main/pokemon_names.c'), str(temp / 'assets.S'),
                        '-o', str(temp / 'probe')], check=True)
        return subprocess.check_output([str(temp / 'probe')], text=True).strip()


if __name__ == '__main__':
    print(check())
