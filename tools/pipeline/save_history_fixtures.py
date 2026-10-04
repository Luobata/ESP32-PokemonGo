"""Load immutable historical bytes into the production C test harnesses."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tools/pipeline/fixtures/save_history'


def c_cases():
    manifest = json.loads((FIXTURES / 'manifest.json').read_text())
    header = (ROOT / 'firmware/main/save.h').read_text()
    current = int(re.search(r'#define SAVE_VERSION\s+(\d+)', header)[1])
    oldest = int(re.search(r'#define SAVE_LEGACY_VERSION\s+(\d+)', header)[1])
    assert current == manifest['current_version'], 'New schema requires historical fixtures and migration expectations'
    assert oldest == manifest['oldest_version'], 'Do not silently drop supported historical save versions'
    assert set(range(oldest, current+1)) <= {f['version'] for f in manifest['fixtures']}
    code = ['#include <assert.h>', '#include <stdio.h>']
    rows = []
    for index, record in enumerate(manifest['fixtures']):
        data = (FIXTURES / record['file']).read_bytes()
        assert len(data) == record['size']
        assert hashlib.sha256(data).hexdigest() == record['sha256'], record['file']
        assert int.from_bytes(data[:2], 'little') == record['version']
        code.append(f'static const unsigned char history_{index}[]={{' + ','.join(str(b) for b in data) + '};')
        rows.append('{' + f'"{record["file"]}",{record["version"]},sizeof(history_{index}),history_{index}' + '}')
    code.append('static const struct {const char *name; unsigned version; size_t size; const unsigned char *data;} history[]={' + ','.join(rows) + '};')
    code.append((ROOT / 'tools/pipeline/fixtures/save_history_assertions.h').read_text())
    return '\n'.join(code) + '\n'
