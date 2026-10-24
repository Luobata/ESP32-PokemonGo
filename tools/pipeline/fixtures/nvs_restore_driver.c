// Integration fixture: RAM flash with real ESP-IDF NVS and production restore code.
#include "usb_backup_device.c"
#include <assert.h>
#include "assets.h"
#include "exp.h"
#include "dungeon.h"
#include "save_history_cases.h"
static uint8_t flash[0x3a0000],image[USB_BACKUP_WAREHOUSE_BYTES];
static esp_partition_t live={1,2,0x9000,USB_BACKUP_BYTES,"nvs",false,false};
static esp_partition_t temp={1,0x40,0x360000,RESTORE_STAGE_SIZE,"save_restore",false,false};
static esp_partition_t store_partition={1,0x41,0x380000,SAVE_BANK_PARTITION_SIZE,"pokewalk_store",false,false};
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
  if(strcmp(info.namespace_name,"pokewalk")|| (strcmp(info.key,"state")&&strcmp(info.key,"state_guard")&&strcmp(info.key,"opening"))){
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
const esp_partition_t *esp_partition_find_first(unsigned type,unsigned sub,const char *label){(void)type;(void)sub;return !strcmp(label,"nvs")?&live:!strcmp(label,"save_restore")?&temp:!strcmp(label,"pokewalk_store")?&store_partition:NULL;}
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
static size_t image_length;
static bool reboot_restore(void){save_bank_reserve(false);upload_reserved=false;return usb_backup_restore_before_boot();}
static bool read_nvs(void *out){image_length=USB_BACKUP_BYTES;return read_part(false,0,out,USB_BACKUP_BYTES);}
static bool snapshot(uint8_t *out,size_t size){
 uint32_t bytes,crc;if(size!=USB_BACKUP_WAREHOUSE_BYTES||!export_begin(&bytes,&crc))return false;
 assert(bytes==USB_BACKUP_WAREHOUSE_BYTES);image_length=bytes;
 bool ok=export_read(0,out,bytes)&&restore_crc32(out,bytes)==crc;cancel();return ok;
}
static bool stage(const uint8_t *data,size_t n,unsigned version){
 cancel();if(!import_begin(n,version))return false;
 for(size_t at=0;at<n;at+=128)if(!import_write(at,data+at,128)){cancel();return false;}
 if(import_finish(restore_crc32(data,n)))return true;
 cancel();return false;
}
bool world_backup_exclusive(bool(*fn)(void*),void *ctx){return fn(ctx);}
void usb_backup_stream_hooks(const usb_backup_stream_t *hooks){(void)hooks;}
static void make_save(uint16_t species,unsigned level){
 memset(&current,0,sizeof(current));current.version=SAVE_VERSION;johto_init(&current.johto);current.species=species;current.level=level;current.exp=exp_for_level(level);current.opening_seen=true;
 party_t party;party_init(&party);mon_t mon={.species_id=species,.level=level,.exp=current.exp,.hp=100};assert(party_receive(&party,&mon));mon.flags=1;mon.species_id=149;mon.level=60;mon.exp=exp_for_level(60);party.box[3]=mon;
 save_store_party(&current,&party);dex_mark_caught(&current.dex,species,false);dex_mark_caught(&current.dex,149,true);
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
  if(history[i].version<23)assert(nvs_set_blob(h,"state",history[i].data,history[i].size)==ESP_OK);
  assert(nvs_set_u8(h,"volume",61)==ESP_OK&&nvs_set_u8(h,"brightness",73)==ESP_OK);
  assert(nvs_commit(h)==ESP_OK);nvs_close(h);
  if(history[i].version>=23){
   // Construct the old bank with immutable historical payload bytes, without
   // checkpointing through the new decoder and mislabelling the source schema.
   save_bank_ref_t historical;
   assert(save_bank_prepare(save_bank_platform(),NULL,history[i].data,history[i].size,&historical));
   assert(nvs_open("pokewalk",NVS_READWRITE,&h)==ESP_OK);
   assert(nvs_set_blob(h,"state",&historical,sizeof(historical))==ESP_OK&&nvs_commit(h)==ESP_OK);nvs_close(h);
   unsigned bank=save_bank_find(save_bank_platform(),&historical);
   unsigned record=history[i].version==23?SAVE_BANK_V23_IMAGE_SIZE:history[i].version<=27?SAVE_BANK_V27_IMAGE_SIZE:SAVE_BANK_IMAGE_SIZE;
   assert(read_nvs(image));image_length=USB_BACKUP_BYTES+record;
   assert(save_bank_platform()->read(save_bank_offset(bank),image+USB_BACKUP_BYTES,record));
  }
  else assert(read_nvs(image));
  make_save(1,7);save_t before=current,loaded;party_t party;
  uint8_t unchanged[USB_BACKUP_BYTES];memcpy(unchanged,flash+live.address,sizeof(unchanged));
  assert(!stage(image,image_length,history[i].version+1));
  assert(!memcmp(unchanged,flash+live.address,sizeof(unchanged))); // forged metadata
  assert(stage(image,image_length,history[i].version));
  assert(save_read(&loaded)&&!memcmp(&loaded,&before,sizeof(before)));
  assert(nvs_flash_deinit()==ESP_OK&&reboot_restore()&&boot_result==1);
  assert(boot_crc==restore_crc32(image,image_length)&&save_init());
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
  assert(nvs_flash_deinit()==ESP_OK&&reboot_restore()&&boot_result==1&&save_init());
  assert(save_read_status(&loaded)==SAVE_READ_OK&&!memcmp(&loaded,&migrated,sizeof(loaded)));
  history_assert(&loaded,history[i].version);
  assert(nvs_flash_deinit()==ESP_OK&&reboot_restore()&&boot_result==0&&save_init());
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
 for(unsigned i=0;i<PARTY_MAX+BOX_CAPACITY;i++){
  mon_t *m=i<PARTY_MAX?&p.party[i]:&p.box[i-PARTY_MAX];
  *m=(mon_t){.species_id=i==0?25:1+i%151,.level=32,.exp=exp_for_level(32),.hp=100};
  // Dense varied bits are much less compressible than one disabled move.
  for(unsigned b=0;b<MOVE_POLICY_BYTES;b++)p.policies[i].disabled[b]=(uint8_t)(1+(i*73+b*31)%255);
  p.policies[i].disabled[MOVE_POLICY_BYTES-1]&=0x07;
 }
 // New inventory and high achievement bits must survive the same crowded NVS cycle.
 for(unsigned item=0;item<ITEM_COUNT;item++)current.inventory.quantity[item]=items_capacity(item);
 current.achievements.claimed=0x8008ffffu;current.achievements.cross_gen_evolutions=37;
 narrative_init(&current.narrative);current.narrative.seen=7;current.narrative.scene=N_BUG_REPORT+1;current.narrative.page=2;current.narrative.bug_evidence=1;current.narrative.focus=2;
 current.narrative.legend=1;current.narrative.pending=(encounter_t){.uid=991,.species_id=243,.level=72,.rarity=5,.hp_ratio=100,.is_shiny=true};
 current.endgame.version=1;current.endgame.champion_gyms=255;current.endgame.champion_elm=1;current.endgame.claimed=1023;
 current.endgame.lake_stage=LAKE_CALM;current.endgame.lake_level=85;current.endgame.lake_partner=(mon_t){.species_id=130,.level=85,.exp=exp_for_level(85),.hp=100,.intimacy=70,.flags=1};
 current.johto.phase=JOHTO_ACTIVE;current.johto.starter=152;current.johto.badges=255;
 for(unsigned route=0;route<8;route++)current.johto.research[route]=600;
 for(unsigned reward=0;reward<JOHTO_REWARD_COUNT;reward++)current.research_rewards[reward]=99;
 save_store_party(&current,&p);
 activity_init(&current.activities);uint8_t slots[3]={0,1,2};
 assert(activity_begin(&current.activities,ACT_SEA,p.party,p.policies,slots,3,731,false));
 for(unsigned i=0;i<ITEM_COUNT;i++)current.activities.pending.quantity[i]=60000+i;
 current.activities.bug_completed=24;current.activities.bug_choices=8;current.activities.sea_clears=12;current.activities.silver_feather=1;
 trainer_event_t event;assert(trainer_step_filtered(&current.activities.run.battle,&event,current.activities.run.policies));
 assert(save_write(&current));
 remember_unrelated();
 // Full warehouse + dense policies + shared Wi-Fi/other-game occupancy, using
 // real NVS copy-on-write, page garbage collection and remount.
 for(unsigned i=0;i<300;i++){
  current.playtime_s++;move_policy_set(&current.members.policies[i%(PARTY_MAX+BOX_CAPACITY)],85,i&1);
  assert(save_write(&current));save_t loaded;assert(save_read(&loaded)&&!memcmp(&loaded,&current,sizeof(current)));
  if(i%17==0){assert(nvs_flash_deinit()==ESP_OK&&save_init());assert(save_read(&loaded)&&!memcmp(&loaded,&current,sizeof(current)));}
 }
 assert(snapshot(image,sizeof(image)));save_t expected=current;make_save(1,7);assert(stage(image,sizeof(image),SAVE_VERSION));
 assert(nvs_flash_deinit()==ESP_OK&&reboot_restore()&&boot_result==1&&save_init());
 save_t loaded;assert(save_read(&loaded)&&save_validate_world(&loaded,&p)&&!memcmp(&loaded,&expected,sizeof(expected)));
 check_unrelated();
 printf("V31 full 759-individual dense policies + live expedition and pending rewards: stored=%zu, 300 writes, GC/remount and export/import passed\n",stored_size());
}
static void write_faults(void){
 uint8_t baseline[USB_BACKUP_BYTES],bank_baseline[SAVE_BANK_PARTITION_SIZE];memcpy(baseline,flash+live.address,sizeof(baseline));memcpy(bank_baseline,flash+SAVE_BANK_PARTITION_AT,sizeof(bank_baseline));
 save_t old,next,got;assert(save_read(&old));next=old;next.playtime_s+=333;
 bool complete=false;unsigned failures=0;remember_unrelated();
 for(unsigned cut=0;cut<1024;cut++){
  assert(nvs_flash_deinit()==ESP_OK);memcpy(flash+live.address,baseline,sizeof(baseline));memcpy(flash+SAVE_BANK_PARTITION_AT,bank_baseline,sizeof(bank_baseline));assert(save_init());
  flash_operations_left=(int)cut;bool ok=save_write(&next);flash_operations_left=-1;
  assert(nvs_flash_deinit()==ESP_OK&&save_init());
  save_read_result_t read_result=save_read_status(&got);if(read_result!=SAVE_READ_OK)fprintf(stderr,"write fault cut=%u result=%u saved=%u size=%zu\n",cut,read_result,ok,(size_t)0);assert(read_result==SAVE_READ_OK);
  assert(!memcmp(&got,&old,sizeof(got))||!memcmp(&got,&next,sizeof(got)));check_unrelated();
  if(ok){assert(!memcmp(&got,&next,sizeof(got)));complete=true;break;}
  if(cut==0)assert(!memcmp(&got,&old,sizeof(got)));
  failures++;assert(save_write(&next)&&save_read(&got)&&!memcmp(&got,&next,sizeof(got)));
 }
 assert(complete&&failures);current=next;
 printf("V31 interrupted bank/NVS writes: %u fault points, old/new complete state after remount, retry and unrelated keys passed\n",failures);
}
static void shared_occupancy(void);
static void legacy_capacity_regression(void){
 make_save(25,32);shared_occupancy();
 // Keep both the historical and replacement dungeon keys as on an upgraded
 // shared device. These values are synthetic public fixtures, never player data.
 nvs_handle_t h;dungeon_t d={0};memcpy(&d,dungeon_history,sizeof(dungeon_history));d.version=4;
 assert(nvs_open("pw_dungeon",NVS_READWRITE,&h)==ESP_OK);
 assert(nvs_set_blob(h,"run_v4",&d,sizeof(d))==ESP_OK&&nvs_commit(h)==ESP_OK);nvs_close(h);
 bool full=false;save_v22_t raw={0};raw.version=21;
 raw.species=current.species;raw.level=current.level;raw.exp=current.exp;raw.pet=current.pet;
 party_serialize(&current.members,raw.party);memcpy(raw.dex.seen,current.dex.seen,19);memcpy(raw.dex.caught,current.dex.caught,19);memcpy(raw.dex.shiny_seen,current.dex.shiny_seen,19);memcpy(raw.dex.shiny_caught,current.dex.shiny_caught,19);memcpy(raw.inventory.quantity,current.inventory.quantity,sizeof(raw.inventory.quantity));raw.exploration=current.exploration;
 raw.challenge=current.challenge;raw.dungeon=current.dungeon;
 for(unsigned i=0;i<8;i++){
  raw.playtime_s++;assert(nvs_open("pokewalk",NVS_READWRITE,&h)==ESP_OK);
  esp_err_t e=nvs_set_blob(h,"state",&raw,sizeof(raw));nvs_close(h);
  if(e==ESP_ERR_NVS_NOT_ENOUGH_SPACE){full=true;break;}assert(e==ESP_OK);
 }
 assert(full);assert(save_read(&current));remember_unrelated();
 for(unsigned i=0;i<300;i++){current.playtime_s++;assert(save_write(&current));}
 check_unrelated();
 puts("Synthetic shared-device occupancy: V21 raw save reproduces NOT_ENOUGH_SPACE; V31 preserves all keys and saves 300 times");
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
 save_t expected=current;assert(save_write(&current));assert(stage(image,image_length,source_version));
 assert(nvs_flash_deinit()==ESP_OK&&reboot_restore()&&boot_result==1&&save_init());
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
 assert(nvs_flash_deinit()==ESP_OK&&reboot_restore()&&boot_result==1&&save_init());
 assert(save_read_status(&current)==SAVE_READ_OK&&!memcmp(&current,&expected,sizeof(current)));check_unrelated();
 assert(nvs_flash_deinit()==ESP_OK&&reboot_restore()&&boot_result==0&&save_init());
 assert(save_read_status(&current)==SAVE_READ_OK&&!memcmp(&current,&expected,sizeof(current)));
 printf("Private isolated NVS: old import/boot, 300 writes/remount, new export/import with distinct progress; stored=%zu, unrelated_keys=%u unchanged\n",stored_size(),retained_count);
}
static void dungeon_cleanup_case(unsigned mode){
 nvs_handle_t h;assert(nvs_open("pw_dungeon",NVS_READWRITE,&h)==ESP_OK);
 unsigned char obsolete[788];memset(obsolete,0xa5,sizeof(obsolete));
 assert(nvs_set_blob(h,"run_v1",obsolete,sizeof(obsolete))==ESP_OK);
 dungeon_v4_t previous={0};memcpy(&previous,dungeon_history,sizeof(dungeon_history));previous.version=4;
 dungeon_t expected={0};memcpy(&expected,&previous,sizeof(dungeon_v2_t));expected.version=6;
 for(unsigned side=0;side<2;side++)for(unsigned i=0;i<6;i++)memset(expected.battle.session.sides[side].mons[i].pp,0,4);
 for(unsigned i=0;i<3;i++)memcpy(&expected.members[i],&previous.members[i],sizeof(mon_v27_t));
 memcpy(expected.slots,previous.slots,3);expected.count=previous.count;expected.base_level=previous.base_level;
 if(mode==5||mode==6){
  dungeon_v2_t old={.version=2,.phase=DUNGEON_LOST,.pending=mode==6};
  assert(nvs_set_blob(h,"run_v2",&old,sizeof(old))==ESP_OK);
 }else if(mode!=4){
  assert(nvs_set_blob(h,"run_v3",dungeon_history,sizeof(dungeon_history)-(mode==3))==ESP_OK);
  if(mode==1||mode==2){dungeon_v4_t written=previous;if(mode==2)written.count=255;assert(nvs_set_blob(h,"run_v4",&written,sizeof(written))==ESP_OK);}
 }
 assert(nvs_commit(h)==ESP_OK);nvs_close(h);
 uint8_t before[USB_BACKUP_BYTES];memcpy(before,flash+live.address,sizeof(before));
 if(mode==7)fail_storage_write=true;
 dungeon_load();fail_storage_write=false;
 const dungeon_t *run=dungeon_get();
 if(mode==0||mode==1||mode==7)assert(!memcmp(run,&expected,sizeof(expected)));
 if(mode==5)assert(run->version==6&&run->phase==DUNGEON_LOST);
 if(mode==2||mode==3||mode==4||mode==6||mode==7)assert(!memcmp(before,flash+live.address,sizeof(before)));
 assert(nvs_flash_deinit()==ESP_OK&&save_init());
 assert(nvs_open("pw_dungeon",NVS_READONLY,&h)==ESP_OK);size_t n=0;
 esp_err_t e=nvs_get_blob(h,"run_v1",NULL,&n);
 assert(e==((mode==0||mode==1||mode==5)?ESP_ERR_NVS_NOT_FOUND:ESP_OK));
 if(mode==0||mode==7){unsigned char raw[sizeof(dungeon_history)];n=sizeof(raw);assert(nvs_get_blob(h,"run_v3",raw,&n)==ESP_OK&&!memcmp(raw,dungeon_history,n));}
 if(mode==1){n=0;assert(nvs_get_blob(h,"run_v3",NULL,&n)==ESP_ERR_NVS_NOT_FOUND);dungeon_v4_t raw;n=sizeof(raw);assert(nvs_get_blob(h,"run_v4",&raw,&n)==ESP_OK&&!memcmp(&raw,&previous,n));}
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
   assert(read_nvs(image));uint32_t original_crc=restore_crc32(image,image_length);
   assert(save_read(&current)&&save_write(&current));
   uint8_t live_before[USB_BACKUP_BYTES];memcpy(live_before,flash+live.address,sizeof(live_before));
   bool valid=stage(image,image_length,source.version);
   assert(restore_crc32(image,image_length)==original_crc);
   assert(!memcmp(live_before,flash+live.address,sizeof(live_before)));
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
 assert(nvs_flash_deinit()==ESP_OK);assert(reboot_restore());assert(boot_result==1&&boot_crc==restore_crc32(image,image_length));assert(save_init());
 assert(save_read_status(&loaded)==SAVE_READ_OK&&save_validate_world(&loaded,&party));
 assert(loaded.species==25&&loaded.level==32&&!memcmp(&loaded,&wanted,sizeof(wanted)));
 nvs_handle_t h;uint8_t value;assert(nvs_open("pokewalk",NVS_READONLY,&h)==ESP_OK);
 assert(nvs_get_u8(h,"volume",&value)==ESP_OK&&value==32);assert(nvs_get_u8(h,"brightness",&value)==ESP_OK&&value==42);nvs_close(h);
 assert(nvs_flash_deinit()==ESP_OK);assert(reboot_restore());assert(boot_result==0);assert(save_init());assert(save_read(&loaded)&&loaded.species==25); // another boot stays restored
 current=loaded;assert(snapshot(image,sizeof(image)));make_save(1,7);assert(stage(image,sizeof(image),SAVE_VERSION));
 flash[temp.address+0x1000]^=1;assert(nvs_flash_deinit()==ESP_OK);assert(reboot_restore());assert(boot_result==2);assert(save_init());assert(save_read(&loaded)&&!memcmp(&loaded,&before,sizeof(before)));
 historical_restore();shared_occupancy();policy_capacity_stress();write_faults();
 assert(nvs_flash_deinit()==ESP_OK);puts("Real ESP-IDF NVS + production save/device/journal: historical V5-V31, distinct saves, schema rejection, settings, restore, second boot and rollback passed");
}
