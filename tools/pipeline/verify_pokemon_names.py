#!/usr/bin/env python3
"""Check curated names through actual assets.c and native page navigation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import ASSETS, Renderer, build, png
from generate_pokemon_names import generate, OUTPUT

DRIVER = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "assets.h"
#include "pokemon_names.h"
int main(int argc, char **argv) {
    (void)argv;
    assert(pokemon_names_get_style() == POKEMON_NAMES_OFFICIAL);
    assert(pokemon_names_legacy_count() == 151);
    assert(assets_init());
    for (int style = 0; style < POKEMON_NAMES_STYLE_COUNT; style++) {
        assert(pokemon_names_set_style(style));
        for (unsigned id = 1; id <= 151; id++) {
            species_t sp;
            memset(&sp, 0, sizeof(sp));
            assert(assets_species(id, &sp) && sp.id == id);
            printf("ROW\t%d\t%u\t%.*s\t", style, id, sp.name_zh_len, sp.name_zh);
            sp.name_zh = NULL; sp.name_zh_len = 0;
            for (unsigned k = 0; k < sizeof(sp); k++) printf("%02x", ((unsigned char *)&sp)[k]);
            putchar('\n');
        }
    }
    assert(!pokemon_names_set_style(-1));
    assert(!pokemon_names_set_style(POKEMON_NAMES_STYLE_COUNT));
    assert(pokemon_names_get_style() == POKEMON_NAMES_GS_LEGACY);
    assert(assets_init()); // Asset reload must not silently change display preference.
    assert(pokemon_names_get_style() == POKEMON_NAMES_GS_LEGACY);
    uint8_t length = 99;
    assert(!pokemon_names_override(0, &length) && length == 0);
    length = 99;
    assert(!pokemon_names_override(152, &length) && length == 0);
    assert(pokemon_names_override(1, NULL));
    if (argc == 1) {
        const char *retained = pokemon_names_override(149, &length);
        assert(retained && length == 6 && strcmp(retained, "肥大") == 0);
        assert(pokemon_names_set_style(POKEMON_NAMES_OFFICIAL));
        assert(strcmp(retained, "肥大") == 0); // Existing readers keep valid immutable storage.
        length = 99;
        assert(!pokemon_names_override(149, &length) && length == 0);
    }
    return 0;
}
'''


def original_names() -> dict[int, str]:
    blob = (ROOT / 'assets/gen1.bin').read_bytes()
    magic, version, stride, count, pool_size = struct.unpack_from('<4sHHII', blob)
    assert magic == b'GEN1' and count == 151 and len(blob) == 16 + stride * count + pool_size
    pool = 16 + stride * count
    names = {}
    for index in range(count):
        record = 16 + index * stride
        offset = struct.unpack_from('<H', blob, record + 20)[0]
        length = blob[record + 22]
        names[index + 1] = blob[pool + offset:pool + offset + length].decode()
    return names


def compile_probe(temp: Path, name_source: Path, missing=False) -> dict:
    main = ROOT / 'firmware/main'
    assembly = []
    for name in ASSETS:
        symbol = '_binary_' + name.replace('.', '_')
        path = str(ROOT / 'assets' / name).replace('\\', '\\\\').replace('"', '\\"')
        assembly += ['.balign 4', f'.global {symbol}_start', f'.global {symbol}_end',
                     f'{symbol}_start:', f'.incbin "{path}"', f'{symbol}_end:']
    (temp / 'assets.S').write_text('\n'.join(assembly) + '\n')
    (temp / 'driver.c').write_text(DRIVER)
    subprocess.run(['cc', '-std=gnu11', '-O2', '-DHOST_BUILD=1',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                    '-I', str(main), '-I', str(ROOT / 'tools/inspector/host/include'),
                    str(temp / 'driver.c'), str(main / 'assets.c'), str(name_source),
                    str(temp / 'assets.S'), '-o', str(temp / 'names')], check=True)
    lines = subprocess.check_output([str(temp / 'names')] + (['missing'] if missing else []), text=True).splitlines()
    rows = {}
    for line in lines:
        token, style, sid, name, metadata = line.split('\t')
        assert token == 'ROW'
        rows[int(style), int(sid)] = (name, metadata)
    assert len(rows) == 302
    return rows


def verify_assets(document: dict) -> dict:
    assert OUTPUT.read_text() == generate(), 'generated name source is stale'
    expected = {row['id']: row['name'] for row in document['records']}
    assert set(expected) == set(range(1, 152)), 'current curated release must cover all 151 IDs'
    official = original_names()
    assert expected[149] == '肥大' and official[149] == '快龙'
    assert expected[149] != '富阿', 'Crystal names must not leak into the Gold/Silver table'
    with tempfile.TemporaryDirectory(prefix='verify_names_') as directory:
        temp = Path(directory)
        rows = compile_probe(temp, OUTPUT)
        for sid in range(1, 152):
            assert rows[0, sid][0] == official[sid], f'official name changed #{sid}'
            assert rows[1, sid][0] == expected[sid], f'legacy source mismatch #{sid}'
            assert rows[0, sid][1] == rows[1, sid][1], f'non-name species fields changed #{sid}'
        # Remove a real entry only in a private build: the production assets API
        # must retain its official name when the selected dictionary is incomplete.
        target = '    [149] = "肥大",'
        assert OUTPUT.read_text().count(target) == 1
        missing = temp / 'names_missing.c'
        missing.write_text(OUTPUT.read_text().replace(target, '    [149] = NULL,'))
        partial = compile_probe(temp, missing, missing=True)
        assert partial[1, 149] == rows[0, 149], 'missing entry must fall back to official name and metadata'
        assert partial[1, 148] == rows[1, 148], 'fallback must not reset the selected version'
    return {'species': 151, 'actual_asset_reads': 604, 'sanitizers': ['address', 'undefined'],
            'fallback': 'private missing #149 entry retained official 快龙',
            'metadata_unchanged': True}


def verify_font(document: dict) -> int:
    blob = (ROOT / 'assets/font16.bin').read_bytes()
    magic, version, size, per, count = struct.unpack_from('<4sHHHI', blob)
    assert magic == b'FNT1' and size == 16 and per == 32
    codepoints = struct.unpack_from(f'<{count}H', blob, 14)
    required = set(''.join(row['name'] for row in document['records']) + '译名官方怀旧长按切换')
    missing = sorted(required - {chr(cp) for cp in codepoints})
    assert not missing, 'font missing names/UI characters; run normal firmware build: ' + ''.join(missing)
    glyphs = 14 + count * 2
    for char in required:
        index = codepoints.index(ord(char))
        assert any(blob[glyphs + index * per:glyphs + (index + 1) * per]), f'blank glyph {char}'
    return len(required)


def without_style(state):
    return {key: value for key, value in state.items() if key != 'names'}


def verify_native(evidence: Path) -> dict:
    executable, version = build()
    changed, same = [], []
    for page in (*range(7), 9):
        renderer = Renderer(executable)
        try:
            frame = renderer.command(f'boot {page} 149 12 149 3 1 0')
            assert renderer.inspect()['names'] == 0, 'old seven-argument fixture must use official names'
            if page in (3, 4):
                frame = renderer.command('tick 2000')
            before = renderer.inspect()
            legacy = renderer.command('names 1')
            after = renderer.inspect()
            assert after['names'] == 1 and without_style(before) == without_style(after), f'name switch changed game state P{page}'
            assert renderer.command('check')['mismatch'] == 0, f'name redraw left stale pixels P{page}'
            restored = renderer.command('names 0')
            assert restored['pixels'] == frame['pixels'], f'official roundtrip changed pixels P{page}'
            (changed if legacy['pixels'] != frame['pixels'] else same).append(page)
            if page in (3, 5):
                (evidence / f'P{page}-official.png').write_bytes(png(frame['pixels']))
                (evidence / f'P{page}-gs-legacy.png').write_bytes(png(legacy['pixels']))
            if page == 5:
                before = renderer.inspect()
                actual_key = renderer.command('key 0 3')
                after = renderer.inspect()
                assert after['names'] == 1 and without_style(before) == without_style(after)
                assert actual_key['pixels'] == legacy['pixels'], 'hardware long A must match the preview selector'
                renderer.command('key 2 1')
                assert renderer.inspect()['page'] == 1 and renderer.inspect()['names'] == 1
        finally:
            renderer.close()
    assert {1, 2, 3, 4, 5, 9} <= set(changed), f'names failed to reach a named page: {changed}'
    renderer = Renderer(executable)
    try:
        renderer.command('boot 5 149 12 149 3 1 0 1')
        assert renderer.inspect()['names'] == 1, 'explicit fixture preference was lost'
        renderer.command('key 0 3')
        assert renderer.inspect()['names'] == 0, 'hardware toggle must work in both directions'
    finally:
        renderer.close()
    return {'build': version, 'pages': 8, 'changed_pixels': changed,
            'pages_without_visible_species_names': same, 'hardware_long_A': True,
            'game_state_unchanged': True, 'roundtrip_pixels_equal': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=ROOT / 'reports/evidence/pokemon-names-2026-09-08')
    args = parser.parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    raw = (ROOT / 'data/pokemon_names/gs_legacy.json').read_bytes()
    document = json.loads(raw)
    result = {'dataset_sha256': hashlib.sha256(raw).hexdigest(),
              'assets': verify_assets(document), 'font_characters': verify_font(document),
              'native': verify_native(args.evidence)}
    (args.evidence / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
