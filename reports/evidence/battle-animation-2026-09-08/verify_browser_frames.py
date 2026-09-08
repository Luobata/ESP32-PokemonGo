"""Replay the UI-driven browser samples against the final production C build."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, rgb888

# Readback: actual 240x320 browser Canvas RGBA after UI clicks and 60ms steps.
# First flow was observed before the P2-only refresh fix; it must ALSO match the
# final executable. The second flow was observed on the final build directly.
CASES = [
('entry-0', ['boot 3 25 12 19 1 7 0'], 0, 'P3', '43980bc6f0d3aae5b1de92ee385fdb5e2bb993d30cfa626f5c70ae4e09c73246'),
('entry-360', ['tick 360'], 360, 'P3', '0860adf10e5c2caa2d9774b531d4f5c5f5021454831becb7f1f3f1243305b201'),
('choice-720', ['tick 360'], 720, 'P3', 'd60e8424cafeb27a42e04a19048aafd5651ca56fb7c044d9ec63d8fdbcaacb28'),
('capture-before-throw', ['key 0 1'], 720, 'P4', '510dc8382e89b5fc6d8b050250e614f15e475150af9b4748e73c15a2957b8d26'),
('capture-failed', ['key 0 1'], 720, 'P4', '331070424cf68ee4d82ea1e53a06c81906b3a9143fbc2808084e67badd9bc60c'),
('retaliation-start', ['key 2 1', 'tick 60'], 780, 'P3', '03755ae6d85b2aa803471770932b91c80ed678b5a6b33fb92ef6a5ae97a1bada'),
('retaliation-hp-middle', ['tick 540'], 1320, 'P3', 'a8fa6d69ccf6f7081d9d7e6ade354aac3357b866695982621ecbce043361f5fe'),
('choice-after-retaliation', ['tick 300'], 1620, 'P3', 'b03eabd4139d5d520a31dd40b8e690cb3cea019a68e3b161ad387b01b46ee7a2'),
('capture-retry', ['check', 'key 0 1'], 1620, 'P4', '441da33f108754124f1452b94471523e1f008b9a5268563399833809afcb410f'),
('final-build-entry', ['boot 3 25 1 150 5 1 0'], 0, 'P3', '43980bc6f0d3aae5b1de92ee385fdb5e2bb993d30cfa626f5c70ae4e09c73246'),
('final-build-choice', ['tick 720'], 720, 'P3', 'aa74d11f49d1b7925cd753ff96a64f67cbb921bf6a0f5a6111058ef0fcae61fb'),
('automatic-battle-locked', ['key 1 1', 'key 2 1'], 720, 'P3', '70466f42b749194b91e024acdff6d24b1982cb487eccf771bbbe4e9456adbf8e'),
('experience-start', ['tick 1020'], 1740, 'P3', '1aa39b1d3c79902e15f2aeb7ea72eb4481eb92e72912740c6b0d0faaff2a61a3'),
('experience-middle', ['tick 540'], 2280, 'P3', '9e162396e5c34fad60bf92282be43f2afe2a9fffeb2d824b736c803105fb3a1d'),
('experience-end', ['tick 540'], 2820, 'P3', '43b2b9435db35346502abe645326d0585cabb9d22d5007a7b705c75ef94d59d1'),
('processed-encounter-removed', ['check', 'key 2 1'], 2820, 'P2', '2fcc4ee85a2a932d8dc1313eac4c7d13fc352d2b6df737fe298a70e038f8260e'),
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
        for i in range(0,len(rgb),3): rgba.extend(rgb[i:i+3]); rgba.append(255)
        native_hash = hashlib.sha256(rgba).hexdigest()
        assert (frame['ms'],frame['page'],native_hash)==(ms,page,browser_hash), label
        assert r.command('check')['mismatch'] == 0, label
        results.append({'label':label, 'ms':ms, 'page':page, 'rgba_sha256':native_hash})
finally:
    r.close()
result = {'status':'PASS','final_build':version,'frames_matched':len(results),
          'pixels_per_frame':76800,'browser_url':'http://127.0.0.1:8766/firmware.html',
          'observed_builds':['ef8bb306abb21e4247a0','196048ce3b666b6e83d9'],
          'scope':'UI-operated Canvas readback vs final C renderer; no physical LCD capture',
          'frames':results}
(Path(__file__).parent/'browser-parity.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='frames'}))
