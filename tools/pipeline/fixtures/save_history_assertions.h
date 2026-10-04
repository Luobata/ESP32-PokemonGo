// Expectations describe synthetic progress, independent of current byte layout.
// Shared by the decoder/world boot and real-NVS USB restore integration tests.
static void history_assert(const save_t *s, unsigned version) {
    party_t p; assert(s->version==SAVE_VERSION && save_validate_world(s,&p));
    assert(s->species==25 && s->level==32 && s->exp==32768 && s->opening_seen);
    assert(p.party_count==2 && party_total(&p)==3);
    assert(p.party[0].species_id==25 && p.party[0].level==32 && p.party[0].exp==32768);
    assert(p.party[1].species_id==1 && p.party[1].level==16 && p.party[1].exp==4096);
    const mon_t *box=&p.box[version<12 ? 148 : 3];
    assert(box->species_id==149 && box->flags==1 && box->level==60 && box->exp==216000);
    assert(dex_count_caught(&s->dex)==3 && dex_is_shiny_caught(&s->dex,149));
    assert(s->pet.stamina==45*NURT_Q && s->pet.mood==80*NURT_Q);
    assert(s->pet.satiety==70*NURT_Q && s->pet.intimacy==30*NURT_Q);
    assert(s->scans==19 && s->motion_q10==7890);
    assert(s->queue.count==1 && s->queue.next_uid==43 && s->queue.dropped==3);
    const encounter_t *e=&s->queue.items[0];
    assert(e->uid==42 && e->species_id==133 && e->is_shiny && e->hp_ratio==64);
    assert(e->level==(version<16 ? 0 : 28) && e->activity==(version<16 ? 0 : 2));
    if(version>=6) {
        assert(s->inventory.quantity[ITEM_POKE]==42 && s->inventory.quantity[ITEM_LEAF_STONE]==2);
        assert(s->inventory.quantity[ITEM_MILK]==3);
    } else {
        inventory_t initial; items_inventory_init(&initial);
        assert(!memcmp(&s->inventory,&initial,sizeof(initial)));
    }
    if(version>=7) {
        assert(s->challenge.wild_wins==27 && s->challenge.defeated==3);
        const trainer_session_t *session=&s->challenge.session;
        assert(session->rng==0x12345678 && session->turns==7 && session->active==1);
        assert(session->trainer==2 && session->ability==1024 && session->participated==1);
        for(unsigned side=0;side<2;side++) {
            const trainer_side_t *t=&session->sides[side];
            assert(t->count==2 && t->reflect==2 && t->mons[1].hp==0);
            const trainer_mon_t *m=&t->mons[0];
            assert(m->species==(side?74:25) && m->level==32 && m->special==2 && m->defense==-1);
            unsigned max=version<=12 ? combat_max_hp(m->species,m->level) : 100;
            assert(m->max_hp==max && m->hp==(version<=12 ? (60*max+99)/100 : 60));
        }
    } else assert(s->challenge.wild_wins==1 && !s->challenge.session.active);
    assert(s->achievements.evolutions==(version<8 ? 0 : 4));
    assert(s->achievements.claimed==(version<8 ? 0 : 5));
    assert(s->refresh.online_s==120 && s->refresh.base_started==1);
    if(version>=10) assert(s->refresh.discoveries==8 && s->refresh.history[0].key==123);
    if(version>=11) {
        assert(s->exploration.route==2 && s->exploration.energy==13 && s->exploration.steps==234);
        assert(s->exploration.tracked_species==(version==11 ? 0 : 133));
    }
    assert(s->exploration.research_flags==(version<14 ? 0 : 0x12));
    if(version>=15) {
        assert(s->dungeon.clears==2 && s->dungeon.run_id==23 && s->dungeon.paid_nodes==0x13);
        assert(s->dungeon.receipt.xp==310 && s->dungeon.receipt.items.quantity[ITEM_GREAT]==2);
        assert(s->dungeon.receipt.first_elite==1);
    }
    assert(!s->dungeon.receipt.partner_species && !s->dungeon.receipt.partner_shiny);
    if(version>=16) {
        assert(s->exploration_updates.rounds[2]==3 && s->exploration_updates.targets[2]==133);
        assert(s->exploration_updates.chapters[2]==2 && s->exploration_updates.activity_runs[1]==3);
        assert(s->exploration_updates.activity_progress[1]==2 && s->exploration_updates.activity_uid[1]==42);
    }
    assert(s->rest_clock.epoch_us==(version<17 ? 0 : 1728000000000000LL));
    assert(s->rest_clock.online_us==(version<17 ? 0 : 120000000));
    if(version<18){
        exploration_regions_t empty={.selected=version>=11?2:0};
        assert(!memcmp(&s->regions,&empty,sizeof(empty)));
    }else{
        assert(s->regions.selected==4&&s->regions.region[0].steps==57&&s->regions.region[0].clears==2);
        assert(s->regions.region[0].clues==2&&s->regions.region[0].pulse==1&&s->regions.region[0].target==131);
        assert(s->regions.region[0].pity==4&&s->regions.region[0].deep==1&&s->regions.region[0].traced==1&&s->regions.region[0].claimed==1&&s->regions.region[0].challenge_clear==1);
        assert(s->regions.dungeon_pity==3&&s->regions.expedition_clears==1);
        assert(s->regions.pending_items.quantity[ITEM_WATER_STONE]==1&&s->regions.pending_partner.species_id==131&&s->regions.pending_partner.is_shiny&&s->regions.pending_partner.level==42);
    }
}
