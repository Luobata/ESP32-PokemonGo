#!/usr/bin/env python3
"""Device import staging boundaries with flash/NVS adapters mocked, no hardware writes.

Actual decoding/migration is covered by verify_save_import_compatibility.py;
actual journal power interruptions are covered by verify_usb_import.py.
"""
from pathlib import Path
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
HEADER=r'''
#pragma once
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
typedef int esp_err_t;typedef unsigned nvs_handle_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NO_MEM 0x101
#define ESP_ERR_NVS_NOT_FOUND 0x1102
#define NVS_READONLY 0
#define ESP_PARTITION_TYPE_DATA 1
#define ESP_PARTITION_SUBTYPE_DATA_NVS 2
#define ESP_MAC_WIFI_STA 0
#define ESP_LOGE(...) do {} while (0)
const char *esp_err_to_name(esp_err_t);
typedef struct {unsigned type,subtype,address,size;char label[17];} esp_partition_t;
typedef struct {uint8_t app_elf_sha256[32];} esp_app_desc_t;
const esp_partition_t *esp_partition_find_first(unsigned,unsigned,const char*);
esp_err_t esp_partition_read(const esp_partition_t*,uint32_t,void*,size_t);
esp_err_t esp_partition_write(const esp_partition_t*,uint32_t,const void*,size_t);
esp_err_t esp_partition_erase_range(const esp_partition_t*,uint32_t,size_t);
const esp_app_desc_t *esp_app_get_description(void);
esp_err_t esp_read_mac(uint8_t*,unsigned);void esp_restart(void);
esp_err_t nvs_flash_init_partition_ptr(const esp_partition_t*);
esp_err_t nvs_flash_deinit_partition(const char*);
esp_err_t nvs_open_from_partition(const char*,const char*,unsigned,nvs_handle_t*);
esp_err_t nvs_get_blob(nvs_handle_t,const char*,void*,size_t*);
esp_err_t nvs_get_u8(nvs_handle_t,const char*,uint8_t*);
esp_err_t nvs_open(const char*,int,nvs_handle_t*);
void nvs_close(nvs_handle_t);
'''
C=r'''

#include <stdlib.h>
#include <assert.h>
static unsigned import_allocations;
static void *denied_import_malloc(size_t n){(void)n;import_allocations++;return NULL;}
#define malloc denied_import_malloc
#include "usb_backup_device.c"
#undef malloc
static esp_partition_t live={1,2,0x9000,USB_BACKUP_BYTES,"nvs"};
static esp_partition_t temp={1,0x40,0x360000,RESTORE_STAGE_SIZE,"save_restore"};
static esp_app_desc_t app={{0x12,0x34}};
static uint8_t flash[RESTORE_STAGE_SIZE],image[USB_BACKUP_BYTES],live_data[USB_BACKUP_BYTES];
static uint8_t banks[SAVE_BANK_PARTITION_SIZE],payload[sizeof(save_t)];
static save_bank_ref_t ref;
static size_t blob_len;static unsigned failure,journals,checkpoints,decoded,validated,mounts,unmounts;
static bool mounted,game_loaded=true,reservation;
static int reported;
static usb_restore_detail_t detail;
void usb_backup_restore_detail(usb_restore_detail_t d){detail=d;}
const char *esp_err_to_name(esp_err_t e){(void)e;return "test";}
bool world_save_loaded(void){return game_loaded;}
const esp_partition_t *esp_partition_find_first(unsigned typ,unsigned sub,const char *label){assert(typ==1);if(!strcmp(label,"nvs")){assert(sub==2);return &live;}assert(sub==0x40&&!strcmp(label,"save_restore"));return &temp;}
const esp_app_desc_t *esp_app_get_description(void){return &app;}
esp_err_t esp_read_mac(uint8_t *out,unsigned kind){assert(kind==0);memset(out,0,6);return 0;}
void esp_restart(void){}
esp_err_t esp_partition_read(const esp_partition_t *p,uint32_t at,void *out,size_t n){assert(at+n<=p->size);memcpy(out,(p==&live?live_data:flash)+at,n);return 0;}
esp_err_t esp_partition_write(const esp_partition_t *p,uint32_t at,const void *in,size_t n){assert(p==&temp&&at+n<=sizeof(flash));if(failure==2)return -1;memcpy(flash+at,in,n);return 0;}
esp_err_t esp_partition_erase_range(const esp_partition_t *p,uint32_t at,size_t n){assert(p==&temp&&!mounted&&at+n<=sizeof(flash));if(failure==1)return -1;memset(flash+at,255,n);return 0;}
static bool br(uint32_t at,void *out,size_t n){assert(at+n<=sizeof(banks));memcpy(out,banks+at,n);return true;}
static bool bw(uint32_t at,const void *in,size_t n){assert(at+n<=sizeof(banks));memcpy(banks+at,in,n);return failure!=12;}
static bool be(uint32_t at,size_t n){assert(at+n<=sizeof(banks));memset(banks+at,255,n);return true;}
const save_bank_io_t *save_bank_platform(void){static const save_bank_io_t store={br,bw,be};return &store;}
void save_bank_reserve(bool value){reservation=value;}
esp_err_t nvs_flash_init_partition_ptr(const esp_partition_t *p){assert(!mounted);assert(p->address==0x361000&&p->size==USB_BACKUP_BYTES&&p->subtype==2&&!strcmp(p->label,"pw_import"));assert(!memcmp(flash+0x1000,image,sizeof(image)));mounts++;if(failure==3)return -1;if(failure==10)return ESP_ERR_NO_MEM;mounted=true;return 0;}
esp_err_t nvs_flash_deinit_partition(const char *label){assert(!strcmp(label,"pw_import")&&mounted);unmounts++;if(failure==9)return -1;mounted=false;return 0;}
esp_err_t nvs_open(const char *ns,int mode,nvs_handle_t *h){assert(!strcmp(ns,"pokewalk")&&mode==NVS_READONLY);*h=1;return 0;}
esp_err_t nvs_open_from_partition(const char *p,const char *ns,unsigned mode,nvs_handle_t *h){assert(mounted&&!strcmp(p,"pw_import")&&!strcmp(ns,"pokewalk")&&mode==0);if(failure==4)return -1;*h=2;return 0;}
esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *out,size_t *len){assert(!strcmp(key,"state"));if(h==1){assert(*len>=sizeof(ref));memcpy(out,&ref,sizeof(ref));*len=sizeof(ref);return 0;}assert(h==2&&mounted);if(failure==5||blob_len>*len)return -1;memcpy(out,flash+0x1000,blob_len);*len=blob_len;return 0;}
esp_err_t nvs_get_u8(nvs_handle_t h,const char *key,uint8_t *out){assert(h==2&&!strcmp(key,"opening"));*out=1;return 0;}
void nvs_close(nvs_handle_t h){assert(h==1||(h==2&&mounted));}
save_read_result_t save_decode(save_t *out,const void *blob,size_t len,uint8_t opening){assert(out==blob&&len==blob_len&&opening==1);decoded++;return failure==6?SAVE_READ_ERROR:out->version==17?SAVE_READ_OK:SAVE_READ_MIGRATED;}
bool save_validate_world(const save_t *out,party_t *party){assert(out&&party);validated++;return failure!=7;}
bool world_backup_validate(world_backup_reader_t reader,void *ctx,unsigned version){
 static save_t saved;static party_t party;size_t n=sizeof(saved);uint8_t opening=0;
 if(!reader(ctx,&saved,&n,&opening)||n<2||n>sizeof(saved)||saved.version!=version)return false;
 save_read_result_t result=save_decode(&saved,&saved,n,opening);
 return (result==SAVE_READ_OK||result==SAVE_READ_MIGRATED)&&save_validate_world(&saved,&party);
}
bool world_backup_snapshot(bool (*reader)(void*),void *arg){checkpoints++;assert(!mounted);return failure!=8&&reader(arg);}
bool world_backup_exclusive(bool(*fn)(void*),void *arg){return fn(arg);}
bool restore_journal_prepare_staged(const restore_io_t *j,const uint8_t build[32],uint32_t crc){assert(j&&!mounted&&reservation);assert(!memcmp(build,app.app_elf_sha256,32));(void)crc;journals++;return failure!=11;}
int restore_journal_apply(const restore_io_t *j,const uint8_t b[32],uint32_t *crc){(void)j;(void)b;(void)crc;return 0;}
void usb_backup_init(bool (*r)(uint8_t*,size_t),void (*e)(const char*),const char *d,const char *f,unsigned v){assert(!r&&e&&d&&f&&v==SAVE_VERSION);}
void usb_backup_restore_hooks(bool (*s)(const uint8_t*,size_t,unsigned),void(*r)(void),int result,uint32_t crc){assert(!s&&r);reported=result;(void)crc;}
void usb_backup_stream_hooks(const usb_backup_stream_t *hooks){assert(hooks==&streams);}
static bool stage_test(unsigned version){
 if(!import_begin(sizeof(image),version))return false;
 for(size_t at=0;at<sizeof(image);at+=128)if(!import_write(at,image+at,128)){detail=USB_RESTORE_DETAIL_FLASH;return false;}
 return import_finish(123);
}
static void reset(void){failure=0;cancel();assert(!mounted);memset(image,0,sizeof(image));image[0]=17;blob_len=sizeof(save_v17_t);journals=checkpoints=decoded=validated=0;detail=USB_RESTORE_DETAIL_NONE;}
int main(void){
 (void)denied_import_malloc;memset(banks,255,sizeof(banks));payload[0]=23;assert(save_bank_prepare(save_bank_platform(),NULL,payload,sizeof(payload),&ref));
 boot_result=1;game_loaded=false;usb_backup_device_start();assert(reported==3);
 game_loaded=true;usb_backup_device_start();assert(reported==1);boot_result=2;usb_backup_device_start();assert(reported==2);
 memset(live_data,0xa5,sizeof(live_data));
 reset();assert(stage_test(17)&&journals==1&&checkpoints==0&&decoded==1&&validated==1&&!mounted&&reservation);
 const usb_restore_detail_t errors[]={USB_RESTORE_DETAIL_NONE,USB_RESTORE_DETAIL_FLASH,USB_RESTORE_DETAIL_FLASH,USB_RESTORE_DETAIL_NVS,USB_RESTORE_DETAIL_READ,USB_RESTORE_DETAIL_READ,USB_RESTORE_DETAIL_CONTENT,USB_RESTORE_DETAIL_CONTENT,USB_RESTORE_DETAIL_NONE,USB_RESTORE_DETAIL_NVS,USB_RESTORE_DETAIL_MEMORY};
 for(unsigned f=1;f<=10;f++){
  reset();failure=f;
  if(f==8){uint32_t size,crc;assert(!export_begin(&size,&crc));continue;}
  assert(!stage_test(17)&&!journals);assert(detail==errors[f]);
  for(unsigned i=0;i<sizeof(live_data);i++)assert(live_data[i]==0xa5);
  cancel();assert(!reservation);
  if(f==9){assert(mounted);failure=0;cancel();assert(!mounted);}
  else assert(!mounted);
 }
 reset();assert(!stage_test(16)&&!decoded&&!journals&&!mounted&&detail==USB_RESTORE_DETAIL_VERSION);
 reset();blob_len=1;assert(!stage_test(17)&&!decoded&&!journals);
 reset();blob_len=sizeof(save_t)+1;assert(!stage_test(17)&&!decoded&&!journals);
 reset();image[0]=16;blob_len=sizeof(save_v16_t);assert(stage_test(16)&&journals==1);
 reset();live.address=0x8000;assert(!stage_test(17)&&!journals&&detail==USB_RESTORE_DETAIL_LAYOUT);live.address=0x9000;
 reset();failure=11;assert(!stage_test(17)&&journals==1&&!mounted&&detail==USB_RESTORE_DETAIL_JOURNAL);
 reset();uint32_t size,crc;assert(export_begin(&size,&crc)&&size==USB_BACKUP_EXTENDED_BYTES&&checkpoints==1);
 uint8_t chunk[128];assert(export_read(0,chunk,sizeof(chunk))&&!memcmp(chunk,live_data,sizeof(chunk)));assert(!export_read(size,chunk,1));
 assert(import_begin(USB_BACKUP_EXTENDED_BYTES,23)&&reservation);failure=12;assert(!import_write(USB_BACKUP_BYTES,chunk,sizeof(chunk)));cancel();assert(!reservation);
 for(unsigned i=0;i<sizeof(live_data);i++)assert(live_data[i]==0xa5);
 assert(mounts&&unmounts&&!import_allocations);puts("stream device import: fixed chunks, zero decoder allocations, flash/NVS/memory/schema/checkpoint/journal errors, cancellation and reservation isolation passed");
}
'''
with tempfile.TemporaryDirectory() as d:
    t=Path(d);(t/'device.h').write_text(HEADER)
    for name in ('esp_partition.h','esp_app_desc.h','esp_mac.h','esp_system.h','esp_log.h','nvs.h','nvs_flash.h'):
        (t/name).write_text('#include "device.h"\n')
    (t/'test.c').write_text(C)
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(t),'-I',str(ROOT/'firmware/main'),str(t/'test.c'),str(ROOT/'firmware/main/save_bank.c'),'-o',str(t/'test')],check=True)
    subprocess.run([str(t/'test')],check=True)
