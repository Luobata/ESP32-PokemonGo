#!/usr/bin/env python3
"""Exercise actual P0/P9 pages and nav; real NVS tests are separate."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import Renderer, build, png
from server import page_value


def main():
    exe, version = build()
    evidence = ROOT/'reports/evidence/starter-capture-2026-09-07'
    evidence.mkdir(parents=True, exist_ok=True)
    cases = []
    for index, sid in enumerate((1,4,7,25)):
        r=Renderer(exe)
        try:
            r.command('boot 0 25 12 74 3 1 0')
            assert r.inspect()['needs_starter'] and r.inspect()['party_count']==0
            frame=r.command('key 2 1')
            assert frame['page']=='P9', 'skipping Oak must enter starter selection'
            for _ in range(index): frame=r.command('key 1 1')
            assert r.inspect()['party_count']==0, 'browsing cannot receive a starter'
            (evidence/f'P9-{sid:03d}.png').write_bytes(png(frame['pixels']))
            assert r.command('check')['mismatch']==0
            frame=r.command('key 0 1')
            state=r.inspect()
            assert frame['page']=='P1' and state['pet']==sid and state['level']==1
            assert state['party_count']==1 and state['caught']==1 and state['opening_seen']
            assert not state['needs_starter']
            r.command('page 9')
            r.command('key 1 1')
            r.command('key 0 1')
            state=r.inspect()
            assert state['pet']==sid and state['party_count']==1 and state['caught']==1
            cases.append(f'choose #{sid:03d}, persist fixture, no duplicate')
        finally:r.close()

    r=Renderer(exe)
    try:
        r.command('boot 9 25 12 74 3 1 0')
        # C is previous, including wraparound to Pikachu, never a bypass.
        assert r.command('key 2 1')['page']=='P9'
        r.command('save_fail 1')
        assert r.command('key 0 1')['page']=='P9'
        state=r.inspect()
        assert state['pet']==0 and state['party_count']==0 and state['caught']==0
        assert r.command('check')['mismatch']==0
        assert r.command('key 0 1')['page']=='P1'
        assert r.inspect()['pet']==25 and r.inspect()['party_count']==1
        cases.append('C wrap, failed save stays pending, retry receives Pikachu once')
    finally:r.close()

    r=Renderer(exe)
    try:
        r.command('boot 0 25 12 74 3 1 0')
        # Read every opening dialogue using normal A (first A reveals, next advances).
        for _ in range(20):
            if r.inspect()['page']==9:break
            r.command('tick 300')
            r.command('key 0 1')
        assert r.inspect()['page']==9 and r.inspect()['party_count']==0
        for page in range(1,7):
            assert r.command(f'page {page}')['page']=='P9', f'new game bypass via P{page}'
        cases.append('full opening reaches P9; every gameplay route guarded')
    finally:r.close()

    r=Renderer(exe)
    try:
        r.command('boot 1 133 30 74 3 1 0')
        before=r.inspect()
        r.command('page 0')
        assert r.command('key 2 1')['page']=='P1'
        r.command('page 9');r.command('key 0 1')
        after=r.inspect()
        assert all(before[k]==after[k] for k in ('pet','level','exp','party_count','caught'))
        cases.append('existing Eevee fixture retained after replaying opening/starter')
    finally:r.close()

    assert page_value({'page':9})==9
    for page in (7,8,True,-1,10):
        try:page_value({'page':page})
        except ValueError:pass
        else:raise AssertionError(f'unsupported page accepted: {page}')
    cases.append('HTTP P9 accepted; P7/P8 and malformed pages rejected')
    out={'build':version,'passed':cases,'scope':'actual C pages/navigation; fixture storage, see verify_starter.py for real world/save'}
    (evidence/'starter-preview.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(out,ensure_ascii=False))


if __name__=='__main__':main()
