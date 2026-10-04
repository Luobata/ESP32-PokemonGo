#include "usb_backup.h"
#include "restore_journal.h"
#include "world.h"
#include "save.h"
#include "esp_partition.h"
#include "esp_app_desc.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "esp_log.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nvs.h"
#include "nvs_flash.h"

static const esp_partition_t *nvs_partition,*staging;
static int boot_result;
static uint32_t boot_crc;
static esp_partition_t scratch;
static bool scratch_mounted;
static bool locate(void) {
 nvs_partition=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,ESP_PARTITION_SUBTYPE_DATA_NVS,"nvs");
 staging=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x40,"save_restore");
 return nvs_partition&&nvs_partition->address==0x9000&&nvs_partition->size==USB_BACKUP_BYTES&&
        staging&&staging->address==0x360000&&staging->size==RESTORE_STAGE_SIZE;
}
static bool read_part(bool stage,uint32_t at,void *data,size_t size) {
 const esp_partition_t *p=stage?staging:nvs_partition;return p&&esp_partition_read(p,at,data,size)==ESP_OK;
}
static bool write_part(bool stage,uint32_t at,const void *data,size_t size) {
 const esp_partition_t *p=stage?staging:nvs_partition;return p&&esp_partition_write(p,at,data,size)==ESP_OK;
}
static bool erase_part(bool stage,uint32_t at,size_t size) {
 const esp_partition_t *p=stage?staging:nvs_partition;return p&&esp_partition_erase_range(p,at,size)==ESP_OK;
}
static const restore_io_t io={read_part,write_part,erase_part};
bool usb_backup_restore_before_boot(void) {
 if(!locate())return true; // old partition tables can export, but cannot import
 boot_result=restore_journal_apply(&io,esp_app_get_description()->app_elf_sha256,&boot_crc);
 if(boot_result<0)ESP_LOGE("restore","Restore journal needs recovery; refusing to start game");
 return boot_result>=0;
}
static bool read_nvs(void *out) {return read_part(false,0,out,USB_BACKUP_BYTES);}
static bool snapshot(uint8_t *out,size_t size) {return size==USB_BACKUP_BYTES&&world_backup_snapshot(read_nvs,out);}
static bool prepare(void *image) {return restore_journal_prepare(&io,image,esp_app_get_description()->app_elf_sha256);}
static bool validate_image(const uint8_t *image, unsigned version) {
 // The journal has already been resolved before game startup. Leave its commit
 // sector erased while checking a separate NVS instance, never the live save.
 if(scratch_mounted){
  if(nvs_flash_deinit_partition(scratch.label)!=ESP_OK)return false;
  scratch_mounted=false;
 }
 if(!erase_part(true,0,RESTORE_STAGE_SIZE)||!write_part(true,0x1000,image,USB_BACKUP_BYTES))return false;
 scratch=*staging;
 scratch.address+=0x1000;scratch.size=USB_BACKUP_BYTES;
 scratch.subtype=ESP_PARTITION_SUBTYPE_DATA_NVS;
 snprintf(scratch.label,sizeof(scratch.label),"pw_import");
 if(nvs_flash_init_partition_ptr(&scratch)!=ESP_OK)return false;
 scratch_mounted=true;
 save_t *saved=malloc(sizeof(*saved));party_t *party=malloc(sizeof(*party));
 bool valid=false;nvs_handle_t h;
 if(saved&&party&&nvs_open_from_partition(scratch.label,"pokewalk",NVS_READONLY,&h)==ESP_OK){
  size_t len=sizeof(*saved);uint8_t opening=0;
  esp_err_t e=nvs_get_blob(h,"state",saved,&len);
  (void)nvs_get_u8(h,"opening",&opening);nvs_close(h);
  if(e==ESP_OK&&len>=sizeof(saved->version)&&saved->version==version){
   save_read_result_t result=save_decode(saved,saved,len,opening);
   valid=(result==SAVE_READ_OK||result==SAVE_READ_MIGRATED)&&save_validate_world(saved,party);
  }
 }
 free(party);free(saved);
 if(nvs_flash_deinit_partition(scratch.label)!=ESP_OK)valid=false;
 else scratch_mounted=false;
 return valid;
}
static bool stage(const uint8_t *image,size_t size,unsigned version) {
 return size==USB_BACKUP_BYTES&&locate()&&validate_image(image,version)&&
        world_backup_snapshot(prepare,(void*)image);
}
static void emit(const char *line) { fputs(line,stdout);fflush(stdout); }
void usb_backup_device_start(void) {
    uint8_t mac[6];char id[13],build[65];
    if(esp_read_mac(mac,ESP_MAC_WIFI_STA)!=ESP_OK)return;
    snprintf(id,sizeof(id),"%02x%02x%02x%02x%02x%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    const esp_app_desc_t *app=esp_app_get_description();
    for(unsigned i=0;i<32;i++)snprintf(build+2*i,3,"%02x",app->app_elf_sha256[i]);
    usb_backup_init(snapshot,emit,id,build,SAVE_VERSION);
    usb_backup_restore_hooks(locate()?stage:NULL,esp_restart,boot_result,boot_crc);
}
