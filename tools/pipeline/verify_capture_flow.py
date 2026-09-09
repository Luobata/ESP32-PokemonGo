#!/usr/bin/env python3
"""Drive production P2/P3/P4 and inspect encounter effects through host services.

Pages, battle, capture, assets, rendering and nav are the actual firmware C.
The host clock/queue/party/NVS fixture is the same one used by the inspector.
"""
from pathlib import Path
import argparse
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build


class Flow:
    def __init__(self, exe, pet=25, level=12, wild=19, rarity=1, seed=7):
        self.r = Renderer(exe)
        self.checks = 0
        self.command(f'boot 3 {pet} {level} {wild} {rarity} {seed} 0')
        self.uid = self.state()['uid']
        assert self.phase() == 'entry', 'new encounter skipped its entry animation'
        self.locked('ACBAC', 'entry')
        self.until(lambda: self.phase() == 'choice', 'entry and original front motion', limit=200)

    def close(self):
        self.r.close()

    def state(self):
        return self.r.inspect()

    def encounter(self, uid=None):
        state = self.state()
        target = self.uid if uid is None else uid
        active = state['active']
        if active and active['uid'] == target:
            return active
        return next((e for e in state['queue'] if e['uid'] == target), None)

    def phase(self):
        return (self.state()['presentation'] or {}).get('phase')

    def command(self, command):
        result = self.r.command(command)
        check = self.r.command('check')
        assert check['mismatch'] == 0, f'{command}: {check["mismatch"]} stale pixels'
        self.checks += 1
        return result

    def key(self, key):
        return self.command(f'key {"ABC".index(key)} 1')

    def tick(self, ms=60):
        return self.command(f'tick {ms}')

    def until(self, condition, label, limit=800):
        for _ in range(limit):
            if condition():
                return
            self.tick()
        raise AssertionError(f'timed out: {label}')

    def victory(self):
        self.key('B')
        assert self.encounter()['auto_battle'] and self.state()['active']
        assert all(e['uid'] != self.uid for e in self.state()['queue'])
        self.locked('ABABA', 'battle')
        self.until(lambda: self.phase() == 'attack', 'first attack animation')
        self.locked('ABABA', 'attack')
        self.until(lambda: self.encounter()['reward_settled'], 'battle settlement')
        assert self.encounter()['won'], 'fixture did not win'
        self.locked('ACBAC', 'exp')
        self.until(lambda: self.phase() == 'result', 'experience animation', limit=120)

    def locked(self, keys, phase):
        before = self.state()
        assert self.phase() == phase, (phase, self.phase())
        for key in keys:
            self.key(key)
            assert self.state() == before, f'{phase}: {key} bypassed the phase lock'


def negative_probes():
    # Mutate a private build, never the developer's source/assets. A red result
    # must be a flow assertion, not a compilation or fixture setup failure.
    changes = (
        ('missing retaliation', 'play_capture.c',
         's_session.retaliation_pending = true;', 's_session.retaliation_pending = false;'),
        ('unlocked counter', 'play_battle.c',
         'return !s_entering && !s_wild_animating && !s_escape_feedback && !s_exp_anim && !s_playing && !s_counter_anim &&',
         'return !s_entering && !s_wild_animating && !s_escape_feedback && !s_exp_anim && (!s_playing || s_counter_anim) &&'),
        ('reinitialized battle', 'play_battle.c',
         'if (!s_session.initialized || (!s_session.started &&',
         'if (true || (!s_session.started &&'),
        ('victory miss kept active', 'play_capture.c',
         'world_take_uid(c->uid, NULL);', '/* negative: retain failed encounter */'),
        ('counter starts automatic battle', 'play_battle.c',
         '} else if (!s_session.auto_battle) {', '} else if (false) {'),
        ('unlocked automatic battle', 'play_battle.c',
         'return !s_entering && !s_wild_animating && !s_escape_feedback && !s_exp_anim && !s_playing && !s_counter_anim &&',
         'return !s_entering && !s_wild_animating && !s_escape_feedback && !s_exp_anim && (!s_playing || s_session.auto_battle) && !s_counter_anim &&'),
        ('unlocked EXP animation', 'play_battle.c',
         'return !s_entering && !s_wild_animating && !s_escape_feedback && !s_exp_anim && !s_playing && !s_counter_anim &&',
         'return !s_entering && !s_wild_animating && !s_escape_feedback && !s_playing && !s_counter_anim &&'),
    )
    with tempfile.TemporaryDirectory(prefix='capture_flow_negative_') as directory:
        root = Path(directory)
        for name in ('firmware/main', 'firmware/components/bsp/include', 'tools/inspector/host'):
            shutil.copytree(ROOT / name, root / name)
        (root / 'assets').mkdir()
        for path in (ROOT / 'assets').glob('*.bin'):
            shutil.copy2(path, root / 'assets' / path.name)
        shutil.copy2(ROOT / 'tools/inspector/native.py', root / 'tools/inspector/native.py')
        test = root / 'tools/pipeline/verify_capture_flow.py'
        test.parent.mkdir(parents=True)
        shutil.copy2(__file__, test)
        for label, name, old, new in changes:
            source = root / 'firmware/main' / name
            original = source.read_text()
            assert original.count(old) == 1, f'mutation anchor changed: {label}'
            source.write_text(original.replace(old, new))
            # Automatic capture is guarded by the page and by battle.c. This
            # semantic negative disables both in the private fixture only.
            extra = root / 'firmware/main/battle.c'
            extra_original = extra.read_text()
            if label == 'unlocked automatic battle':
                token = ': !s->auto_battle && s->pet_hp > 0;'
                assert extra_original.count(token) == 1
                extra.write_text(extra_original.replace(token, ': s->pet_hp > 0;'))
            result = subprocess.run([sys.executable, str(test)], text=True,
                                    capture_output=True, timeout=60)
            source.write_text(original)
            extra.write_text(extra_original)
            assert result.returncode and 'AssertionError' in result.stderr, (
                f'{label}: mutation escaped or infrastructure failed\n{result.stdout}\n{result.stderr}')
            print(f'PASS negative: {label}')


def main():
    exe, version = build()
    checks = cases = 0

    # Before any battle, a missed throw has a mandatory, single wild reply.
    f = Flow(exe)
    try:
        initial = f.encounter()
        exp = f.state()['exp']
        f.key('A'); assert f.state()['page'] == 4
        f.key('A')  # Pointer is 0: an unambiguous miss.
        pending = f.encounter()
        assert pending['retaliation'] and pending['started'] and pending['attacks'] == 0
        assert (pending['pet_hp'], pending['wild_hp']) == (initial['pet_hp'], initial['wild_hp'])
        for key in 'AABBCCAABC':
            f.key(key)
        assert f.encounter() == pending and f.state()['page'] == 4
        f.tick(40)
        after = f.encounter()
        assert f.state()['page'] == 3 and after['attacks'] == 1 and not after['retaliation']
        assert after['pet_hp'] < initial['pet_hp'] and after['wild_hp'] == initial['wild_hp']
        for key in 'ACBAC':
            f.key(key)
            assert f.state()['page'] == 3 and f.encounter() == after, 'counter animation can be bypassed'
        f.until(lambda: f.phase() == 'choice', 'choice after one counter', limit=30)
        assert f.encounter() == after and not after['auto_battle']
        assert f.state()['presentation']['visible_pet_hp'] == after['pet_hp']
        f.tick(2400)
        assert f.encounter() == after, 'counter silently started automatic battle'
        f.key('B'); f.locked('ABABA', 'battle')
        f.until(lambda: f.encounter()['attacks'] == 2, 'explicit player battle choice')
        next_turn = f.encounter()
        assert next_turn['pet_hp'] == after['pet_hp'] and next_turn['wild_hp'] < after['wild_hp']
        f.locked('ABABA', 'attack')
        assert f.state()['exp'] == exp
        cases += 1
    finally:
        checks += f.checks; f.close()

    # Unthrown cancellation retains the choice. Once a throw has started this
    # encounter, cancellation still keeps its HP; leaving the chain ends it.
    f = Flow(exe, level=20, wild=133, rarity=3, seed=11)
    try:
        initial = f.encounter()
        for _ in range(3):
            f.key('A'); assert f.state()['page'] == 4
            f.key('C'); assert f.state()['page'] == 3
            assert f.phase() == 'choice', 'unthrown cancel replayed the entry'
            assert f.encounter() == initial and f.state()['active'] is None
        f.key('A'); f.key('A'); f.key('C'); f.tick(40)
        f.until(lambda: f.phase() == 'choice', 'first reply', limit=30)
        partial = f.encounter()
        assert partial['attacks'] == 1 and not partial['finished']
        assert f.state()['active'] == partial
        assert all(e['uid'] != f.uid for e in f.state()['queue'])
        for _ in range(3):
            f.key('A'); assert f.state()['page'] == 4
            f.key('C'); assert f.state()['page'] == 3
            assert f.phase() == 'choice' and f.encounter() == partial, 'cancel reset HP or entry'
        f.key('A'); f.key('A')
        assert f.encounter()['retaliation']
        f.key('C'); f.tick(40)
        after = f.encounter()
        assert f.state()['page'] == 3 and after['attacks'] == partial['attacks'] + 1
        assert after['wild_hp'] == partial['wild_hp'] and after['pet_hp'] < partial['pet_hp']
        f.until(lambda: f.phase() == 'choice', 'second reply', limit=30)
        pending_count = len(f.state()['queue'])
        f.key('C')
        f.until(lambda: f.state()['page'] == 2, 'successful escape feedback', limit=20)
        assert f.state()['active'] is None and f.encounter() is None
        assert len(f.state()['queue']) == pending_count, 'handled encounter was requeued'
        for page in (3, 4):
            f.command(f'page {page}')
            assert f.state()['page'] == 2 and f.encounter() is None, 'abandoned encounter revived'
        cases += 1
    finally:
        checks += f.checks; f.close()

    # Even a direct preview-page change cannot discard an owed counterattack.
    f = Flow(exe)
    try:
        before = f.encounter()
        f.key('A'); f.key('A')
        f.command('page 4')
        after = f.encounter()
        assert f.state()['page'] == 3 and after['attacks'] == 1
        assert after['pet_hp'] < before['pet_hp'] and after['wild_hp'] == before['wild_hp']
        cases += 1
    finally:
        checks += f.checks; f.close()

    # A victory grants EXP once. Cancelling before the throw retains its one
    # chance; a miss consumes/removes the uid immediately, before the hold ends.
    f = Flow(exe, pet=139, level=100, wild=137, seed=3)
    try:
        before = f.state()
        f.victory()
        won = f.state()
        assert won['exp'] == before['exp'] + 60 and f.encounter()['exp_granted']
        for _ in range(2):
            f.key('A'); f.key('C')
            assert not f.encounter()['capture_used'] and f.state()['exp'] == won['exp']
            assert f.phase() == 'result', 'return replayed entry or EXP'
        f.key('A'); f.key('B'); f.key('A')
        assert f.encounter() is None and f.state()['active'] is None
        assert len(f.state()['queue']) == len(won['queue']), 'already detached target changed pending queue'
        assert f.state()['party_count'] == won['party_count'] and f.state()['caught'] == won['caught']
        for key in 'ABCAABC': f.key(key)
        f.tick(40); assert f.state()['page'] == 2
        for page in (4, 3, 4):
            f.command(f'page {page}')
            assert f.state()['page'] == 2 and f.encounter() is None
        assert f.state()['exp'] == won['exp']
        cases += 1
    finally:
        checks += f.checks; f.close()

    # A winning throw commits party/dex/queue exactly once despite queued keys.
    f = Flow(exe, pet=139, level=100, wild=137, seed=3)
    try:
        f.victory(); won = f.state()
        f.key('A'); f.tick(300); f.key('A')
        caught = f.state()
        assert f.encounter() is None
        assert caught['party_count'] == won['party_count'] + 1 and caught['caught'] == won['caught'] + 1
        for key in 'AABBCACABC': f.key(key)
        f.tick(40)
        f.command('page 4')
        final = f.state()
        assert final['page'] == 2 and final['party_count'] == caught['party_count']
        assert final['caught'] == caught['caught'] and final['exp'] == won['exp']
        cases += 1
    finally:
        checks += f.checks; f.close()

    # Lethal retaliation finishes the same fight and animates a multi-level
    # reward. No key may reopen capture or leave during that EXP animation.
    f = Flow(exe, level=1, wild=150, rarity=5, seed=1)
    try:
        f.key('A'); f.key('A'); f.key('C'); f.tick(40)
        hit = f.encounter()
        assert hit['attacks'] == 1 and hit['finished'] and not hit['won'] and hit['pet_hp'] == 0
        f.until(lambda: f.encounter()['reward_settled'], 'lethal counter settlement')
        settled = f.encounter(); exp = f.state()['exp']
        assert f.phase() == 'exp' and f.state()['presentation']['visible_exp'] == 0
        f.locked('ACBAC', 'exp')
        visible = []
        for _ in range(18):
            f.tick()
            visible.append(f.state()['presentation'])
        assert f.phase() == 'result'
        assert visible[-1]['visible_exp'] == exp and visible[-1]['visible_level'] == f.state()['level']
        assert len({v['visible_level'] for v in visible}) >= 3, 'multi-level EXP growth snapped'
        assert all(a['visible_exp'] <= b['visible_exp'] for a, b in zip(visible, visible[1:]))
        f.command('page 4'); assert f.state()['page'] == 3
        assert f.encounter() == settled and f.state()['exp'] == exp
        assert f.phase() == 'result', 'reopening defeat replayed EXP'
        f.key('A'); assert f.state()['page'] == 5, 'defeat A did not offer care'
        assert f.encounter() is None and f.state()['active'] is None
        f.command('page 3')
        assert f.state()['page'] == 2 and f.encounter() is None and f.state()['exp'] == exp
        cases += 1
    finally:
        checks += f.checks; f.close()

    # Failure to persist queue removal does not publish a battle or consume a
    # throw. The unchanged pending entry can be selected and started again.
    f = Flow(exe)
    try:
        initial = f.encounter(); count = len(f.state()['queue'])
        f.command('save_fail 1'); f.key('B')
        assert f.phase() == 'choice' and f.encounter() == initial
        assert f.state()['active'] is None and len(f.state()['queue']) == count
        f.key('A'); f.command('save_fail 1'); f.key('A')
        assert f.state()['page'] == 4 and f.encounter() == initial
        assert f.state()['active'] is None and len(f.state()['queue']) == count
        assert f.state()['inventory'][:3] == [12,3,1], 'failed save spent a ball'
        f.key('C')
        f.until(lambda: f.state()['page'] == 3, 'retry pending encounter')
        assert f.phase() == 'choice' and f.encounter() == initial
        f.key('B'); f.tick()
        assert f.encounter()['auto_battle'] and f.encounter()['attacks'] == 1
        assert f.state()['active'] and len(f.state()['queue']) == count - 1
        cases += 1
    finally:
        checks += f.checks; f.close()

    print(f'PASS: {cases} actual C capture/battle flows; {checks} dirty/full checks; build {version}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative', action='store_true', help='also prove seven broken variants fail')
    args = parser.parse_args()
    main()
    if args.negative:
        negative_probes()
