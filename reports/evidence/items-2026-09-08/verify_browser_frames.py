"""Replay observed browser Canvas frames against the final production C build."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, rgb888

# Actual UI clicks, paused 60 ms steps, and Canvas RGBA readback.
# Each boot starts a fresh native process, as does loading a browser fixture.
CASES = [
('items-bag-initial',['boot 10 25 12 74 3 1 0 1'],0,'P10','63e87a11805a77c079869547c12add21447413e4de7446955d2631bde9563ef4'),
('items-care-feed',['check','key 2 1','key 0 1','tick 60'],60,'P5','3bcb4e4b89aa9e226fb8e312e3f3bbf74062a5a6aabe5377e3d581ccad9f112b'),
]

exe, version = build()
r = Renderer(exe)
results = []
try:
    for label, commands, ms, page, browser_hash in CASES:
        for command in commands:
            if command.startswith('boot ') and results:
                r.close()
                r = Renderer(exe)
            frame = r.command(command)
        rgb = rgb888(frame['pixels'])
        rgba = bytearray()
        for i in range(0, len(rgb), 3):
            rgba.extend(rgb[i:i+3])
            rgba.append(255)
        native_hash = hashlib.sha256(rgba).hexdigest()
        assert (frame['ms'], frame['page'], native_hash) == (ms, page, browser_hash), (label, native_hash)
        assert r.command('check')['mismatch'] == 0, label
        results.append({'label': label, 'ms': ms, 'page': page, 'rgba_sha256': native_hash})
finally:
    r.close()
result = {'status': 'PASS', 'final_build': version, 'frames_matched': len(results),
          'pixels_per_frame': 76800, 'browser_url': 'http://127.0.0.1:8766/firmware.html',
          'observed_builds': ['7cd46e736258d0ee8940'],
          'scope': 'UI-operated Canvas readback vs final C renderer; no physical LCD capture',
          'frames': results}
(Path(__file__).parent / 'browser-parity.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'frames'}))
