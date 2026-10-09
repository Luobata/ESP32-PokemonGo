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
#include <string.h>
#include "nvs.h"
#include "nvs_flash.h"
#if defined(ESP_PLATFORM) && !defined(HOST_BUILD)
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#endif

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
static bool rejected(usb_restore_detail_t detail,const char *phase,esp_err_t err) {
 (void)phase;(void)err; // Logging can be compiled out in host validation builds.
 usb_backup_restore_detail(detail);
 ESP_LOGE("restore","Import rejected at %s: %s",phase,esp_err_to_name(err));
 return false;
}
static bool prepare(void *image) {
 return restore_journal_prepare(&io,image,esp_app_get_description()->app_elf_sha256)||
        rejected(USB_RESTORE_DETAIL_JOURNAL,"journal",ESP_FAIL);
}
static bool read_import(void *context,void *blob,size_t *size,uint8_t *opening) {
 unsigned version=*(const unsigned*)context;nvs_handle_t h;
 esp_err_t e=nvs_open_from_partition(scratch.label,"pokewalk",NVS_READONLY,&h);
 if(e!=ESP_OK)return rejected(e==ESP_ERR_NO_MEM?USB_RESTORE_DETAIL_MEMORY:USB_RESTORE_DETAIL_READ,"open",e);
 e=nvs_get_blob(h,"state",blob,size);
 (void)nvs_get_u8(h,"opening",opening);nvs_close(h);
 if(e!=ESP_OK)return rejected(e==ESP_ERR_NO_MEM?USB_RESTORE_DETAIL_MEMORY:USB_RESTORE_DETAIL_READ,"read",e);
 if(*size<sizeof(uint16_t))return rejected(USB_RESTORE_DETAIL_CONTENT,"length",ESP_FAIL);
 if(((const save_t*)blob)->version!=version)return rejected(USB_RESTORE_DETAIL_VERSION,"schema",ESP_FAIL);
 return true;
}
static bool validate_image(const uint8_t *image, unsigned version) {
 // The journal has already been resolved before game startup. Leave its commit
 // sector erased while checking a separate NVS instance, never the live save.
 if(scratch_mounted){
  esp_err_t e=nvs_flash_deinit_partition(scratch.label);
  if(e!=ESP_OK)return rejected(USB_RESTORE_DETAIL_NVS,"retry unmount",e);
  scratch_mounted=false;
 }
 if(!erase_part(true,0,RESTORE_STAGE_SIZE)||!write_part(true,0x1000,image,USB_BACKUP_BYTES))return rejected(USB_RESTORE_DETAIL_FLASH,"scratch write",ESP_FAIL);
 scratch=*staging;
 scratch.address+=0x1000;scratch.size=USB_BACKUP_BYTES;
 scratch.subtype=ESP_PARTITION_SUBTYPE_DATA_NVS;
 snprintf(scratch.label,sizeof(scratch.label),"pw_import");
 esp_err_t e=nvs_flash_init_partition_ptr(&scratch);
 if(e!=ESP_OK)return rejected(e==ESP_ERR_NO_MEM?USB_RESTORE_DETAIL_MEMORY:USB_RESTORE_DETAIL_NVS,"mount",e);
 scratch_mounted=true;
 // V21 needs 13 KB for decoded save + party. Reuse the world's locked work
 // buffers instead of competing with the 24 KB upload and Wi-Fi heap.
 usb_backup_restore_detail(USB_RESTORE_DETAIL_CONTENT);
 bool valid=world_backup_validate(read_import,&version,version);
#if defined(ESP_PLATFORM) && !defined(HOST_BUILD)
 // Sample with the upload buffer and temporary NVS mount still alive.
 const uint32_t caps=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT;
 ESP_LOGI("restore","@@IMPORT_MEMORY valid=%d free=%u minimum=%u largest=%u stack_free=%u",
          valid,(unsigned)heap_caps_get_free_size(caps),
          (unsigned)heap_caps_get_minimum_free_size(caps),
          (unsigned)heap_caps_get_largest_free_block(caps),
          (unsigned)uxTaskGetStackHighWaterMark(NULL));
#endif
 e=nvs_flash_deinit_partition(scratch.label);
 if(e!=ESP_OK)valid=rejected(USB_RESTORE_DETAIL_NVS,"unmount",e);
 else scratch_mounted=false;
 return valid;
}
static bool stage(const uint8_t *image,size_t size,unsigned version) {
 if(size!=USB_BACKUP_BYTES||!locate())return rejected(USB_RESTORE_DETAIL_LAYOUT,"layout",ESP_FAIL);
 if(!validate_image(image,version))return false;
 usb_backup_restore_detail(USB_RESTORE_DETAIL_CHECKPOINT);
 return world_backup_snapshot(prepare,(void*)image);
}
static void emit(const char *line) { fputs(line,stdout);fflush(stdout); }
void usb_backup_device_start(void) {
    uint8_t mac[6];char id[13],build[65];
    if(esp_read_mac(mac,ESP_MAC_WIFI_STA)!=ESP_OK)return;
    snprintf(id,sizeof(id),"%02x%02x%02x%02x%02x%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
    const esp_app_desc_t *app=esp_app_get_description();
    for(unsigned i=0;i<32;i++)snprintf(build+2*i,3,"%02x",app->app_elf_sha256[i]);
    usb_backup_init(snapshot,emit,id,build,SAVE_VERSION);
    // Raw flash verification alone is not proof the game adopted the save.
    int result=boot_result==1&&!world_save_loaded()?3:boot_result;
    usb_backup_restore_hooks(locate()?stage:NULL,esp_restart,result,boot_crc);
}
