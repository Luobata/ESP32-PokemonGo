#!/usr/bin/env python3
"""Actual six-member world/save switching, stale selection and NVS failure checks."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import verify_encounter_lifecycle as lifecycle
import verify_starter as starter

ROOT = starter.ROOT

CASES = r'''
// Scan metadata is outside this test. Party/save/nurture code is production C.
bool assets_species(uint16_t id,species_t *out) {
    if(id<1||id>151)return false;memset(out,0,sizeof(*out));out->id=id;
    out->hp=out->attack=out->defense=out->special=out->speed=40;return true;
}
uint32_t assets_species_count(void) {return 151;}
// This suite covers inactive-campaign party transactions; active campaigns are
// validated against real assets in verify_trainer_campaign.py.
bool trainer_store_valid(const trainer_store_t *st) {return !st->session.active&&!st->league_active;}

static void seed_team(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
    const uint8_t ids[]={1,25,25,133,94,150};
    const uint8_t levels[]={31,12,45,20,40,55};
    const uint8_t intimacy[]={73,40,7,25,0,100};
    party_init(&s_party);dex_init(&s_dex);
    for(unsigned i=0;i<PARTY_MAX;i++) {
        mon_t m={.species_id=ids[i],.level=levels[i],.hp=(uint8_t)(13+i*15),
            .intimacy=intimacy[i],.explore_value=(uint16_t)(17+i*103),
            .nickname_idx=(uint8_t)(8+i),.flags=(uint8_t)(i*3),.exp=exp_for_level(levels[i])+i};
        assert(party_receive(&s_party,&m));dex_mark_caught(&s_dex,ids[i],m.flags&1);
    }
    for(unsigned i=0;i<3;i++) {
        mon_t m={.species_id=(uint8_t)(149+i),.level=(uint8_t)(20+i),.hp=72,
            .intimacy=5,.explore_value=543,.flags=1,.nickname_idx=0xff,.exp=exp_for_level(20+i)+i};
        assert(party_receive(&s_party,&m));dex_mark_caught(&s_dex,m.species_id,true);
    }
    s_w.species=1;s_w.level=31;s_w.exp=exp_for_level(31);s_w.explore_value=17;
    s_w.pet=(nurture_t){.satiety=20*NURT_Q+201,.mood=11*NURT_Q+301,
        .stamina=13*NURT_Q+401,.intimacy=73*NURT_Q+900,.last_us=314159};
    enc_queue_init(&s_queue);
    encounter_t e={.species_id=19,.rarity=3,.hp_ratio=100,.ts=200};enc_queue_push(&s_queue,&e);
    s_w.pending=1;
    battle_session_t session={.initialized=true,.pet_species=1,.pet_level=31,
        .wild_species=19,.pet_hp=45,.pet_hp_max=45,.wild_hp=20,.wild_hp_max=20,.rng=0x12345678};
    assert(world_battle_set_uid(1,&session));world_debug_save();
}
static void equal_shared(const nurture_t *a,const nurture_t *b,bool clock) {
    assert(a->satiety==b->satiety&&a->mood==b->mood&&a->stamina==b->stamina);
    if(clock)assert(a->last_us==b->last_us);
}
static void unchanged(const world_t *w,const party_t *party,const uint8_t *bytes) {
    world_t now={0};world_snapshot(&now);assert(!memcmp(w,&now,sizeof(now)));
    assert(!memcmp(party,&s_party,sizeof(s_party))&&!memcmp(bytes,disk,sizeof(disk)));
}
static void snapshot_readonly(void) {
    world_party_snapshot(NULL);
    world_party_t got;memset(&got,0xff,sizeof(got));world_party_snapshot(&got);
    assert(!got.count&&!got.box_count&&got.switch_locked);
    for(unsigned i=0;i<PARTY_MAX;i++)assert(!got.members[i].species_id);
    fresh();world_party_snapshot(&got);assert(!got.count&&got.switch_locked);
    mon_t expected={.species_id=1};
    assert(world_set_leader(0,&expected,NULL)==WORLD_SWITCH_STORAGE_UNAVAILABLE);tests++;
    seed_team();party_t before=s_party;unsigned writes_before=writes;
    world_party_snapshot(&got);assert(got.count==6&&got.box_count==3&&!got.switch_locked);
    assert(got.members[0].intimacy==73&&s_party.party[0].intimacy==74);
    assert(!memcmp(&before,&s_party,sizeof(before))&&writes==writes_before);
    got.members[1].hp=0;world_party_t again;world_party_snapshot(&again);
    assert(again.members[1].hp==28); // Caller's copy never mutates stored data.
    assert(world_set_leader(0,&again.members[0],&again)==WORLD_SWITCH_ALREADY_LEADER);
    assert(again.count==6&&again.members[0].intimacy==73&&writes==writes_before);
    assert(world_set_leader(0,NULL,NULL)==WORLD_SWITCH_INVALID);
    assert(world_set_leader(6,&again.members[0],NULL)==WORLD_SWITCH_INVALID);
    assert(world_set_leader(255,&again.members[0],NULL)==WORLD_SWITCH_INVALID);tests++;
}
static void every_position(void) {
    for(unsigned index=1;index<PARTY_MAX;index++) {
        seed_team();world_party_t before,after;world_party_snapshot(&before);
        party_t old=s_party;world_t w=s_w;inventory_t inventory=s_inventory;dex_t dex=s_dex;
        enc_queue_t queue=s_queue;unsigned committed=commits;
        mon_t expected[PARTY_MAX];memcpy(expected,before.members,sizeof(expected));
        mon_t chosen=expected[index];
        for(unsigned i=index;i>0;i--)expected[i]=expected[i-1];expected[0]=chosen;
        assert(world_set_leader(index,&before.members[index],&after)==WORLD_SWITCH_OK);
        assert(commits==committed+1&&after.count==6&&after.box_count==3&&!after.switch_locked);
        assert(!memcmp(after.members,expected,sizeof(expected)));
        assert(!memcmp(s_party.party,expected,sizeof(expected))&&!memcmp(s_party.box,old.box,sizeof(old.box)));
        assert(s_w.species==chosen.species_id&&s_w.level==chosen.level&&s_w.exp==chosen.exp);
        assert(s_w.explore_value==chosen.explore_value&&s_w.pet.intimacy==chosen.intimacy*NURT_Q);
        equal_shared(&w.pet,&s_w.pet,true);assert(nurture_ability_factor(&s_w.pet)==614);
        assert(!memcmp(&inventory,&s_inventory,sizeof(inventory))&&!memcmp(&dex,&s_dex,sizeof(dex)));
        assert(!memcmp(&queue,&s_queue,sizeof(queue)));
        battle_session_t cached;assert(world_battle_get_uid(1,&cached)&&!cached.initialized);
        save_t saved;assert(save_read_status(&saved)==SAVE_READ_OK&&saved.version==SAVE_VERSION);
        assert(saved.species==chosen.species_id&&saved.level==chosen.level&&saved.exp==chosen.exp);
        assert(saved.pet.intimacy==chosen.intimacy*NURT_Q);
        reboot();world_party_snapshot(&after);
        assert(!memcmp(after.members,expected,sizeof(expected))&&!memcmp(s_party.box,old.box,sizeof(old.box)));
        equal_shared(&w.pet,&s_w.pet,false);assert(s_w.pet.last_us==-1&&erase_calls==0);tests++;
    }
}
static void failures_and_stale(void) {
    for(unsigned i=0;i<3;i++) {
        seed_team();world_party_t view;world_party_snapshot(&view);
        world_t w=s_w;party_t party=s_party;world_battle_slot_t sessions[ENC_QUEUE_LIMIT];
        memcpy(sessions,s_battles,sizeof(sessions));uint8_t bytes[sizeof(disk)];memcpy(bytes,disk,sizeof(bytes));
        unsigned old_commits=commits;failure=(int[]){1,2,4}[i];
        assert(world_set_leader(2,&view.members[2],NULL)==WORLD_SWITCH_SAVE_FAILED);failure=0;
        unchanged(&w,&party,bytes);assert(!memcmp(sessions,s_battles,sizeof(sessions))&&commits==old_commits);
        assert(world_set_leader(2,&view.members[2],NULL)==WORLD_SWITCH_OK);tests++;
    }
    seed_team();world_party_t view;world_party_snapshot(&view);unsigned before=commits;
    for(unsigned i=0;i<8;i++) {
        mon_t wrong=view.members[1];((uint8_t*)&wrong)[(unsigned[]){0,1,2,3,4,6,7,8}[i]]^=1;
        assert(world_set_leader(1,&wrong,NULL)==WORLD_SWITCH_STALE);tests++;
    }
    // Same species, different individual: the original member at index 1 was
    // Lv12; this snapshot describes Lv45 at index 2.
    assert(view.members[1].species_id==view.members[2].species_id);
    assert(world_set_leader(1,&view.members[2],NULL)==WORLD_SWITCH_STALE&&commits==before);
    assert(world_set_leader(2,&view.members[2],NULL)==WORLD_SWITCH_OK);
    assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_STALE);tests++;
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);world_party_snapshot(&view);
    assert(world_set_leader(1,&view.members[0],NULL)==WORLD_SWITCH_INVALID);tests++;
}
static void battle_lock(void) {
    seed_team();world_party_t view;world_party_snapshot(&view);battle_session_t session;
    assert(world_battle_get_uid(1,&session));session.started=true;
    assert(world_battle_set_uid(1,&session));world_party_snapshot(&view);assert(view.switch_locked);
    uint8_t bytes[sizeof(disk)];memcpy(bytes,disk,sizeof(bytes));party_t party=s_party;world_t w=s_w;
    assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_BUSY);
    assert(world_set_leader(0,&view.members[0],NULL)==WORLD_SWITCH_BUSY);unchanged(&w,&party,bytes);
    session.finished=session.won=true;session.wild_hp=0;assert(world_battle_set_uid(1,&session));
    assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_BUSY);
    world_end_active_encounter();assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_OK);tests++;
}
static void play_stamina_boundary(void) {
    const int32_t stamina[]={0,1,4*NURT_Q,5*NURT_Q-1,5*NURT_Q,6*NURT_Q};
    for(unsigned i=0;i<sizeof(stamina)/sizeof(stamina[0]);i++) {
        seed_team();s_w.pet.stamina=stamina[i];s_w.pet.mood=20*NURT_Q;s_w.pet.intimacy=10*NURT_Q;s_dirty=false;
        nurture_t before=s_w.pet;unsigned writes=commits;
        bool ok=world_play();
        assert(ok==(stamina[i]>=5*NURT_Q));
        if(!ok){assert(!memcmp(&before,&s_w.pet,sizeof(before)));assert(!s_dirty);}
        else {assert(s_w.pet.stamina==before.stamina-5*NURT_Q);assert(s_w.pet.mood==35*NURT_Q);assert(s_w.pet.intimacy==11*NURT_Q);assert(s_dirty);}
        assert(commits==writes);tests++;
    }
}
static void individual_bond(void) {
    seed_team();world_party_t view;world_party_snapshot(&view);nurture_t shared=s_w.pet;
    for(unsigned i=0;i<20;i++) {
        assert(world_set_leader(1,&view.members[1],&view)==WORLD_SWITCH_OK);
        assert(view.members[0].intimacy==(i%2?73:40));equal_shared(&shared,&s_w.pet,true);
    }
    assert(s_w.species==1&&s_w.pet.intimacy==73*NURT_Q);tests++;
    assert(world_set_leader(1,&view.members[1],&view)==WORLD_SWITCH_OK);
    assert(s_w.species==25&&s_w.pet.intimacy==40*NURT_Q);world_play();
    assert(s_w.pet.intimacy==41*NURT_Q);world_party_snapshot(&view);
    assert(view.members[0].intimacy==41&&view.members[1].intimacy==73);
    uint16_t first_explore=view.members[1].explore_value;
    assert(world_set_leader(1,&view.members[1],&view)==WORLD_SWITCH_OK);
    assert(s_w.pet.intimacy==73*NURT_Q&&s_w.explore_value==first_explore&&view.members[1].intimacy==41);
    assert(s_w.pet.stamina==shared.stamina-NURT_PLAY_STAMINA);reboot();
    world_party_snapshot(&view);assert(view.members[0].intimacy==73&&view.members[1].intimacy==41);tests++;
}
static void legacy_and_protection(void) {
    seed_team();save_v5_t old;memcpy(&old,disk,sizeof(old));old.version=5;
    memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);reboot();
    assert(!s_dirty && disk_len==sizeof(save_t) && ((save_t*)disk)->version==SAVE_VERSION);
    world_party_t view;world_party_snapshot(&view);
    assert(view.count==6&&view.box_count==3&&view.members[0].intimacy==73);
    assert(world_set_leader(5,&view.members[5],&view)==WORLD_SWITCH_OK);
    assert(disk_len==sizeof(save_t)&&s_inventory.quantity[ITEM_BERRY]==2);reboot();
    world_party_snapshot(&view);assert(view.members[0].species_id==150&&view.count==6&&view.box_count==3);tests++;
    seed_team();((save_t*)disk)->version=SAVE_VERSION+1;uint8_t bytes[sizeof(disk)];memcpy(bytes,disk,sizeof(bytes));reboot();
    world_party_snapshot(&view);assert(!view.count&&view.switch_locked);
    mon_t target={.species_id=25,.level=12};
    assert(world_set_leader(1,&target,NULL)==WORLD_SWITCH_STORAGE_UNAVAILABLE);
    world_debug_save();assert(!memcmp(bytes,disk,sizeof(bytes))&&erase_calls==0);tests++;
}
static pthread_t rest_thread;
static atomic_bool worker_done;
static world_party_t commit_view;
static void *rest_worker(void *unused) {
    (void)unused;is_scan_worker=1;world_rest();atomic_store(&worker_done,true);return NULL;
}
static void observe_commit(void) {
    assert(!s_lock->held&&s_save_lock->held);
    world_party_t actual;world_party_snapshot(&actual);assert(!memcmp(&actual,&commit_view,sizeof(actual)));
    assert(!pthread_create(&rest_thread,NULL,rest_worker,NULL));
    while(!atomic_load(&worker_waiting))sched_yield();assert(!atomic_load(&worker_done));
    world_mark_seen(74,true);extra_commit_hook=NULL;
}
static void concurrent_care(void) {
    for(unsigned fail=0;fail<2;fail++) {
        seed_team();world_party_snapshot(&commit_view);nurture_t before=s_w.pet;
        atomic_store(&worker_waiting,false);atomic_store(&worker_done,false);
        extra_commit_hook=observe_commit;failure=fail?4:0;
        assert(world_set_leader(2,&commit_view.members[2],NULL)==(fail?WORLD_SWITCH_SAVE_FAILED:WORLD_SWITCH_OK));
        failure=0;assert(!pthread_join(rest_thread,NULL)&&atomic_load(&worker_done));
        assert(s_w.pet.stamina==before.stamina+NURT_REST_STAMINA);
        assert(s_w.pet.satiety==before.satiety&&s_w.pet.mood==before.mood&&dex_is_seen(&s_dex,74));
        assert(s_w.species==(fail?1:25)&&s_w.level==(fail?31:45)&&s_dirty);
        world_debug_save();reboot();assert(s_w.pet.stamina==before.stamina+NURT_REST_STAMINA);
        assert(dex_is_seen(&s_dex,74)&&s_w.species==(fail?1:25)&&erase_calls==0);tests++;
    }
}
static void easier_curve_preserves_progress(void) {
    seed_team();
    for(unsigned i=0;i<PARTY_MAX+BOX_SPECIES;i++){
        mon_t *m=i<PARTY_MAX?&s_party.party[i]:&s_party.box[i-PARTY_MAX];
        if(m->species_id)m->exp=5u*m->level*m->level*m->level/2u;
    }
    s_w.exp=s_party.party[0].exp;world_debug_save();party_t expected=s_party;
    for(unsigned i=0;i<PARTY_MAX+BOX_SPECIES;i++){
        mon_t *m=i<PARTY_MAX?&expected.party[i]:&expected.box[i-PARTY_MAX];
        if(m->species_id){uint8_t previous=m->level;m->level=exp_to_level(m->exp,LEVEL_MAX);assert(m->level>=previous);}
    }
    reboot();assert(!memcmp(&s_party,&expected,sizeof(expected)));
    assert(s_w.level==expected.party[0].level&&s_w.exp==expected.party[0].exp);
    reboot();assert(!memcmp(&s_party,&expected,sizeof(expected)));tests++;
}
static void duplicate_box_exchange(void) {
    seed_team();world_party_t view;world_party_snapshot(&view);
    mon_t outgoing=view.members[5],incoming=s_party.box[148],duplicate=s_party.box[149];
    party_t before=s_party;uint8_t stored[sizeof(disk)];memcpy(stored,disk,sizeof(stored));
    failure=4;assert(world_box_exchange(5,&outgoing,&incoming)==WORLD_SWITCH_SAVE_FAILED);failure=0;
    assert(!memcmp(&before,&s_party,sizeof(before))&&!memcmp(stored,disk,sizeof(stored)));
    assert(world_box_exchange(5,&outgoing,&incoming)==WORLD_SWITCH_OK);
    assert(!memcmp(&s_party.party[5],&incoming,sizeof(incoming)));
    assert(!memcmp(&s_party.box[148],&outgoing,sizeof(outgoing))&&!memcmp(&s_party.box[149],&duplicate,sizeof(duplicate)));
    assert(party_total(&s_party)==9);party_t swapped=s_party;reboot();assert(!memcmp(&s_party,&swapped,sizeof(swapped)));
    assert(world_box_exchange(5,&outgoing,&incoming)==WORLD_SWITCH_STALE);
    // Choose the second individual of the same species, not the first match.
    world_party_snapshot(&view);assert(world_box_exchange(5,&view.members[5],&duplicate)==WORLD_SWITCH_OK);
    assert(!memcmp(&s_party.party[5],&duplicate,sizeof(duplicate))&&!memcmp(&s_party.box[148],&outgoing,sizeof(outgoing)));
    // A partially occupied party follows exactly the same non-destructive swap.
    seed_team();s_party.party_count=1;memset(&s_party.party[1],0,5*sizeof(mon_t));
    s_party.box[0]=s_party.party[0];s_party.box[0].flags^=1;world_debug_save();world_party_snapshot(&view);
    outgoing=view.members[0];incoming=s_party.box[148];duplicate=s_party.box[0];
    assert(world_box_exchange(0,&outgoing,&incoming)==WORLD_SWITCH_OK);
    assert(s_party.party_count==1&&!memcmp(&s_party.box[0],&duplicate,sizeof(duplicate))&&!memcmp(&s_party.box[148],&outgoing,sizeof(outgoing)));
    swapped=s_party;reboot();assert(!memcmp(&s_party,&swapped,sizeof(swapped)));tests+=7;
}
static void box_migration_and_capacity(void) {
    seed_team();party_t before=s_party;((save_t*)disk)->version=11;
    reboot();assert(((save_t*)disk)->version==SAVE_VERSION&&!memcmp(&before,&s_party,sizeof(before)));
    seed_team();((save_t*)disk)->version=11;((save_t*)disk)->party[2+(PARTY_MAX+148)*MON_BYTES]=150;
    save_t invalid;assert(save_read_status(&invalid)==SAVE_READ_ERROR);
    party_t p;party_init(&p);p.party_count=6;
    for(unsigned i=0;i<6;i++)p.party[i]=(mon_t){.species_id=25,.level=10,.exp=exp_for_level(10)+i};
    for(unsigned i=0;i<BOX_SPECIES;i++)p.box[i]=(mon_t){.species_id=(uint8_t)(i+1),.level=20,.exp=exp_for_level(20)+i};
    before=p;assert(party_exchange_at(&p,0,150)&&party_total(&p)==157);
    uint8_t raw[PARTY_BYTES];party_serialize(&p,raw);party_t restored;assert(party_deserialize(&restored,raw,sizeof(raw))&&!memcmp(&p,&restored,sizeof(p)));
    assert(party_exchange_at(&restored,0,150)&&!memcmp(&restored,&before,sizeof(before)));tests+=4;
}
int main(void) {
    snapshot_readonly();every_position();failures_and_stale();battle_lock();play_stamina_boundary();individual_bond();
    legacy_and_protection();concurrent_care();easier_curve_preserves_progress();duplicate_box_exchange();box_migration_and_capacity();
    printf("{\"cases\":%u,\"party_slots\":%d,\"box_slots\":%d,\"mon_bytes\":%zu,\"save_version\":%d,\"save_bytes\":%zu,\"erase_calls\":%u}\n",
        tests,PARTY_MAX,BOX_SPECIES,sizeof(mon_t),SAVE_VERSION,sizeof(save_t),erase_calls);
    return 0;
}
'''


def run(root: Path) -> dict:
    stubs, driver = lifecycle.harness()
    driver = driver[:driver.index('// Only species statistics')] + CASES
    with tempfile.TemporaryDirectory(prefix='world_party_verify_') as folder:
        temp = Path(folder)
        (temp / 'device_stubs.h').write_text(stubs)
        for name in ('esp_event.h', 'esp_log.h', 'esp_timer.h', 'esp_wifi.h', 'nvs.h',
                     'nvs_flash.h', 'bsp_battery.h', 'freertos/FreeRTOS.h',
                     'freertos/semphr.h', 'freertos/task.h'):
            path = temp / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('#include "device_stubs.h"\n')
        (temp / 'driver.c').write_text(driver)
        command = ['cc', '-std=gnu11', '-DHOST_BUILD', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-variable', '-Wno-unused-function', '-Wno-unused-parameter',
                   '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                   '-ffunction-sections', '-fdata-sections', '-pthread', '-I', str(temp),
                   '-I', str(root / 'firmware/main'), str(temp / 'driver.c'),
                   *[str(root / 'firmware/main' / name) for name in
                     ('party.c', 'encounter.c', 'exploration.c', 'battle.c', 'combat.c', 'nurture.c', 'exp.c', 'items.c')], '-lz',
                   '-Wl,-dead_strip' if sys.platform == 'darwin' else '-Wl,--gc-sections',
                   '-o', str(temp / 'probe')]
        subprocess.run(command, check=True, capture_output=True, text=True)
        result = subprocess.run([str(temp / 'probe')], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stdout + '\n' + result.stderr)
        return json.loads(result.stdout.strip().splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative', action='store_true')
    parser.add_argument('--evidence-dir', type=Path, default=ROOT/'reports/evidence/party-2026-09-08')
    args = parser.parse_args()
    result = run(ROOT)
    result.update(sanitized=True, concurrent_care=True,
                  scope='Actual world/save/party/nurture C; pthread locks; simulated NVS/device boundary',
                  negative_checks=[])
    if args.negative:
        changes = [
            ('rollback', 'bool ok = save_write(&s_save_buf);', 'bool ok = (save_write(&s_save_buf), true);'),
            ('stale member', 'if (memcmp(&wanted, &selected, sizeof(wanted)) != 0)', 'if (false)'),
            ('active lock', 'if (s_active.encounter.uid || s_challenge.session.active || s_challenge.league_active)', 'if (false)'),
            ('individual intimacy', 's_w.pet.intimacy = s_save_buf.pet.intimacy;', 's_w.pet.intimacy = s_w.pet.intimacy;'),
            ('shared axes', 's_w.species = next_leader.species_id;', 's_w.pet.stamina = NURT_MAX; s_w.species = next_leader.species_id;'),
            ('pending stats', 'memset(s_battles, 0, sizeof(s_battles));', '(void)s_battles;'),
        ]
        for label, old, new in changes:
            with tempfile.TemporaryDirectory(prefix='world_party_negative_') as folder:
                root = Path(folder)
                shutil.copytree(ROOT / 'firmware/main', root / 'firmware/main')
                file = root / 'firmware/main/world.c'
                source = file.read_text()
                start = source.index('world_switch_result_t world_set_leader(')
                end = source.index('\nstatic encounter_t *find_encounter_locked', start)
                function = source[start:end]
                assert function.count(old) == 1, label
                file.write_text(source[:start] + function.replace(old, new) + source[end:])
                try:
                    run(root)
                except AssertionError:
                    result['negative_checks'].append(label)
                else:
                    raise AssertionError('negative escaped: ' + label)
    result['source_sha256'] = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in
        ('firmware/main/world.c', 'firmware/main/world.h', 'firmware/main/party.c',
         'firmware/main/party.h', 'firmware/main/save.c', 'firmware/main/save.h')}
    output = args.evidence_dir
    output.mkdir(parents=True, exist_ok=True)
    (output / 'world-save.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
