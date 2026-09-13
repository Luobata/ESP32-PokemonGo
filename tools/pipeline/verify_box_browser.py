#!/usr/bin/env python3
"""Full-capacity warehouse: filters, stable sorting, paging and safe exchange."""
import json
from pathlib import Path
from verify_party_menu import ROOT, font_check
from native import Renderer, build, png

OUT = ROOT / 'reports/evidence/box-browser'
OUT.mkdir(parents=True, exist_ok=True)
exe, version = build()
r = Renderer(exe)


def cmd(text):
    return r.command(text)


def state():
    return r.inspect()


def view():
    return state()['party_view']


def key(button, hold=False):
    return cmd(f'key {button} {3 if hold else 1}')


def shot(name):
    frame = cmd('check')
    assert not frame['mismatch']
    (OUT / f'{name}.png').write_bytes(png(frame['pixels']))


def open_box():
    cmd('page 12')
    key(2)
    for _ in range(3):
        key(1)
    key(2)
    assert view()['box'] and not view()['details']


def menu(row):
    key(0, True)
    assert view()['box_menu'] == 1
    for _ in range(row):
        key(1)
    key(2)


def choose_setting(row, option, field, total):
    menu(row)
    current = view()[field]
    for _ in range((option - current) % total):
        key(1)
    key(2)
    assert not view()['box_menu'] and view()[field] == option


def members():
    count = view()['box_matches']
    result = []
    for _ in range(count):
        v = view()
        result.append((v['species'], v['box_slot']))
        key(1)
    assert len(set(slot for _, slot in result)) == count
    return result


try:
    cmd('boot 12 6 30 74 3 123 0 0 0')
    for species in (1, 4, 7, 10, 13):
        cmd(f'party_add {species} 10 40 0 0')
    # Even species already in the party can have a distinct warehouse member.
    for species in range(1, 152):
        cmd(f'party_add {species} 5 40 0 0')
    for species, level, shiny in ((1, 16, 0), (25, 40, 1), (64, 30, 0), (67, 28, 0),
                                 (133, 20, 0), (6, 40, 0), (9, 40, 0)):
        cmd(f'party_add {species} {level} 40 0 {shiny}')
    for item in range(8, 15):
        cmd(f'inventory {item} 0')
    open_box()
    before = state()
    assert before['box_count'] == 151 and view()['box_matches'] == 151
    assert [species for species, _ in members()] == list(range(1, 152))
    shot('full-warehouse')

    # Sorting changes only the display order; the selected physical slot survives.
    for _ in range(24):
        key(1)
    selected = view()['box_slot']
    choose_setting(2, 1, 'box_sort', 2)
    assert view()['box_slot'] == selected
    ordered = members()
    levels = {i: 5 for i in range(1, 152)}
    levels.update({1: 16, 25: 40, 64: 30, 67: 28, 133: 20, 6: 40, 9: 40})
    # The traversal starts at the retained member rather than the first row.
    pivot = ordered.index((6, 5))
    ordered = ordered[pivot:] + ordered[:pivot]
    assert [sid for sid, _ in ordered] == sorted(levels, key=lambda sid: (-levels[sid], sid))
    assert state()['party'] == before['party'] and state()['inventory'] == before['inventory']
    shot('level-sort')

    choose_setting(0, 1, 'box_filter', 3)
    assert members() == [(25, 24)]
    shot('shiny')
    choose_setting(1, 2, 'box_type', 18)  # fire + shiny gives no match
    assert view()['box_matches'] == 0
    key(2)
    assert not view()['details']
    shot('no-matches')
    menu(4)  # clear filters remains available even on empty results
    assert view()['box_matches'] == 151 and view()['box_sort'] == 1

    choose_setting(1, 10, 'box_type', 18)  # flying matches Charizard's second type
    types = dict(members())
    assert 6 in types and 16 in types and 25 not in types
    shot('flying-type')
    menu(4)
    choose_setting(0, 2, 'box_filter', 3)
    ready = {species for species, _ in members()}
    assert 1 in ready and not ready.intersection({6, 9, 25, 64, 67, 133})
    cmd('inventory 9 1')  # water stone: Eevee + applicable water species
    cmd('inventory 13 1')  # link machine
    choose_setting(0, 2, 'box_filter', 3)
    ready = {species for species, _ in members()}
    assert {1, 61, 64, 67, 75, 90, 93, 120, 133} <= ready
    assert 25 not in ready and 6 not in ready
    shot('evolution-ready')
    assert state()['inventory'][9] == 1 and state()['inventory'][13] == 1

    menu(4)
    choose_setting(2, 0, 'box_sort', 2)
    # Select the first row, then reach all 31 groups without displaying page numbers.
    while view()['box_row']:
        key(0)
    menu(3)
    assert view()['box_paging']
    key(0)
    assert view()['box_row'] == 150 and view()['species'] == 151
    shot('last-partial-group')
    key(1)
    assert view()['box_row'] == 0
    visited = []
    for _ in range(31):
        visited.append(view()['box_row'])
        key(1)
    assert visited == list(range(0, 151, 5)) and view()['box_row'] == 0
    key(2)
    assert not view()['box_paging'] and not view()['details']
    key(2)
    assert view()['details'] and view()['species'] == 1
    key(1, True)
    key(0, True)
    key(1, True)
    assert not view()['box_menu'] and view()['box']

    # Filtered/sorted exchange must keep the chosen shiny individual, not use the row as a slot.
    choose_setting(0, 1, 'box_filter', 3)
    choose_setting(2, 1, 'box_sort', 2)
    key(2)
    cmd('save_fail 1')
    key(2)
    assert '保存失败' in view()['feedback'] and state()['party'] == before['party']
    assert view()['species'] == 25
    key(2)
    assert not view()['box'] and state()['party'][0]['flags'] & 1
    assert state()['level'] == 40 and state()['box_count'] == 151
    open_box()
    assert view()['box_matches'] == 0  # the only shiny is now in the party
    menu(4)
    all_members = members()
    assert sum(sid == 6 for sid, _ in all_members) == 2  # distinct outgoing Charizard retained
    assert [slot for sid, slot in all_members if sid == 6] == [5, 24]
    assert len(all_members) == 151
    shot('after-exchange')
finally:
    r.close()

for count in (0, 1, 5, 6):
    r = Renderer(exe)
    try:
        cmd('boot 12 6 30 74 3 123 0 0 0')
        for species in (1, 4, 7, 10, 13):
            cmd(f'party_add {species} 10 40 0 0')
        for species in range(20, 20 + count):
            cmd(f'party_add {species} 10 40 0 0')
        open_box()
        assert view()['box_matches'] == count
        menu(3)
        assert view()['box_paging'] == bool(count)
        if count:
            key(0)
            assert view()['box_row'] == (count - 1) // 5 * 5
            key(1)
            assert view()['box_row'] == 0
            key(1, True)
            assert not view()['box_paging'] and view()['box']
        else:
            key(2)
            assert not view()['details']
            shot('empty-warehouse')
            menu(4)
            assert view()['box_matches'] == 0
    finally:
        r.close()

result = dict(status='PASS', renderer=version, font_characters=font_check(),
              checks=['151 physical slots', 'stable dex/level order', 'selection preserved',
                      'shiny + type intersection', 'secondary type', 'empty recovery',
                      'level/item evolution eligibility', 'no item consumption',
                      '0/1/5/6/151 group boundaries', 'C leaves paging before details',
                      'long B returns', 'filtered save retry and exact individual exchange',
                      'no warehouse loss', 'band rendering'])
(OUT / 'verification.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(result, ensure_ascii=False))
