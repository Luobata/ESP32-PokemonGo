#!/usr/bin/env python3
"""Update an existing PokeWalk over USB without writing its data partitions.

Run from the extracted PokeWalk-update.zip. Requires esptool 4.x.
Allows only the documented additive V23 store partition; never moves old data.
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
# Table/NVS/PHY, card identity/restore journal/Wi-Fi, and expanded storage.
# Only the table sector may change during the strictly additive migration.
DATA_RANGES = ((0x8000, 0x8000), (0x350000, 0x30000), (0x380000, 0x20000))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def app_valid(data):
    return (len(data) >= 208 and data[0] == 0xe9 and
            struct.unpack_from('<I', data, 32)[0] == 0xabcd5432 and
            data[80:112].split(b'\0')[0] == b'PokeWalk')



def partitions(raw):
    records={};end=None
    for i in range(0,0xc00,32):
        magic=struct.unpack_from('<H',raw,i)[0]
        if magic==0xebeb:
            if raw[i+16:i+32]!=hashlib.md5(raw[:i]).digest():raise ValueError('分区表摘要无效')
            end=i+32;break
        if magic!=0x50aa:raise ValueError('分区表缺少有效校验记录')
        _,kind,sub,at,size,label,flags=struct.unpack_from('<HBBII16sI',raw,i)
        name=label.rstrip(b'\0').decode('ascii')
        if name in records or not size:raise ValueError('分区表重复或空分区')
        records[name]=(kind,sub,at,size,flags)
    if end is None or any(b!=255 for b in raw[end:0xc00]):raise ValueError('分区表尾部无效')
    spans=sorted((v[2],v[2]+v[3]) for v in records.values())
    if any(a[1]>b[0] for a,b in zip(spans,spans[1:])):raise ValueError('分区重叠')
    return records

def additive_store_only(before,after):
    old,new=partitions(before),partitions(after)
    addition={'pokewalk_store':(1,0x41,0x380000,0x20000,0)}
    return 'pokewalk_store' not in old and new==dict(old,**addition)

def update(bundle, port, backup_dir, runner=None):
    bundle = Path(bundle)
    manifest = json.loads((bundle / 'update.json').read_text())
    app = (bundle / 'PokeWalk.bin').read_bytes()
    table = (bundle / 'partition-table.bin').read_bytes()
    if (manifest.get('format') not in ('pokewalk-app-update-v1','pokewalk-app-update-v2') or
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
        migrate=before[0][:0xc00]!=table[:0xc00]
        if migrate and (manifest.get('format')!='pokewalk-app-update-v2' or not additive_store_only(before[0],table)):
            raise ValueError('分区变化超出新增仓库存储区范围，禁止写入；请保留备份')
        journal = before[1][0x10000:0x11000]
        if (struct.unpack_from('<I',journal)[0] in (0x31525750,0x32525750) and struct.unpack_from('<I',journal,4)[0]==0x6000 and
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
        # during the backup. Data partitions are never passed to write_flash.
        target = tmp / 'verified-app.bin'
        target.write_bytes(app)
        run('write_flash', hex(APP_AT), target)
        run('verify_flash', hex(APP_AT), target)
        expected=list(before)
        if migrate:
            # Sector erase is 4 KiB. Preserve all bytes after the 0xc00 table.
            next_sector=table[:0xc00]+before[0][0xc00:0x1000]
            (tmp/'verified-table.bin').write_bytes(next_sector)
            run('write_flash','0x8000',tmp/'verified-table.bin')
            run('verify_flash','0x8000',tmp/'verified-table.bin')
            expected[0]=next_sector+before[0][0x1000:]
        for (at, size), data in zip(DATA_RANGES, expected):
            dest = tmp / f'after-{at:x}.bin'
            run('read_flash', hex(at), hex(size), dest)
            if dest.read_bytes() != data:
                raise RuntimeError(f'更新后数据分区发生变化；暂不重启，请保留原始备份：{backup}')
        run('chip_id', reset=True)
        return {'updated': True, 'data_unchanged': True, 'partition_added':migrate, 'backup': str(backup)}


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
