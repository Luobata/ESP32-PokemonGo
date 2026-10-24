#!/usr/bin/env python3
"""Full physical warehouse: production world transactions, no private player data.

Real party/save/EXP code, synthetic progress and fault-injected NVS adapter.
The separate capture-capacity UI test drives the actual page and button events.
"""
import verify_trainer_campaign as h

h.CASES = r'''
static uint16_t setup(unsigned target, bool won) {
    fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
    party_init(&s_party);
    mon_t leader={.species_id=target,.level=77,.exp=exp_for_level(77),.hp=100,.nickname_idx=255};
    for(unsigned i=0;i<PARTY_MAX;i++)assert(party_receive(&s_party,&leader));
    for(unsigned i=0;i<BOX_CAPACITY;i++) {
        s_party.box[i]=(mon_t){.species_id=target==1?2:1,.level=10,
            .exp=exp_for_level(10),.hp=100,.nickname_idx=255,.flags=i%2};
        move_policy_set(&s_party.policies[PARTY_MAX+i],85,false);
    }
    s_w.species=target;s_w.level=77;s_w.exp=leader.exp;
    enc_queue_init(&s_queue);
    encounter_t e={.species_id=target,.rarity=5,.level=77,.hp_ratio=100,
        .activity=ENC_ACTIVITY_EXPLORATION};
    enc_queue_push(&s_queue,&e);uint16_t uid=s_queue.items[0].uid;
    battle_session_t session;
    assert(battle_session_init(&session,target,77,target,77,1024,123));
    if(won){session.started=session.finished=session.won=session.loot_checked=true;session.wild_hp=0;}
    assert(world_battle_set_uid(uid,&session));
    s_exploration_wins=12;world_debug_save();
    return uid;
}
static void full_guard(void) {
    for(unsigned target=1;target<=251;target++)for(unsigned won=0;won<2;won++) {
        uint16_t uid=setup(target,won);
        assert(!world_capture_has_room(target));
        assert(world_capture_break_chain_uid(uid)&&!s_exploration_wins);
        battle_session_t session;assert(world_battle_get_uid(uid,&session));session.started=true;
        if(won)session.capture_used_after_win=true;
        unsigned balls=s_inventory.quantity[ITEM_POKE];
        assert(world_capture_ball_spend_uid(uid,ITEM_POKE,&session));
        party_t before=s_party;dex_t dex=s_dex;
        mon_t caught={.species_id=target,.level=78,.exp=exp_for_level(78),.hp=100,.flags=1};
        // Capture assigns stable encounter traits; Smeargle stores sketches instead.
        caught.special.traits.hp_type=target==235?0:1;
        assert(world_capture_replace_uid(uid,&caught,BOX_CAPACITY,NULL)==WORLD_CAPTURE_FULL);
        assert(!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&dex,&s_dex,sizeof(dex)));
        unsigned slot=(unsigned[]){150,151,254,255,256,451,452,648,752}[(target+won)%9];
        mon_t expected=s_party.box[slot],stale=expected;stale.level++;
        assert(world_capture_replace_uid(uid,&caught,slot,&stale)==WORLD_CAPTURE_STALE);
        assert(world_capture_replace_uid(uid,&caught,BOX_CAPACITY,&expected)==WORLD_CAPTURE_INVALID);
        for(unsigned k=0;k<3;k++){
          failure=(int[]){1,2,4}[k];assert(world_capture_replace_uid(uid,&caught,slot,&expected)==WORLD_CAPTURE_SAVE_FAILED);failure=0;
          assert(!memcmp(&before,&s_party,sizeof(before))&&s_inventory.quantity[ITEM_POKE]==balls-1);
        }
        assert(world_capture_replace_uid(uid,&caught,slot,&expected)==WORLD_CAPTURE_OK);
        assert(party_total(&s_party)==759&&!memcmp(&s_party.box[slot],&caught,sizeof(caught)));
        assert(move_policy_allows(&s_party.policies[PARTY_MAX+slot],85));
        for(unsigned j=0;j<BOX_CAPACITY;j++)if(j!=slot)assert(!memcmp(&s_party.box[j],&before.box[j],sizeof(mon_t)));
        assert(world_capture_replace_uid(uid,&caught,slot,&caught)==WORLD_CAPTURE_INVALID);
        party_t saved=s_party;reboot();assert(!memcmp(&saved,&s_party,sizeof(saved)));
        tests++;
    }
}
static void room_and_retry(void) {
    uint16_t uid=setup(150,false);
    mon_t old=s_party.box[83];assert(world_box_release(83,&old)==WORLD_SWITCH_OK);
    assert(world_capture_has_room(150)&&party_total(&s_party)==758);
    assert(world_capture_break_chain_uid(uid)&&s_exploration_wins==0);
    battle_session_t session;assert(world_battle_get_uid(uid,&session));session.started=true;
    unsigned balls=s_inventory.quantity[ITEM_POKE];
    assert(world_capture_ball_spend_uid(uid,ITEM_POKE,&session));
    mon_t caught={.species_id=150,.level=78,.exp=exp_for_level(78),.hp=100,.flags=1,.nickname_idx=255};
    caught.special.traits.hp_type=1;
    party_t before=s_party;unsigned written=writes;
    for(unsigned mode=0;mode<3;mode++) {
        failure=(int[]){1,2,4}[mode];assert(!world_capture_uid(uid,&caught));failure=0;
        assert(!memcmp(&before,&s_party,sizeof(before))&&world_capture_has_room(150));
        assert(s_inventory.quantity[ITEM_POKE]==balls-1);
    }
    assert(writes>written&&world_capture_uid(uid,&caught));
    assert(!world_capture_uid(uid,&caught)&&party_total(&s_party)==759);
    assert(!memcmp(&s_party.box[83],&caught,sizeof(caught)));
    assert(move_policy_allows(&s_party.policies[PARTY_MAX+83],85));
    assert(s_inventory.quantity[ITEM_POKE]==balls-1);
    party_t saved=s_party;reboot();assert(s_storage_ready&&!memcmp(&saved,&s_party,sizeof(saved)));
    assert(dex_is_shiny_caught(&s_dex,150));tests++;
}
static void existing_box_or_team_space(void) {
    setup(150,false);
    s_party.box[23].species_id=150;mon_t old=s_party.box[23];
    assert(!world_capture_has_room(150));
    mon_t better=old;better.level=80;better.exp=exp_for_level(80);better.flags=1;
    assert(!party_receive(&s_party,&better)&&!memcmp(&s_party.box[23],&old,sizeof(old)));
    s_party.box[23].species_id=1;s_party.party_count=5;
    assert(world_capture_has_room(150)&&party_receive(&s_party,&better));
    assert(!memcmp(&s_party.party[5],&better,sizeof(better)));
    assert(!world_capture_has_room(0)&&!world_capture_has_room(252));tests++;
}
int main(void) {
    assert(assets_init());full_guard();room_and_retry();existing_box_or_team_space();
    printf("{\"passed\":true,\"cases\":%u,\"sanitized\":true,\"physical_device\":false}\n",tests);
    return 0;
}
'''

if __name__ == '__main__':
    h.run()
