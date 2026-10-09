// Integration fixture: RAM flash with real ESP-IDF NVS and production restore code.
#include "usb_backup_device.c"
#include <assert.h>
#include "assets.h"
#include "exp.h"
#include "dungeon.h"
#include "save_history_cases.h"
static uint8_t flash[0x380000],image[USB_BACKUP_BYTES];
static esp_partition_t live={1,2,0x9000,USB_BACKUP_BYTES,"nvs",false,false};
static esp_partition_t temp={1,0x40,0x360000,RESTORE_STAGE_SIZE,"save_restore",false,false};
static esp_app_desc_t app={{0x12,0x34}};
static save_t current;
static bool fail_storage_write;
static int flash_operations_left=-1;
static bool flash_fault(void){if(flash_operations_left<0)return false;if(!flash_operations_left)return true;flash_operations_left--;return false;}
// Host-only records: compare every unrelated key byte-for-byte, never print
// private values. This is not a firmware allocation or a checked-in player save.
static struct {nvs_entry_info_t info;size_t size;uint8_t data[4096];} retained[128];
static unsigned retained_count;
static void read_entry(const nvs_entry_info_t *info,uint8_t *data,size_t *size){
 nvs_handle_t h;assert(nvs_open(info->namespace_name,NVS_READONLY,&h)==ESP_OK);esp_err_t e=ESP_FAIL;
 switch(info->type){
 // API suffixes differ from C types.
 #define READ(kind,suffix,type) case NVS_TYPE_##kind:{type v;e=nvs_get_##suffix(h,info->key,&v);*size=sizeof(v);memcpy(data,&v,sizeof(v));break;}
 READ(U8,u8,uint8_t) READ(I8,i8,int8_t) READ(U16,u16,uint16_t) READ(I16,i16,int16_t)
 READ(U32,u32,uint32_t) READ(I32,i32,int32_t) READ(U64,u64,uint64_t) READ(I64,i64,int64_t)
 #undef READ
 case NVS_TYPE_STR:e=nvs_get_str(h,info->key,(char*)data,size);break;
 case NVS_TYPE_BLOB:e=nvs_get_blob(h,info->key,data,size);break;
 default:assert(0);
 }
 nvs_close(h);assert(e==ESP_OK);
}
static void remember_unrelated(void){
 retained_count=0;nvs_iterator_t it=NULL;
 esp_err_t e=nvs_entry_find("nvs",NULL,NVS_TYPE_ANY,&it);
 while(e==ESP_OK){nvs_entry_info_t info;nvs_entry_info(it,&info);
  if(strcmp(info.namespace_name,"pokewalk")|| (strcmp(info.key,"state")&&strcmp(info.key,"opening"))){
   assert(retained_count<128);retained[retained_count].info=info;retained[retained_count].size=4096;
   read_entry(&info,retained[retained_count].data,&retained[retained_count].size);retained_count++;
  }
  e=nvs_entry_next(&it);
 }
 assert(e==ESP_ERR_NVS_NOT_FOUND);nvs_release_iterator(it);
}
static void check_unrelated(void){
 uint8_t bytes[4096];for(unsigned i=0;i<retained_count;i++){size_t n=sizeof(bytes);
  read_entry(&retained[i].info,bytes,&n);assert(n==retained[i].size&&!memcmp(bytes,retained[i].data,n));}
}
static size_t stored_size(void){nvs_handle_t h;size_t n=0;assert(nvs_open("pokewalk",NVS_READONLY,&h)==ESP_OK);assert(nvs_get_blob(h,"state",NULL,&n)==ESP_OK);nvs_close(h);return n;}
const esp_partition_t *esp_partition_find_first(unsigned type,unsigned sub,const char *label){(void)type;(void)sub;return !strcmp(label,"nvs")?&live:!strcmp(label,"save_restore")?&temp:NULL;}
uint32_t esp_partition_get_main_flash_sector_size(void){return 4096;}
esp_err_t esp_partition_read(const esp_partition_t *p,size_t at,void *out,size_t n){assert(at+n<=p->size);memcpy(out,flash+p->address+at,n);return ESP_OK;}
esp_err_t esp_partition_write(const esp_partition_t *p,size_t at,const void *in,size_t n){if(fail_storage_write||flash_fault())return ESP_FAIL;assert(at+n<=p->size);for(size_t i=0;i<n;i++)flash[p->address+at+i]&=((const uint8_t*)in)[i];return ESP_OK;}
esp_err_t esp_partition_read_raw(const esp_partition_t *p,size_t at,void *out,size_t n){return esp_partition_read(p,at,out,n);}
esp_err_t esp_partition_write_raw(const esp_partition_t *p,size_t at,const void *in,size_t n){return esp_partition_write(p,at,in,n);}
esp_err_t esp_partition_erase_range(const esp_partition_t *p,size_t at,size_t n){if(flash_fault())return ESP_FAIL;assert(at+n<=p->size&&at%4096==0&&n%4096==0);memset(flash+p->address+at,255,n);return ESP_OK;}
const esp_app_desc_t *esp_app_get_description(void){return &app;}
esp_err_t esp_read_mac(uint8_t *out,unsigned kind){(void)kind;memset(out,0,6);return ESP_OK;}
const char *esp_err_to_name(esp_err_t err){(void)err;return "test";}
void esp_restart(void){}
bool world_save_loaded(void){return true;}
void usb_backup_restore_detail(usb_restore_detail_t detail){(void)detail;}
bool world_backup_validate(world_backup_reader_t reader,void *ctx,unsigned version){
 static save_t saved;static party_t party;size_t size=sizeof(saved);uint8_t opening=0;
 if(!reader(ctx,&saved,&size,&opening)||size<2||size>sizeof(saved)||saved.version!=version)return false;
 save_read_result_t result=save_decode(&saved,&saved,size,opening);
 return (result==SAVE_READ_OK||result==SAVE_READ_MIGRATED)&&save_validate_world(&saved,&party);
}
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
 assert(nvs_open("pw_dungeon",NVS_READWRITE,&h)==ESP_OK);
 assert(nvs_set_blob(h,"run_v3",dungeon_history,sizeof(dungeon_history))==ESP_OK);
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
  assert(nvs_open("pw_dungeon",NVS_READONLY,&h)==ESP_OK);
  unsigned char run_bytes[sizeof(dungeon_history)];size_t run_size=sizeof(run_bytes);
  assert(nvs_get_blob(h,"run_v3",run_bytes,&run_size)==ESP_OK&&run_size==sizeof(run_bytes)&&!memcmp(run_bytes,dungeon_history,run_size));nvs_close(h);

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
static void policy_capacity_stress(void){
 nvs_handle_t legacy;uint8_t old_run[788];memset(old_run,0x5a,sizeof(old_run));
 assert(nvs_open("pw_dungeon",NVS_READWRITE,&legacy)==ESP_OK);
 assert(nvs_set_blob(legacy,"run_v1",old_run,sizeof(old_run))==ESP_OK);assert(nvs_commit(legacy)==ESP_OK);nvs_close(legacy);

 nvs_handle_t hw;uint8_t calibration[1904];memset(calibration,0x5a,sizeof(calibration));
 assert(nvs_open("phy",NVS_READWRITE,&hw)==ESP_OK);
 assert(nvs_set_blob(hw,"cal_data",calibration,sizeof(calibration))==ESP_OK);assert(nvs_commit(hw)==ESP_OK);nvs_close(hw);

 dungeon_load();
 assert(nvs_open("pw_dungeon",NVS_READONLY,&legacy)==ESP_OK);size_t obsolete=0;
 assert(nvs_get_blob(legacy,"run_v1",NULL,&obsolete)==ESP_ERR_NVS_NOT_FOUND);nvs_close(legacy);
 make_save(25,32);party_t p;party_init(&p);p.party_count=PARTY_MAX;
 for(unsigned i=0;i<PARTY_MAX+BOX_SPECIES;i++){
  mon_t *m=i<PARTY_MAX?&p.party[i]:&p.box[i-PARTY_MAX];
  *m=(mon_t){.species_id=i==0?25:1+i%151,.level=32,.exp=exp_for_level(32),.hp=100};
  // Dense varied bits are much less compressible than one disabled move.
  for(unsigned b=0;b<MOVE_POLICY_BYTES;b++)p.policies[i].disabled[b]=(uint8_t)(1+(i*73+b*31)%255);
  p.policies[i].disabled[MOVE_POLICY_BYTES-1]&=0x7f;
 }
 save_store_party(&current,&p);assert(save_write(&current));
 remember_unrelated();
 // Full warehouse + dense policies + shared Wi-Fi/other-game occupancy, using
 // real NVS copy-on-write, page garbage collection and remount.
 for(unsigned i=0;i<300;i++){
  current.playtime_s++;move_policy_set(&current.move_policies[i%(PARTY_MAX+BOX_SPECIES)],85,i&1);
  assert(save_write(&current));save_t loaded;assert(save_read(&loaded)&&!memcmp(&loaded,&current,sizeof(current)));
  if(i%17==0){assert(nvs_flash_deinit()==ESP_OK&&save_init());assert(save_read(&loaded)&&!memcmp(&loaded,&current,sizeof(current)));}
 }
 assert(snapshot(image,sizeof(image)));save_t expected=current;make_save(1,7);assert(stage(image,sizeof(image),SAVE_VERSION));
 assert(nvs_flash_deinit()==ESP_OK&&usb_backup_restore_before_boot()&&boot_result==1&&save_init());
 save_t loaded;assert(save_read(&loaded)&&save_validate_world(&loaded,&p)&&!memcmp(&loaded,&expected,sizeof(expected)));
 check_unrelated();
 printf("V22 full 157-individual dense policies: stored=%zu, 300 writes, GC/remount and export/import passed\n",stored_size());
}
static void write_faults(void){
 uint8_t baseline[USB_BACKUP_BYTES];memcpy(baseline,flash+live.address,sizeof(baseline));
 save_t old,next,got;assert(save_read(&old));next=old;next.playtime_s+=333;
 bool complete=false;unsigned failures=0;remember_unrelated();
 for(unsigned cut=0;cut<1024;cut++){
  assert(nvs_flash_deinit()==ESP_OK);memcpy(flash+live.address,baseline,sizeof(baseline));assert(save_init());
  flash_operations_left=(int)cut;bool ok=save_write(&next);flash_operations_left=-1;
  assert(nvs_flash_deinit()==ESP_OK&&save_init());
  assert(save_read_status(&got)==SAVE_READ_OK);
  assert(!memcmp(&got,&old,sizeof(got))||!memcmp(&got,&next,sizeof(got)));check_unrelated();
  if(ok){assert(!memcmp(&got,&next,sizeof(got)));complete=true;break;}
  if(cut==0)assert(!memcmp(&got,&old,sizeof(got)));
  failures++;assert(save_write(&next)&&save_read(&got)&&!memcmp(&got,&next,sizeof(got)));
 }
 assert(complete&&failures);current=next;
 printf("V22 interrupted NVS writes: %u fault points, old/new complete state after remount, retry and unrelated keys passed\n",failures);
}
static void shared_occupancy(void);
static void legacy_capacity_regression(void){
 make_save(25,32);shared_occupancy();
 // Keep both the historical and replacement dungeon keys as on an upgraded
 // shared device. These values are synthetic public fixtures, never player data.
 nvs_handle_t h;dungeon_t d={0};memcpy(&d,dungeon_history,sizeof(dungeon_history));d.version=4;
 assert(nvs_open("pw_dungeon",NVS_READWRITE,&h)==ESP_OK);
 assert(nvs_set_blob(h,"run_v4",&d,sizeof(d))==ESP_OK&&nvs_commit(h)==ESP_OK);nvs_close(h);
 bool full=false;save_t raw=current;raw.version=21;
 for(unsigned i=0;i<8;i++){
  raw.playtime_s++;assert(nvs_open("pokewalk",NVS_READWRITE,&h)==ESP_OK);
  esp_err_t e=nvs_set_blob(h,"state",&raw,sizeof(raw));nvs_close(h);
  if(e==ESP_ERR_NVS_NOT_ENOUGH_SPACE){full=true;break;}assert(e==ESP_OK);
 }
 assert(full);assert(save_read(&current));remember_unrelated();
 for(unsigned i=0;i<300;i++){current.playtime_s++;assert(save_write(&current));}
 check_unrelated();
 puts("Synthetic shared-device occupancy: V21 raw save reproduces NOT_ENOUGH_SPACE; V22 preserves all keys and saves 300 times");
}
static void shared_occupancy(void){
 // Synthetic values only. Sizes/types reproduce a shared device's ordinary
 // Wi-Fi, calibration, other-game and old dungeon occupancy, without secrets.
 nvs_handle_t h;uint8_t bytes[1904];memset(bytes,0x5a,sizeof(bytes));
 const struct {const char *ns,*key;size_t size;} records[]={
  {"phy","cal_data",1904},{"nvs.net80211","sta.apinfo",700},
  {"other_game","state",896},{"other_wifi","credentials",108}};
 for(unsigned i=0;i<sizeof(records)/sizeof(records[0]);i++){
  assert(nvs_open(records[i].ns,NVS_READWRITE,&h)==ESP_OK);
  assert(nvs_set_blob(h,records[i].key,bytes,records[i].size)==ESP_OK&&nvs_commit(h)==ESP_OK);nvs_close(h);
 }
 assert(nvs_open("nvs.net80211",NVS_READWRITE,&h)==ESP_OK);
 for(unsigned i=0;i<40;i++){char key[16];snprintf(key,sizeof(key),"wifi_%02u",i);assert(nvs_set_u32(h,key,123+i)==ESP_OK);}
 assert(nvs_set_str(h,"sta.ssid","synthetic-regression-network")==ESP_OK);
 assert(nvs_set_str(h,"sta.pswd","synthetic-placeholder-not-a-real-password")==ESP_OK);
 assert(nvs_commit(h)==ESP_OK);nvs_close(h);
}
static void private_roundtrip(void){
 remember_unrelated();assert(read_nvs(image));
 nvs_handle_t h;uint16_t source_version;uint8_t source[sizeof(save_t)];size_t n=sizeof(source);
 assert(nvs_open("pokewalk",NVS_READONLY,&h)==ESP_OK&&nvs_get_blob(h,"state",source,&n)==ESP_OK);nvs_close(h);memcpy(&source_version,source,2);
 save_t expected=current;assert(stage(image,sizeof(image),source_version));
 assert(nvs_flash_deinit()==ESP_OK&&usb_backup_restore_before_boot()&&boot_result==1&&save_init());
 assert(save_read(&current)&&!memcmp(&current,&expected,sizeof(current)));check_unrelated();
 for(unsigned i=0;i<300;i++){
  current.playtime_s++;assert(save_write(&current));
  if(i%17==0)assert(nvs_flash_deinit()==ESP_OK&&save_init());
  save_t got;assert(save_read_status(&got)==SAVE_READ_OK&&!memcmp(&got,&current,sizeof(got)));
 }
 check_unrelated();expected=current;assert(snapshot(image,sizeof(image)));
 // Make durable data observably different before restoring the new backup.
 current.playtime_s+=100;assert(save_write(&current));
 assert(stage(image,sizeof(image),SAVE_VERSION));
 assert(nvs_flash_deinit()==ESP_OK&&usb_backup_restore_before_boot()&&boot_result==1&&save_init());
 assert(save_read_status(&current)==SAVE_READ_OK&&!memcmp(&current,&expected,sizeof(current)));check_unrelated();
 assert(nvs_flash_deinit()==ESP_OK&&usb_backup_restore_before_boot()&&boot_result==0&&save_init());
 assert(save_read_status(&current)==SAVE_READ_OK&&!memcmp(&current,&expected,sizeof(current)));
 printf("Private isolated NVS: old import/boot, 300 writes/remount, new export/import with distinct progress; stored=%zu, unrelated_keys=%u unchanged\n",stored_size(),retained_count);
}
static void dungeon_cleanup_case(unsigned mode){
 nvs_handle_t h;assert(nvs_open("pw_dungeon",NVS_READWRITE,&h)==ESP_OK);
 unsigned char obsolete[788];memset(obsolete,0xa5,sizeof(obsolete));
 assert(nvs_set_blob(h,"run_v1",obsolete,sizeof(obsolete))==ESP_OK);
 dungeon_t expected={0};memcpy(&expected,dungeon_history,sizeof(dungeon_history));expected.version=4;
 if(mode==5||mode==6){
  dungeon_v2_t old={.version=2,.phase=DUNGEON_LOST,.pending=mode==6};
  assert(nvs_set_blob(h,"run_v2",&old,sizeof(old))==ESP_OK);
 }else if(mode!=4){
  assert(nvs_set_blob(h,"run_v3",dungeon_history,sizeof(dungeon_history)-(mode==3))==ESP_OK);
  if(mode==1||mode==2){dungeon_t written=expected;if(mode==2)written.count=255;assert(nvs_set_blob(h,"run_v4",&written,sizeof(written))==ESP_OK);}
 }
 assert(nvs_commit(h)==ESP_OK);nvs_close(h);
 uint8_t before[USB_BACKUP_BYTES];memcpy(before,flash+live.address,sizeof(before));
 if(mode==7)fail_storage_write=true;
 dungeon_load();fail_storage_write=false;
 const dungeon_t *run=dungeon_get();
 if(mode==0||mode==1||mode==7)assert(!memcmp(run,&expected,sizeof(expected)));
 if(mode==5)assert(run->version==4&&run->phase==DUNGEON_LOST);
 if(mode==2||mode==3||mode==4||mode==6||mode==7)assert(!memcmp(before,flash+live.address,sizeof(before)));
 assert(nvs_flash_deinit()==ESP_OK&&save_init());
 assert(nvs_open("pw_dungeon",NVS_READONLY,&h)==ESP_OK);size_t n=0;
 esp_err_t e=nvs_get_blob(h,"run_v1",NULL,&n);
 assert(e==((mode==0||mode==1||mode==5)?ESP_ERR_NVS_NOT_FOUND:ESP_OK));
 if(mode==0||mode==7){unsigned char raw[sizeof(dungeon_history)];n=sizeof(raw);assert(nvs_get_blob(h,"run_v3",raw,&n)==ESP_OK&&!memcmp(raw,dungeon_history,n));}
 if(mode==1){n=0;assert(nvs_get_blob(h,"run_v3",NULL,&n)==ESP_ERR_NVS_NOT_FOUND);dungeon_t raw;n=sizeof(raw);assert(nvs_get_blob(h,"run_v4",&raw,&n)==ESP_OK&&!memcmp(&raw,&expected,n));}
 nvs_close(h);printf("Validated dungeon cleanup scenario %u passed\n",mode);
}
int main(int argc,char **argv){
 assert(assets_init());assert(locate());memset(flash,255,sizeof(flash));
 bool cleanup_test=argc>1&&!strcmp(argv[1],"--dungeon-cleanup");
 bool capacity_test=argc>1&&!strcmp(argv[1],"--legacy-capacity");
 if(argc>1&&!cleanup_test&&!capacity_test){FILE *f=fopen(argv[1],"rb");assert(f);assert(fread(flash+live.address,1,live.size,f)==live.size);assert(fclose(f)==0);}
 assert(save_init());
 if(cleanup_test){dungeon_cleanup_case((unsigned)atoi(argv[2]));return 0;}
 if(capacity_test){legacy_capacity_regression();return 0;}
 if(argc>1){
  if(argc>2&&!strcmp(argv[2],"validate")){
   nvs_handle_t h;assert(nvs_open("pokewalk",NVS_READONLY,&h)==ESP_OK);
   save_t source;size_t n=sizeof(source);assert(nvs_get_blob(h,"state",&source,&n)==ESP_OK);nvs_close(h);
   assert(read_nvs(image));uint32_t original_crc=restore_crc32(image,sizeof(image));
   bool valid=validate_image(image,source.version);
   assert(restore_crc32(image,sizeof(image))==original_crc);
   assert(!memcmp(image,flash+live.address,sizeof(image)));
   printf("Private isolated import validation: schema=%u bytes=%zu accepted=%u source_unchanged=1\n",source.version,n,valid);
   assert(valid);return 0;
  }
  assert(save_read(&current));
  if(argc>2&&!strcmp(argv[2],"roundtrip")){private_roundtrip();return 0;}
  if(argc>2)dungeon_load();
  for(unsigned i=0;i<300;i++){current.playtime_s++;assert(save_write(&current));}
  puts("Private NVS fixture: 300 writes passed");return 0;
 }

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
 historical_restore();shared_occupancy();policy_capacity_stress();write_faults();
 assert(nvs_flash_deinit()==ESP_OK);puts("Real ESP-IDF NVS + production save/device/journal: historical V5-V22, distinct saves, schema rejection, settings, restore, second boot and rollback passed");
}
