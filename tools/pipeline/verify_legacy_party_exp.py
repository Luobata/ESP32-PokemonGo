#!/usr/bin/env python3
"""Repair old captured levels with missing EXP using actual world/save C."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import verify_encounter_lifecycle as lifecycle
import verify_world_party as party_gate

ROOT = party_gate.ROOT
ORIGINAL_HARNESS = lifecycle.harness
ASSET_STUB = party_gate.CASES[:party_gate.CASES.index('static void seed_team')]


def harness():
    stubs, driver = ORIGINAL_HARNESS()
    driver = driver.replace('static int failure,init_error;',
                            'static int failure,init_error,repair_write_failure;')
    driver = driver.replace('failure=init_error=0;', 'failure=init_error=repair_write_failure=0;')
    driver = driver.replace('    *len=disk_len;return ESP_OK;', '''
    *len=disk_len;
    if(out&&repair_write_failure){failure=repair_write_failure;repair_write_failure=0;}
    return ESP_OK;''')
    return stubs, driver


CASES = r'''
static party_t raw_party,expected_party;
static uint32_t threshold(uint8_t level) { return level<=1?0:5u*level*level*level/2u; }
static void seed_legacy(bool v5) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
    party_init(&raw_party);
    for(unsigned i=0;i<PARTY_MAX;i++) {
        mon_t member={.species_id=(uint8_t)(i==1?17:30+i),.level=(uint8_t)(i==1?12:21+i),
            .hp=(uint8_t)(40+i),.intimacy=27,.explore_value=(uint16_t)(200+i),
            .nickname_idx=(uint8_t)(10+i),.flags=(uint8_t)(i%2),
            .exp=i%2?0:threshold(21+i)+11};
        if(i==0)member.exp=0; // Also repair the current leader mirror.
        assert(party_receive(&raw_party,&member));
    }
    for(unsigned i=0;i<BOX_SPECIES;i++) {
        uint8_t level=(uint8_t)(1+i%100);uint32_t minimum=threshold(level);
        mon_t member={.species_id=(uint8_t)(i+1),.level=level,.hp=(uint8_t)(50+i%50),
            .intimacy=(uint8_t)(i%101),.explore_value=(uint16_t)(i*31),
            .nickname_idx=(uint8_t)i,.flags=(uint8_t)(i%2),
            .exp=i%3==0?0:i%3==1?minimum+20:minimum};
        assert(party_receive(&raw_party,&member));
    }
    save_t saved;assert(save_read_status(&saved)==SAVE_READ_OK);
    saved.species=raw_party.party[0].species_id;saved.level=raw_party.party[0].level;
    saved.exp=raw_party.party[0].exp;saved.pet.intimacy=27*NURT_Q;
    party_serialize(&raw_party,saved.party);assert(save_write(&saved));
    if(v5){save_v5_t old;memcpy(&old,disk,sizeof(old));old.version=5;
        memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);}
    expected_party=raw_party;
    for(unsigned i=0;i<PARTY_MAX+BOX_SPECIES;i++) {
        mon_t *m=i<PARTY_MAX?&expected_party.party[i]:&expected_party.box[i-PARTY_MAX];
        uint32_t minimum=threshold(m->level);if(m->exp<minimum)m->exp=minimum;
    }
}
static void repaired(void) {
    assert(!memcmp(&s_party,&expected_party,sizeof(s_party)));
    assert(s_w.level==21&&s_w.exp==23152&&s_w.species==30);
    assert(s_w.pet.intimacy==27*NURT_Q&&s_w.explore_value==200);
    assert(s_inventory.quantity[ITEM_BERRY]==2&&s_inventory.quantity[ITEM_POKE]==12);
}
static void all_slots_and_restart(void) {
    for(unsigned v5=0;v5<2;v5++) {
        seed_legacy(v5);unsigned before=commits;reboot();repaired();
        assert(commits==before+1&&!s_dirty&&disk_len==sizeof(save_t));
        save_t saved;assert(save_read_status(&saved)==SAVE_READ_OK&&saved.version==6);
        party_t persisted;assert(party_deserialize(&persisted,saved.party,PARTY_BYTES));
        assert(!memcmp(&persisted,&expected_party,sizeof(persisted)));
        unsigned once=commits;reboot();repaired();assert(commits==once&&!s_dirty&&erase_calls==0);tests++;
    }
}
static void missing_exp_switch_win(void) {
    seed_legacy(false);reboot();world_party_t view;world_party_snapshot(&view);
    assert(view.members[1].species_id==17&&view.members[1].level==12&&view.members[1].exp==4320);
    assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_OK);
    world_grant_exp(60);assert(s_w.species==17&&s_w.level==12&&s_w.exp==4380);
    reboot();world_party_snapshot(&view);
    assert(view.members[0].species_id==17&&view.members[0].level==12&&view.members[0].exp==4380);
    assert(view.members[0].hp==41&&view.members[0].intimacy==27&&view.members[0].flags==1);tests++;
}
static void repair_save_failures(void) {
    for(unsigned v5=0;v5<2;v5++)for(unsigned i=0;i<3;i++) {
        seed_legacy(v5);uint8_t original[sizeof(disk)];memcpy(original,disk,sizeof(original));
        size_t original_len=disk_len;unsigned before=commits;
        repair_write_failure=(int[]){1,2,4}[i];reboot();failure=0;
        repaired();assert(s_storage_ready&&s_dirty&&commits==before);
        assert(disk_len==original_len&&!memcmp(original,disk,sizeof(original))&&erase_calls==0);
        world_debug_save();assert(!s_dirty&&commits==before+1);reboot();repaired();tests++;
    }
}
static void runtime_guards(void) {
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
    s_w.species=17;s_w.level=12;s_w.exp=0;s_party.party[0].species_id=17;
    world_grant_exp(60);assert(s_w.level==12&&s_w.exp==4380);reboot();
    assert(s_w.level==12&&s_w.exp==4380);tests++;
    s_w.level=100;s_w.exp=UINT32_MAX-5;world_grant_exp(60);
    assert(s_w.level==100&&s_w.exp==UINT32_MAX);reboot();assert(s_w.exp==UINT32_MAX);tests++;
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
    mon_t missing={.species_id=17,.level=12,.hp=71,.intimacy=40,.explore_value=123,.flags=1};
    assert(party_receive(&s_party,&missing)); // Old runtime caller without EXP.
    world_party_t view;world_party_snapshot(&view);party_t before=s_party;
    failure=4;assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_SAVE_FAILED);failure=0;
    assert(!memcmp(&before,&s_party,sizeof(before)));
    assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_OK&&s_w.exp==4320&&s_w.level==12);tests++;
    fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);enc_queue_init(&s_queue);
    encounter_t e={.species_id=17,.rarity=3,.hp_ratio=100,.ts=1};enc_queue_push(&s_queue,&e);
    assert(world_capture_uid(1,&missing)&&s_party.party[1].exp==4320&&s_party.party[1].level==12);
    reboot();assert(s_party.party[1].exp==4320&&s_party.party[1].intimacy==40);tests++;
}
static void malformed_protection(void) {
    for(unsigned mode=0;mode<2;mode++) {
        seed_legacy(false);save_t saved;memcpy(&saved,disk,sizeof(saved));
        if(mode)saved.party[2+MON_BYTES+1]=0;else saved.version=7;
        memcpy(disk,&saved,sizeof(saved));uint8_t old[sizeof(disk)];memcpy(old,disk,sizeof(old));
        unsigned before=commits;reboot();world_debug_save();
        assert(!s_storage_ready&&commits==before&&!memcmp(old,disk,sizeof(old))&&erase_calls==0);tests++;
    }
}
int main(void) {
    all_slots_and_restart();missing_exp_switch_win();repair_save_failures();runtime_guards();malformed_protection();
    printf("{\"cases\":%u,\"members_checked_per_load\":157,\"pidgeotto_level\":12,\"repaired_exp\":4320,\"after_reward_exp\":4380,\"save_version\":%u,\"save_bytes\":%zu,\"erase_calls\":%u}\n",
        tests,SAVE_VERSION,sizeof(save_t),erase_calls);
    return 0;
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative', action='store_true')
    args = parser.parse_args()
    lifecycle.harness = harness
    party_gate.CASES = ASSET_STUB + CASES
    result = party_gate.run(ROOT)
    result.update(sanitized=True, scope='Actual world/save/party/exp C with simulated NVS/device boundary',
                  negative_checks=[])
    if args.negative:
        changes = [
            ('load repair', 'uint16_t exp_repaired = normalize_party_exp(&s_party);', 'uint16_t exp_repaired = 0;'),
            ('box repair',
             'for (unsigned i = 0; i < PARTY_MAX + BOX_SPECIES; i++) {\n        if (i < PARTY_MAX && i >= party->party_count)',
             'for (unsigned i = 0; i < PARTY_MAX; i++) {\n        if (i < PARTY_MAX && i >= party->party_count)'),
            ('immediate persistence', 'save_now("legacy_experience");', '(void)exp_repaired;'),
            ('keep higher EXP', 'if (member->exp < minimum)', 'if (member->exp != minimum)'),
            ('reward baseline', 'uint32_t base = s_w.exp < minimum ? minimum : s_w.exp;', 'uint32_t base = s_w.exp;'),
            ('reward overflow', 's_w.exp = base > UINT32_MAX - amount ? UINT32_MAX : base + amount;', 's_w.exp = base + amount;'),
        ]
        for label, old, new in changes:
            with tempfile.TemporaryDirectory(prefix='legacy_exp_negative_') as folder:
                root = Path(folder);shutil.copytree(ROOT/'firmware/main',root/'firmware/main')
                path=root/'firmware/main/world.c';source=path.read_text()
                assert source.count(old)==1,label
                path.write_text(source.replace(old,new))
                try: party_gate.run(root)
                except AssertionError: result['negative_checks'].append(label)
                else: raise AssertionError('negative escaped: '+label)
    result['world_sha256']=hashlib.sha256((ROOT/'firmware/main/world.c').read_bytes()).hexdigest()
    output=ROOT/'reports/evidence/party-2026-09-08/legacy-exp.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
