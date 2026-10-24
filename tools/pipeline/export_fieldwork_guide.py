#!/usr/bin/env python3
"""Export the development fieldwork walkthrough without relabelling a release."""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from build import load_data

OUTPUT = ROOT / 'tools/save-manager/web/guide/fieldwork.js'
TYPES = dict(zip(
    'NORMAL FIRE WATER ELECTRIC GRASS ICE FIGHTING POISON GROUND FLYING PSYCHIC BUG ROCK GHOST DRAGON DARK STEEL'.split(),
    '一般 火 水 电 草 冰 格斗 毒 地面 飞行 超能 虫 岩石 幽灵 龙 恶 钢'.split()))


def catalog():
    source = (ROOT / 'firmware/main/johto_routes.c').read_text()
    routes_source = (ROOT / 'firmware/main/johto.c').read_text().split('const johto_trainer_t')[0]
    routes = re.findall(r'\{"([^"]+)","[^"]+",(\d+),\d+,\d+,', routes_source)
    paths = re.findall(r'\{"([^"]+)",\{([\d,]+)\}\}', source.split('static uint32_t route_mix')[0])
    assert len(routes) == 8 and len(paths) == 24
    mons = {m['id']: m for m in load_data(ROOT / 'assets/gen1.bin')}
    table = source.split('static const johto_probe_t PROBES[JOHTO_PROBE_COUNT]={')[1].split('\n};')[0]
    sites = []
    for line in table.strip().splitlines():
        head = re.match(r'\s*\{(\d+),(\d+),(\d+),(\d+),TY_(\w+),TY_(\w+),', line)
        assert head, line
        legend, step, route, path = map(int, head.groups()[:4])
        types = [TYPES[t] for t in head.groups()[4:] if t != 'NONE']
        strings = re.findall(r'"([^"\n]*)"', line)
        assert len(strings) == 8
        # Prefer the investigation path, then already accessible routes. Examples
        # are suggestions, never requirements for a particular species or move.
        candidates = []
        for index, (name, pool) in enumerate(paths):
            r, p = divmod(index, 3)
            if int(routes[r][1]) > max(4, int(routes[route][1])):
                continue
            for species in map(int, pool.split(',')):
                m = mons[species]
                if set(types) & {m['t1'], m['t2']}:
                    candidates.append((r != route or p != path, int(routes[r][1]), sum(m['st']), r, p, m))
        candidates.sort(key=lambda c: c[:5] + (c[5]['id'],))
        examples = []
        def add(candidate):
            _, _, _, r, p, m = candidate
            if any(e['id'] == m['id'] for e in examples):
                return
            examples.append(dict(id=m['id'], name=m['zh'], routeId=r, pathId=p,
                                 location=routes[r][0] + ' · ' + paths[r*3+p][0]))
        for type_name in types:
            add(next(c for c in candidates if type_name in (c[5]['t1'], c[5]['t2'])))
        for candidate in candidates:
            if len(examples) >= 2:
                break
            add(candidate)
        sites.append(dict(id=len(sites), legend=legend, step=step+1, title=strings[0],
                          clues=strings[1:3], hints=strings[3:5], routeId=route, pathId=path,
                          route=routes[route][0], path=paths[route*3+path][0],
                          badges=max(4, int(routes[route][1])), types=types,
                          examples=examples, found=strings[6], next=strings[7]))
    assert len(sites) == 17
    sources = ['firmware/main/johto_routes.c', 'firmware/main/johto_routes.h',
               'firmware/main/johto.c', 'firmware/main/johto_story.c', 'assets/gen1.bin']
    return dict(status='released', version='2026.10.24 · 城都伙伴协作调查',
                sourceHashes={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sources},
                sites=sites)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check', action='store_true')
    args = p.parse_args()
    rendered = 'export const FIELDWORK_GUIDE = ' + json.dumps(catalog(), ensure_ascii=False, indent=2) + ';\n'
    if args.check:
        assert OUTPUT.read_text() == rendered, 'Stale fieldwork guide: rerun export_fieldwork_guide.py'
    else:
        OUTPUT.write_text(rendered)
    print(json.dumps(dict(passed=True, sites=17, sourceCheck=args.check)))


if __name__ == '__main__':
    main()
