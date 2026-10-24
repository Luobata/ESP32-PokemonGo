#!/usr/bin/env python3
"""Compile a pinned Crystal catalog while preserving all 151 existing records.

Output goes to an explicit staging directory. Installing gameplay assets and
enabling new species require the versioned runtime/save migration separately.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

from convert_pokemon_art import PinnedTree, COMMIT, generate as art
from convert_pokemon_animation import generate as animation

ROOT = Path(__file__).resolve().parents[2]
TYPES = 'NORMAL FIRE WATER ELECTRIC GRASS ICE FIGHTING POISON GROUND FLYING PSYCHIC BUG ROCK GHOST DRAGON DARK STEEL'.split()


def constants(text: str, start: int) -> dict[str, int]:
    names = re.findall(r'^\s*const\s+(\w+)', text, re.M)
    return {name: start+i for i, name in enumerate(names)}


def catalog(tree: PinnedTree) -> list[dict]:
    names = re.findall(r'INCLUDE "data/pokemon/base_stats/([^/]+)\.asm"', tree.read('data/pokemon/base_stats.asm').decode())
    species = constants(tree.read('constants/pokemon_constants.asm').decode(), 1)
    moves = constants(tree.read('constants/move_constants.asm').decode(), 0)
    scripts = tree.read('data/pokemon/evos_attacks.asm').decode()
    sections = re.split(r'^\w+EvosAttacks:\s*$', scripts, flags=re.M)[1:]
    if len(names) != 251 or len(sections) != 251:
        raise ValueError('expected all 251 Crystal species and learning scripts')
    sizes = {r['id']: r for r in json.loads((ROOT/'data/pokemon_johto/names_sizes.json').read_text())['pokemon']}
    rows = []
    for sid, (name, script) in enumerate(zip(names, sections), 1):
        raw = tree.read(f'data/pokemon/base_stats/{name}.asm').decode()
        stats = re.search(r'^\s*db\s+(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*$', raw, re.M)
        types = re.search(r'^\s*db\s+(\w+),\s*(\w+)\s*; type', raw, re.M)
        catch = re.search(r'^\s*db\s+(\d+)\s*; catch rate', raw, re.M)
        if not stats or not types or not catch:
            raise ValueError(f'incomplete base data: {name}')
        tm = re.search(r'^[ \t]*tmhm[ \t]*([^;\n]*)', raw, re.M)
        evolutions, learn = [], []
        for line in script.splitlines():
            fields = line.split(';')[0].strip()
            if not fields.startswith('db '):
                continue
            fields = [v.strip() for v in fields[3:].split(',')]
            if fields[0].startswith('EVOLVE_'):
                evolutions.append({'method': fields[0], 'conditions': fields[1:-1], 'target': species[fields[-1]]})
            elif len(fields) == 2 and fields[0].isdigit():
                learn.append([int(fields[0]), moves[fields[1]]])
        row = {'id': sid, 'slug': name, 'stats': list(map(int, stats.groups())),
               'types': [TYPES.index(t.removesuffix('_TYPE')) for t in types.groups()], 'catch_rate': int(catch[1]),
               'evolutions': evolutions, 'level_up': learn,
               'tm_hm': [moves[x.strip()] for x in tm[1].split(',') if x.strip()] if tm else []}
        if sid > 151:
            row.update(sizes[sid])
        rows.append(row)
    return rows


def species_blob(existing: bytes, rows: list[dict]) -> bytes:
    magic, version, stride, count, pool_size = struct.unpack_from('<4sHHII', existing)
    if (magic,version,stride) != (b'GEN1',1,32) or count not in (151,251) or len(existing)!=16+count*32+pool_size:
        raise ValueError('invalid existing species asset')
    records = bytearray(existing[16:16+151*32])
    # Only retain the original strings referenced by the original records.
    end = max(max(struct.unpack_from('<H', records, i*32)[0]+records[i*32+2],
                  struct.unpack_from('<H', records, i*32+20)[0]+records[i*32+22]) for i in range(151))
    pool = bytearray(existing[16+count*32:16+count*32+end])
    for row in rows[151:]:
        r = bytearray(32)
        slug, zh = row['slug'].encode(), row['name_zh'].encode()
        struct.pack_into('<HB',r,0,len(pool),len(slug));pool+=slug
        r[3],r[4] = row['types'][0], row['types'][1] if row['types'][1]!=row['types'][0] else 255
        r[5],r[6],r[7] = 31,row['catch_rate'],255
        simple = [e for e in row['evolutions'] if e['method']=='EVOLVE_LEVEL']
        if len(simple)==1:
            r[7:10] = bytes((0,simple[0]['target'],int(simple[0]['conditions'][0])))
        hp,attack,defense,speed,special,_ = row['stats']
        r[10:15] = bytes((hp,attack,defense,special,speed))
        r[15] = 2 if row['id']==251 else int(row['id'] in (243,244,245,249,250))
        struct.pack_into('<HHHB',r,16,row['height_dm'],row['weight_hg'],len(pool),len(zh));pool+=zh
        records += r
    if len(pool)>65535:
        raise ValueError('name pool exceeds existing offset width')
    return struct.pack('<4sHHII',b'GEN1',1,32,251,len(pool))+records+pool


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    tree= PinnedTree(args.src)
    rows=catalog(tree)
    products=art(args.src,species_blob((ROOT/'assets/gen1.bin').read_bytes(),rows))
    products.update(animation(args.src,products['gen1_front.bin']))
    names_source=ROOT/'data/pokemon_johto/names_sizes.json'
    products['johto_catalog.json']=(json.dumps({'commit':COMMIT,'inputs':tree.inputs,
        'names_sizes_source':{**{k:v for k,v in json.loads(names_source.read_text()).items() if k!='pokemon'},
                              'local_sha256':hashlib.sha256(names_source.read_bytes()).hexdigest()},
        'pokemon':rows},ensure_ascii=False,indent=2)+'\n').encode()
    args.out.mkdir(parents=True,exist_ok=True)
    for name,data in products.items():
        (args.out/name).write_bytes(data)
    manifest={'species':len(rows),'outputs':{name:{'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in products.items()}}
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'species':251,'staging':str(args.out),'art_bytes':sum(len(products[n]) for n in ('gen1.bin','gen1_front.bin','gen1_back.bin','palettes.bin')),
                      'animation_bytes':json.loads(products['pokemon_animation_sources.json'])['compiled_atlas_bytes']}))


if __name__=='__main__':
    main()
