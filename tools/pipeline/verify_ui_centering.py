#!/usr/bin/env python3
"""Measure visible ink in actual C-rendered pages (not layout constants alone)."""
from pathlib import Path
import json
import sys
from PIL import Image, ImageChops

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build, rgb888, png


def main():
    exe, version = build()
    evidence = ROOT / 'reports/evidence/starter-capture-2026-09-07'
    evidence.mkdir(parents=True, exist_ok=True)
    results = []

    def centered(frame, box, label):
        im = Image.frombytes('RGB', (240, 320), rgb888(frame['pixels']))
        crop = im.crop(box)
        bbox = ImageChops.difference(crop, Image.new('RGB', crop.size, 'white')).getbbox()
        assert bbox, f'{label}: empty visible content'
        l, t, r, b = bbox
        gaps = [l, crop.width-r, t, crop.height-b]
        if abs(gaps[0]-gaps[1]) > 1 or abs(gaps[2]-gaps[3]) > 1:
            (evidence / 'centering-failure.png').write_bytes(png(frame['pixels']))
            raise AssertionError(f'{label}: visible margins L/R/T/B = {gaps}')
        results.append({'label': label, 'box': box, 'gaps': gaps})

    # Exclude the two inward corner pixels at x5/x233; the remaining
    # interior retains the same horizontal center as the straight frame edges.
    for page in [0, 1, 2, 4, 5, 6, 9]:
        r = Renderer(exe)
        try:
            frame = r.command(f'boot {page} 25 12 74 3 1 0')
            centered(frame, (6, 287, 233, 315), f'P{page} footer')
            (evidence / f'P{page}.png').write_bytes(png(frame['pixels']))
            if page == 1:
                frame = r.command('tick 800')
                centered(frame, (6, 287, 233, 315), 'P1 footer pending indicator')
            assert r.command('check')['mismatch'] == 0
        finally:
            r.close()

    # Species have unequal original transparent borders. Measure all 151 forms,
    # retaining original integer-scale artwork and the existing grid sampling.
    for sid in range(1, 152):
        r = Renderer(exe)
        try:
            frame = r.command(f'boot 5 {sid} 12 74 3 1 0')
            centered(frame, (120, 64, 232, 176), f'P5 front #{sid:03d}')
            frame = r.command('page 1')
            centered(frame, (72, 58, 168, 154), f'P1 back #{sid:03d}')
            frame = r.command('page 6')
            for _ in range((sid-1)//20):
                frame = r.command('key 1 1')
            index = (sid-1) % 20
            x, y = 5 + (index % 5)*46, 40 + (index//5)*56
            centered(frame, (x, y, x+46, y+32), f'P6 thumbnail #{sid:03d}')
            centered(frame, (x, y+34, x+46, y+50), f'P6 number #{sid:03d}')
            assert r.command('check')['mismatch'] == 0, f'P6 #{sid}: stale band'
        finally:
            r.close()
    out = {'build': version, 'checks': len(results), 'max_allowed_gap_difference_px': 1,
           'results': results}
    (evidence / 'centering.json').write_text(json.dumps(out, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({'build':version, 'centering_checks':len(results), 'species':151,
                      'evidence':str(evidence/'centering.json')}))


if __name__ == '__main__':
    main()
