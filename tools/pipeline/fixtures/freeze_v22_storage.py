#!/usr/bin/env python3
"""One-time append of the initial V22 storage fixture. Never run by tests.

Its logical bytes come from the immutable synthetic V21 historical fixture,
whose source commit/layout is retained. Only schema and storage codec change.
The encoder hash records the exact initial V22 implementation used, even before
its first release commit. Existing historical bytes are never regenerated.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[3]
DEST = ROOT/'tools/pipeline/fixtures/save_history'

if __name__ == '__main__':
    manifest = json.loads((DEST/'manifest.json').read_text())
    name = 'v22-pwz1.bin'
    if any(r['file'] == name for r in manifest['fixtures']):
        raise SystemExit('V22 fixture already frozen; add a new case instead of regenerating it')
    source = next(r for r in manifest['fixtures'] if r['version'] == 21)
    data = (DEST/source['file']).read_bytes()
    assert len(data) == source['size'] and hashlib.sha256(data).hexdigest() == source['sha256']
    with tempfile.TemporaryDirectory() as d:
        t = Path(d)
        (t/'writer.c').write_text('''#include "save_storage.h"
#include <stdio.h>
#include <assert.h>
int main(int argc,char **argv){assert(argc==3);uint8_t raw[7792],out[7792];
FILE *f=fopen(argv[1],"rb");assert(f&&fread(raw,1,sizeof(raw),f)==sizeof(raw));fclose(f);
save_put16(raw,SAVE_STORAGE_VERSION);size_t n=save_storage_encode(out,sizeof(out),raw,sizeof(raw));assert(n);
f=fopen(argv[2],"wb");assert(f&&fwrite(out,1,n,f)==n);assert(!fclose(f));}
''')
        subprocess.run(['cc', '-std=c11', '-I', str(ROOT/'firmware/main'), str(t/'writer.c'), '-o', str(t/'writer')], check=True)
        subprocess.run([str(t/'writer'), str(DEST/source['file']), str(t/name)], check=True)
        encoded = (t/name).read_bytes()
    assert not (DEST/name).exists()
    (DEST/name).write_bytes(encoded)
    manifest['fixtures'].append(dict(file=name, version=22, size=len(encoded),
        sha256=hashlib.sha256(encoded).hexdigest(), source_commit=source['source_commit'],
        source_type='save_t (frozen V21 decoded layout, schema 22, PWZ1 envelope)',
        source_fixture=source['file'], source_fixture_sha256=source['sha256'],
        source_hashes={'firmware/main/save_storage.h': hashlib.sha256((ROOT/'firmware/main/save_storage.h').read_bytes()).hexdigest()},
        provenance='Initial V22 storage fixture, encoded from the named synthetic historical V21 bytes; source_commit identifies that logical layout, encoder identified by source_hashes. No player data.'))
    manifest['current_version'] = 22
    (DEST/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(f'Appended {name}: {len(encoded)} bytes')
