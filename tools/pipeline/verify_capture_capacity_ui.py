#!/usr/bin/env python3
"""Actual capture renderer/navigation with full-box and save-failure fixtures."""
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import Renderer, build


def main():
    exe, version = build()
    checks = 0

    def cmd(r, line):
        nonlocal checks
        frame = r.command(line)
        assert r.command('check')['mismatch'] == 0, line
        checks += 1
        return frame

    def scene(count, target=0, team=1):
        r = Renderer(exe)
        cmd(r, f'boot 4 150 77 150 5 1 0 0 {team}')
        cmd(r, f'box_fixture {count} {target}')
        # Guaranteed hit isolates capacity/settlement from rare-species timing.
        for ball in range(3):
            cmd(r, f'inventory {ball} 0')
        cmd(r, 'inventory 3 1')
        cmd(r, 'page 4')
        return r

    # Full storage spends one ball, runs animation, then requires explicit
    # selection plus a default-cancel second confirmation. No silent replacement.
    r = scene(753)
    try:
        before=r.inspect()
        cmd(r,'tick 300');cmd(r,'key 2 0');cmd(r,'key 2 4');cmd(r,'key 2 1')
        cmd(r,'tick 10000')
        assert r.inspect()['page']==4 and r.inspect()['box_count']==753
        assert r.inspect()['inventory'][3]==before['inventory'][3]-1
        assert r.inspect()['exp']==before['exp']
        listing=cmd(r,'check')['pixels']
        cmd(r,'key 0 1')  # Wrap to row 752, exercising widened indices.
        confirmed=cmd(r,'key 2 1')  # Confirmation is visible, still no mutation.
        # Incoming identity remains visible above the old partner confirmation.
        assert confirmed['pixels'][40*480:56*480]==listing[40*480:56*480]
        assert any(confirmed['pixels'][40*480:56*480][i:i+2] != b'\xff\xff' for i in range(0,16*480,2))
        assert r.inspect()['exp']==before['exp']
        cmd(r,'key 2 1')  # Default cancel returns to the list.
        assert r.inspect()['exp']==before['exp']
        cmd(r,'key 2 1');cmd(r,'key 1 1');cmd(r,'key 2 1')
        assert r.inspect()['box_count']==753 and r.inspect()['active'] is None
        assert r.inspect()['exp']>before['exp']
        assert r.inspect()['inventory'][3]==before['inventory'][3]-1
    finally:r.close()

    # Declining a new catch also has a default-cancel confirmation.
    r=scene(753)
    try:
        before=r.inspect();cmd(r,'tick 300');cmd(r,'key 2 1');cmd(r,'tick 10000')
        cmd(r,'key 1 3');cmd(r,'key 2 1')
        assert r.inspect()['page']==4 and r.inspect()['exp']==before['exp']
        cmd(r,'key 1 3');cmd(r,'key 1 1');cmd(r,'key 2 1')
        assert r.inspect()['page']!=4 and r.inspect()['box_count']==753
        assert r.inspect()['exp']==before['exp'] and r.inspect()['party']==before['party']
    finally:r.close()

    # Repeated same-species captures use empty slots; no automatic best-of merge.
    for count,target,team in ((752,0,1),(752,150,1),(753,0,0)):
        r=scene(count,target,team)
        try:
            before=r.inspect();cmd(r,'tick 300');cmd(r,'key 2 1');after=r.inspect()
            assert after['active'] is None and after['exp']>before['exp']
            assert after['party_count']+after['box_count']==before['party_count']+before['box_count']+1
            assert after['inventory'][3]==before['inventory'][3]-1
        finally:r.close()

    # Failed replacement preserves the old warehouse and retries the same ball.
    r=scene(753)
    try:
        before=r.inspect();cmd(r,'tick 300');cmd(r,'key 2 1');cmd(r,'tick 10000')
        cmd(r,'key 2 1');cmd(r,'key 1 1');cmd(r,'save_fail 1');cmd(r,'key 2 1')
        assert r.inspect()['exp']==before['exp'] and r.inspect()['box_count']==753
        cmd(r,'save_fail 0');cmd(r,'key 2 1')
        assert r.inspect()['exp']>before['exp'] and r.inspect()['box_count']==753
        assert r.inspect()['inventory'][3]==before['inventory'][3]-1
    finally:r.close()

    blob = (ROOT / 'assets/font16.bin').read_bytes()
    count = struct.unpack_from('<I', blob, 10)[0]
    codes = set(struct.unpack_from(f'<{count}H', blob, 14))
    for char in '仓库已满选择要替换的仓库伙伴取消确认替换放走新伙伴这是闪光伙伴，无法撤销':
        assert ord(char) < 128 or ord(char) in codes, char
    print(json.dumps(dict(passed=True, build=version, frame_checks=checks,
                         full_box_manual_replacement=True, same_ball_retry=True, physical_device=False)))


if __name__ == '__main__':
    main()
