#!/usr/bin/env python3
"""Actual items/world/save transactions, V5 migration, failure injection and concurrency."""
from __future__ import annotations
import argparse
import json
import re
import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import verify_encounter_lifecycle as lifecycle
import verify_starter as starter

ROOT = starter.ROOT
MAIN = starter.MAIN

CASES = r'''
// This suite exercises inactive-campaign item transactions.
bool trainer_store_valid(const trainer_store_t *s){return !s->session.active&&!s->league_active;}

static void ready(uint16_t species, uint8_t level) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
    s_party.party[0].species_id=species;s_w.species=species;
    s_w.level=level;s_w.exp=exp_for_level(level);
    s_w.pet.satiety=20*NURT_Q;s_w.pet.mood=30*NURT_Q;
    s_w.pet.stamina=10*NURT_Q;s_w.pet.intimacy=12*NURT_Q;
    s_w.explore_value=7;dex_mark_caught(&s_dex,species,false);world_debug_save();
}
static void stock(uint8_t id,uint16_t n) {s_inventory.quantity[id]=n;world_debug_save();}
static void snapshot_unchanged(const world_t *before,const inventory_t *inventory,
                               const party_t *party,const uint8_t *bytes) {
    world_t after={0};world_snapshot(&after);assert(!memcmp(before,&after,sizeof(after)));
    inventory_t got;world_inventory_snapshot(&got);assert(!memcmp(inventory,&got,sizeof(got)));
    assert(!memcmp(party,&s_party,sizeof(s_party))&&!memcmp(bytes,disk,sizeof(disk)));
}
static void initial_and_caps(void) {
    fresh();inventory_t inv;world_inventory_snapshot(&inv);
    assert(inv.quantity[ITEM_POKE]==12&&inv.quantity[ITEM_GREAT]==3&&inv.quantity[ITEM_ULTRA]==1);
    assert(inv.quantity[ITEM_BERRY]==2&&inv.quantity[ITEM_MILK]==2);
    const uint8_t caps[]={99,30,20,1,20,20,20,20,9,9,9,9,9,5,5,30,30,30,30};
    for(unsigned i=0;i<ITEM_COUNT;i++) {
        assert(items_info(i)&&items_capacity(i)==caps[i]);
        if(i!=ITEM_POKE&&i!=ITEM_GREAT&&i!=ITEM_ULTRA&&i!=ITEM_BERRY&&i!=ITEM_MILK)assert(!inv.quantity[i]);
        inventory_t invalid=inv;invalid.quantity[i]=caps[i]+1;assert(!items_inventory_valid(&invalid));
    }
    assert(!items_info(ITEM_NONE)&&!items_capacity(ITEM_NONE));
    assert(world_item_use(1,ITEM_BERRY,NULL)==ITEM_USE_STORAGE_UNAVAILABLE);
    assert(world_choose_starter(25)==WORLD_STARTER_OK);reboot();
    world_inventory_snapshot(&inv);assert(inv.quantity[ITEM_POKE]==12&&inv.quantity[ITEM_BERRY]==2);
    tests++;
}
static void v5_migration(void) {
    ready(25,30);s_w.pet.intimacy=42*NURT_Q;s_w.pet.satiety=37*NURT_Q;
    mon_t extra={.species_id=150,.level=50,.exp=exp_for_level(50),.flags=1,.hp=83,.intimacy=17};
    assert(party_receive(&s_party,&extra));dex_mark_caught(&s_dex,150,true);world_debug_save();
    save_v5_t old;memcpy(&old,disk,sizeof(old));old.version=5;
    memset(disk,0,sizeof(disk));memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);
    uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));
    unsigned before_commits=commits;save_t read;
    assert(save_read_status(&read)==SAVE_READ_MIGRATED&&read.version==SAVE_VERSION&&read.inventory.quantity[ITEM_BERRY]==2);
    assert(!memcmp(read.party,old.party,PARTY_BYTES)&&!memcmp(&read.dex,&old.dex,sizeof(old.dex)));
    assert(commits==before_commits&&!memcmp(original,disk,sizeof(disk))&&save_exists());
    reboot();memcpy(original,disk,sizeof(disk));assert(!s_dirty&&!world_needs_starter()&&s_w.species==25&&s_party.party_count==2);
    assert(s_w.level==30&&s_w.exp==old.exp&&s_w.pet.intimacy==old.pet.intimacy);
    failure=4;assert(world_item_use(25,ITEM_BERRY,NULL)==ITEM_USE_SAVE_FAILED);failure=0;
    assert(s_inventory.quantity[ITEM_BERRY]==2&&!memcmp(original,disk,sizeof(disk)));
    assert(world_item_use(25,ITEM_BERRY,NULL)==ITEM_USE_OK);
    assert(disk_len==sizeof(save_t)&&s_inventory.quantity[ITEM_BERRY]==1);
    reboot();assert(s_inventory.quantity[ITEM_BERRY]==1&&s_w.pet.satiety==67*NURT_Q);
    assert(s_party.party_count==2&&s_party.party[1].species_id==150&&dex_is_shiny_caught(&s_dex,150));
    assert(save_read_status(&read)==SAVE_READ_OK&&!s_dirty&&erase_calls==0);tests++;
}
static void malformed_inventory(void) {
    for(unsigned id=0;id<ITEM_COUNT;id++) {
        ready(1,1);save_t invalid;memcpy(&invalid,disk,sizeof(invalid));
        invalid.inventory.quantity[id]=items_capacity(id)+1;
        memcpy(disk,&invalid,sizeof(invalid));uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));
        reboot();assert(!s_storage_ready&&world_needs_starter());
        assert(world_item_use(1,ITEM_BERRY,NULL)==ITEM_USE_STORAGE_UNAVAILABLE);
        world_debug_save();assert(!memcmp(original,disk,sizeof(disk))&&erase_calls==0);tests++;
    }
    ready(1,1);save_t invalid;memcpy(&invalid,disk,sizeof(invalid));invalid.version=7;
    memcpy(disk,&invalid,sizeof(invalid));uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));
    reboot();assert(!s_storage_ready);world_debug_save();assert(!memcmp(original,disk,sizeof(disk)));tests++;
}
static void care_rules(void) {
    const int delta[][4]={{30,5,0,0},{10,20,0,0},{20,10,0,0},{0,25,0,2}};
    for(unsigned i=0;i<4;i++) {
        ready(25,20);unsigned item=ITEM_BERRY+i;stock(item,2);
        world_t before=s_w;item_use_result_t result;
        assert(world_item_use(25,item,&result)==ITEM_USE_OK&&result.remaining==1);
        assert(s_w.pet.satiety==before.pet.satiety+delta[i][0]*NURT_Q);
        assert(s_w.pet.mood==before.pet.mood+delta[i][1]*NURT_Q);
        assert(s_w.pet.stamina==before.pet.stamina+delta[i][2]*NURT_Q);
        assert(s_w.pet.intimacy==before.pet.intimacy+delta[i][3]*NURT_Q);
        assert(result.species_before==25&&result.species_after==25&&s_w.exp==before.exp);
        nurture_t changed=s_w.pet;reboot();changed.last_us=-1;
        assert(!memcmp(&s_w.pet,&changed,sizeof(changed))&&s_inventory.quantity[item]==1);tests++;
    }
    ready(25,20);stock(ITEM_ENERGY_ROOT,1);s_w.pet.mood=3*NURT_Q;s_w.pet.stamina=60*NURT_Q;
    assert(world_item_use(25,ITEM_ENERGY_ROOT,NULL)==ITEM_USE_OK);
    assert(s_w.pet.stamina==60*NURT_Q&&s_w.pet.mood==23*NURT_Q);tests++;
    ready(25,20);s_w.pet.satiety=s_w.pet.mood=NURT_MAX;
    assert(world_item_use(25,ITEM_BERRY,NULL)==ITEM_USE_NOT_APPLICABLE&&s_inventory.quantity[ITEM_BERRY]==2);
    assert(world_item_use(26,ITEM_BERRY,NULL)==ITEM_USE_WRONG_TARGET);
    assert(world_item_use(25,ITEM_NONE,NULL)==ITEM_USE_INVALID);
    assert(world_item_use(25,ITEM_POKE,NULL)==ITEM_USE_NOT_APPLICABLE);tests++;
    ready(25,20);stock(ITEM_BERRY,1);world_feed();assert(s_inventory.quantity[ITEM_BERRY]==0);
    nurture_t after=s_w.pet;world_feed();assert(!memcmp(&after,&s_w.pet,sizeof(after)));tests++;
}
static void transaction_failures(void) {
    for(unsigned which=0;which<3;which++) for(unsigned j=0;j<3;j++) {
        unsigned item=(unsigned[]){ITEM_BERRY,ITEM_THUNDER_STONE,ITEM_LINK_MACHINE}[which];
        unsigned species=which==2?64:25;ready(species,30);stock(item,1);
        world_t before=s_w;inventory_t inv=s_inventory;party_t party=s_party;
        uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));
        failure=(int[]){1,2,4}[j];assert(world_item_use(species,item,NULL)==ITEM_USE_SAVE_FAILED);failure=0;
        snapshot_unchanged(&before,&inv,&party,original);
        assert(world_item_use(species,item,NULL)==ITEM_USE_OK&&s_inventory.quantity[item]==0);
        reboot();assert(s_inventory.quantity[item]==0);tests++;
    }
}
static void evolutions(void) {
    const uint8_t routes[][3]={
        {ITEM_FIRE_STONE,37,38},{ITEM_FIRE_STONE,58,59},{ITEM_FIRE_STONE,133,136},
        {ITEM_WATER_STONE,61,62},{ITEM_WATER_STONE,90,91},{ITEM_WATER_STONE,120,121},{ITEM_WATER_STONE,133,134},
        {ITEM_THUNDER_STONE,25,26},{ITEM_THUNDER_STONE,133,135},
        {ITEM_LEAF_STONE,44,45},{ITEM_LEAF_STONE,70,71},{ITEM_LEAF_STONE,102,103},
        {ITEM_MOON_STONE,30,31},{ITEM_MOON_STONE,33,34},{ITEM_MOON_STONE,35,36},{ITEM_MOON_STONE,39,40},
        {ITEM_LINK_MACHINE,64,65},{ITEM_LINK_MACHINE,67,68},{ITEM_LINK_MACHINE,75,76},{ITEM_LINK_MACHINE,93,94},
    };
    for(unsigned i=0;i<sizeof(routes)/sizeof(routes[0]);i++) {
        uint8_t item=routes[i][0],from=routes[i][1],to=routes[i][2];
        ready(from,30);stock(item,1);s_party.party[0].flags=1;
        mon_t before=s_party.party[0];uint32_t xp=s_w.exp;item_use_result_t result;
        assert(world_item_use(from,item,&result)==ITEM_USE_OK);
        assert(result.species_before==from&&result.species_after==to&&s_w.species==to);
        assert(s_inventory.quantity[item]==0&&dex_is_shiny_caught(&s_dex,to));
        assert(s_party.party_count==1&&s_party.party[0].level==before.level&&s_party.party[0].exp==xp);
        assert(s_party.party[0].flags==before.flags&&s_party.party[0].hp==before.hp&&s_w.explore_value==7);
        assert(s_w.pet.mood==45*NURT_Q&&s_w.pet.intimacy==12*NURT_Q);
        assert(world_item_use(from,item,NULL)==ITEM_USE_WRONG_TARGET);
        reboot();assert(s_w.species==to&&s_w.exp==xp&&s_inventory.quantity[item]==0);tests++;
    }
    ready(1,15);stock(ITEM_GROWTH_MACHINE,1);
    assert(world_item_use(1,ITEM_GROWTH_MACHINE,NULL)==ITEM_USE_LEVEL_TOO_LOW);
    assert(s_inventory.quantity[ITEM_GROWTH_MACHINE]==1);
    s_w.level=16;s_w.exp=exp_for_level(16);
    assert(world_item_use(1,ITEM_GROWTH_MACHINE,NULL)==ITEM_USE_OK&&s_w.species==2);
    assert(s_w.pet.intimacy==12*NURT_Q&&s_w.explore_value==7);tests++;
    ready(25,100);stock(ITEM_GROWTH_MACHINE,1);stock(ITEM_FIRE_STONE,1);
    assert(world_item_use(25,ITEM_GROWTH_MACHINE,NULL)==ITEM_USE_NOT_APPLICABLE);
    assert(world_item_use(25,ITEM_FIRE_STONE,NULL)==ITEM_USE_NOT_APPLICABLE);
    s_w.pet.intimacy=NURT_MAX;s_w.explore_value=1000;
    assert(!world_evolve_leader(25,26));tests++;
    ready(64,100);s_w.pet.intimacy=NURT_MAX;s_w.explore_value=1000;
    assert(!world_evolve_leader(64,65));tests++;
    ready(1,20);s_w.pet.intimacy=NURT_MAX;s_w.explore_value=1000;
    inventory_t inv=s_inventory;world_t before=s_w;party_t party=s_party;
    uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));
    failure=4;assert(!world_evolve_leader(1,2));failure=0;
    // collect_save syncs existing nurture mirrors before forming the candidate.
    party.party[0].intimacy=100;party.party[0].explore_value=1000;
    snapshot_unchanged(&before,&inv,&party,original);
    assert(world_evolve_leader(1,2)&&!memcmp(&inv,&s_inventory,sizeof(inv)));tests++;
}
static uint16_t begin_encounter(uint8_t rarity,int wanted,battle_session_t *out) {
    enc_queue_init(&s_queue);
    uint32_t ts=1;
    for(;ts<1000000;ts++) {
        item_loot_t loot=items_roll_loot(rarity,items_loot_seed(1,ts,19,rarity));
        if(wanted<0||loot.item_id==wanted)break;
    }
    assert(ts<1000000);
    encounter_t e={.species_id=19,.rarity=rarity,.ts=ts,.hp_ratio=100};enc_queue_push(&s_queue,&e);
    s_w.pending=s_queue.count;
    *out=(battle_session_t){.initialized=true,.pet_species=s_w.species,.wild_species=19,
        .pet_level=s_w.level,.wild_level=5,.rng=0x12345678,.pet_hp=50,.pet_hp_max=50,
        .wild_hp=40,.wild_hp_max=40,.next_by_pet=true};
    assert(world_battle_set_uid(1,out));world_debug_save();return 1;
}
static void win(uint16_t uid,battle_session_t *session) {
    session->started=true;assert(world_battle_set_uid(uid,session));
    session->finished=session->won=true;session->wild_hp=0;session->auto_battle=true;
    assert(world_battle_set_uid(uid,session));
}
static void loot_transactions(void) {
    const int wants[]={ITEM_NONE,ITEM_POKE,ITEM_MASTER};
    for(unsigned i=0;i<3;i++)for(unsigned j=0;j<3;j++) {
        ready(1,20);battle_session_t session;
        uint16_t uid=begin_encounter(5,wants[i],&session);win(uid,&session);
        inventory_t before=s_inventory;uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));
        failure=(int[]){1,2,4}[j];item_loot_t result;
        assert(!world_battle_loot_uid(uid,&result));failure=0;
        assert(!s_active.session.loot_checked&&!memcmp(&before,&s_inventory,sizeof(before)));
        assert(!memcmp(original,disk,sizeof(disk))&&s_active.session.rng==session.rng);
        assert(world_battle_loot_uid(uid,&result)&&result.item_id==wants[i]);
        assert(s_active.session.loot_checked&&s_active.session.rng==session.rng);
        unsigned saved=commits;inventory_t awarded=s_inventory;item_loot_t again;
        // A stale page copy cannot clear world-owned once markers.
        assert(world_battle_set_uid(uid,&session)&&s_active.session.loot_checked);
        assert(world_battle_loot_uid(uid,&again)&&!memcmp(&result,&again,sizeof(result)));
        assert(commits==saved&&!memcmp(&awarded,&s_inventory,sizeof(awarded)));
        reboot();assert(!s_active.encounter.uid&&!memcmp(&awarded,&s_inventory,sizeof(awarded)));tests++;
    }
    for(unsigned room=0;room<2;room++) {
        ready(1,20);stock(ITEM_POKE,items_capacity(ITEM_POKE)-room);battle_session_t s;
        uint16_t uid=begin_encounter(5,ITEM_POKE,&s);win(uid,&s);item_loot_t out;
        assert(world_battle_loot_uid(uid,&out)&&out.full&&out.quantity==room);
        assert(s_inventory.quantity[ITEM_POKE]==items_capacity(ITEM_POKE));tests++;
    }
    ready(1,20);battle_session_t s;uint16_t uid=begin_encounter(5,ITEM_MASTER,&s);item_loot_t out;
    assert(!world_battle_loot_uid(uid,&out));s.started=true;s.finished=true;s.won=false;
    assert(world_battle_set_uid(uid,&s)&&!world_battle_loot_uid(uid,&out));tests++;
}
static void balls_and_capture(void) {
    for(unsigned ball=0;ball<ITEM_BALL_COUNT;ball++)for(unsigned j=0;j<3;j++) {
        ready(1,20);stock(ball,1);battle_session_t s,previous;
        uint16_t uid=begin_encounter(1,-1,&s);previous=s;s.started=true;
        uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));
        failure=(int[]){1,2,4}[j];assert(!world_capture_ball_spend_uid(uid,ball,&s));failure=0;
        assert(s_inventory.quantity[ball]==1&&s_queue.count==1&&!s_active.encounter.uid);
        battle_session_t got;assert(world_battle_get_uid(uid,&got)&&!memcmp(&got,&previous,sizeof(got)));
        assert(!memcmp(original,disk,sizeof(disk)));
        assert(world_capture_ball_spend_uid(uid,ball,&s)&&s_inventory.quantity[ball]==0);
        assert(s_queue.count==0&&s_active.encounter.uid==uid&&s_active.session.started);
        assert(!world_capture_ball_spend_uid(uid,ball,&s)); // No stock.
        assert(world_item_use(1,ITEM_BERRY,NULL)==ITEM_USE_BUSY);
        reboot();assert(!s_inventory.quantity[ball]&&!s_queue.count&&!s_active.encounter.uid);tests++;
    }
    ready(1,20);stock(ITEM_MASTER,1);battle_session_t s;
    uint16_t uid=begin_encounter(5,ITEM_NONE,&s);win(uid,&s);item_loot_t loot;
    assert(world_battle_loot_uid(uid,&loot));assert(world_battle_get_uid(uid,&s));
    battle_session_t before=s;s.capture_used_after_win=true;
    failure=4;assert(!world_capture_ball_spend_uid(uid,ITEM_MASTER,&s));failure=0;
    assert(!s_active.session.capture_used_after_win&&s_inventory.quantity[ITEM_MASTER]==1);
    assert(world_capture_ball_spend_uid(uid,ITEM_MASTER,&s));
    assert(!world_capture_ball_spend_uid(uid,ITEM_POKE,&s)&&s_inventory.quantity[ITEM_POKE]==12);
    assert(s_active.session.loot_checked&&s_active.session.capture_used_after_win);tests++;
    // Catch result persistence is a second commit. A failure retains the
    // already-spent ball and active target; retry can save the same result.
    mon_t caught={.species_id=19,.level=5,.hp=100,.flags=1,.intimacy=40};
    party_t party=s_party;dex_t dex=s_dex;unsigned spent=s_inventory.quantity[ITEM_MASTER];
    uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(disk));failure=4;
    assert(!world_capture_uid(uid,&caught));failure=0;
    assert(!memcmp(&party,&s_party,sizeof(party))&&!memcmp(&dex,&s_dex,sizeof(dex)));
    assert(!memcmp(original,disk,sizeof(disk))&&s_active.encounter.uid==uid);
    assert(world_capture_uid(uid,&caught)&&s_party.party_count==2&&s_party.party[1].intimacy==40);
    assert(s_inventory.quantity[ITEM_MASTER]==spent&&!s_active.encounter.uid);
    assert(!world_capture_uid(uid,&caught));reboot();assert(s_party.party[1].intimacy==40);tests++;
}
static pthread_t care_thread;
static atomic_bool care_done;
static void *care_worker(void *unused) {
    (void)unused;is_scan_worker=1;world_rest();atomic_store(&care_done,true);return NULL;
}
static void during_item_commit(void) {
    assert(!s_lock->held&&s_save_lock->held);
    inventory_t inventory;world_inventory_snapshot(&inventory);assert(inventory.quantity[ITEM_BERRY]==2);
    assert(s_w.pet.satiety==20*NURT_Q);
    assert(!pthread_create(&care_thread,NULL,care_worker,NULL));
    while(!atomic_load(&worker_waiting))sched_yield();
    assert(!atomic_load(&care_done));world_mark_seen(74,true);extra_commit_hook=NULL;
}
static void concurrent_care(void) {
    ready(1,20);atomic_store(&worker_waiting,false);atomic_store(&care_done,false);
    extra_commit_hook=during_item_commit;
    assert(world_item_use(1,ITEM_BERRY,NULL)==ITEM_USE_OK);
    assert(!pthread_join(care_thread,NULL));
    assert(s_w.pet.satiety==50*NURT_Q&&s_w.pet.mood==35*NURT_Q&&s_w.pet.stamina==10*NURT_Q);
    assert(s_inventory.quantity[ITEM_BERRY]==1&&dex_is_seen(&s_dex,74)&&s_dirty);
    world_debug_save();reboot();assert(s_w.pet.stamina==10*NURT_Q&&s_inventory.quantity[ITEM_BERRY]==1);
    assert(dex_is_seen(&s_dex,74));tests++;
}
static void distribution(void) {
    for(unsigned rarity=1;rarity<=5;rarity++) {
        unsigned dropped=0,master=0,advanced=0;
        assert(items_drop_chance(rarity)==15+rarity*10);
        for(uint32_t seed=0;seed<100000;seed++) {
            item_loot_t a=items_roll_loot(rarity,seed),b=items_roll_loot(rarity,seed);
            assert(!memcmp(&a,&b,sizeof(a)));
            if(a.item_id==ITEM_NONE){assert(!a.quantity);continue;}
            assert(a.item_id<ITEM_COUNT&&a.quantity>=1&&a.quantity<=3&&!a.full);
            if(a.item_id!=ITEM_POKE)assert(a.quantity==1);else assert(a.quantity>=2);
            dropped++;master+=a.item_id==ITEM_MASTER;
            advanced+=(a.item_id>=ITEM_ULTRA&&a.item_id<=ITEM_GROWTH_MACHINE);
        }
        unsigned expected=items_drop_chance(rarity)*1000;
        assert(dropped>expected-700&&dropped<expected+700);
        if(rarity<5)assert(!master);else assert(master>0&&master<1000);
        printf("rarity %u drops %u/100000 master %u advanced %u\n",rarity,dropped,master,advanced);
    }
    assert(items_roll_loot(0,1).item_id==ITEM_NONE&&items_roll_loot(6,1).item_id==ITEM_NONE);tests++;
}
int main(void) {
    assert(assets_init());
    nurture_t axes;nurture_init(&axes);
    for(unsigned item=ITEM_FIRE_STONE;item<=ITEM_LINK_MACHINE;item++)for(unsigned sid=1;sid<=151;sid++) {
        item_use_result_t out;
        if(items_apply(item,sid,1,&axes,&out)==ITEM_USE_OK)
            printf("ROUTE %u %u %u\n",item,sid,out.species_after);
    }
    initial_and_caps();v5_migration();malformed_inventory();
    care_rules();transaction_failures();evolutions();loot_transactions();balls_and_capture();
    concurrent_care();distribution();
    printf("{\"cases\":%u,\"items\":%u,\"save_version\":%u,\"legacy_bytes\":%zu,\"save_bytes\":%zu,\"erase_calls\":%u}\n",
           tests,ITEM_COUNT,SAVE_VERSION,sizeof(save_v5_t),sizeof(save_t),erase_calls);
    return 0;
}
'''


def source_routes() -> tuple[set[tuple[int,int,int]],dict]:
    src=Path(__import__('os').environ.get('POKECRYSTAL_SOURCE','/tmp/pokecrystal'));commit='7a7881d0d62e0ddbd82dcf10e7116807487ac651'
    files=['constants/pokemon_constants.asm','data/pokemon/evos_attacks_pointers.asm','data/pokemon/evos_attacks.asm']
    texts={};hashes={}
    for name in files:
        data=(src/name).read_bytes()
        assert data==subprocess.check_output(['git','-C',str(src),'show',f'{commit}:{name}'])
        texts[name]=data.decode();hashes[name]=hashlib.sha256(data).hexdigest()
    symbols=re.findall(r'^\s*const (\w+)',texts[files[0]],re.M)[:151]
    ids={name:i+1 for i,name in enumerate(symbols)}
    labels=re.findall(r'^\s*dw (\w+)',texts[files[1]],re.M)[:151]
    item_ids={'FIRE_STONE':8,'WATER_STONE':9,'THUNDERSTONE':10,'LEAF_STONE':11,'MOON_STONE':12}
    expected=set()
    for sid,label in enumerate(labels,1):
        body=texts[files[2]].split(label+':',1)[1].split('db 0',1)[0]
        for mode,param,target in re.findall(r'db EVOLVE_(ITEM|TRADE),\s*([^,]+),\s*(\w+)',body):
            if target not in ids:continue
            item=item_ids.get(param.strip()) if mode=='ITEM' else 13 if param.strip()=='-1' else None
            if item is not None:expected.add((item,sid,ids[target]))
    assert len(expected)==20,expected
    return expected,dict(commit=commit,sha256=hashes)


def run(root: Path, sanitizer: bool = True) -> dict:
    stubs, driver = lifecycle.harness()
    driver = driver[:driver.index('// Only species statistics')]+CASES
    with tempfile.TemporaryDirectory(prefix='items_verify_') as td:
        directory = Path(td)
        (directory/'device_stubs.h').write_text(stubs)
        for name in ('esp_event.h','esp_log.h','esp_timer.h','esp_wifi.h','nvs.h','nvs_flash.h',
                     'bsp_battery.h','freertos/FreeRTOS.h','freertos/semphr.h','freertos/task.h'):
            path=directory/name;path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text('#include "device_stubs.h"\n')
        (directory/'driver.c').write_text(driver)
        asm=[]
        for name in ('gen1.bin','gen1_front.bin','gen1_back.bin','palettes.bin','moves.bin','ui.bin','font16.bin'):
            symbol='_binary_'+name.replace('.','_')
            asm += ['.balign 4',f'.global {symbol}_start',f'.global {symbol}_end',
                    f'{symbol}_start:',f'.incbin "{ROOT / "assets" / name}"',f'{symbol}_end:']
        (directory/'assets.S').write_text('\n'.join(asm)+'\n')
        command=['cc','-std=gnu11','-DHOST_BUILD','-O1','-g','-Wall','-Wextra','-Werror',
            '-Wno-unused-function','-Wno-unused-variable','-Wno-unused-parameter','-Wno-unused-but-set-variable',
            '-ffunction-sections','-fdata-sections','-I',str(directory),'-I',str(root/'firmware/main'),
            str(directory/'driver.c'),*[str(root/'firmware/main'/name) for name in
                ('party.c','encounter.c','nurture.c','exp.c','items.c','evolution.c','assets.c','pokemon_names.c')],
            str(directory/'assets.S'),'-pthread','-lz',
            '-Wl,-dead_strip' if sys.platform=='darwin' else '-Wl,--gc-sections','-o',str(directory/'probe')]
        if sanitizer:command[1:1]=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        subprocess.run(command,check=True,capture_output=True,text=True)
        result=subprocess.run([str(directory/'probe')],capture_output=True,text=True,timeout=90)
        if result.returncode:raise AssertionError(result.stdout+'\n'+result.stderr)
        expected,provenance=source_routes()
        actual={tuple(map(int,line.split()[1:])) for line in result.stdout.splitlines() if line.startswith('ROUTE ')}
        assert actual==expected, f'upstream evolution route mismatch: {actual ^ expected}'
        print('\n'.join(line for line in result.stdout.splitlines() if not line.startswith('ROUTE ')))
        summary=json.loads(result.stdout.splitlines()[-1])
        summary['source_evolution_routes']=len(actual);summary['source']=provenance
        return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative',action='store_true')
    args=parser.parse_args()
    result=run(ROOT)
    result['sanitized']=True
    result['scope']='Actual C assets/items/world/save, source bins, pthread ordering; fake NVS/clock/device boundary'
    result['negative_checks']=[]
    if args.negative:
        import shutil
        changes=[('loot once','world.c','if (session->loot_checked) {','if (false) {'),
            ('inventory rollback','world.c','bool ok = save_write(&s_save_buf);','bool ok = (save_write(&s_save_buf), true);'),
            ('stone bypass','world.c','sp.evolve_trigger != EVO_TRIGGER_LEVEL ||\n            sp.evolve_to != natural_target',
             'false ||\n            sp.evolve_to != natural_target'),
            ('capacity clamp','world.c','if (loot.quantity > room) loot.quantity = (uint8_t)room;',
             'if (false) loot.quantity = (uint8_t)room;'),
            ('v5 regrant','save.c','} else if (!items_inventory_valid(&out->inventory)) return SAVE_READ_ERROR;',
             '} else { items_inventory_init(&out->inventory); }')]
        for label,name,old,new in changes:
            with tempfile.TemporaryDirectory(prefix='items_negative_') as td:
                root=Path(td);shutil.copytree(MAIN,root/'firmware/main')
                source=root/'firmware/main'/name;text=source.read_text()
                assert old in text
                source.write_text(text.replace(old,new))
                try:run(root)
                except AssertionError:result['negative_checks'].append(label)
                else:raise AssertionError('negative escaped: '+label)
    out=ROOT/'reports/evidence/items-2026-09-08';out.mkdir(parents=True,exist_ok=True)
    (out/'world-save.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS actual item transactions:',out/'world-save.json')


if __name__=='__main__':main()
