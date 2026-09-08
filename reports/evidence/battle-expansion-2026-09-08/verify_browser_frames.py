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
('dragonite-slide-start', ['boot 3 149 12 149 5 1 0 0'], 0, 'P3', '43980bc6f0d3aae5b1de92ee385fdb5e2bb993d30cfa626f5c70ae4e09c73246'),
('dragonite-motion-start', ['tick 720'], 720, 'P3', 'e8796e9a03578240de0e1f8884fcf4d77e9d7d2e7db0fb04b3ec6a93a2351b7f'),
('dragonite-motion-middle', ['tick 300'], 1020, 'P3', '801ccf6a08429cbef4062bb018f22a4214f724d6247ba90ee43f775a0447a616'),
('feida-motion-same-time', ['names 1'], 1020, 'P3', '8f2af5e142afa62ed890cc0017b2a69cd9489d4b51b0697aeba3a3db7fbe3707'),
('feida-ready', ['tick 1800'], 2820, 'P3', 'a7b5cc5742716f779b72479c17783076c73491b0138212d02bfbfb453c4f84c6'),
('escape-choice', ['boot 3 9 30 150 5 4 0 0', 'tick 1920'], 1920, 'P3', '5d747876dd9b3b3636ef66490ced099a3102bf8fd7ded2aaca3f2d7be2653679'),
('escape-failed-feedback', ['key 2 1'], 1920, 'P3', '68ace8619532933ba912be896f57acfaca96cafc398a546d4bb890e70e59cc37'),
('escape-retaliation-start', ['tick 720'], 2640, 'P3', 'c9abd0484a55883eaae4d47c38addbb48fb9c5f707cde47ebe3c8a204c2b141f'),
('escape-choice-after-one-retaliation', ['tick 1200'], 3840, 'P3', 'bea3087312560791a061a1f9418210ee214c1b35905070b0aac0a02107ac4a36'),
('capture-available-after-escape-failure', ['key 0 1'], 3840, 'P4', '6420fe549c85b5ffcc5c116db7c5cc4e2cdf4fb5eb12752ee951236874f70fdd'),
('defeat-fixture-choice', ['boot 3 11 1 150 5 1 0 0', 'tick 1920'], 1920, 'P3', '82a0643a024f091006997ddd6609fea43b91bd964e9e8d3c10c0bb63139381d1'),
('defeat-penalty-result', ['key 2 1', 'tick 2880'], 4800, 'P3', 'cd5473533f109224fcd9ac75fad65dbdd8f9155e99ec56897e29af89d87348fe'),
('defeat-to-care', ['key 0 1'], 4800, 'P5', 'cb387e771faf5fcb060dc31c2a81dbe845bc07cba453bf2f538b1308474ae96f'),
('care-long-A-switch-names', ['key 0 3'], 4800, 'P5', 'fb673bc3d8f999d7c24fbecfb032b8ac6928c7ef2c28edf91c56400de60f3f4d'),
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
          'observed_builds': ['4e927afa07140fc618d7', 'ab8989a0323c39a95133', '68ff02e5d313e457b575'],
          'scope': 'UI-operated Canvas readback vs final C renderer; no physical LCD capture',
          'frames': results}
(Path(__file__).parent / 'browser-parity.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'frames'}))
