#!/usr/bin/env python3
"""Verify five-slot FIFO, V5 migration and active encounter ownership in real C.

Reuses the starter test's fake NVS/device boundary, but uses real pthread
mutexes and an overlapping scan to exercise first-attack commit ordering.
No rendering or battle formulas are mirrored here.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import verify_starter as starter


def replace_once(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def harness() -> tuple[str, str]:
    stub = starter.STUB
    stub = replace_once(stub, "#include <assert.h>", """#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <sched.h>
extern atomic_bool worker_waiting;
extern _Thread_local int is_scan_worker;""")
    stub = replace_once(stub, "typedef struct {bool held;} test_mutex_t;",
                        "typedef struct {pthread_mutex_t mutex;bool held;} test_mutex_t;")
    start = stub.index("static inline SemaphoreHandle_t xSemaphoreCreateMutex(void)")
    end = stub.index("// A simulated reboot", start)
    stub = stub[:start] + r"""
static inline SemaphoreHandle_t xSemaphoreCreateMutex(void) {
    assert(test_mutex_count<128);test_mutex_t *s=&test_mutexes[test_mutex_count++];
    pthread_mutexattr_t attr;assert(!pthread_mutexattr_init(&attr));
    assert(!pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_ERRORCHECK));
    assert(!pthread_mutex_init(&s->mutex,&attr));pthread_mutexattr_destroy(&attr);return s;
}
static inline int xSemaphoreTake(SemaphoreHandle_t s,unsigned timeout) {
    (void)timeout;assert(s);if(is_scan_worker)atomic_store(&worker_waiting,true);
    assert(!pthread_mutex_lock(&s->mutex));assert(!s->held);s->held=true;return pdTRUE;
}
static inline void xSemaphoreGive(SemaphoreHandle_t s) {
    assert(s&&s->held);s->held=false;assert(!pthread_mutex_unlock(&s->mutex));
}
""" + stub[end:]
    driver = starter.DRIVER[:starter.DRIVER.index("int main(void) {")]
    driver = replace_once(driver, "static bool inspect_commit,background_update;", """
static bool inspect_commit,background_update;
static void (*extra_commit_hook)(void);
atomic_bool worker_waiting;
_Thread_local int is_scan_worker;
""")
    driver = replace_once(driver, "    if(failure==4)return ESP_FAIL;",
                          "    if(extra_commit_hook)extra_commit_hook();\n    if(failure==4)return ESP_FAIL;")
    driver = replace_once(driver, "    test_mutex_count=0;memset(test_mutexes,0,sizeof(test_mutexes));", """
    for(unsigned i=0;i<test_mutex_count;i++)assert(!pthread_mutex_destroy(&test_mutexes[i].mutex));
    test_mutex_count=0;memset(test_mutexes,0,sizeof(test_mutexes));extra_commit_hook=NULL;
""")
    return stub, driver + CASES


CASES = r"""
// Only species statistics used to choose a scan result are mocked. Actual
// encounter.c owns identity generation, FIFO and scan insertion.
bool assets_species(uint16_t id,species_t *out) {
    if(id<1||id>151)return false;memset(out,0,sizeof(*out));out->id=id;
    out->hp=out->attack=out->defense=out->special=out->speed=20+id%80;return true;
}
uint32_t assets_species_count(void) {return 151;}
// Campaigns are inactive in this world/queue harness; real validation is tested by verify_combat_system.
bool trainer_store_valid(const trainer_store_t *s) {return !s->session.active && !s->league_active;}

static void seed_pending(unsigned count) {
    enc_queue_init(&s_queue);
    for(unsigned i=0;i<count;i++) {
        encounter_t e={.species_id=19+i,.ts=100+i,.rarity=i?1:5,.hp_ratio=100};
        enc_queue_push(&s_queue,&e);
    }
    s_w.pending=s_queue.count;s_dirty=true;world_debug_save();
    s_last_n=1;memset(s_recs,0,sizeof(s_recs));s_recs[0].rssi=-60;s_recs[0].ssid[0]='x';
}
static battle_session_t prepared(uint16_t uid) {
    encounter_t entry;assert(world_get_encounter_uid(uid,&entry));
    battle_session_t session={.initialized=true,.pet_species=1,.wild_species=entry.species_id,
                             .rng=0x12345678,.pet_hp=25,.pet_hp_max=25,.wild_hp=15,.wild_hp_max=15};
    assert(world_battle_set_uid(uid,&session));return session;
}
static void started(uint16_t uid,battle_session_t *session) {
    session->started=true;session->wild_hp--;
    assert(world_battle_set_uid(uid,session));
    assert(xSemaphoreTake(s_lock,portMAX_DELAY));
    assert(!enc_queue_find(&s_queue,uid)&&s_active.encounter.uid==uid);
    xSemaphoreGive(s_lock);
    encounter_t entry;assert(world_get_encounter_uid(uid,&entry));
    save_t persisted;assert(save_read_status(&persisted)==SAVE_READ_OK);
    assert(!enc_queue_find(&persisted.queue,uid));
}
static void fifo_and_pending(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);seed_pending(5);
    enc_queue_t visible;world_queue_snapshot(&visible);assert(visible.count==5);
    uint16_t oldest=s_queue.items[0].uid,retained=s_queue.items[3].uid;
    battle_session_t session=prepared(oldest);unsigned before=commits;
    world_end_active_encounter();assert(s_queue.count==5&&world_battle_get_uid(oldest,&session));
    assert(commits==before);assert(world_debug_spawn());
    assert(s_queue.count==5&&s_queue.dropped==1&&!world_get_encounter_uid(oldest,&(encounter_t){0}));
    assert(visible.items[0].uid==oldest&&visible.dropped==0); // Displayed snapshot stays immutable.
    world_queue_snapshot(&visible);assert(visible.items[0].uid!=oldest&&visible.dropped==1);
    assert(world_get_encounter_uid(retained,&(encounter_t){0}));tests++;
}
static void begin_failures(void) {
    const int modes[]={1,2,4}; // NVS open, blob write, commit; no opening-key rewrite.
    for(unsigned i=0;i<sizeof(modes)/sizeof(modes[0]);i++) {
        int mode=modes[i];
        fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);seed_pending(5);
        uint16_t uid=s_queue.items[0].uid;enc_queue_t original=s_queue;
        battle_session_t initial=prepared(uid),next=initial,got;
        next.started=true;next.wild_hp--;uint8_t old[sizeof(disk)];memcpy(old,disk,sizeof(old));
        failure=mode;
        assert(!world_battle_set_uid(uid,&next));failure=0;
        assert(!s_active.encounter.uid&&!memcmp(&s_queue,&original,sizeof(original)));
        assert(world_battle_get_uid(uid,&got)&&!memcmp(&got,&initial,sizeof(got)));
        assert(!memcmp(disk,old,sizeof(old))&&s_dirty);
        started(uid,&next);assert(s_queue.count==4&&s_w.pending==4&&s_queue.dropped==0);
        unsigned before=commits;next.rng++;assert(world_battle_set_uid(uid,&next));assert(commits==before);
        reboot();assert(!world_get_encounter_uid(uid,&(encounter_t){0})&&!world_battle_get_uid(uid,&got));
        assert(s_queue.count==4);tests++;
    }
}
static void active_lifetime(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);seed_pending(5);
    uint16_t uid=s_queue.items[0].uid;uint32_t ts=s_queue.items[0].ts;
    battle_session_t session=prepared(uid),got;started(uid,&session);
    // A second encounter cannot replace the active one.
    uint16_t other=s_queue.items[0].uid;battle_session_t second=prepared(other);second.started=true;
    assert(!world_battle_set_uid(other,&second));assert(enc_queue_find(&s_queue,other));
    for(unsigned i=0;i<12;i++)assert(world_debug_spawn());
    assert(s_queue.count==5&&s_w.pending==5&&s_queue.dropped==11);
    encounter_t entry;assert(world_get_encounter_uid(uid,&entry)&&entry.ts==ts&&entry.species_id==19);
    assert(world_battle_get_uid(uid,&got)&&!memcmp(&got,&session,sizeof(got)));
    // Explicitly drive allocation through the active uid on wrap.
    s_queue.next_uid=uid;assert(world_debug_spawn());
    for(unsigned i=0;i<s_queue.count;i++)assert(s_queue.items[i].uid!=uid);
    world_update_hp_uid(uid,0);assert(world_get_encounter_uid(uid,&entry)&&entry.hp_ratio==0);
    assert(world_mark_exp_granted_uid(uid)&&!world_mark_exp_granted_uid(uid));
    world_grant_exp(60);assert(s_w.exp==60&&world_get_encounter_uid(uid,&entry)&&entry.exp_granted);
    // A won target remains active for its single capture opportunity.
    session.finished=session.won=session.reward_settled=true;session.capture_used_after_win=false;
    assert(world_battle_set_uid(uid,&session));
    assert(world_battle_get_uid(uid,&got)&&got.won&&!got.capture_used_after_win);
    unsigned pending=s_queue.count;world_end_active_encounter();
    assert(!world_get_encounter_uid(uid,&entry)&&!world_battle_set_uid(uid,&session));
    assert(s_queue.count==pending);world_end_active_encounter();
    reboot();assert(!world_get_encounter_uid(uid,&entry)&&s_w.exp==60);tests++;
}
static void active_capture_and_take(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);seed_pending(2);
    uint16_t uid=s_queue.items[0].uid;battle_session_t session=prepared(uid);started(uid,&session);
    mon_t wrong={.species_id=20,.level=3,.hp=100};assert(!world_capture_uid(uid,&wrong));
    mon_t mon={.species_id=19,.level=3,.hp=100,.flags=1};
    assert(world_capture_uid(uid,&mon)&&s_party.party_count==2&&dex_is_shiny_caught(&s_dex,19));
    assert(!world_capture_uid(uid,&mon)&&!world_battle_get_uid(uid,&session));
    assert(s_queue.count==1);reboot();assert(s_party.party_count==2&&s_queue.count==1);
    uid=s_queue.items[0].uid;session=prepared(uid);started(uid,&session);
    encounter_t removed;assert(world_take_uid(uid,&removed)&&removed.species_id==20);
    assert(!world_take_uid(uid,&removed)&&!world_get_encounter_uid(uid,&removed));tests++;
}
static void legacy_migration(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);save_t old;
    assert(save_read_status(&old)==SAVE_READ_OK);enc_queue_init(&old.queue);
    old.queue.count=ENC_QUEUE_CAP;old.queue.next_uid=17;old.queue.dropped=9;
    for(unsigned i=0;i<16;i++)old.queue.items[i]=(encounter_t){
        .uid=i+1,.species_id=1+i,.ts=100+i,.rarity=1+i%5,.hp_ratio=100};
    old.queue.items[11].hp_ratio=99;old.queue.items[13].exp_granted=true;
    assert(save_write(&old));uint8_t party[PARTY_BYTES];memcpy(party,old.party,sizeof(party));reboot();
    const uint16_t expected[]={10,11,13,15,16};
    assert(s_queue.count==5&&s_queue.next_uid==17&&s_queue.dropped==18&&s_dirty);
    for(unsigned i=0;i<5;i++)assert(s_queue.items[i].uid==expected[i]);
    world_debug_save();assert(save_read_status(&old)==SAVE_READ_OK);
    assert(!memcmp(party,old.party,sizeof(party))&&old.version==SAVE_VERSION&&sizeof(save_v5_t)==2296);
    reboot();assert(s_queue.count==5&&s_queue.dropped==18&&!s_dirty);tests++;
}
static pthread_t scan_thread;
static atomic_bool worker_done;
static uint16_t begin_uid;
static void *scan_worker(void *unused) {
    (void)unused;is_scan_worker=1;assert(world_debug_spawn());atomic_store(&worker_done,true);return NULL;
}
static void scan_during_commit(void) {
    assert(!s_lock->held&&s_save_lock->held&&!s_active.encounter.uid);
    assert(enc_queue_find(&s_queue,begin_uid));
    assert(!pthread_create(&scan_thread,NULL,scan_worker,NULL));
    while(!atomic_load(&worker_waiting))sched_yield();
    assert(!atomic_load(&worker_done));
    // Read-only world snapshots remain usable while the scan waits for NVS.
    encounter_t entry;assert(world_get_encounter_uid(begin_uid,&entry));
    enc_queue_t pending;world_queue_snapshot(&pending);assert(pending.count==5&&pending.items[0].uid==begin_uid);
    world_mark_seen(74,true); // Non-queue updates may still arrive during NVS.
    extra_commit_hook=NULL;
}
static void concurrent_scan(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);seed_pending(5);
    begin_uid=s_queue.items[0].uid;battle_session_t session=prepared(begin_uid);
    atomic_store(&worker_waiting,false);atomic_store(&worker_done,false);
    extra_commit_hook=scan_during_commit;started(begin_uid,&session);
    assert(!pthread_join(scan_thread,NULL)&&atomic_load(&worker_done));
    assert(s_queue.count==5&&s_queue.items[4].uid==6&&s_queue.dropped==0&&s_dirty&&dex_is_seen(&s_dex,74));
    assert(s_active.encounter.uid==begin_uid&&s_active.encounter.ts==100);
    world_debug_save();reboot();assert(s_queue.count==5&&s_queue.items[4].uid==6&&dex_is_seen(&s_dex,74));
    assert(!world_get_encounter_uid(begin_uid,&(encounter_t){0}));tests++;
}
static void defeat_consequences(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);seed_pending(2);
    uint16_t uid=s_queue.items[0].uid; battle_session_t s=prepared(uid);started(uid,&s);
    assert(!world_apply_defeat_uid(uid));
    s.finished=true;s.pet_hp=0;s.won=false;assert(world_battle_set_uid(uid,&s));
    s_w.pet.stamina=33*NURT_Q;s_w.pet.mood=28*NURT_Q;
    uint32_t exp=s_w.exp;int32_t sat=s_w.pet.satiety,bond=s_w.pet.intimacy;
    assert(world_apply_defeat_uid(uid));
    assert(s_w.pet.stamina==13*NURT_Q&&s_w.pet.mood==13*NURT_Q);
    assert(s_w.exp==exp&&s_w.pet.satiety==sat&&s_w.pet.intimacy==bond);
    assert(nurture_ability_factor(&s_w.pet)==614);
    save_t sv;assert(save_read_status(&sv)==SAVE_READ_OK);
    assert(sv.pet.stamina==13*NURT_Q&&sv.pet.mood==13*NURT_Q&&sv.exp==exp);
    assert(world_apply_defeat_uid(uid)&&s_w.pet.stamina==13*NURT_Q);
    assert(world_battle_get_uid(uid,&s)&&s.defeat_applied);
    assert(!world_apply_defeat_uid(uid+1));
    world_rest();world_play();assert(nurture_ability_factor(&s_w.pet)==1024);
    assert(s_w.pet.stamina==56*NURT_Q&&s_w.pet.mood==28*NURT_Q);
    assert(world_apply_defeat_uid(uid)&&s_w.pet.stamina==56*NURT_Q);
    world_debug_save();reboot();assert(s_w.exp==exp&&s_w.pet.mood==28*NURT_Q);tests++;

    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);seed_pending(1);
    uid=s_queue.items[0].uid;s=prepared(uid);started(uid,&s);
    s.finished=true;s.won=true;assert(world_battle_set_uid(uid,&s));
    assert(!world_apply_defeat_uid(uid));
    s.won=false;s.pet_hp=0;assert(world_battle_set_uid(uid,&s));
    s_w.pet.stamina=4*NURT_Q;s_w.pet.mood=3*NURT_Q;failure=4;
    assert(world_apply_defeat_uid(uid));assert(s_dirty&&s_w.pet.stamina==0&&s_w.pet.mood==0);
    assert(world_apply_defeat_uid(uid)&&s_w.pet.stamina==0);failure=0;
    world_debug_save();reboot();assert(s_w.pet.stamina==0&&s_w.pet.mood==0);tests++;
}
int main(void) {
    fifo_and_pending();begin_failures();active_lifetime();active_capture_and_take();legacy_migration();concurrent_scan();defeat_consequences();
    printf("{\"cases\":%u,\"pending_limit\":%d,\"storage_slots\":%d,\"save_version\":%d,\"save_bytes\":%zu,\"erase_calls\":%u}\n",
           tests,ENC_QUEUE_LIMIT,ENC_QUEUE_CAP,SAVE_VERSION,sizeof(save_t),erase_calls);
    return 0;
}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sanitize", action="store_true")
    args = parser.parse_args()
    stub, driver = harness()
    with tempfile.TemporaryDirectory(prefix="encounter-lifecycle-") as folder:
        temp = Path(folder)
        (temp / "device_stubs.h").write_text(stub)
        for name in ("esp_event.h", "esp_log.h", "esp_timer.h", "esp_wifi.h", "nvs.h",
                     "nvs_flash.h", "bsp_battery.h", "freertos/FreeRTOS.h",
                     "freertos/semphr.h", "freertos/task.h"):
            path = temp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "device_stubs.h"\n')
        (temp / "driver.c").write_text(driver)
        command = ["cc", "-std=gnu11", "-DHOST_BUILD", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
                   "-Wno-unused-variable", "-Wno-unused-function", "-Wno-unused-parameter",
                   "-ffunction-sections", "-fdata-sections", "-pthread", "-I", str(temp),
                   "-I", str(starter.MAIN), str(temp / "driver.c"),
                   *[str(starter.MAIN / name) for name in ("party.c", "encounter.c", "nurture.c", "exp.c", "items.c")],
                   "-lz", "-Wl,-dead_strip" if sys.platform == "darwin" else "-Wl,--gc-sections",
                   "-o", str(temp / "verify")]
        if args.sanitize:
            command[1:1] = ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
        subprocess.run(command, check=True)
        result = subprocess.run([str(temp / "verify")], check=True, capture_output=True, text=True, timeout=20)
        summary = json.loads(result.stdout.strip().splitlines()[-1])
        summary.update(sanitized=args.sanitize, concurrent_scan=True,
                       scope="actual world/save/encounter/party C; pthread locks and simulated NVS/device services")
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
