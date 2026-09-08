#!/usr/bin/env python3
"""Exercise production world/save code with NVS failures and simulated reboots.

Only RTOS, WiFi and NVS device services are mocked. Starter transactions, V5
serialization, party/dex updates and runtime battle-session ownership execute
the actual firmware sources. UI/real-flash behavior is verified separately.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "firmware/main"

STUB = r"""
#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int esp_err_t;
#define ESP_OK 0
#define ESP_FAIL -1
#define ESP_ERR_NVS_NOT_FOUND 0x1102
#define ESP_ERR_NVS_NO_FREE_PAGES 0x110d
#define ESP_ERR_NVS_NEW_VERSION_FOUND 0x1110
#define ESP_ERROR_CHECK(x) assert((x)==ESP_OK)
static inline void test_log(const char *tag,const char *fmt,...) {(void)tag;(void)fmt;}
#define ESP_LOGI(...) test_log(__VA_ARGS__)
#define ESP_LOGW(...) test_log(__VA_ARGS__)
#define ESP_LOGE(...) test_log(__VA_ARGS__)
static inline const char *esp_err_to_name(esp_err_t e) {(void)e;return "injected";}
typedef int BaseType_t;
typedef struct {bool held;} test_mutex_t;
typedef test_mutex_t *SemaphoreHandle_t;
extern test_mutex_t test_mutexes[128];
extern unsigned test_mutex_count;
#define portMAX_DELAY 0xffffffffu
#define pdTRUE 1
#define pdPASS 1
#define pdMS_TO_TICKS(x) (x)
static inline SemaphoreHandle_t xSemaphoreCreateMutex(void) {
    assert(test_mutex_count<128);return &test_mutexes[test_mutex_count++];
}
static inline int xSemaphoreTake(SemaphoreHandle_t s,unsigned timeout) {
    (void)timeout;assert(s&&!s->held);s->held=true;return pdTRUE;
}
static inline void xSemaphoreGive(SemaphoreHandle_t s) {assert(s&&s->held);s->held=false;}
// A simulated reboot starts world state but does not run the background task.
#define xTaskCreate(...) pdPASS
static inline void vTaskDelay(unsigned t) {(void)t;}
extern int64_t test_time;
static inline int64_t esp_timer_get_time(void) {return test_time;}
typedef unsigned nvs_handle_t;
#define NVS_READONLY 0
#define NVS_READWRITE 1
esp_err_t nvs_flash_init(void);
esp_err_t nvs_flash_erase(void);
esp_err_t nvs_open(const char*,int,nvs_handle_t*);
esp_err_t nvs_set_blob(nvs_handle_t,const char*,const void*,size_t);
esp_err_t nvs_get_blob(nvs_handle_t,const char*,void*,size_t*);
esp_err_t nvs_set_u8(nvs_handle_t,const char*,uint8_t);
esp_err_t nvs_get_u8(nvs_handle_t,const char*,uint8_t*);
esp_err_t nvs_erase_key(nvs_handle_t,const char*);
esp_err_t nvs_commit(nvs_handle_t);
void nvs_close(nvs_handle_t);
typedef int wifi_auth_mode_t;
enum {WIFI_AUTH_OPEN,WIFI_AUTH_WEP,WIFI_AUTH_WPA_PSK,WIFI_AUTH_WPA2_PSK,
      WIFI_AUTH_WPA_WPA2_PSK,WIFI_AUTH_WPA3_PSK,WIFI_AUTH_WPA2_WPA3_PSK,
      WIFI_AUTH_WPA2_ENTERPRISE,WIFI_AUTH_WPA3_ENTERPRISE,WIFI_AUTH_WAPI_PSK};
typedef struct {uint8_t bssid[6],ssid[33],primary;int8_t rssi;wifi_auth_mode_t authmode;} wifi_ap_record_t;
typedef struct {int unused;} wifi_init_config_t;
#define WIFI_INIT_CONFIG_DEFAULT() ((wifi_init_config_t){0})
#define WIFI_MODE_STA 1
static inline esp_err_t esp_netif_init(void) {return ESP_OK;}
static inline esp_err_t esp_event_loop_create_default(void) {return ESP_OK;}
static inline void esp_netif_create_default_wifi_sta(void) {}
static inline esp_err_t esp_wifi_init(const wifi_init_config_t *p) {(void)p;return ESP_OK;}
static inline esp_err_t esp_wifi_set_mode(int m) {(void)m;return ESP_OK;}
static inline esp_err_t esp_wifi_start(void) {return ESP_OK;}
static inline esp_err_t esp_wifi_scan_start(void *p,bool b) {(void)p;(void)b;return ESP_FAIL;}
static inline esp_err_t esp_wifi_scan_get_ap_records(uint16_t *n,wifi_ap_record_t *p) {(void)n;(void)p;return ESP_FAIL;}
static inline int bsp_battery_soc(void) {return 100;}
"""

DRIVER = r"""
#include "device_stubs.h"
#include "world.h"
#include "save.h"
#include "exp.h"
test_mutex_t test_mutexes[128];
unsigned test_mutex_count;
int64_t test_time=1000000;
static uint8_t disk[sizeof(save_t)+16],staged[sizeof(save_t)+16];
static size_t disk_len,staged_len;
static bool have_disk,have_opening,namespace_exists,staging,stage_opening;
static unsigned commits,writes,erase_calls,tests;
static int failure,init_error;
static bool inspect_commit,background_update;

esp_err_t nvs_flash_init(void) {return init_error;}
esp_err_t nvs_flash_erase(void) {erase_calls++;return ESP_OK;}
esp_err_t nvs_open(const char *ns,int mode,nvs_handle_t *out) {
    assert(!strcmp(ns,"pokewalk"));
    if(failure==1)return ESP_FAIL;
    if(mode==NVS_READONLY&&!namespace_exists)return ESP_ERR_NVS_NOT_FOUND;
    namespace_exists=true;*out=1;return ESP_OK;
}
esp_err_t nvs_set_blob(nvs_handle_t h,const char *key,const void *data,size_t len) {
    (void)h;assert(!strcmp(key,"state"));writes++;
    if(failure==2)return ESP_FAIL;
    assert(len<=sizeof(staged));memcpy(staged,data,len);staged_len=len;staging=true;return ESP_OK;
}
esp_err_t nvs_get_blob(nvs_handle_t h,const char *key,void *out,size_t *len) {
    (void)h;assert(!strcmp(key,"state"));
    if(failure==5)return ESP_FAIL;
    if(!have_disk)return ESP_ERR_NVS_NOT_FOUND;
    if(out){if(*len<disk_len)return ESP_FAIL;memcpy(out,disk,disk_len);}
    *len=disk_len;return ESP_OK;
}
esp_err_t nvs_set_u8(nvs_handle_t h,const char *key,uint8_t value) {
    (void)h;assert(!strcmp(key,"opening")&&value==1);
    if(failure==3)return ESP_FAIL;
    stage_opening=true;return ESP_OK;
}
esp_err_t nvs_get_u8(nvs_handle_t h,const char *key,uint8_t *out) {
    (void)h;assert(!strcmp(key,"opening"));if(!have_opening)return ESP_ERR_NVS_NOT_FOUND;
    *out=1;return ESP_OK;
}
esp_err_t nvs_erase_key(nvs_handle_t h,const char *key) {(void)h;(void)key;erase_calls++;return ESP_OK;}
esp_err_t nvs_commit(nvs_handle_t h) {
    (void)h;
    if(inspect_commit){
        world_t before={0};world_snapshot(&before);
        assert(world_needs_starter()&&before.species==0);
        if(background_update)world_mark_seen(74,true);
    }
    if(failure==4)return ESP_FAIL;
    if(staging){memcpy(disk,staged,staged_len);disk_len=staged_len;have_disk=true;}
    if(stage_opening)have_opening=true;
    staging=stage_opening=false;commits++;return ESP_OK;
}
void nvs_close(nvs_handle_t h) {(void)h;staging=stage_opening=false;}
void sens_init(sens_core_t *core) {memset(core,0,sizeof(*core));}

// Including production C makes only test fixtures able to seed a queue/save;
// behavior under test always uses public world/save APIs.
static unsigned alert_count, alert_rarity; static bool alert_shiny;
void sfx_encounter(uint8_t rarity, bool shiny) { alert_count++;alert_rarity=rarity;alert_shiny=shiny; }
#define TAG starter_world_tag
#include "world.c"
#undef TAG
#define TAG starter_save_tag
#include "save.c"
#include "achievements.c"
#undef TAG

static void fresh(void) {
    memset(disk,0,sizeof(disk));disk_len=0;have_disk=have_opening=namespace_exists=false;
    staging=stage_opening=inspect_commit=background_update=false;
    failure=init_error=0;commits=writes=erase_calls=0;
    test_mutex_count=0;memset(test_mutexes,0,sizeof(test_mutexes));
    assert(world_start());assert(world_needs_starter());assert(s_party.party_count==0);
}
static void reboot(void) {
    assert(!s_lock->held&&!s_save_lock->held);
    test_time=1000000;assert(world_start());
}
static void one_starter(unsigned sid) {
    world_t snapshot={0};world_snapshot(&snapshot);
    assert(!world_needs_starter());assert(snapshot.species==sid&&snapshot.level==1&&snapshot.exp==0);
    assert(s_party.party_count==1&&party_total(&s_party)==1&&s_party.party[0].species_id==sid);
    assert(dex_is_caught(world_dex(),sid)&&dex_count_caught(world_dex())==1);
    assert(save_opening_seen());
    save_t persisted;assert(save_read_status(&persisted)==SAVE_READ_OK);
    assert(persisted.version==SAVE_VERSION&&persisted.species==sid&&persisted.level==1&&persisted.exp==0);
    assert(persisted.party[0]==1&&persisted.party[2]==sid&&persisted.opening_seen);
}
static void legacy(void) {
    fresh();save_t saved={0};saved.version=SAVE_VERSION;nurture_init(&saved.pet);
    saved.pet.intimacy=42*NURT_Q;saved.pet.satiety=37*NURT_Q;saved.pet.last_us=777777;
    party_t p;party_init(&p);
    mon_t first={.species_id=150,.level=57,.hp=83,.intimacy=42,.explore_value=89,.flags=1,.exp=exp_for_level(57)};
    mon_t second={.species_id=133,.level=23,.hp=79,.nickname_idx=3,.exp=exp_for_level(23)};
    assert(party_receive(&p,&first)&&party_receive(&p,&second));party_serialize(&p,saved.party);
    saved.species=150;saved.level=57;saved.exp=first.exp;saved.scans=7654;saved.motion_q10=12345;
    enc_queue_init(&saved.queue);encounter_t e={.species_id=74,.ts=55,.rarity=3,.hp_ratio=100};enc_queue_push(&saved.queue,&e);
    dex_init(&saved.dex);dex_mark_caught(&saved.dex,150,true);dex_mark_caught(&saved.dex,133,false);
    assert(save_write(&saved));reboot();
    uint8_t old[sizeof(disk)];memcpy(old,disk,sizeof(old));unsigned before=commits;
    assert(!world_needs_starter());
    for(unsigned i=0;i<4;i++)assert(world_choose_starter((unsigned[]){1,4,7,25}[i])==WORLD_STARTER_ALREADY_CHOSEN);
    assert(commits==before&&!memcmp(disk,old,sizeof(old)));
    assert(s_w.species==150&&s_w.level==57&&s_w.exp==first.exp&&s_w.explore_value==89);
    assert(s_w.pet.intimacy==42*NURT_Q&&s_w.pet.last_us==-1&&s_w.scans==7654&&s_motion_q10==12345);
    assert(s_party.party_count==2&&!memcmp(&s_dex,&saved.dex,sizeof(s_dex)));
    assert(!memcmp(&s_queue,&saved.queue,sizeof(s_queue))&&erase_calls==0);tests++;
}
static void protected_error(int which) {
    legacy();uint8_t old[sizeof(disk)];save_t damaged;memcpy(&damaged,disk,sizeof(damaged));
    if(which==0)damaged.version=4;
    else if(which==1)disk_len--;
    else if(which==2)failure=5;
    else if(which==3)init_error=ESP_ERR_NVS_NO_FREE_PAGES;
    else if(which==4)init_error=ESP_ERR_NVS_NEW_VERSION_FOUND;
    else if(which==5)damaged.party[2]=0;
    else if(which==6)failure=1;
    else if(which==7){damaged.party[2+PARTY_MAX*MON_BYTES]=152;damaged.party[2+PARTY_MAX*MON_BYTES+1]=12;}
    else if(which==8){memset(damaged.party,0,PARTY_BYTES);damaged.species=damaged.level=damaged.exp=0;}
    else if(which==9){memset(damaged.party,0,PARTY_BYTES);damaged.species=damaged.level=damaged.exp=0;memset(damaged.dex.caught,0,DEX_BYTES);}
    else if(which==10){damaged.party[2+PARTY_MAX*MON_BYTES]=2;damaged.party[2+PARTY_MAX*MON_BYTES+1]=12;}
    else if(which==11)damaged.party[2+2*MON_BYTES+7]=1;
    else if(which==12)damaged.queue.count=255;
    else if(which==13)damaged.queue.count=ENC_QUEUE_CAP+1;
    else if(which==14)damaged.queue.items[0].species_id=0;
    else if(which==15)damaged.queue.items[0].species_id=152;
    else if(which==16)damaged.queue.items[0].uid=0;
    else if(which==17){damaged.queue.count=2;damaged.queue.items[1]=damaged.queue.items[0];}
    else if(which==18)damaged.queue.items[0].rarity=0;
    else if(which==19)damaged.queue.items[0].rarity=6;
    else if(which==20)damaged.queue.items[0].hp_ratio=101;
    else if(which==21)memset(&damaged.queue.items[0].is_shiny,2,sizeof(bool));
    else if(which==22)memset(&damaged.queue.items[0].is_transient,2,sizeof(bool));
    else if(which==23)memset(&damaged.queue.items[0].exp_granted,2,sizeof(bool));
    else if(which==24)memset(&damaged.opening_seen,2,sizeof(bool));
    memcpy(disk,&damaged,sizeof(damaged));
    memcpy(old,disk,sizeof(old));unsigned before=writes;reboot();
    assert(world_needs_starter());
    assert(world_choose_starter(25)==WORLD_STARTER_STORAGE_UNAVAILABLE);
    world_debug_save();assert(writes==before&&!memcmp(disk,old,sizeof(old))&&erase_calls==0);tests++;
}
static void valid_queue_boundaries(void) {
    legacy();save_t saved;assert(save_read_status(&saved)==SAVE_READ_OK);
    enc_queue_init(&saved.queue);saved.queue.count=ENC_QUEUE_CAP;saved.queue.next_uid=0;
    for(unsigned i=0;i<ENC_QUEUE_CAP;i++)saved.queue.items[i]=(encounter_t){
        .uid=i+1,.species_id=i%2?1:151,.rarity=i%2?1:5,.hp_ratio=i%2?0:100,
        .is_shiny=i%2,.is_transient=!(i%2),.exp_granted=i%2};
    saved.queue.items[ENC_QUEUE_CAP-2].uid=UINT16_MAX;
    assert(save_write(&saved));reboot();assert(!world_needs_starter());
    // Zero HP / granted EXP are valid legacy fields, but identify processed
    // encounters; the remaining eight untouched entries trim to the newest five.
    assert(s_queue.count==ENC_QUEUE_LIMIT&&s_queue.dropped==3&&s_queue.next_uid==0);
    for(unsigned i=0;i<ENC_QUEUE_LIMIT;i++)
        assert(!memcmp(&s_queue.items[i],&saved.queue.items[6+2*i],sizeof(encounter_t)));
    battle_session_t session;assert(world_battle_get_uid(UINT16_MAX,&session));tests++;
    // Taking entries leaves tail bytes behind; an empty active prefix is valid
    // even when the unowned tail no longer contains canonical encounter values.
    memset(saved.queue.items,0xff,sizeof(saved.queue.items));saved.queue.count=0;
    assert(save_write(&saved));reboot();assert(!world_needs_starter()&&s_queue.count==0);
    assert(world_choose_starter(25)==WORLD_STARTER_ALREADY_CHOSEN);tests++;
}
static void battles(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
    enc_queue_init(&s_queue);battle_session_t got={0},sample={.rng=0x12345678,.pet_species=1,.wild_species=19,.initialized=true};
    for(unsigned i=0;i<ENC_QUEUE_LIMIT;i++){
        encounter_t e={.ts=100+i,.species_id=19,.rarity=1,.hp_ratio=100};enc_queue_push(&s_queue,&e);
        uint16_t uid=s_queue.items[i].uid;assert(world_battle_get_uid(uid,&got));
        battle_session_t zero={0};assert(!memcmp(&got,&zero,sizeof(got)));
        sample.rng++;assert(world_battle_set_uid(uid,&sample));assert(world_battle_get_uid(uid,&got));assert(!memcmp(&got,&sample,sizeof(got)));
    }
    uint16_t removed=s_queue.items[0].uid;uint32_t timestamp=s_queue.items[0].ts;
    assert(world_take_uid(removed,NULL));assert(!world_battle_get_uid(removed,&got)&&!world_battle_set_uid(removed,&sample));
    s_queue.next_uid=removed;encounter_t again={.ts=timestamp,.species_id=19,.rarity=1,.hp_ratio=100};enc_queue_push(&s_queue,&again);
    assert(world_battle_get_uid(removed,&got));battle_session_t zero={0};assert(!memcmp(&got,&zero,sizeof(got)));
    assert(world_battle_set_uid(removed,&sample));enc_queue_find(&s_queue,removed)->ts++;
    assert(world_battle_get_uid(removed,&got)&&!memcmp(&got,&zero,sizeof(got)));
    assert(world_battle_set_uid(removed,&sample));world_debug_save();reboot();
    assert(world_battle_get_uid(removed,&got)&&!memcmp(&got,&zero,sizeof(got)));
    assert(!world_battle_get_uid(0,&got)&&!world_battle_set_uid(0,&sample));tests++;
}
int main(void) {
    for(unsigned i=0;i<4;i++){
        unsigned sid=(unsigned[]){1,4,7,25}[i];fresh();inspect_commit=true;
        assert(world_choose_starter(sid)==WORLD_STARTER_OK);inspect_commit=false;one_starter(sid);
        unsigned before=commits;assert(world_choose_starter(sid)==WORLD_STARTER_ALREADY_CHOSEN);
        assert(world_choose_starter(sid==25?1:25)==WORLD_STARTER_ALREADY_CHOSEN);assert(commits==before);
        reboot();one_starter(sid);tests++;
    }
    for(failure=1;failure<=4;){int mode=failure;fresh();failure=mode;inspect_commit=true;
        assert(world_choose_starter(4)==WORLD_STARTER_SAVE_FAILED);
        assert(world_needs_starter()&&s_party.party_count==0&&s_w.species==0&&dex_count_caught(&s_dex)==0);
        failure=0;assert(world_choose_starter(7)==WORLD_STARTER_OK);inspect_commit=false;one_starter(7);
        tests++;failure=mode+1;
    }
    fresh();for(unsigned sid=0;sid<152;sid++)if(sid!=1&&sid!=4&&sid!=7&&sid!=25)
        assert(world_choose_starter(sid)==WORLD_STARTER_INVALID);
    assert(!have_disk&&s_party.party_count==0&&writes==0);tests++;
    fresh();world_debug_save();assert(have_disk);reboot();assert(world_needs_starter()&&s_w.species==0);
    assert(save_mark_opening_seen());reboot();assert(world_needs_starter()&&save_opening_seen());
    assert(world_choose_starter(25)==WORLD_STARTER_OK);one_starter(25);tests++;
    fresh();namespace_exists=have_opening=true;reboot();assert(world_needs_starter());
    assert(world_choose_starter(1)==WORLD_STARTER_OK);one_starter(1);tests++;
    fresh();inspect_commit=background_update=true;assert(world_choose_starter(1)==WORLD_STARTER_OK);
    inspect_commit=background_update=false;assert(dex_is_seen(&s_dex,74)&&s_dirty);world_debug_save();
    reboot();assert(dex_is_seen(&s_dex,74));tests++;
    legacy();for(int mode=0;mode<25;mode++)protected_error(mode);valid_queue_boundaries();battles();
    printf("{\"cases\":%u,\"save_version\":%d,\"save_bytes\":%zu,\"battle_slots\":%d,\"erase_calls\":%u}\n",
           tests,SAVE_VERSION,sizeof(save_t),ENC_QUEUE_LIMIT,erase_calls);
    return 0;
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="starter-verify-") as temp:
        temp = Path(temp)
        (temp / "device_stubs.h").write_text(STUB)
        for name in ("esp_event.h", "esp_log.h", "esp_timer.h", "esp_wifi.h", "nvs.h",
                     "nvs_flash.h", "bsp_battery.h", "freertos/FreeRTOS.h",
                     "freertos/semphr.h", "freertos/task.h"):
            path = temp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "device_stubs.h"\n')
        (temp / "driver.c").write_text(DRIVER)
        command = ["cc", "-std=gnu11", "-DHOST_BUILD", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                   "-Wno-unused-variable", "-Wno-unused-function", "-Wno-unused-parameter",
                   "-ffunction-sections", "-fdata-sections", "-I", str(temp), "-I", str(MAIN),
                   str(temp / "driver.c"), *[str(MAIN / name) for name in
                   ("party.c", "encounter.c", "nurture.c", "exp.c", "items.c")], "-lz",
                   "-Wl,-dead_strip" if sys.platform == "darwin" else "-Wl,--gc-sections",
                   "-o", str(temp / "verify")]
        if args.sanitize:
            command[1:1] = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        subprocess.run(command, check=True)
        result = subprocess.run([str(temp / "verify")], check=True, capture_output=True, text=True)
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        summary["sanitized"] = args.sanitize
        summary["scope"] = "actual world.c/save.c/party.c/encounter.c; simulated NVS/RTOS/device services"
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
