#!/usr/bin/env python3
"""Actual party UI: cancel or end a run and exchange the selected individual."""
import json
from pathlib import Path
from verify_party_menu import ROOT, font_check
from native import Renderer, build, png

OUT = ROOT / 'reports/evidence/party-dungeon-exit'
OUT.mkdir(parents=True, exist_ok=True)
exe, version = build()


def key(r, button, hold=False):
    return r.command(f'key {button} {3 if hold else 1}')


def setup(active=True, slot=0, box_row=0):
    r = Renderer(exe)
    r.command('boot 16 25 30 74 3 123 0 0 0')
    for species in (1, 4, 7, 10, 13):
        r.command(f'party_add {species} 20 40 100 0')
    r.command('party_add 25 40 85 500 1')
    if box_row:
        r.command('party_add 133 35 70 500 0')
    if active:
        key(r, 1)
        key(r, 2)  # choose owned companions
        key(r, 2)  # select leader
        for _ in range(6):
            key(r, 1)
        key(r, 2)  # depart
        assert r.inspect()['dungeon']['playing']
    r.command('page 12')
    for _ in range(slot):
        key(r, 1)
    key(r, 2)  # leader details
    for _ in range(3):
        key(r, 1)
    key(r, 2)  # warehouse
    for _ in range(box_row):
        key(r, 1)
    key(r, 2)  # shiny Pikachu details
    assert r.inspect()['party_view']['species'] == (133 if box_row else 25)
    return r


def shot(r, name):
    frame = r.command('check')
    assert frame['mismatch'] == 0
    (OUT / f'{name}.png').write_bytes(png(frame['pixels']))
    return frame['pixels']


def assert_exchanged(r):
    state = r.inspect()
    assert state['party'][0]['flags'] & 1
    assert state['level'] == 40
    assert state['box_count'] == 1
    assert not state['party_view']['box']
    assert state['party_view']['feedback'] == '队伍已更换'


r = setup()
try:
    before = r.inspect()
    details = shot(r, 'before')
    key(r, 2)
    prompt = shot(r, 'confirm-cancel-default')
    assert prompt != details
    assert r.inspect()['party'] == before['party']
    key(r, 2)  # C on default cancel must never terminate the run
    assert shot(r, 'cancelled') == details
    assert r.inspect()['dungeon'] == before['dungeon']
    key(r, 2)
    key(r, 1)  # select end
    key(r, 1, True)  # long B cancels even with end selected
    assert shot(r, 'back-cancelled') == details
    key(r, 2)
    assert shot(r, 'reopened-default') == prompt
    key(r, 1)
    shot(r, 'confirm-end-selected')
    key(r, 2)
    assert_exchanged(r)
    assert r.inspect()['nurture']['stamina'] == before['nurture']['stamina']
    assert r.inspect()['dungeon']['phase'] != before['dungeon']['phase']
    shot(r, 'exchanged')
    r.command('page 16')  # reloading the run must not restore the old active run
    assert r.inspect()['dungeon']['phase'] == 6  # DUNGEON_LOST
finally:
    r.close()

for fail_after in (0, 1):
    r = setup()
    try:
        before = r.inspect()
        key(r, 2)
        key(r, 1)
        r.command(f'save_fail_after {fail_after}')
        key(r, 2)
        state = r.inspect()
        assert state['party'] == before['party']
        assert '保存失败' in state['party_view']['feedback']
        shot(r, f'save-failure-{fail_after}')
        if fail_after == 0:
            assert state['dungeon'] == before['dungeon']
        else:
            assert state['dungeon']['phase'] == 6
        key(r, 2)  # retry end or retry exchange; no duplicate entry fee
        assert_exchanged(r)
        assert r.inspect()['nurture']['stamina'] == before['nurture']['stamina']
    finally:
        r.close()

r = setup(active=False)
try:
    key(r, 2)  # ordinary exchange still completes with one confirmation
    assert_exchanged(r)
finally:
    r.close()

r = setup(slot=2, box_row=1)
try:
    before = r.inspect()['party']
    key(r, 2)
    key(r, 1)
    key(r, 2)
    after = r.inspect()
    assert after['party'][2]['species'] == 133
    assert after['party'][2]['level'] == 35
    assert after['party_view']['selected'] == 2
    assert after['box_count'] == 2
    assert all(after['party'][i] == before[i] for i in range(6) if i != 2)
finally:
    r.close()

result = dict(status='PASS', renderer=version, font_characters=font_check(),
              checks=['default cancel', 'long B cancel', 'reopen resets choice',
                      'end and exchange shiny individual', 'no stamina charge/refund',
                      'abandon persistence', 'abandon save retry', 'exchange save retry',
                      'ordinary exchange unchanged', 'nonleader slot and warehouse row',
                      'band rendering'])
(OUT / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
