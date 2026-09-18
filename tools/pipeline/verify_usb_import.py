#!/usr/bin/env python3
"""Fault-injected restore journal and physical-consent USB import tests."""
from pathlib import Path
import subprocess,tempfile,json
ROOT=Path(__file__).resolve().parents[2]
C=r'''
#include "restore_journal.h"
#include "usb_backup.h"
#include "save.h"
#include <assert.h>
#include <setjmp.h>
#include <stdio.h>
#include <string.h>
static unsigned char stage[RESTORE_STAGE_SIZE],nvs[RESTORE_IMAGE_SIZE],original[RESTORE_IMAGE_SIZE],incoming[RESTORE_IMAGE_SIZE],build[32];
static int calls,cut,failwrite;static jmp_buf power;
static void step(void){if(++calls==cut)longjmp(power,1);}
static bool rd(bool s,uint32_t at,void *p,size_t n){step();assert(at+n<=(s?sizeof(stage):sizeof(nvs)));memcpy(p,(s?stage:nvs)+at,n);return true;}
static bool wr(bool s,uint32_t at,const void *p,size_t n){if(++calls==cut){memcpy((s?stage:nvs)+at,p,n/2);longjmp(power,1);}assert(at+n<=(s?sizeof(stage):sizeof(nvs)));if(!s&&failwrite){failwrite=0;return false;}memcpy((s?stage:nvs)+at,p,n);return true;}
static bool er(bool s,uint32_t at,size_t n){if(++calls==cut){memset((s?stage:nvs)+at,255,n/2);longjmp(power,1);}assert(at+n<=(s?sizeof(stage):sizeof(nvs)));memset((s?stage:nvs)+at,255,n);return true;}
static restore_io_t io={rd,wr,er};
static void reset(void){memset(stage,255,sizeof(stage));memcpy(nvs,original,sizeof(nvs));calls=cut=failwrite=0;}
static unsigned test_schema=SAVE_VERSION;
static char transcript[80000];static int snapshots,staged,restarts;
static void emit(const char *s){assert(strlen(transcript)+strlen(s)<sizeof(transcript));strcat(transcript,s);}
static bool snapshot(uint8_t *out,size_t n){assert(n==sizeof(original));memcpy(out,original,n);snapshots++;return true;}
static bool prepare(const uint8_t *p,size_t n){assert(n==sizeof(incoming));assert(!memcmp(p,incoming,n));staged++;return true;}
static void restart(void){restarts++;}
static const char *session="0123456789abcdef0123456789abcdef";
static void feed(const char *s){while(*s)assert(usb_backup_feed(*s++));}
static void cmd(const char *v){char s[400];snprintf(s,sizeof(s),"!PWBACKUP %s %s\n",v,session);feed(s);}
static void init(void){transcript[0]=0;snapshots=staged=restarts=0;usb_backup_init(snapshot,emit,"001122334455","1111111111111111111111111111111111111111111111111111111111111111",test_schema);usb_backup_restore_hooks(prepare,restart,0,0);cmd("HELLO");}
static void offer_for(unsigned version,const char *firmware){char s[300];snprintf(s,sizeof(s),"!PWBACKUP OFFER %s 001122334455 %s %u 24576 %08x\n",session,firmware,version,restore_crc32(incoming,sizeof(incoming)));feed(s);}
static void offer(void){offer_for(test_schema,"1111111111111111111111111111111111111111111111111111111111111111");}
static void upload(bool corrupt){char s[400];for(unsigned at=0;at<sizeof(incoming);at+=128){int n=snprintf(s,sizeof(s),"!PWBACKUP RDATA %s 1 %u ",session,at);for(unsigned i=0;i<128;i++)n+=snprintf(s+n,sizeof(s)-n,"%02x",incoming[at+i]^(corrupt&&at==0&&i==0));strcpy(s+n,"\n");feed(s);}snprintf(s,sizeof(s),"!PWBACKUP RFIN %s 1\n",session);feed(s);}
static void accept(void){usb_backup_import_mode(true);offer();assert(usb_backup_state()==USB_RESTORE_OFFER);assert(snapshots==0);usb_backup_restore_confirm(true);assert(snapshots==1);for(unsigned i=0;i<192;i++)usb_backup_tick(i);assert(usb_backup_state()==USB_BACKUP_WAIT_ACK);}
int main(void){
 for(unsigned i=0;i<sizeof(nvs);i++){original[i]=i;incoming[i]=i*7+3;}memset(build,17,32);uint32_t crc;
 reset();assert(restore_journal_prepare(&io,incoming,build));int prep_calls=calls;assert(!memcmp(nvs,original,sizeof(nvs)));
 unsigned char committed[RESTORE_STAGE_SIZE];memcpy(committed,stage,sizeof(stage));calls=0;
 assert(restore_journal_apply(&io,build,&crc)==1);int apply_calls=calls;assert(crc==restore_crc32(incoming,sizeof(incoming)));assert(!memcmp(nvs,incoming,sizeof(nvs)));assert(restore_journal_apply(&io,build,&crc)==0);
 // Simulate power interruption at every I/O boundary, both before and after commit.
 for(int k=1;k<=prep_calls;k++){reset();cut=k;if(!setjmp(power))restore_journal_prepare(&io,incoming,build);cut=0;assert(!memcmp(nvs,original,sizeof(nvs)));int r=restore_journal_apply(&io,build,&crc);assert(r==0||r==1);assert(!memcmp(nvs,r?incoming:original,sizeof(nvs)));}
 for(int k=1;k<=apply_calls;k++){reset();memcpy(stage,committed,sizeof(stage));cut=k;if(!setjmp(power))restore_journal_apply(&io,build,&crc);cut=0;int r=restore_journal_apply(&io,build,&crc);assert(r==0||r==1);assert(!memcmp(nvs,incoming,sizeof(nvs)));}
 reset();memcpy(stage,committed,sizeof(stage));stage[0x1000]^=1;assert(restore_journal_apply(&io,build,&crc)==2);assert(!memcmp(nvs,original,sizeof(nvs)));
 reset();memcpy(stage,committed,sizeof(stage));failwrite=1;assert(restore_journal_apply(&io,build,&crc)==2);assert(!memcmp(nvs,original,sizeof(nvs)));
 reset();memcpy(stage,committed,sizeof(stage));unsigned char other[32]={0};assert(restore_journal_apply(&io,other,&crc)==-1);assert(!memcmp(nvs,original,sizeof(nvs)));
 reset();memcpy(stage,committed,sizeof(stage));stage[0x1000]^=1;stage[0x7000]^=1;assert(restore_journal_apply(&io,build,&crc)==-1);assert(!memcmp(nvs,original,sizeof(nvs)));
 init();usb_backup_import_mode(true);
 offer_for(test_schema+1,"1111111111111111111111111111111111111111111111111111111111111111");assert(strstr(transcript,"INCOMPATIBLE")&&!snapshots&&!staged&&usb_backup_state()==USB_BACKUP_IDLE);
 transcript[0]=0;offer_for(test_schema,"2222222222222222222222222222222222222222222222222222222222222222");assert(strstr(transcript,"INCOMPATIBLE")&&!snapshots&&!staged&&usb_backup_state()==USB_BACKUP_IDLE);
 init();offer();assert(strstr(transcript,"OPEN_IMPORT"));assert(!snapshots);usb_backup_import_mode(true);offer();usb_backup_restore_confirm(false);assert(usb_backup_state()==USB_BACKUP_IDLE);assert(!snapshots&&!staged);assert(strstr(transcript,"CANCELLED"));
 init();accept();upload(false);assert(!staged); // no disk ACK, no incoming accepted
 feed("!PWBACKUP ACK ffffffffffffffffffffffffffffffff 1\n");assert(usb_backup_state()==USB_BACKUP_WAIT_ACK);
 feed("!PWBACKUP ACK 0123456789abcdef0123456789abcdef 1\n");assert(usb_backup_state()==USB_RESTORE_RECEIVING);upload(false);assert(staged==1&&usb_backup_state()==USB_RESTORE_STAGED);cmd("BYE");usb_backup_tick(1300);assert(restarts==1);puts(transcript);
 init();accept();feed("!PWBACKUP ACK 0123456789abcdef0123456789abcdef 1\n");upload(true);assert(!staged&&usb_backup_state()==USB_BACKUP_FAILED);
 init();accept();feed("!PWBACKUP ACK 0123456789abcdef0123456789abcdef 1\n");feed("!PWBACKUP RFIN 0123456789abcdef0123456789abcdef 1\n");assert(!staged&&usb_backup_state()==USB_BACKUP_FAILED);
 init();accept();usb_backup_tick(16000);assert(!staged&&usb_backup_state()==USB_BACKUP_FAILED);
 const unsigned future_versions[]={18,99,65535};
 for(unsigned i=0;i<3;i++){
  test_schema=future_versions[i];init();accept();
  feed("!PWBACKUP ACK 0123456789abcdef0123456789abcdef 1\n");
  upload(false);assert(staged==1&&usb_backup_state()==USB_RESTORE_STAGED);
 }
 fprintf(stderr,"journal interruption boundaries: %d prepare, %d apply\n",prep_calls,apply_calls);
 return 0;
}
'''
JS=r'''
import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {webcrypto} from 'node:crypto';
const {Receiver,envelope,decodeBackup}=await import(process.argv[2]);
const r=new Receiver('0123456789abcdef0123456789abcdef');let file,next=0,staged=false;
for(const line of readFileSync(process.argv[3],'utf8').split('\n')){const x=r.accept(line);if(x?.complete)file=await envelope(x.complete,webcrypto);if(x?.next){next+=128;assert.equal(x.next.offset,next);}if(x?.staged)staged=true;}
assert.equal(next,24576);assert(staged);const decoded=await decodeBackup(JSON.stringify(file),webcrypto);assert.equal(decoded.bytes.length,24576);
for(const [key,value] of [['sha256','0'.repeat(64)],['crc32','0'.repeat(8)],['save_version',65536],['firmware','dirty'],['nvs_offset',0],['format_version',2],['nvs_size',32768],['payload_base64','YQ==']])await assert.rejects(()=>decodeBackup(JSON.stringify({...file,[key]:value}),webcrypto));
assert.equal(r.accept('!PWBACKUP RESTORED 0123456789abcdef0123456789abcdef 1 12345678').restored.result,1);
'''
with tempfile.TemporaryDirectory() as d:
 t=Path(d);(t/'test.c').write_text(C);(t/'test.mjs').write_text(JS)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(ROOT/'firmware/main'),str(t/'test.c'),str(ROOT/'firmware/main/usb_backup.c'),str(ROOT/'firmware/main/restore_journal.c'),'-o',str(t/'test')],check=True)
 p=subprocess.run([str(t/'test')],text=True,capture_output=True,check=True);(t/'wire').write_text(p.stdout);print(p.stderr.strip())
 subprocess.run(['node',str(t/'test.mjs'),(ROOT/'tools/save-manager/web/backup.mjs').as_uri(),str(t/'wire')],check=True)
print(json.dumps({'passed':True,'journal':'power interruption at every I/O boundary, corrupted image, write failure rollback, incompatible build','protocol':'physical consent, cancel, prebackup ACK, CRC, truncation, timeout, staged reboot','browser':'production decoder with real C transcript and corrupt files'}))
