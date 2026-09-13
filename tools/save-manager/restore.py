#!/usr/bin/env python3
"""Developer-only, same-device/same-firmware restore. Never erases whole flash."""
import argparse
import base64
import datetime as dt
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

SIZE, ADDRESS = 0x6000, 0x9000

def decode(path):
    path=Path(path)
    if path.stat().st_size>45000: raise ValueError('备份文件过大')
    d=json.loads(path.read_text())
    if any(d.get(k)!=v for k,v in {'format':'pokewalk-nvs-backup','format_version':1,'chip':'esp32c3','save_version':15,'nvs_offset':ADDRESS,'nvs_size':SIZE}.items()):
        raise ValueError('备份格式、存档版本或分区不支持')
    if not re.fullmatch('[a-f0-9]{12}',d.get('device_id','')): raise ValueError('设备标识无效')
    if not re.fullmatch('[a-f0-9]{64}',d.get('firmware','')): raise ValueError('固件版本无效')
    raw=base64.b64decode(d['payload_base64'],validate=True)
    if len(raw)!=SIZE or hashlib.sha256(raw).hexdigest()!=d.get('sha256') or f'{zlib.crc32(raw):08x}'!=d.get('crc32'):
        raise ValueError('备份长度或校验值不符，禁止恢复')
    return d,raw

def envelope(raw,device,firmware):
    return {'format':'pokewalk-nvs-backup','format_version':1,'created_at':dt.datetime.now(dt.timezone.utc).isoformat(),
            'chip':'esp32c3','device_id':device,'firmware':firmware,'save_version':15,
            'nvs_offset':ADDRESS,'nvs_size':SIZE,'crc32':f'{zlib.crc32(raw):08x}',
            'sha256':hashlib.sha256(raw).hexdigest(),'payload_base64':base64.b64encode(raw).decode()}

def write_private(directory,data):
    directory=Path(directory);directory.mkdir(mode=0o700,parents=True,exist_ok=True)
    path=directory/f'PokeWalk-before-restore-{uuid.uuid4().hex}.pksave'
    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w') as f:
        json.dump(data,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    decode(path)
    return path

def partition_valid(raw):
    # Check the actual connected layout, not an assumption from a repository.
    for i in range(0,len(raw)-31,32):
        magic,typ,sub,address,size,label,_=struct.unpack_from('<HBBII16sI',raw,i)
        if magic==0xffff:break
        if magic==0x50aa and label.rstrip(b'\0')==b'nvs':return typ==1 and sub==2 and address==ADDRESS and size==SIZE
    return False

def staging_address(raw):
    for i in range(0,len(raw)-31,32):
        magic,typ,sub,address,size,label,_=struct.unpack_from('<HBBII16sI',raw,i)
        if magic==0xffff:break
        if magic==0x50aa and label.rstrip(b'\0')==b'save_restore':
            if (typ,sub,address,size)!=(1,0x40,0x360000,0x10000):raise ValueError('恢复暂存分区布局不支持')
            return address
    return None

def journal_pending(raw):
    return len(raw)>=52 and struct.unpack_from('<II',raw)==(0x31525750,SIZE) and struct.unpack_from('<I',raw,48)[0]==zlib.crc32(raw[:48])

def app_identity(raw):
    if len(raw)<208 or raw[0]!=0xe9 or struct.unpack_from('<I',raw,32)[0]!=0xabcd5432:raise ValueError('不是可识别的 PokeWalk 应用')
    version=raw[48:80].split(b'\0')[0].decode('ascii')
    name=raw[80:112].split(b'\0')[0].decode('ascii')
    if name!='PokeWalk':raise ValueError('设备当前不是 PokeWalk，请先烧录对应游戏版本')
    return raw[176:208].hex()

def restore(path,port,confirm,backup_dir,runner=None):
    meta,payload=decode(path)
    if confirm!=meta['device_id']:raise ValueError('需要 --confirm-device 与备份中的完整设备标识一致')
    # esptool 4.x is provided by this project's ESP-IDF environment.
    def run(*args,first=False,reset=False):
        if runner:return runner(*args,first=first,reset=reset)
        cmd=[sys.executable,'-m','esptool','--chip','esp32c3','--port',port,'--before','default_reset' if first else 'no_reset','--after','hard_reset' if reset else 'no_reset',*map(str,args)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
        if p.returncode:raise RuntimeError('设备读写失败；当前未确认恢复完成。请保持连接检查设备。')
        return p.stdout
    with tempfile.TemporaryDirectory(prefix='pokewalk-restore-') as tmp:
        tmp=Path(tmp)
        mac=run('read_mac',first=True)
        ids=re.findall(r'(?i)MAC:\s*([0-9a-f:]{17})',mac)
        if not ids or ids[-1].replace(':','').lower()!=meta['device_id']:raise ValueError('连接的不是备份所属设备，禁止恢复')
        run('read_flash','0x8000','0xc00',tmp/'partitions.bin')
        partitions=(tmp/'partitions.bin').read_bytes()
        if not partition_valid(partitions):raise ValueError('连接设备的 NVS 分区与备份不兼容')
        stage=staging_address(partitions)
        if stage is not None:
            run('read_flash',hex(stage),'0x1000',tmp/'journal.bin')
            if journal_pending((tmp/'journal.bin').read_bytes()):raise ValueError('设备有尚未完成的网页导入；请先用原固件完成恢复，不可直接覆盖 NVS')
        run('read_flash','0x10000','0x100',tmp/'app.bin')
        firmware=app_identity((tmp/'app.bin').read_bytes())
        if firmware!=meta['firmware']:raise ValueError('开发版恢复要求相同固件版本；请先烧录备份对应版本')
        run('read_flash',hex(ADDRESS),hex(SIZE),tmp/'before.bin')
        before=(tmp/'before.bin').read_bytes()
        if len(before)!=SIZE:raise ValueError('当前存档备份不完整，禁止恢复')
        safe=write_private(backup_dir,envelope(before,meta['device_id'],firmware))
        print('当前存档已备份：',safe)
        (tmp/'restore.bin').write_bytes(payload)
        try:
            run('write_flash',hex(ADDRESS),tmp/'restore.bin')
            run('read_flash',hex(ADDRESS),hex(SIZE),tmp/'after.bin')
            if (tmp/'after.bin').read_bytes()!=payload:raise RuntimeError('恢复回读校验失败')
        except Exception as e:
            raise RuntimeError(f'恢复未完成，请勿继续游戏。可用预恢复备份重试：{safe}') from e
        run('chip_id',reset=True)
        return {'restored':True,'verified':True,'previous_backup':str(safe)}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('file',type=Path);p.add_argument('--restore',action='store_true');p.add_argument('--port');p.add_argument('--confirm-device');p.add_argument('--backup-dir',type=Path,default=Path.home()/'PokeWalk Backups')
    a=p.parse_args()
    try:
        d,_=decode(a.file)
        if not a.restore:print(json.dumps({k:v for k,v in d.items() if k!='payload_base64'},ensure_ascii=False,indent=2));return
        if not a.port:p.error('恢复必须显式指定 --port；先关闭浏览器串口连接')
        print(json.dumps(restore(a.file,a.port,a.confirm_device,a.backup_dir),ensure_ascii=False))
    except Exception as e:raise SystemExit(str(e))
if __name__=='__main__':main()
