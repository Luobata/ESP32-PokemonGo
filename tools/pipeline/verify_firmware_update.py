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
                assert len(files)==len(u.DATA_RANGES)
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

# Actual checksummed ESP partition tables: permit exactly the additive store.
def make_table(records):
    raw=b''.join(struct.pack('<HBBII16sI',0x50aa,kind,sub,at,size,label.encode(),0) for label,kind,sub,at,size in records)
    raw+=b'\xeb\xeb'+bytes([255])*14+u.hashlib.md5(raw).digest()
    return raw+bytes([255])*(0xc00-len(raw))
old_records=[('nvs',1,2,0x9000,0x6000),('phy_init',1,1,0xf000,0x1000),('factory',0,0,0x10000,0x340000),('cardid',1,0x40,0x356000,0x4000),('save_restore',1,0x42,0x360000,0x10000),('wifi',1,2,0x370000,0x6000),('recovery',0,0x10,0x700000,0x100000)]
addition=('pokewalk_store',1,0x41,0x380000,0x20000)
for failure in ('none','moved','removed','added-other','overlap','bad-digest','v1-package','journal-v2','write-table','verify-table','readback-data'):
 with tempfile.TemporaryDirectory() as folder:
  root=Path(folder);before_table=make_table(old_records);records=old_records+[addition]
  if failure=='moved':records=[(n,k,s,a+(0x1000 if n=='nvs' else 0),z) for n,k,s,a,z in records]
  if failure=='removed':records=records[1:]
  if failure=='added-other':records+=[('unknown',1,0x43,0x3a0000,0x1000)]
  if failure=='overlap':records[-1]=('pokewalk_store',1,0x41,0x370000,0x20000)
  after_table=make_table(records)
  if failure=='bad-digest':after_table=bytes([after_table[0]^1])+after_table[1:]
  app=bytearray(4096);app[0]=0xe9;struct.pack_into('<I',app,32,0xabcd5432);app[80:88]=b'PokeWalk'
  (root/'PokeWalk.bin').write_bytes(app);(root/'partition-table.bin').write_bytes(after_table)
  (root/'update.json').write_text(json.dumps({'format':'pokewalk-app-update-v1' if failure=='v1-package' else 'pokewalk-app-update-v2','address':0x10000,'size':len(app),'sha256':u.sha(app),'partition_sha256':u.sha(after_table)}))
  memory={at:bytearray((i*13+7)&255 for i in range(size)) for at,size in u.DATA_RANGES};memory[0x8000][:0xc00]=before_table
  if failure=='journal-v2':
   marker=bytearray(60);struct.pack_into('<II',marker,0,0x32525750,0x6000);struct.pack_into('<I',marker,48,zlib.crc32(marker[:48]));struct.pack_into('<I',marker,56,zlib.crc32(marker[:56]));memory[0x350000][0x10000:0x1003c]=marker
  original={at:bytes(data) for at,data in memory.items()};calls=[]
  def runner(*args,first=False,reset=False):
   calls.append((args,reset));cmd=args[0]
   if cmd=='read_mac':return 'MAC: 00:11:22:33:44:55'
   if cmd=='read_flash':
    at,size=int(args[1],0),int(args[2],0);Path(args[3]).write_bytes(app[:size] if at==0x10000 else memory[at][:size])
   elif cmd=='write_flash':
    assert len(list((root/'backup').glob('*/flash-*.bin')))==3
    at=int(args[1],0);assert at in (0x10000,0x8000)
    if at==0x8000:
     if failure=='write-table':raise RuntimeError('interrupted table write')
     sector=Path(args[2]).read_bytes();assert len(sector)==4096 and sector[0xc00:]==original[0x8000][0xc00:0x1000];memory[at][:4096]=sector
     if failure=='readback-data':memory[0x380000][123]^=1
   elif cmd=='verify_flash':
    if int(args[1],0)==0x8000 and failure=='verify-table':raise RuntimeError('table verification failed')
   else:assert cmd=='chip_id' and reset
   return ''
  try:
   result=u.update(root,'fake',root/'backup',runner);assert failure=='none' and result['partition_added'] and result['data_unchanged']
  except (ValueError,RuntimeError,OSError):
   assert failure!='none';assert not any(reset for _,reset in calls)
  writes=[args for args,_ in calls if args[0]=='write_flash']
  assert len(writes)==(2 if failure in ('none','write-table','verify-table','readback-data') else 0)
  if failure!='readback-data':assert bytes(memory[0x380000])==original[0x380000]
  assert bytes(memory[0x8000][0x1000:])==original[0x8000][0x1000:]
  assert bytes(memory[0x350000])==original[0x350000]
print('additive V23 partition migration, exact old addresses/data, durable backup, v2 pending journal and no-reset failure paths: passed')
