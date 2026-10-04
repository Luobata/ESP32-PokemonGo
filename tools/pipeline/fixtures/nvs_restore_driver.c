// Integration fixture: RAM flash with real ESP-IDF NVS and production restore code.
#include "usb_backup_device.c"
#include <assert.h>
#include "assets.h"
#include "exp.h"
#include "save_history_cases.h"
static uint8_t flash[0x380000],image[USB_BACKUP_BYTES];
static esp_partition_t live={1,2,0x9000,USB_BACKUP_BYTES,"nvs",false,false};
static esp_partition_t temp={1,0x40,0x360000,RESTORE_STAGE_SIZE,"save_restore",false,false};
static esp_app_desc_t app={{0x12,0x34}};
static save_t current;
const esp_partition_t *esp_partition_find_first(unsigned type,unsigned sub,const char *label){(void)type;(void)sub;return !strcmp(label,"nvs")?&live:!strcmp(label,"save_restore")?&temp:NULL;}
uint32_t esp_partition_get_main_flash_sector_size(void){return 4096;}
esp_err_t esp_partition_read(const esp_partition_t *p,size_t at,void *out,size_t n){assert(at+n<=p->size);memcpy(out,flash+p->address+at,n);return ESP_OK;}
esp_err_t esp_partition_write(const esp_partition_t *p,size_t at,const void *in,size_t n){assert(at+n<=p->size);for(size_t i=0;i<n;i++)flash[p->address+at+i]&=((const uint8_t*)in)[i];return ESP_OK;}
esp_err_t esp_partition_read_raw(const esp_partition_t *p,size_t at,void *out,size_t n){return esp_partition_read(p,at,out,n);}
esp_err_t esp_partition_write_raw(const esp_partition_t *p,size_t at,const void *in,size_t n){return esp_partition_write(p,at,in,n);}
esp_err_t esp_partition_erase_range(const esp_partition_t *p,size_t at,size_t n){assert(at+n<=p->size&&at%4096==0&&n%4096==0);memset(flash+p->address+at,255,n);return ESP_OK;}
const esp_app_desc_t *esp_app_get_description(void){return &app;}
esp_err_t esp_read_mac(uint8_t *out,unsigned kind){(void)kind;memset(out,0,6);return ESP_OK;}
const char *esp_err_to_name(esp_err_t err){(void)err;return "test";}
void esp_restart(void){}
bool world_save_loaded(void){return true;}
bool world_backup_snapshot(bool(*reader)(void*),void *out){return save_write(&current)&&reader(out);}
void usb_backup_init(bool(*r)(uint8_t*,size_t),void(*e)(const char*),const char *d,const char *f,unsigned v){(void)r;(void)e;(void)d;(void)f;(void)v;}
void usb_backup_restore_hooks(bool(*s)(const uint8_t*,size_t,unsigned),void(*r)(void),int b,uint32_t crc){(void)s;(void)r;(void)b;(void)crc;}
static void make_save(uint16_t species,unsigned level){
 memset(&current,0,sizeof(current));current.version=SAVE_VERSION;current.species=species;current.level=level;current.exp=exp_for_level(level);current.opening_seen=true;
 party_t party;party_init(&party);mon_t mon={.species_id=species,.level=level,.exp=current.exp,.hp=100};assert(party_receive(&party,&mon));mon.flags=1;mon.species_id=149;mon.level=60;mon.exp=exp_for_level(60);party.box[3]=mon;
 party_serialize(&party,current.party);dex_mark_caught(&current.dex,species,false);dex_mark_caught(&current.dex,149,true);
 current.pet.stamina=45*NURT_Q;current.challenge.wild_wins=7;current.challenge.defeated=1;
 current.dungeon.clears=2;items_inventory_init(&current.inventory);exploration_init(&current.exploration);
 assert(save_write(&current));
 nvs_handle_t h;assert(nvs_open("pokewalk",NVS_READWRITE,&h)==ESP_OK);
 assert(nvs_set_u8(h,"volume",(uint8_t)level)==ESP_OK);assert(nvs_set_u8(h,"brightness",(uint8_t)(level+10))==ESP_OK);
 assert(nvs_commit(h)==ESP_OK);nvs_close(h);
}
static void historical_restore(void){
 for(unsigned i=0;i<sizeof(history)/sizeof(history[0]);i++){
  printf("Real-NVS historical restore: %s\n",history[i].name);
  // Write historical bytes using the real NVS engine, producing a complete
  // partition image, then replace live progress with a different modern save.
  nvs_handle_t h;assert(nvs_open("pokewalk",NVS_READWRITE,&h)==ESP_OK);
  assert(nvs_set_blob(h,"state",history[i].data,history[i].size)==ESP_OK);
  assert(nvs_set_u8(h,"volume",61)==ESP_OK&&nvs_set_u8(h,"brightness",73)==ESP_OK);
  assert(nvs_commit(h)==ESP_OK);nvs_close(h);assert(read_nvs(image));
  make_save(1,7);save_t before=current,loaded;party_t party;
  uint8_t unchanged[USB_BACKUP_BYTES];memcpy(unchanged,flash+live.address,sizeof(unchanged));
  assert(!stage(image,sizeof(image),history[i].version+1));
  assert(!memcmp(unchanged,flash+live.address,sizeof(unchanged))); // forged metadata
  assert(stage(image,sizeof(image),history[i].version));
  assert(save_read(&loaded)&&!memcmp(&loaded,&before,sizeof(before)));
  assert(nvs_flash_deinit()==ESP_OK&&usb_backup_restore_before_boot()&&boot_result==1);
  assert(boot_crc==restore_crc32(image,sizeof(image))&&save_init());
  assert(save_read(&loaded)&&save_validate_world(&loaded,&party));
  history_assert(&loaded,history[i].version);
  assert(nvs_open("pokewalk",NVS_READONLY,&h)==ESP_OK);uint8_t v;
  assert(nvs_get_u8(h,"volume",&v)==ESP_OK&&v==61);
  assert(nvs_get_u8(h,"brightness",&v)==ESP_OK&&v==73);nvs_close(h);
  // Commit normalized progress as world_start does, export/import it once
  // more, then reboot. No repeated rewards or double HP/stat conversion.
  save_t migrated=loaded;current=loaded;assert(save_write(&current));assert(snapshot(image,sizeof(image)));
  make_save(1,7);assert(stage(image,sizeof(image),SAVE_VERSION));
  assert(nvs_flash_deinit()==ESP_OK&&usb_backup_restore_before_boot()&&boot_result==1&&save_init());
  assert(save_read_status(&loaded)==SAVE_READ_OK&&!memcmp(&loaded,&migrated,sizeof(loaded)));
  history_assert(&loaded,history[i].version);
  assert(nvs_flash_deinit()==ESP_OK&&usb_backup_restore_before_boot()&&boot_result==0&&save_init());
  assert(save_read_status(&loaded)==SAVE_READ_OK);history_assert(&loaded,history[i].version);
 }
}
int main(void){
 assert(assets_init());assert(locate());memset(flash,255,sizeof(flash));assert(save_init());
 make_save(25,32);save_t wanted=current;assert(snapshot(image,sizeof(image)));
 make_save(1,7);save_t before=current,loaded;party_t party;assert(save_read(&loaded)&&loaded.species==1);
 uint8_t unchanged[USB_BACKUP_BYTES];memcpy(unchanged,flash+live.address,sizeof(unchanged));
 assert(!stage(image,sizeof(image),SAVE_VERSION-1));assert(!memcmp(unchanged,flash+live.address,sizeof(unchanged)));
 assert(stage(image,sizeof(image),SAVE_VERSION));assert(save_read(&loaded)&&loaded.species==1); // live remains old until reboot
 assert(nvs_flash_deinit()==ESP_OK);assert(usb_backup_restore_before_boot());assert(boot_result==1&&boot_crc==restore_crc32(image,sizeof(image)));assert(save_init());
 assert(save_read_status(&loaded)==SAVE_READ_OK&&save_validate_world(&loaded,&party));
 assert(loaded.species==25&&loaded.level==32&&!memcmp(&loaded,&wanted,sizeof(wanted)));
 nvs_handle_t h;uint8_t value;assert(nvs_open("pokewalk",NVS_READONLY,&h)==ESP_OK);
 assert(nvs_get_u8(h,"volume",&value)==ESP_OK&&value==32);assert(nvs_get_u8(h,"brightness",&value)==ESP_OK&&value==42);nvs_close(h);
 assert(nvs_flash_deinit()==ESP_OK);assert(usb_backup_restore_before_boot());assert(boot_result==0);assert(save_init());assert(save_read(&loaded)&&loaded.species==25); // another boot stays restored
 current=loaded;assert(snapshot(image,sizeof(image)));make_save(1,7);assert(stage(image,sizeof(image),SAVE_VERSION));
 flash[temp.address+0x1000]^=1;assert(nvs_flash_deinit()==ESP_OK);assert(usb_backup_restore_before_boot());assert(boot_result==2);assert(save_init());assert(save_read(&loaded)&&!memcmp(&loaded,&before,sizeof(before)));
 historical_restore();
 assert(nvs_flash_deinit()==ESP_OK);puts("Real ESP-IDF NVS + production save/device/journal: historical V5-V17, distinct saves, schema rejection, settings, restore, second boot and rollback passed");
}
