#!/usr/bin/env python3
"""Address-aware updater with isolated flash/transport; never touches hardware."""
from pathlib import Path
import importlib.util
import json
import struct
import tempfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('updater', ROOT/'tools/release/update_firmware.py')
u = importlib.util.module_from_spec(spec)
spec.loader.exec_module(u)

for failure in ('none', 'layout', 'other-game', 'journal', 'corrupt', 'readback', 'write', 'backup'):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        app = bytearray(4096);app[0] = 0xe9
        struct.pack_into('<I', app, 32, 0xabcd5432)
        app[80:88] = b'PokeWalk'
        table = bytes([0x55])*0xc00
        (root/'PokeWalk.bin').write_bytes(app)
        (root/'partition-table.bin').write_bytes(table)
        (root/'update.json').write_text(json.dumps({'format':'pokewalk-app-update-v1','address':0x10000,'size':len(app),'sha256':u.sha(app),'partition_sha256':u.sha(table)}))
        if failure == 'corrupt':(root/'PokeWalk.bin').write_bytes(b'corrupt')
        memory = {at:bytearray([0xa5])*size for at,size in u.DATA_RANGES}
        memory[0x8000][:0xc00] = table
        if failure == 'layout':memory[0x8000][0] ^= 1
        if failure == 'journal':
            marker = bytearray(52);struct.pack_into('<II',marker,0,0x31525750,0x6000)
            struct.pack_into('<I',marker,48,zlib.crc32(marker[:48]))
            memory[0x350000][0x10000:0x10034] = marker
        original = {at:bytes(data) for at,data in memory.items()}
        calls = []
        def runner(*args,first=False,reset=False):
            calls.append((args,reset))
            command = args[0]
            if command == 'read_mac':return 'MAC: 00:11:22:33:44:55'
            if command == 'read_flash':
                at,size = int(args[1],0),int(args[2],0)
                data = app[:size] if at==0x10000 else memory[at]
                if at == 0x10000 and failure == 'other-game':data = bytes(size)
                Path(args[3]).write_bytes(data)
            elif command == 'write_flash':
                assert int(args[1],0)==0x10000 and Path(args[2]).read_bytes()==app
                files=list((root/'backup').glob('*/flash-*.bin'))
                assert len(files)==2
                for file in files:assert file.read_bytes()==original[int(file.stem.split('-')[1],16)]
                if failure == 'write':raise RuntimeError('simulated write failure')
                if failure == 'readback':memory[0x8000][0x1000] ^= 1
            elif command == 'verify_flash':assert int(args[1],0)==0x10000
            else:assert command=='chip_id' and reset
            return ''
        if failure == 'backup':(root/'backup').write_text('not a directory')
        try:
            result=u.update(root,'fake-port',root/'backup',runner)
            assert failure=='none' and result['data_unchanged']
            assert calls[-1][1]
        except (ValueError,RuntimeError,OSError):
            assert failure!='none'
            assert not any(reset for _,reset in calls)
        writes=[args for args,_ in calls if args[0]=='write_flash']
        assert len(writes)==(1 if failure in ('none','write','readback') else 0)
        assert not any(args[0].startswith('erase') for args,_ in calls)
        if failure!='readback':assert all(bytes(memory[at])==data for at,data in original.items())
print('app-only update, pre-write backup, protected data, unsafe inputs and interrupted update: passed')
