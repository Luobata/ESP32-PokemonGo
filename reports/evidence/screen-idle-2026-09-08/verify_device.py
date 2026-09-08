"""Verify display PWM, wake semantics and continued scans on the installed board."""
import argparse
import json
from pathlib import Path
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tools/device'))
import monitor
import serial

parser = argparse.ArgumentParser()
parser.add_argument('--port', required=True)
args = parser.parse_args()
out = Path(__file__).resolve().parent
events = []
pending = bytearray()
status_pattern = re.compile(r'@@DISPLAY_STATE off=(\d+) brightness=(\d+) page=(\d+) scans=(\d+) pending=(\d+) pet=(\d+) level=(\d+) exp=(\d+)')
fields = ('off', 'brightness', 'page', 'scans', 'pending', 'pet', 'level', 'exp')
ser = serial.Serial(args.port, 115200, timeout=0.1)

def read_for(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        pending.extend(ser.read(8192))
        while b'\n' in pending:
            raw, _, remaining = pending.partition(b'\n')
            pending[:] = remaining
            line = raw.decode(errors='replace').strip()
            # Keep display and boot evidence only; discard Wi-Fi identifiers.
            if any(text in line for text in ('@@DISPLAY', 'Silent build:', 'world: 读档', 'main: 就绪')):
                events.append(line)

def status():
    start = len(events)
    ser.write(b'q'); ser.flush()
    for _ in range(20):
        read_for(0.1)
        for line in events[start:]:
            match = status_pattern.search(line)
            if match:
                return dict(zip(fields, map(int, match.groups())))
    raise AssertionError('device did not respond to display status')

def key(value):
    ser.write(value.encode()); ser.flush(); read_for(0.25)

checks = {}
try:
    monitor.reset(ser)
    read_for(6)
    assert any('Silent build:' in line for line in events)
    original = status()
    assert original['page'] == 0 and original['brightness'] == 100 and not original['off']
    key('b'); assert status()['page'] == 9
    key('c'); baseline = status(); assert baseline['page'] == 0
    start = time.monotonic()
    read_for(max(0, 28 - (time.monotonic() - start)))
    before = status(); assert not before['off'] and before['brightness'] == 100
    read_for(max(0, 30.6 - (time.monotonic() - start)))
    asleep = status(); assert asleep['off'] and asleep['brightness'] == 0
    checks['automatic_timeout'] = {'before_30s': before, 'after_30s': asleep}
    print('30-second display timeout: PASS', flush=True)
    read_for(35)
    later = status()
    assert later['off'] and later['brightness'] == 0 and later['scans'] > asleep['scans']
    checks['background_scans_while_off'] = {'before': asleep['scans'], 'after': later['scans']}
    print('Background scanning while display is off: PASS', flush=True)
    key('b'); woke = status()
    assert not woke['off'] and woke['brightness'] == 100 and woke['page'] == 0
    key('b'); assert status()['page'] == 9
    checks['first_B_only_wakes_second_B_opens_menu'] = True
    for _ in range(4): key('b')
    key('a'); key('b'); key('a')
    manual = status(); assert manual['page'] == 9 and manual['off'] and manual['brightness'] == 0
    key('a'); restored = status()
    assert not restored['off'] and restored['page'] == 9 and restored['brightness'] == 100
    checks['manual_off_and_A_only_wakes'] = True
    key('c'); key('c')
    final = status(); assert final['page'] == 0
    assert (final['pet'], final['level'], final['exp']) == (original['pet'], original['level'], original['exp'])
    checks['original_leader_preserved'] = {k: final[k] for k in ('pet', 'level', 'exp')}
    result = {'status': 'PASS', 'checks': checks, 'final_state': final,
              'scope': 'Actual board PWM duty readback and serial semantic inputs; physical finger presses and current draw not measured.'}
    (out / 'device.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False), flush=True)
finally:
    (out / 'device-filtered.log').write_text('\n'.join(events) + '\n')
    ser.close()
