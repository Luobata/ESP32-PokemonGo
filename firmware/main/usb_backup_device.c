#include "usb_backup.h"
#include "restore_journal.h"
#include "world.h"
#include "save.h"
#include "save_bank.h"
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
static bool scratch_mounted,upload_reserved;
static unsigned upload_version,upload_size;
static uint32_t upload_bank;
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
 if(!locate())return true;
 boot_result=restore_journal_apply(&io,esp_app_get_description()->app_elf_sha256,&boot_crc);
 if(boot_result<0)ESP_LOGE("restore","Restore journal needs recovery; refusing to start game");
 return boot_result>=0;
}
static bool rejected(usb_restore_detail_t detail,const char *phase,esp_err_t err) {
 (void)phase;(void)err;
 usb_backup_restore_detail(detail);
 ESP_LOGE("restore","Import rejected at %s: %s",phase,esp_err_to_name(err));
 return false;
}
static uint32_t crc_update(uint32_t c,const uint8_t *p,size_t n) {
 while(n--){c^=*p++;for(unsigned i=0;i<8;i++)c=(c>>1)^(0xedb88320u&-(c&1u));}return c;
}
static bool current_ref(save_bank_ref_t *ref) {
 nvs_handle_t h;size_t n=sizeof(*ref);
 if(nvs_open("pokewalk",NVS_READONLY,&h)!=ESP_OK)return false;
 esp_err_t e=nvs_get_blob(h,"state",ref,&n);
 if(e==ESP_ERR_NVS_NOT_FOUND){n=sizeof(*ref);e=nvs_get_blob(h,"state_guard",ref,&n);}
 nvs_close(h);
 return e==ESP_OK&&n==sizeof(*ref)&&save_bank_ref_valid(ref);
}
static bool copy_snapshot(void *result) {
 const save_bank_io_t *store=save_bank_platform();save_bank_ref_t ref;
 if(!locate()||!store||!current_ref(&ref))return false;
 int bank=save_bank_find(store,&ref);if(bank<0)return false;
 if(!store->erase(SAVE_BANK_EXPORT_AT,SAVE_BANK_EXPORT_SIZE))return false;
 uint8_t buf[256];uint32_t expected=~0u,actual=~0u;
 for(uint32_t at=0;at<USB_BACKUP_EXTENDED_BYTES;at+=sizeof(buf)){
  bool read=at<USB_BACKUP_BYTES?read_part(false,at,buf,sizeof(buf)):
    store->read(bank*SAVE_BANK_STRIDE+at-USB_BACKUP_BYTES,buf,sizeof(buf));
  if(!read||!store->write(SAVE_BANK_EXPORT_AT+at,buf,sizeof(buf)))return false;
  expected=crc_update(expected,buf,sizeof(buf));
 }
 for(uint32_t at=0;at<USB_BACKUP_EXTENDED_BYTES;at+=sizeof(buf)){
  if(!store->read(SAVE_BANK_EXPORT_AT+at,buf,sizeof(buf)))return false;
  actual=crc_update(actual,buf,sizeof(buf));
 }
 if(actual!=expected)return false;
 *(uint32_t*)result=~actual;return true;
}
static bool export_begin(uint32_t *bytes,uint32_t *crc) {
 if(!world_backup_snapshot(copy_snapshot,crc))return false;
 *bytes=USB_BACKUP_EXTENDED_BYTES;return true;
}
static bool export_read(uint32_t at,void *out,size_t n) {
 const save_bank_io_t *store=save_bank_platform();
 return store&&at<=USB_BACKUP_EXTENDED_BYTES&&n<=USB_BACKUP_EXTENDED_BYTES-at&&store->read(SAVE_BANK_EXPORT_AT+at,out,n);
}
static bool release_upload(void *unused) {
 (void)unused;save_bank_reserve(false);upload_reserved=false;return true;
}
static void cancel(void) {
 if(upload_reserved)world_backup_exclusive(release_upload,NULL);
 if(scratch_mounted&&nvs_flash_deinit_partition(scratch.label)==ESP_OK)scratch_mounted=false;
}
static bool prepare_upload(void *unused) {
 (void)unused;const save_bank_io_t *store=save_bank_platform();save_bank_ref_t ref;
 if(!store)return rejected(USB_RESTORE_DETAIL_LAYOUT,"store",ESP_FAIL);
 if(!current_ref(&ref))return rejected(USB_RESTORE_DETAIL_READ,"current reference",ESP_FAIL);
 int active=save_bank_find(store,&ref);if(active<0)return rejected(USB_RESTORE_DETAIL_CONTENT,"current bank",ESP_FAIL);
 upload_bank=(1u-(unsigned)active)*SAVE_BANK_STRIDE;
 // Reserve before erasing the unreferenced bank. Background saves must not
 // reuse it until cancel/reboot; live progress and the committed bank stay intact.
 save_bank_reserve(true);upload_reserved=true;
 if(!erase_part(true,0,RESTORE_STAGE_SIZE)||
    (upload_size==USB_BACKUP_EXTENDED_BYTES&&!store->erase(upload_bank,SAVE_BANK_STRIDE))) {
  release_upload(NULL);return rejected(USB_RESTORE_DETAIL_FLASH,"upload erase",ESP_FAIL);
 }
 return true;
}
static bool import_begin(uint32_t bytes,unsigned version) {
 if(!locate()||!save_bank_platform())return rejected(USB_RESTORE_DETAIL_LAYOUT,"layout",ESP_FAIL);
 if(!((version>=5&&version<=22&&bytes==USB_BACKUP_BYTES)||(version==23&&bytes==USB_BACKUP_EXTENDED_BYTES)))return false;
 if(scratch_mounted){if(nvs_flash_deinit_partition(scratch.label)!=ESP_OK)return rejected(USB_RESTORE_DETAIL_NVS,"retry unmount",ESP_FAIL);scratch_mounted=false;}
 upload_size=bytes;upload_version=version;
 return world_backup_exclusive(prepare_upload,NULL);
}
static bool import_write(uint32_t at,const void *data,size_t n) {
 if(!upload_reserved||at>upload_size||n>upload_size-at)return false;
 uint8_t check[128];if(n>sizeof(check))return false;
 const save_bank_io_t *store=save_bank_platform();bool ok;
 if(at<USB_BACKUP_BYTES){
  ok=n<=USB_BACKUP_BYTES-at&&write_part(true,0x1000+at,data,n)&&read_part(true,0x1000+at,check,n);
 }else ok=store&&store->write(upload_bank+at-USB_BACKUP_BYTES,data,n)&&store->read(upload_bank+at-USB_BACKUP_BYTES,check,n);
 return ok&&!memcmp(data,check,n);
}
static bool read_import(void *context,void *blob,size_t *size,uint8_t *opening) {
 unsigned version=*(const unsigned*)context;nvs_handle_t h;
 esp_err_t e=nvs_open_from_partition(scratch.label,"pokewalk",NVS_READONLY,&h);
 if(e!=ESP_OK)return rejected(e==ESP_ERR_NO_MEM?USB_RESTORE_DETAIL_MEMORY:USB_RESTORE_DETAIL_READ,"open",e);
 size_t capacity=*size;e=nvs_get_blob(h,"state",blob,size);
 if(e==ESP_ERR_NVS_NOT_FOUND){*size=capacity;e=nvs_get_blob(h,"state_guard",blob,size);}
 (void)nvs_get_u8(h,"opening",opening);nvs_close(h);
 if(e!=ESP_OK)return rejected(e==ESP_ERR_NO_MEM?USB_RESTORE_DETAIL_MEMORY:USB_RESTORE_DETAIL_READ,"read",e);
 if(*size<sizeof(uint16_t))return rejected(USB_RESTORE_DETAIL_CONTENT,"length",ESP_FAIL);
 if(((const save_t*)blob)->version!=version)return rejected(USB_RESTORE_DETAIL_VERSION,"schema",ESP_FAIL);
 // A V23 import must reference its uploaded bank, not coincidentally find a
 // pre-existing record on this device. Validate both the header and full bytes.
 if(version==23){
  save_bank_ref_t uploaded;
  const save_bank_io_t *store=save_bank_platform();
  if(*size!=sizeof(uploaded)||!store||!store->read(upload_bank,&uploaded,sizeof(uploaded))||
     memcmp(blob,&uploaded,sizeof(uploaded))||!save_bank_check(store,upload_bank/SAVE_BANK_STRIDE,&uploaded))
   return rejected(USB_RESTORE_DETAIL_CONTENT,"bank",ESP_FAIL);
 }
 return true;
}
static bool prepare_journal(void *crc) {
 return restore_journal_prepare_staged(&io,esp_app_get_description()->app_elf_sha256,*(uint32_t*)crc)||
        rejected(USB_RESTORE_DETAIL_JOURNAL,"journal",ESP_FAIL);
}
static bool import_finish(uint32_t crc) {
 if(!upload_reserved)return false;
 scratch=*staging;scratch.address+=0x1000;scratch.size=USB_BACKUP_BYTES;
 scratch.subtype=ESP_PARTITION_SUBTYPE_DATA_NVS;snprintf(scratch.label,sizeof(scratch.label),"pw_import");
 esp_err_t e=nvs_flash_init_partition_ptr(&scratch);
 if(e!=ESP_OK)return rejected(e==ESP_ERR_NO_MEM?USB_RESTORE_DETAIL_MEMORY:USB_RESTORE_DETAIL_NVS,"mount",e);
 scratch_mounted=true;usb_backup_restore_detail(USB_RESTORE_DETAIL_CONTENT);
 bool valid=world_backup_validate(read_import,&upload_version,upload_version);
#if defined(ESP_PLATFORM) && !defined(HOST_BUILD)
 const uint32_t caps=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT;
 ESP_LOGI("restore","@@IMPORT_MEMORY valid=%d free=%u minimum=%u largest=%u stack_free=%u",
          valid,(unsigned)heap_caps_get_free_size(caps),(unsigned)heap_caps_get_minimum_free_size(caps),
          (unsigned)heap_caps_get_largest_free_block(caps),(unsigned)uxTaskGetStackHighWaterMark(NULL));
#endif
 e=nvs_flash_deinit_partition(scratch.label);
 if(e!=ESP_OK)valid=rejected(USB_RESTORE_DETAIL_NVS,"unmount",e);else scratch_mounted=false;
 // No checkpoint here: it could replace the uploaded inactive bank. The
 // required checkpoint + verified computer backup happened before upload ACK.
 return valid&&world_backup_exclusive(prepare_journal,&crc);
}
static const usb_backup_stream_t streams={export_begin,export_read,import_begin,import_write,import_finish,cancel};
static void emit(const char *line) { fputs(line,stdout);fflush(stdout); }
void usb_backup_device_start(void) {
 uint8_t mac[6];char id[13],build[65];
 if(esp_read_mac(mac,ESP_MAC_WIFI_STA)!=ESP_OK)return;
 snprintf(id,sizeof(id),"%02x%02x%02x%02x%02x%02x",mac[0],mac[1],mac[2],mac[3],mac[4],mac[5]);
 const esp_app_desc_t *app=esp_app_get_description();
 for(unsigned i=0;i<32;i++)snprintf(build+2*i,3,"%02x",app->app_elf_sha256[i]);
 usb_backup_init(NULL,emit,id,build,SAVE_VERSION);
 int result=boot_result==1&&!world_save_loaded()?3:boot_result;
 usb_backup_restore_hooks(NULL,esp_restart,result,boot_crc);
 usb_backup_stream_hooks(&streams);
}
