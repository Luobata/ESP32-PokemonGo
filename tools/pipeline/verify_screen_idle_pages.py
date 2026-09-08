#!/usr/bin/env python3
"""Exercise display-idle decisions through the actual C pages and timer engine.

The native host supplies clock, inventory and storage fixtures. This gate does
not claim to measure physical backlight power or WiFi/养成 task scheduling.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build


class Flow:
    def __init__(self, executable, page=3, pet=25, level=12, wild=19, rarity=1, seed=7):
        self.renderer = Renderer(executable)
        self.checks = 0
        self.command(f'boot {page} {pet} {level} {wild} {rarity} {seed} 0')

    def close(self):
        self.renderer.close()

    def state(self):
        return self.renderer.inspect()

    def command(self, command):
        self.frame = self.renderer.command(command)
        checked = self.renderer.command('check')
        assert checked['mismatch'] == 0, f'{command}: stale horizontal bands'
        self.checks += 1
        return self.frame

    def tick(self, ms=60):
        return self.command(f'tick {ms}')

    def key(self, button, event=1):
        return self.command(f'key {"ABC".index(button)} {event}')

    def display(self, *, busy=None, off=False):
        actual = self.state()['display']
        assert actual['off'] is off and actual['backlight'] == (0 if off else 100), actual
        assert actual['timeout_ms'] == 60000, actual
        if busy is not None:
            assert actual['busy'] is busy, actual
        if off:
            assert not any(self.frame['pixels']), 'native visible frame must be black while off'

    def ready(self):
        phases = set()
        for _ in range(200):
            phase = self.state()['presentation']['phase']
            phases.add(phase)
            if phase == 'choice':
                self.display(busy=False)
                return sorted(phases)
            assert phase in ('entry', 'entrance-motion'), phase
            self.display(busy=True)
            self.tick()
        raise AssertionError('entry did not finish')


def game_state(state):
    """The display clock may change; all observable game data must remain intact."""
    return {key: value for key, value in state.items() if key != 'display'}


def sleep_and_wake(f, button='A'):
    # Semantic DOUBLE is a complete input and has no action on these pages.
    f.key('B', 2)
    f.tick(59999); f.display(busy=False)
    f.tick(101); f.display(busy=False, off=True)
    before = game_state(f.state())
    f.key(button, 0); f.display(busy=False)
    f.tick(50); f.key(button, 4); f.tick(180); f.key(button); f.key(button, 5)
    assert game_state(f.state()) == before, 'waking gesture changed gameplay'
    f.display(busy=False)


def static_page(f):
    f.display(busy=False)
    sleep_and_wake(f)
    return {'page': f.state()['page'], 'wait_ms': 60100, 'wake_did_not_act': True}


def opening(f):
    lengths = []
    for box in range(4):
        f.display(busy=True)
        started = f.frame['ms']
        for _ in range(300):
            if not f.state()['display']['busy']:
                break
            f.display(busy=True)
            f.tick(33)
        else:
            raise AssertionError('opening finite animation never finished')
        lengths.append(f.frame['ms'] - started)
        f.display(busy=False)
        if box == 0:
            complete = f.frame['pixels']
            sleep_and_wake(f)
            assert f.frame['pixels'] == complete, 'wake advanced/skipped the finished dialogue'
        if box < 3:
            f.key('A')
    # Box 4 (zero-based 3) includes the finite Oak breathing motion after typing.
    assert lengths[3] > 20 * 33, lengths
    return {'completed_dialogues': 4, 'finite_animation_ms': lengths,
            'dialogue_wait_can_sleep': True, 'wake_did_not_advance': True}


def encounter_transition(f):
    f.display(busy=False)
    f.key('A'); f.display(busy=True)
    transition_frames = 0
    while f.state()['page'] == 2:
        f.display(busy=True)
        f.tick(60); transition_frames += 1
        assert transition_frames < 100
    assert f.state()['page'] == 3
    phases = f.ready()
    assert not f.state()['can_leave'], 'fixture must distinguish leave lock from screen busy'
    sleep_and_wake(f)
    assert f.state()['page'] == 3 and not f.state()['active'], 'wake started capture/battle'
    return {'transition_samples': transition_frames, 'entry_phases': phases,
            'locked_choice_can_sleep': True}


def battle(f, require_long=False, require_exp=False):
    entry = f.ready()
    f.key('B')
    started = f.frame['ms']
    phases, samples = set(), 0
    while True:
        state = f.state()
        phase = state['presentation']['phase']
        phases.add(phase)
        if phase == 'result':
            f.display(busy=False)
            break
        assert phase in ('battle', 'attack', 'exp'), phase
        f.display(busy=True)
        f.tick(); samples += 1
        assert samples < 1800, 'battle did not settle'
    duration = f.frame['ms'] - started
    assert 'attack' in phases
    if require_long:
        assert duration > 30000, ('fixture no longer exercises long battle', duration)
    if require_exp:
        assert state['active']['won'] and 'exp' in phases, ('no actual victory EXP animation', state)
    # No key resets this deadline: a completed long animation must itself leave
    # a fresh interval, rather than sleeping immediately on its last frame.
    f.tick(59800); f.display(busy=False)
    f.tick(300); f.display(busy=False, off=True)
    before = game_state(f.state())
    f.key('C'); f.display(busy=False)
    assert game_state(f.state()) == before, 'wake C left the battle result'
    f.key('C'); assert f.state()['page'] == 2
    return {'entry_phases': entry, 'battle_phases': sorted(phases),
            'duration_ms': duration, 'animation_samples': samples,
            'won': state['active']['won'], 'fresh_result_timeout': True}


def prepare_master(f):
    f.ready()
    for item in range(3):
        f.command(f'inventory {item} 0')
    f.command('inventory 3 1')
    f.key('A'); assert f.state()['page'] == 4
    f.display(busy=False)


def capture_wait(f):
    prepare_master(f)
    before = game_state(f.state())
    f.tick(60000); f.tick(100); f.display(busy=False, off=True)
    f.tick(30000); f.display(busy=False, off=True)
    assert game_state(f.state()) == before, 'elapsed capture clock auto-threw or spent a ball'
    f.key('A', 0); f.display(busy=False)
    f.tick(50); f.key('A', 4); f.tick(180); f.key('A'); f.key('A', 5)
    assert game_state(f.state()) == before, 'wake A threw or spent the selected Master Ball'
    f.key('A')
    f.display(busy=True)
    after = f.state()
    assert after['party_count'] == before['party_count'] + 1
    assert after['inventory'][3] == before['inventory'][3] - 1
    f.tick(240); f.display(busy=True)
    f.tick(760); assert f.state()['page'] == 2
    f.display(busy=False)
    return {'unattended_ms': 60100, 'wake_did_not_throw': True,
            'next_A_caught_once': True, 'flash_and_hold_protected': True}


def capture_save_retry(f):
    prepare_master(f)
    before = f.state()
    f.command('save_fail_after 1'); f.key('A')
    state = f.state()
    assert state['page'] == 4 and state['active'] and state['party_count'] == before['party_count']
    assert state['inventory'][3] == 0
    f.display(busy=False)
    f.tick(60000); f.tick(100); f.display(busy=False, off=True)
    f.key('A'); f.display(busy=False)
    assert f.state()['party_count'] == before['party_count'], 'wake retried storage'
    f.key('A'); f.display(busy=True)
    assert f.state()['party_count'] == before['party_count'] + 1 and f.state()['inventory'][3] == 0
    f.tick(1000); assert f.state()['page'] == 2
    return {'static_save_error_can_sleep': True, 'wake_did_not_retry': True,
            'separate_retry_caught_once_without_second_ball': True}


def capture_retaliation(f):
    f.ready(); f.key('A'); f.key('A')  # pointer at zero guarantees a miss
    assert f.state()['active']['retaliation']
    f.display(busy=True)
    f.tick(960); assert f.state()['page'] == 4
    f.display(busy=True)
    f.tick(40); assert f.state()['page'] == 3
    phases = set()
    for _ in range(100):
        phase = f.state()['presentation']['phase']; phases.add(phase)
        if phase == 'choice':
            break
        f.display(busy=True)
        f.tick()
    else:
        raise AssertionError('failed throw did not return to choice')
    assert f.state()['active']['attacks'] == 1 and 'retaliation' in phases
    f.display(busy=False)
    return {'hold_ms': 1000, 'retaliation_attacks': 1, 'phases': sorted(phases)}


def care_evolution(f):
    f.command('care_progress 60 40')
    for _ in range(4):
        f.key('B')
    f.key('A'); f.display(busy=True)
    original = f.state()['pet']
    f.tick(363); f.display(busy=True)
    assert f.state()['pet'] == original
    f.tick(33); f.display(busy=True)
    assert f.state()['pet'] == 2
    f.tick(957); f.display(busy=True)
    assert f.state()['page'] == 5
    f.tick(33); f.display(busy=False)
    assert f.state()['page'] == 1
    f.tick(59999); f.display(busy=False)
    f.tick(101); f.display(busy=False, off=True)
    return {'evolution_ms': 396, 'result_hold_ms': 990,
            'evolved_species': 2, 'idle_timeout_resumes_after_return': True}


def starter_retry(f):
    f.command('save_fail 1'); f.key('A')
    assert f.state()['party_count'] == 0
    f.display(busy=False)
    f.tick(60000); f.tick(100); f.display(busy=False, off=True)
    f.key('A'); f.display(busy=False)
    assert f.state()['party_count'] == 0
    f.key('A'); assert f.state()['page'] == 1 and f.state()['party_count'] == 1
    return {'failed_save_wait_can_sleep': True, 'wake_did_not_choose_starter': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path,
                        default=ROOT / 'reports/evidence/screen-idle-2026-09-08/pages.json')
    args = parser.parse_args()
    executable, version = build()
    inputs = ['screen_idle.c', 'screen_idle.h', 'nav.c', 'nav.h', 'play.h'] + [
        f'play_{name}.c' for name in ('opening', 'starter', 'enc', 'battle', 'capture', 'care')]
    def source_hashes():
        return {name: hashlib.sha256((ROOT / 'firmware/main' / name).read_bytes()).hexdigest()
                for name in inputs}
    tested_sources = source_hashes()
    cases = [(f'P{page} static wait', static_page, {'page': page})
             for page in (1, 2, 5, 6, 9, 10, 11, 12)]
    cases += [
        ('opening finite animations and dialogue wait', opening, {'page': 0}),
        ('encounter transition and locked battle choice', encounter_transition, {'page': 2}),
        ('automatic battle longer than 30 seconds', lambda f: battle(f, require_long=True),
         {'pet': 95, 'level': 45, 'wild': 95, 'rarity': 5}),
        ('victory HP and EXP animation', lambda f: battle(f, require_exp=True), {}),
        ('capture pointer wait and consumed wake gesture', capture_wait, {}),
        ('capture successful result storage retry', capture_save_retry, {}),
        ('failed throw timed return and exactly one retaliation', capture_retaliation, {}),
        ('care evolution and timed feedback', care_evolution, {'page': 5, 'pet': 1, 'level': 16}),
        ('starter failed save and consumed wake gesture', starter_retry, {'page': 9}),
    ]
    results, checks = [], 0
    for label, verify, fixture in cases:
        flow = Flow(executable, **fixture)
        try:
            result = verify(flow)
            checks += flow.checks
            results.append({'case': label, 'dirty_checks': flow.checks, **result})
            print(f'PASS {label}')
        finally:
            flow.close()
    assert source_hashes() == tested_sources, 'page/idle source changed during validation; rerun against the final source'
    report = {'build': version, 'cases': len(results), 'dirty_checks': checks, 'results': results,
              'source_sha256': tested_sources,
              'scope': 'Actual C pages, nav, screen_idle, assets and renderer; clock/world/NVS are host fixtures.'}
    args.evidence.parent.mkdir(parents=True, exist_ok=True)
    args.evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'build': version, 'cases': len(results), 'dirty_checks': checks}))


if __name__ == '__main__':
    main()
