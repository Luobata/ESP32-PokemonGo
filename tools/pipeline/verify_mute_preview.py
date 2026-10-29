#!/usr/bin/env python3
"""Drive production menu controls and PCM gating without playing physical audio."""
from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import build, Renderer, png

out = Path(os.environ.get('POKEWALK_EVIDENCE_DIR', ROOT/'reports/evidence/audio-brightness-2026-10-29'))
out.mkdir(exist_ok=True, parents=True)
exe, version = build()
r = Renderer(exe)


def cmd(line):
    frame = r.command(line)
    assert r.command('check')['mismatch'] == 0, line
    return frame


def key(button, event=1):
    return cmd(f'key {button} {event}')


def shot(name):
    (out/f'{name}.png').write_bytes(png(cmd('check')['pixels']))


try:
    cmd('boot 11 25 12 74 3 1 0 0 1')
    assert not r.inspect()['muted'] and r.inspect()['volume'] == 55
    assert any(r.audio(11025))
    for _ in range(5):
        key(1)
    key(2)
    for _ in range(2):
        key(1)
    assert r.inspect()['menu_view']['option_selected'] == 2
    shot('sound-on')
    key(2)
    assert r.inspect()['muted'] and not any(r.audio(3528))
    shot('muted')
    cmd('save_fail 1')
    key(2)
    assert r.inspect()['muted'] and not any(r.audio(3528))
    shot('mute-save-failed')
    key(2)
    assert not r.inspect()['muted'] and any(r.audio(11025))
    key(2)
    key(1)
    key(2)  # Volume editor must not silently unmute.
    key(0)
    assert r.inspect()['volume'] == 60 and r.inspect()['muted']
    assert not any(r.audio(3528))
    key(2)
    key(2, 3)
    assert r.inspect()['display']['off'] and not any(r.audio(3528))
    key(2)
    assert not r.inspect()['display']['off'] and r.inspect()['muted']
    assert not any(r.audio(3528))
    print(json.dumps({'build': version, 'default_muted': False,
                      'toggle_pcm_gate': True, 'write_failure_preserved': True,
                      'volume_keeps_mute': True, 'sleep_silent': True,
                      'dirty_full_equal': True, 'physical_audio_tested': False}))
finally:
    r.close()
