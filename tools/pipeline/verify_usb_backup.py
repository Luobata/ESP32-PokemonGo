#!/usr/bin/env python3
"""Protocol, browser decoder, restore safety and checkpoint regression; no device writes."""
from pathlib import Path
import importlib.util
import json
import shutil
import subprocess
import tempfile
import struct
ROOT=Path(__file__).resolve().parents[2]
C=r'''
#include "usb_backup.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static char transcript[70000];static int reads;static bool readable=true;
static void emit(const char *s){assert(strlen(transcript)+strlen(s)<sizeof(transcript));strcat(transcript,s);}
static bool snapshot(uint8_t *out,size_t size){reads++;for(unsigned i=0;i<size;i++)out[i]=i;return readable;}
static void feed(const char *s){while(*s)assert(usb_backup_feed(*s++));}
static void init(void){transcript[0]=0;reads=0;readable=true;usb_backup_init(snapshot,emit,"001122334455","1111111111111111111111111111111111111111111111111111111111111111",15);}
static const char *hello="!PWBACKUP HELLO 0123456789abcdef0123456789abcdef\n";
int main(void){
 init();usb_backup_request();assert(usb_backup_state()==USB_BACKUP_NO_HOST&&reads==0);
 assert(!usb_backup_feed('a'));feed("!bad acg\n");assert(reads==0);
 char huge[301];memset(huge,'a',sizeof(huge));huge[0]='!';huge[299]='\n';huge[300]=0;feed(huge);assert(!usb_backup_feed('b'));
 feed(hello);assert(strstr(transcript,"READY"));assert(reads==0); // host cannot start a backup
 usb_backup_tick(16000);usb_backup_request();assert(reads==0);
 feed(hello);readable=false;usb_backup_request();assert(usb_backup_state()==USB_BACKUP_FAILED);
 readable=true;usb_backup_request();assert(usb_backup_state()==USB_BACKUP_SENDING);
 feed("!PWBACKUP ACK 0123456789abcdef0123456789abcdef 1\n");assert(usb_backup_state()==USB_BACKUP_SENDING);
 usb_backup_tick(32000);assert(usb_backup_state()==USB_BACKUP_FAILED); // disconnected host
 init();feed(hello);usb_backup_request();usb_backup_request();assert(reads==1);
 for(unsigned i=0;i<192;i++)usb_backup_tick(i);
 assert(usb_backup_state()==USB_BACKUP_WAIT_ACK);
 feed("!PWBACKUP ACK ffffffffffffffffffffffffffffffff 1\n");assert(usb_backup_state()==USB_BACKUP_WAIT_ACK);
 feed("!PWBACKUP ACK 0123456789abcdef0123456789abcdef 2\n");assert(usb_backup_state()==USB_BACKUP_WAIT_ACK);
 feed("!PWBACKUP ACK 0123456789abcdef0123456789abcdef 1\n");assert(usb_backup_state()==USB_BACKUP_DONE);
 puts(transcript);
 usb_backup_request();assert(usb_backup_state()==USB_BACKUP_SENDING);
 feed("!PWBACKUP BYE 0123456789abcdef0123456789abcdef\n");assert(usb_backup_state()==USB_BACKUP_FAILED);
 init();feed(hello);usb_backup_request();for(unsigned i=0;i<192;i++)usb_backup_tick(i);
 usb_backup_tick(61000);assert(usb_backup_state()==USB_BACKUP_FAILED); // no disk ACK
 return 0;
}
'''
JS=r'''
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
const {Receiver,envelope,crc32}=await import(process.argv[2]);
const lines=readFileSync(process.argv[3],'utf8').split('\n');
function replay(xs){const r=new Receiver('0123456789abcdef0123456789abcdef');let last;for(const x of xs){let v=r.accept(x);if(v?.complete)last=v.complete;}return last;}
const q=replay(lines);assert(q);assert.equal(q.bytes.length,24576);assert.equal(q.bytes[2049],1);
const file=await envelope(q,webcrypto);assert.equal(file.save_version,15);assert.equal(file.sha256.length,64);
assert.equal(crc32(new TextEncoder().encode('123456789')),'cbf43926');
const data=lines.findIndex(x=>x.startsWith('!PWBACKUP DATA'));
assert.throws(()=>replay(lines.filter((_,i)=>i!==data)));
const dup=[...lines];dup.splice(data,0,lines[data]);assert.throws(()=>replay(dup));
const corrupt=[...lines];corrupt[data]=corrupt[data].slice(0,-2)+'ff';assert.throws(()=>replay(corrupt));
const truncated=lines.filter(x=>!x.startsWith('!PWBACKUP END'));assert.equal(replay(truncated),undefined);
assert.equal(new Receiver('0'.repeat(32)).accept('!PWBACKUP READY '+'f'.repeat(32)+' 001122334455'),null);
console.log(JSON.stringify(file));
'''
def main():
    spec=importlib.util.spec_from_file_location('restore',ROOT/'tools/save-manager/restore.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    with tempfile.TemporaryDirectory() as tmp:
        t=Path(tmp);(t/'test.c').write_text(C);(t/'test.mjs').write_text(JS)
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'firmware/main'),str(t/'test.c'),str(ROOT/'firmware/main/usb_backup.c'),str(ROOT/'firmware/main/restore_journal.c'),'-o',str(t/'test')],check=True)
        result=subprocess.run([str(t/'test')],capture_output=True,text=True,check=True);(t/'wire.txt').write_text(result.stdout)
        result=subprocess.run(['node',str(t/'test.mjs'),(ROOT/'tools/save-manager/web/backup.mjs').as_uri(),str(t/'wire.txt')],capture_output=True,text=True,check=True)
        f=t/'test.pksave';f.write_text(result.stdout);meta,raw=m.decode(f);assert len(raw)==24576
        header=struct.pack('<IIII32s',0x31525750,24576,0,0,b'\x11'*32)
        import zlib
        assert m.journal_pending(header+struct.pack('<I',zlib.crc32(header)))
        assert not m.journal_pending(b'\xff'*4096)
        calls=[];flash=bytearray(b'\xaa'*24576)
        def fake(*args,**opts):
            calls.append(args)
            if args[0]=='read_mac':return 'MAC: 00:11:22:33:44:55'
            if args[0]=='read_flash':
                if args[1]=='0x8000':data=struct.pack('<HBBII16sI',0x50aa,1,2,0x9000,24576,b'nvs',0)+b'\xff'*32
                elif args[1]=='0x10000':
                    data=bytearray(256);data[0]=0xe9;struct.pack_into('<I',data,32,0xabcd5432);data[48:58]=b'test-build';data[80:88]=b'PokeWalk';data[176:208]=b'\x11'*32
                else:data=flash
                Path(args[3]).write_bytes(data)
            elif args[0]=='write_flash':flash[:]=Path(args[2]).read_bytes()
            return ''
        try:m.restore(f,'fake','bad',t/'backups',fake);raise AssertionError('confirmation bypass')
        except ValueError:pass
        assert not calls
        result=m.restore(f,'fake',meta['device_id'],t/'backups',fake);assert result['verified'] and bytes(flash)==raw
        _,old=m.decode(result['previous_backup']);assert old==b'\xaa'*24576
        assert [c for c in calls if c[0]=='write_flash'][0][1]=='0x9000'
        calls.clear()
        def wrong(*args,**opts):calls.append(args);return 'MAC: 00:11:22:33:44:56'
        try:m.restore(f,'fake',meta['device_id'],t/'backups',wrong);raise AssertionError('wrong device')
        except ValueError:pass
        assert not any(c[0]=='write_flash' for c in calls)
        for key,value in [('sha256','0'*64),('save_version',99),('nvs_offset',0),('nvs_size',1),('payload_base64','garbage')]:
            bad=dict(meta);bad[key]=value;f.write_text(json.dumps(bad))
            try:m.decode(f);raise AssertionError(key)
            except (ValueError,KeyError):pass
    print(json.dumps({'passed':True,'device_protocol':'ASan/UBSan','browser':'real C transcript, missing/duplicate/corrupt/truncated frames','restore':'confirmation, device, metadata, checksum, prebackup and NVS-only roundtrip'}))
if __name__=='__main__':main()
