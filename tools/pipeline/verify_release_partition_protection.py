#!/usr/bin/env python3
"""Reject partition migrations that overwrite player data, even with valid MD5."""
import hashlib,importlib.util,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('pw_partition_check',ROOT/'tools/release/verify_firmware.py');m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
build=ROOT/'release/community';merged=(build/'FoloToy-AI-Passport-full.bin').read_bytes()
m.verify_protected_layout(merged,build)
parts,_=m.parse_partition_table(merged[0x8000:0x8c00]);negative=[]
for name in ['nvs','cardid','save_restore','wifi_config','recovery','factory']:
 copy=bytearray(merged);table=bytearray()
 for p in parts:
  offset=p.offset+(0x1000 if p.label==name else 0)
  table+=m.ENTRY.pack(0x50aa,p.kind,p.subtype,offset,p.size,p.label.encode().ljust(16,b'\0'),0)
 table+=b'\xeb\xeb'+b'\xff'*14+hashlib.md5(table).digest()
 copy[0x8000:0x8c00]=table.ljust(0xc00,b'\xff')
 try:m.verify_protected_layout(bytes(copy),build)
 except ValueError:negative.append(name)
 else:raise AssertionError('accepted moved '+name)
assert len(negative)==6
print(json.dumps({'protected_partitions':negative,'valid_md5_moves_rejected':True,'factory_bytes':m.APP_MAX_SIZE}))
