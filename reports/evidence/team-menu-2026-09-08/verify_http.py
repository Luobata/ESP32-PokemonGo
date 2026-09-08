"""Verify local preview service bytes, without claiming browser interaction."""
import sys, json, hashlib
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import build, Renderer

out = Path(__file__).resolve().parent
url = 'http://127.0.0.1:8766/api/firmware'
meta = json.load(urlopen(url))
assert 11 in meta['pages'] and 12 in meta['pages']
exe, version = build()
records = []
for page, keys in [(11, [(1, 1), (0, 1), (1, 3), (0, 1), (2, 1), (2, 1)]),
                   (10, [(1, 3), (1, 1)]), (12, [(1, 1), (1, 3)])]:
    r = Renderer(exe)
    session = None
    try:
        steps = [({'action': 'reset', 'page': page, 'pet': 25, 'level': 12,
                   'wild': 74, 'rarity': 3, 'seed': 1, 'shiny': 0, 'names': 0, 'team': 1},
                  f'boot {page} 25 12 74 3 1 0 0 1')]
        steps += [({'action': 'key', 'key': k, 'event': e}, f'key {k} {e}') for k, e in keys]
        for data, command in steps:
            expected = r.command(command)
            request = Request(url, data=json.dumps(dict(data, session=session)).encode(),
                              headers={'Content-Type': 'application/json'})
            with urlopen(request) as response:
                actual = response.read()
                session = response.headers['X-Preview-Session']
                assert response.headers['X-Preview-Version'] == version
                assert actual == expected['pixels']
                records.append({'command': command, 'page': response.headers['X-Preview-Page'],
                                'sha256': hashlib.sha256(actual).hexdigest()})
    finally:
        r.close()
result = {'status': 'PASS', 'build': version, 'frames': records,
          'scope': 'Real localhost HTTP API vs C renderer; browser input tested under JS harness, not live desktop.'}
(out / 'http-preview.json').write_text(json.dumps(result, indent=2) + '\n')
print(f'PASS HTTP: {len(records)} frames, P10/P11/P12 routes and long B; build {version}')
