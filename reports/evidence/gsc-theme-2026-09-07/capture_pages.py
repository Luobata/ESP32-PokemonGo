"""Capture final native fixtures; browser hashes are collected through its UI."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, png, rgb888

OUT = Path(__file__).resolve().parent
exe, version = build()
rows = []
for page in range(7):
    r = Renderer(exe)
    commands = [f'boot {page} 25 12 74 3 1 0']
    if page == 0:
        commands += ['tick 60'] * 10 + ['key 0 1']
    if page == 6:
        commands += ['key 1 1']  # Page two shows the caught Pikachu front.
    commands += ['check']
    try:
        for cmd in commands:
            frame = r.command(cmd)
        assert frame['mismatch'] == 0
        rgb = rgb888(frame['pixels'])
        rgba = b''.join(rgb[i:i+3] + b'\xff' for i in range(0, len(rgb), 3))
        (OUT / f'final-P{page}.png').write_bytes(png(frame['pixels']))
        rows.append(dict(page=frame['page'], ms=frame['ms'], build=version,
                         sha256=hashlib.sha256(rgba).hexdigest(), commands=commands,
                         mismatch=frame['mismatch']))
    finally:
        r.close()
(OUT / 'native-pages.json').write_text(json.dumps(rows, indent=2) + '\n')

# A review artifact made from actual firmware screenshots, at native resolution.
from PIL import Image, ImageDraw
sheet = Image.new('RGB', (1024, 720), '#eeede6')
draw = ImageDraw.Draw(sheet)
for page in range(7):
    x, y = 16 + (page % 4)*252, 14 + (page // 4)*350
    draw.text((x, y), ['P0 Opening', 'P1 Idle', 'P2 Encounters', 'P3 Battle',
                       'P4 Capture', 'P5 Care', 'P6 Pokedex'][page], fill='#252923')
    sheet.paste(Image.open(OUT / f'final-P{page}.png'), (x, y+20))
sheet.save(OUT / 'final-pages.png')
print(json.dumps({'build': version, 'frames': rows}, ensure_ascii=False))
