#!/usr/bin/env python3
"""V23 actual USB parser: bounded 48 KiB stream, v1 migration, ACK/failure paths."""
from pathlib import Path
import subprocess,tempfile
ROOT=Path(__file__).resolve().parents[2]
C=r'''
#include "usb_backup.h"
#include "restore_journal.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned char old[USB_BACKUP_WAREHOUSE_BYTES],incoming[USB_BACKUP_WAREHOUSE_BYTES],received[USB_BACKUP_WAREHOUSE_BYTES];
static unsigned nbytes,version,begins,finishes,cancels,restarts,reads;static int fault;
static char output[240000];
static void emit(const char *line){assert(strlen(output)+strlen(line)<sizeof(output));strcat(output,line);}
static bool begin_export(uint32_t *size,uint32_t *crc){*size=sizeof(old);*crc=restore_crc32(old,sizeof(old));return fault!=1;}
static bool read_export(uint32_t at,void *out,size_t n){assert(n==128&&at+n<=sizeof(old));reads++;memcpy(out,old+at,n);return fault!=2;}
static bool begin_import(uint32_t n,unsigned v){begins++;assert(n==nbytes&&v==version);if(fault==3){usb_backup_restore_detail(USB_RESTORE_DETAIL_LAYOUT);return false;}memset(received,0,sizeof(received));return true;}
static bool write_import(uint32_t at,const void *data,size_t n){assert(n==128&&at+n<=nbytes);if(fault==4)return false;memcpy(received+at,data,n);return true;}
static bool finish(uint32_t crc){assert(crc==restore_crc32(incoming,nbytes)&&!memcmp(incoming,received,nbytes));if(fault==5){usb_backup_restore_detail(USB_RESTORE_DETAIL_CONTENT);return false;}finishes++;return true;}
static void cancel(void){cancels++;}
static void restart(void){restarts++;}
static const usb_backup_stream_t streams={begin_export,read_export,begin_import,write_import,finish,cancel};
static const char *token="0123456789abcdef0123456789abcdef";
static void feed(const char *p){while(*p)assert(usb_backup_feed(*p++));}
static void command(const char *word){char line[100];snprintf(line,sizeof(line),"!PWBACKUP %s %s\n",word,token);feed(line);}
static void start(unsigned v,int f){usb_backup_init(NULL,emit,"001122334455","1111111111111111111111111111111111111111111111111111111111111111",29);usb_backup_stream_hooks(&streams);usb_backup_restore_hooks(NULL,restart,0,0);output[0]=0;begins=finishes=cancels=restarts=reads=0;fault=f;version=v;nbytes=v<23?USB_BACKUP_BYTES:v==23?USB_BACKUP_EXTENDED_BYTES:v<=27?USB_BACKUP_EXPANDED_BYTES:USB_BACKUP_WAREHOUSE_BYTES;command("HELLO");usb_backup_import_mode(true);}
static void offer(unsigned v,unsigned n){char line[260];snprintf(line,sizeof(line),"!PWBACKUP OFFER %s 001122334455 %064d %u %u %08x\n",token,0,v,n,restore_crc32(incoming,nbytes));feed(line);}
static void ack(void){feed("!PWBACKUP ACK 0123456789abcdef0123456789abcdef 1\n");}
static void upload(bool corrupt){char line[400];for(unsigned at=0;at<nbytes&&usb_backup_state()==USB_RESTORE_RECEIVING;at+=128){int len=snprintf(line,sizeof(line),"!PWBACKUP RDATA %s 1 %u ",token,at);for(unsigned i=0;i<128;i++)len+=snprintf(line+len,sizeof(line)-len,"%02x",incoming[at+i]^(corrupt&&at==0&&i==0));strcpy(line+len,"\n");feed(line);}feed("!PWBACKUP RFIN 0123456789abcdef0123456789abcdef 1\n");}
static void accept(void){offer(version,nbytes);assert(usb_backup_state()==USB_RESTORE_OFFER&&!begins);usb_backup_restore_confirm(true);for(unsigned i=0;i<576;i++)usb_backup_tick(i*20);}
int main(void){
 for(unsigned i=0;i<sizeof(old);i++){old[i]=(i*13)&255;incoming[i]=(i*7+3)&255;}
 for(unsigned v=5;v<=29;v++){
  start(v,0);accept();assert(reads==576&&usb_backup_state()==USB_BACKUP_WAIT_ACK&&!begins);assert(strstr(output," 73728 "));upload(false);assert(!finishes&&!begins);ack();assert(begins==1);upload(false);assert(finishes==1&&usb_backup_state()==USB_RESTORE_STAGED);command("BYE");usb_backup_tick(13000);assert(restarts==1&&cancels==1);
 }
 for(int f=1;f<=5;f++){
  start(23,f);accept();if(f>2)ack();if(f>3)upload(false);assert(usb_backup_state()==USB_BACKUP_FAILED&&cancels&&!finishes&&!restarts);
  assert(strstr(output,f<3?"SNAPSHOT":f==3?"STAGE LAYOUT":f==4?"STAGE FLASH":"STAGE CONTENT"));
 }
 start(23,0);accept();ack();upload(true);assert(!finishes&&cancels&&strstr(output,"CHECKSUM"));
 start(23,0);accept();ack();command("BYE");assert(cancels&&!finishes);
 start(23,0);accept();ack();usb_backup_tick(16000);assert(cancels&&!finishes&&strstr(output,"TIMEOUT"));
 start(23,0);accept();ack();feed("!PWBACKUP RDATA 0123456789abcdef0123456789abcdef 1 128 00\n");assert(cancels&&!finishes&&strstr(output,"SEQUENCE"));
 start(23,0);offer(23,24576);assert(strstr(output,"INCOMPATIBLE")&&!begins);
 start(22,0);offer(22,49152);assert(strstr(output,"INCOMPATIBLE")&&!begins);
 start(23,0);offer(24,49152);assert(strstr(output,"INCOMPATIBLE")&&!begins);
 start(24,0);offer(28,57344);assert(strstr(output,"INCOMPATIBLE")&&!begins);
 puts("V5–29 stream, 576 export chunks, 72 KiB import, disk ACK, CRC, cancellation, version/length and I/O failures: passed");
}
'''
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder);(p/'test.c').write_text(C)
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(ROOT/'firmware/main'),str(p/'test.c'),str(ROOT/'firmware/main/usb_backup.c'),str(ROOT/'firmware/main/restore_journal.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
