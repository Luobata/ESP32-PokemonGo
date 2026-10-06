#!/usr/bin/env python3
"""Extract Gold's send-out sparkle OAM frames from the pinned source checkout."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import convert_battle_fx as fx

ROOT = Path(__file__).resolve().parents[2]

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--src', type=Path, required=True)
    ap.add_argument('--check', action='store_true')
    args = ap.parse_args()
    fx.SELECTION = tuple((f'shiny{i}', 'speed', 'Sparkle', i) for i in range(3))
    header, manifest = fx.build(args.src)
    header = header.replace('tools/pipeline/convert_battle_fx.py', 'tools/pipeline/convert_shiny_entry.py')
    for path in ('engine/battle_anims/functions.asm', 'engine/battle_anims/helpers.asm',
                 'data/battle_anims/objects.asm', 'gfx/battle_anims/battle_anims.pal'):
        data = (args.src / path).read_bytes()
        assert data == subprocess.check_output(['git', '-C', str(args.src), 'show', fx.COMMIT + ':' + path])
        manifest['sources'][path] = hashlib.sha256(data).hexdigest()
    manifest['presentation'] = dict(script='BattleAnim_SendOutMon.Shiny',
        source_hz=60, star_angles=list(range(0, 64, 8)), spawn_interval_ticks=4,
        radius=16, frames=[0, 1, 2, 1, 2], frame_ticks=4, duration_ticks=60,
        adaptation='Integer 2x sparkle art; circle centered on each battler; background palette flash excludes message window. Existing project shiny sound.')
    for path, text in [(ROOT/'firmware/main/shiny_entry_assets.h', header),
                       (ROOT/'assets/shiny_entry_sources.json', json.dumps(manifest, indent=2)+'\n')]:
        if args.check:
            assert path.read_text() == text, str(path)
        else:
            path.write_text(text)
    print('Verified' if args.check else 'Generated', 'three original Gold sparkle frames')

if __name__ == '__main__':
    main()
