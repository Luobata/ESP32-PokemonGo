"""Record production C animation frames and inspect the actual RGB565 bar rows."""
import hashlib
import json
from pathlib import Path
import struct
import sys
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, rgb888

exe, version = build()
checks = 0
records = []
groups = {}

def command(r, value):
    global checks
    f = r.command(value)
    assert r.command('check')['mismatch'] == 0, value
    checks += 1
    return f

def save_sample(r, frame, label):
    s = r.inspect()
    pixels = struct.unpack('>76800H', frame['pixels'])
    view = s['presentation']
    if view['phase'] != 'entry':
        for x, y, value, maximum in ((152, 198, view['visible_pet_hp'], maxima[0]),
                                     (40, 36, view['visible_wild_hp'], maxima[1])):
            fill = max(1, value * 32 // maximum) if value else 0
            ratio = value * 48 // maximum
            color = 0x05e0 if ratio >= 24 else 0xfd60 if ratio >= 10 else 0xf800
            expected = [color] * (fill * 2) + [0xffff] * (64 - fill * 2)
            assert list(pixels[y*240+x:y*240+x+64]) == expected, (label, value, maximum)
        total, level = view['visible_exp'], view['visible_level']
        lo = 0 if level == 1 else 5 * level**3 // 2
        hi = 5 * (level+1)**3 // 2
        fill = 56 if level == 100 else (total-lo) * 56 // (hi-lo)
        expected = [0xffff] * (112-fill*2) + [0x247f] * (fill*2)
        assert list(pixels[230*240+120:230*240+232]) == expected, (label, total, level)
    rgb = rgb888(frame['pixels'])
    records.append({'label': label, 'page': frame['page'], 'ms': frame['ms'], **view,
                    'rgb_sha256': hashlib.sha256(rgb).hexdigest()})
    return Image.frombytes('RGB', (240,320), rgb)

r = Renderer(exe)
try:
    f = command(r, 'boot 3 25 12 19 1 7 0')
    initial = r.inspect()['queue'][0]
    maxima = (initial['pet_hp'], initial['wild_hp'])
    entry = [save_sample(r,f,'entry-0')]
    for i in range(1,13):
        entry.append(save_sample(r,command(r,'tick 60'),f'entry-{i}'))
    groups['entry'] = entry
    command(r,'key 0 1'); command(r,'key 0 1'); command(r,'key 2 1')
    f = command(r,'tick 40')
    reply = [save_sample(r,f,'retaliation-0')]
    for i in range(1,14):
        reply.append(save_sample(r,command(r,'tick 60'),f'retaliation-{i}'))
    assert r.inspect()['presentation']['phase'] == 'choice'
    assert r.inspect()['active']['attacks'] == 1
    groups['retaliation'] = reply
finally:
    r.close()

r = Renderer(exe)
try:
    command(r,'boot 3 25 1 150 5 1 0')
    initial = r.inspect()['queue'][0]
    maxima = (initial['pet_hp'], initial['wild_hp'])
    command(r,'tick 720'); command(r,'key 1 1')
    xp = []
    for i in range(1100):
        f = command(r,'tick 60')
        view = r.inspect()['presentation']
        sample = save_sample(r,f,f'exp-battle-{i}')
        if view['phase'] in ('exp','result'): xp.append(sample)
        if view['phase'] == 'result': break
    else: raise AssertionError('battle never completed')
    assert len(xp) == 19
    assert len({item['visible_level'] for item in records if item['label'].startswith('exp-battle')}) >= 3
    groups['experience'] = xp
finally:
    r.close()

for name, frames in groups.items():
    duration = [60]*len(frames)
    duration[-1] = 1000
    frames[0].save(OUT / f'{name}.gif', save_all=True, append_images=frames[1:],
                   duration=duration, loop=0, disposal=2)
    frames[-1].save(OUT / f'{name}-end.png')

sheet = Image.new('RGB', (4*256, 3*356), '#eeede6')
draw = ImageDraw.Draw(sheet)
for row, (name, frames) in enumerate(groups.items()):
    for col, index in enumerate((0,len(frames)//3,2*len(frames)//3,len(frames)-1)):
        x,y = col*256+8, row*356+28
        sheet.paste(frames[index], (x,y))
        draw.text((x,y-19), f'{name} / frame {index}', fill='#282d29')
sheet.save(OUT / 'animation-contact-sheet.png')
result = {'build':version, 'dirty_full_checks':checks, 'pixel_samples':len(records),
          'verified':'actual RGB565 HP/EXP rows at every sampled C frame', 'frames':records}
(OUT/'native-pixels.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='frames'},ensure_ascii=False))
