#!/usr/bin/env python3
"""Update an existing PokeWalk over USB without writing its data partitions.

Run from the extracted PokeWalk-update.zip. Requires esptool 4.x.
Does not support first installation, partition migration or pending restores.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import uuid
import zlib

APP_AT, APP_LIMIT = 0x10000, 0x340000
# Table/NVS/PHY, then card identity/restore journal/Wi-Fi. Never written.
DATA_RANGES = ((0x8000, 0x8000), (0x350000, 0x30000))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def app_valid(data):
    return (len(data) >= 208 and data[0] == 0xe9 and
            struct.unpack_from('<I', data, 32)[0] == 0xabcd5432 and
            data[80:112].split(b'\0')[0] == b'PokeWalk')


def update(bundle, port, backup_dir, runner=None):
    bundle = Path(bundle)
    manifest = json.loads((bundle / 'update.json').read_text())
    app = (bundle / 'PokeWalk.bin').read_bytes()
    table = (bundle / 'partition-table.bin').read_bytes()
    if (manifest.get('format') != 'pokewalk-app-update-v1' or
            manifest.get('address') != APP_AT or not app_valid(app) or
            len(app) > APP_LIMIT or len(app) != manifest.get('size') or
            sha(app) != manifest.get('sha256') or len(table) < 0xc00 or
            sha(table) != manifest.get('partition_sha256')):
        raise ValueError('更新包不完整或校验失败，未开始写入')

    def run(*args, first=False, reset=False):
        if runner:
            return runner(*args, first=first, reset=reset)
        command = [sys.executable, '-m', 'esptool', '--chip', 'esp32c3',
                   '--port', port, '--before', 'default_reset' if first else 'no_reset',
                   '--after', 'hard_reset' if reset else 'no_reset', *map(str, args)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError('设备读写失败，更新未确认完成；请保留备份和更新包后重试')
        return result.stdout

    with tempfile.TemporaryDirectory(prefix='pokewalk-update-') as tmp:
        tmp = Path(tmp)
        macs = re.findall(r'(?i)MAC:\s*([0-9a-f:]{17})', run('read_mac', first=True))
        if not macs:
            raise ValueError('无法读取设备身份，未开始写入')
        device = macs[-1].replace(':', '').lower()
        before = []
        for at, size in DATA_RANGES:
            dest = tmp / f'{at:x}.bin'
            run('read_flash', hex(at), hex(size), dest)
            data = dest.read_bytes()
            if len(data) != size:
                raise ValueError('设备数据备份不完整，未开始写入')
            before.append(data)
        if before[0][:0xc00] != table[:0xc00]:
            raise ValueError('设备分区与更新包不同；禁止自动迁移。请先用网页备份，再完整安装和导入')
        journal = before[1][0x10000:0x11000]
        if (struct.unpack_from('<II', journal) == (0x31525750, 0x6000) and
                struct.unpack_from('<I', journal, 48)[0] == zlib.crc32(journal[:48])):
            raise ValueError('设备有未完成的存档导入，请先用原固件完成恢复，未开始写入')
        run('read_flash', hex(APP_AT), '0x100', tmp / 'current-app.bin')
        if not app_valid((tmp / 'current-app.bin').read_bytes()):
            raise ValueError('设备当前不是 PokeWalk；此包只用于更新，未开始写入')

        backup = Path(backup_dir) / f'PokeWalk-before-update-{device}-{uuid.uuid4().hex}'
        backup.mkdir(parents=True, mode=0o700)
        records = []
        for (at, size), data in zip(DATA_RANGES, before):
            dest = backup / f'flash-{at:x}.bin'
            with os.fdopen(os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            if dest.read_bytes() != data:
                raise RuntimeError('更新前备份回读失败，未开始写入')
            records.append({'address': at, 'size': size, 'sha256': sha(data), 'file': dest.name})
        (backup / 'manifest.json').write_text(json.dumps({'device': device, 'ranges': records}, indent=2))
        print('更新前的原始数据已备份并回读校验：', backup)

        # Use the exact bytes validated above, not a file that could be replaced
        # during the backup. Only this one address is ever passed to write_flash.
        target = tmp / 'verified-app.bin'
        target.write_bytes(app)
        run('write_flash', hex(APP_AT), target)
        run('verify_flash', hex(APP_AT), target)
        for (at, size), data in zip(DATA_RANGES, before):
            dest = tmp / f'after-{at:x}.bin'
            run('read_flash', hex(at), hex(size), dest)
            if dest.read_bytes() != data:
                raise RuntimeError(f'更新后数据分区发生变化；暂不重启，请保留原始备份：{backup}')
        run('chip_id', reset=True)
        return {'updated': True, 'data_unchanged': True, 'backup': str(backup)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', required=True)
    parser.add_argument('--update', action='store_true', help='确认更新已安装的 PokeWalk')
    parser.add_argument('--backup-dir', type=Path, default=Path.home() / 'PokeWalk Backups')
    args = parser.parse_args()
    if not args.update:
        parser.error('请先关闭浏览器串口与日志工具，确认更新时添加 --update')
    print(json.dumps(update(Path(__file__).parent, args.port, args.backup_dir), ensure_ascii=False))


if __name__ == '__main__':
    main()
