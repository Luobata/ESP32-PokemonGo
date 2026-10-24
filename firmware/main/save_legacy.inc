// Legacy decode kept independent of V23 capacity; uses the locked RTC scratch.
static bool legacy_policies_valid(const save_v22_t *s) {
 for(unsigned i=0;i<157;i++){
  if(s->move_policies[i].disabled[23]&0x80)return false;
  bool active=i<PARTY_MAX?i<s->party[0]:s->party[2+i*MON_BYTES]!=0;
  if(!active)for(unsigned b=0;b<24;b++)if(s->move_policies[i].disabled[b])return false;
 }
 return true;
}
static save_read_result_t save_decode_legacy(save_v22_t *out, const void *blob, size_t len, uint8_t opening_seen)
{
    if (!out || !blob || len < sizeof(uint16_t) || len > sizeof(*out)) return SAVE_READ_ERROR;
    if(save_le16(blob)==22){
        // The importer reads into out. Preserve compressed input before expansion.
        memmove(storage_buf,blob,len);
        if(!save_storage_decode(out,sizeof(*out),storage_buf,len))return SAVE_READ_ERROR;
        blob=out;len=sizeof(*out);
    }
    bool legacy = len == sizeof(save_v5_t);
    bool version6 = len == sizeof(save_v6_t);
    bool version7 = len == sizeof(save_v7_t);
    bool version8 = len == sizeof(save_v8_t);
    bool version9 = len == sizeof(save_v9_t);
    bool version10 = len == sizeof(save_v10_t);
    bool version15 = len == sizeof(save_v15_t);
    bool version16 = len == sizeof(save_v16_t);
    bool version17 = len == sizeof(save_v17_t);
    bool version18 = len == sizeof(save_v18_t);
    bool version19 = len == sizeof(save_v19_t);
    bool version20 = len == sizeof(save_v20_t);
    bool version21 = len == sizeof(save_v21_t) && save_le16(blob)==21;
    if (!legacy && !version6 && !version7 && !version8 && !version9 && !version10 &&
        !version15 && !version16 && !version17 && !version18 && !version19 && !version20 && len != sizeof(save_v14_t) && len != sizeof(*out))
        return SAVE_READ_ERROR;
    memmove(out, blob, len);
    memset((uint8_t *)out + len, 0, sizeof(*out) - len);
    bool version14 = len == sizeof(save_v14_t) && out->version == 14;
    bool version13 = len == sizeof(save_v14_t) && out->version == 13;
    bool version12 = len == sizeof(save_v14_t) && out->version == 12;
    bool version11 = len == sizeof(save_v14_t) && out->version == 11;
    if(len==sizeof(save_v14_t)&&!(version11||version12||version13||version14))return SAVE_READ_ERROR;
    if (out->version != (legacy ? SAVE_LEGACY_VERSION : version6 ? 6 : version7 ? 7 : version8 ? 8 : version9 ? 9 : version10 ? 10 : version11 ? 11 : version12 ? 12 : version13 ? 13 : version14 ? 14 : version15 ? 15 : version16 ? 16 : version17 ? 17 : version18 ? 18 : version19 ? 19 : version20 ? 20 : version21 ? 21 : 22)) {
        ESP_LOGW(TAG, "存档版本 %u ≠ %d —— 保留原档，禁止新游戏覆盖",
                 out->version, 22);
        return SAVE_READ_ERROR;
    }
    if(out->version<21)memset(out->move_policies,0,sizeof(out->move_policies));
    if(!legacy_policies_valid(out))return SAVE_READ_ERROR;
    if(out->version<20)out->playtime_s=0;
    bool pre19=out->version<19;
    bool pre18=out->version<18;
    bool pre16=out->version<16;
    if(pre16)for(unsigned i=0;i<ENC_QUEUE_CAP;i++){out->queue.items[i].level=0;out->queue.items[i].activity=0;}
    if(!pre16)for(unsigned i=0;i<ENC_QUEUE_CAP;i++)if(out->queue.items[i].level>100||out->queue.items[i].activity>(pre19?8:ENC_ACTIVITY_EXPLORATION))return SAVE_READ_ERROR;
    if(pre19)out->exploration_wins=0;
    if(version15||version16||version17||version18||version19||version20||version21)out->version=22;
    // V5-V11 used species-indexed cells. Validate before adopting physical slots.
    if (out->version < 12) {
        for(unsigned i=0;i<LEGACY_BOX_SPECIES;i++) {
            uint8_t id=out->party[2+(PARTY_MAX+i)*MON_BYTES];
            if(id && id!=i+1)return SAVE_READ_ERROR;
        }
    }
    if(version11||version12||version13||version14)out->version=22;
    // A raw blob can contain an invalid _Bool representation. Compare its bytes
    // before evaluating it so malformed data is rejected without undefined reads.
    const bool no = false, yes = true;
    if (memcmp(&out->opening_seen, &no, sizeof(no)) != 0 &&
        memcmp(&out->opening_seen, &yes, sizeof(yes)) != 0) return SAVE_READ_ERROR;
    out->opening_seen = out->opening_seen || opening_seen != 0;
    if (legacy) {
        items_legacy_inventory_init(&out->inventory);
        out->version = 22;
    } else if (!items_legacy_inventory_valid(&out->inventory)) return SAVE_READ_ERROR;
    if (legacy || version6) {
        out->version = 22;
        // Older saves have no victory counter: grandfather existing adventurers.
        out->challenge.wild_wins = out->species != 0;
    }
    if (version7 || version8) {
        // Read old tail before overwriting it: expanded mons have different strides.
        trainer_store_v8_t previous;
        memcpy(&previous,(uint8_t *)out+sizeof(save_v6_t),sizeof(previous));
        achievement_v25_t achievements={0};
        if(version8)memcpy(&achievements,(uint8_t *)out+offsetof(save_v8_t,achievements),sizeof(achievements));
        trainer_store_t *next=&out->challenge;memset(next,0,sizeof(*next));
        next->wild_wins=previous.wild_wins;next->defeated=previous.defeated;
        next->league_stage=previous.league_stage;next->league_active=previous.league_active;
        // Session header has identical fields; only side/mon strides changed.
        memcpy(&next->session.rng,&previous.session.rng,sizeof(previous.session)-offsetof(trainer_session_v8_t,rng));
        next->session.pending_move=0;
        for(unsigned side=0;side<2;side++){
            trainer_side_t *d=&next->session.sides[side];const trainer_side_v8_t *s=&previous.session.sides[side];
            d->count=s->count;d->active=s->active;d->reflect=s->reflect;d->light_screen=s->light_screen;
            for(unsigned i=0;i<6;i++)memcpy(&d->mons[i],&s->mons[i],sizeof(s->mons[i]));
        }
        out->achievements=achievements;out->version=22;
    }
    if (legacy || version6 || version7 || version8 || version9) {
        memset(&out->refresh,0,sizeof(out->refresh));
        uint64_t seconds=out->last_uptime_us>0?(uint64_t)out->last_uptime_us/1000000:0;
        out->refresh.online_s=seconds>UINT32_MAX-ENC_BASE_INTERVAL_S?UINT32_MAX-ENC_BASE_INTERVAL_S:(uint32_t)seconds;
        // Existing players do not receive another boot gift on migration.
        out->refresh.base_started=out->scans!=0 || out->species!=0;
        out->refresh.next_base_s=out->refresh.online_s+ENC_BASE_INTERVAL_S;
        out->version=22;
    }
    if (legacy || version6 || version7 || version8 || version9 || version10) {
        exploration_init(&out->exploration);
        out->version=22;
    }
    // Early V11 called this byte reserved[0], with no range constraint. Later
    // V11 builds introduced tracking without a schema bump. Preserve valid
    // tracked species from those builds; an impossible ID means no old target.
    // V12+ owned and validated the field, so malformed modern IDs still fail.
    if (version11 && out->exploration.tracked_species > 151)
        out->exploration.tracked_species = 0;
    // V15/V16 receipt tail bytes were C padding, not partner reward fields.
    // Never interpret an old padding value as a new reward (or corrupt save).
    if (version15 || version16) {
        out->dungeon.receipt.partner_species = 0;
        out->dungeon.receipt.partner_shiny = 0;
    }
    if (!exploration_valid(&out->exploration)) return SAVE_READ_ERROR;
    if(pre18){memset(&out->regions,0,sizeof(out->regions));out->regions.selected=out->exploration.route;}
    if(version18)for(unsigned i=0;i<EXPLORATION_REGIONS;i++)if(out->regions.region[i].pity>5)return SAVE_READ_ERROR;
    if(!exploration_regions_valid(&out->regions))return SAVE_READ_ERROR;
    if (!enc_refresh_valid(&out->refresh)) return SAVE_READ_ERROR;
    if (!trainer_store_valid(&out->challenge)) return SAVE_READ_ERROR;
    bool migrated=legacy||version6||version7||version8||version9||version10||version11||version12;
    if(migrated){
        for(unsigned side=0;side<2;side++){
            trainer_side_t *t=&out->challenge.session.sides[side];
            if(t->count>TRAINER_SLOTS)return SAVE_READ_ERROR;
            for(unsigned i=0;i<t->count;i++){
                if(!combat_valid(&t->mons[i]))return SAVE_READ_ERROR;
                combat_migrate_gen2(&t->mons[i]);
            }
        }
    }
    if(migrated||version13)out->exploration.research_flags=0;
    if(!rest_clock_valid(&out->rest_clock))return SAVE_READ_ERROR;
    if(!exploration_updates_valid(&out->exploration_updates))return SAVE_READ_ERROR;
    if(!dungeon_progress_valid(&out->dungeon))return SAVE_READ_ERROR;
    return migrated||version13||version14||version15||version16||version17||version18||version19||version20||version21 ? SAVE_READ_MIGRATED : SAVE_READ_OK;
}

static bool legacy_party_valid(const save_v22_t *saved)
{
    const uint8_t *raw = saved->party;
    if (raw[0] > PARTY_MAX) return false;
    uint8_t box_count = 0;
    for (unsigned i = 0; i < PARTY_MAX + LEGACY_BOX_SPECIES; i++) {
        const uint8_t *mon = raw + 2 + i*MON_BYTES;
        bool active = i < PARTY_MAX ? i < raw[0] : mon[0] != 0;
        if (!active) {
            for (unsigned b = 0; b < MON_BYTES; b++) if (mon[b] != 0) return false;
        } else {
            if (mon[0] < 1 || mon[0] > LEGACY_BOX_SPECIES || mon[1] < 1 || mon[1] > LEVEL_MAX)
                return false;
            if (i >= PARTY_MAX) {
                box_count++;
            }
        }
    }
    if (raw[1] != box_count) return false;
    if (!raw[0]) {
        // Empty V5 snapshots are produced while a fresh game awaits a choice.
        // An absent leader with prior ownership/progress is not a new game.
        for (unsigned i = 0; i < 19; i++)
            if (saved->dex.caught[i] || saved->dex.shiny_caught[i]) return false;
        return box_count == 0 && saved->species == 0 &&
               saved->level == 0 && saved->exp == 0;
    }
    return true;
}
