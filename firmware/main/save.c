// main/save.c —— S18 存档。设计与取舍见 save.h。

#include <string.h>

#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "save.h"
#include "save_storage.h"
#include "save_bank.h"
#include "exp.h"

static const char *TAG = "save";
// Fixed 7792-byte scratch budget for legacy decode and migration.
// C3's separate RTC SRAM keeps this out of the main heap: ordinary BSS would
// consumed the contiguous headroom needed by USB/network operation. V23 uses
// flash-backed streaming; the legacy scratch remains separate from main DRAM.
// No retained contents are read: decode first copies the entire input.
// The existing rest clock already retains RTC SRAM during sleep. Callers
// serialize via the world save lock (boot is single-threaded).
#if defined(ESP_PLATFORM) && !defined(HOST_BUILD)
#include "esp_attr.h"
static RTC_NOINIT_ATTR uint8_t storage_buf[sizeof(save_v22_t)] __attribute__((aligned(8)));
#else
static uint8_t storage_buf[sizeof(save_v22_t)] __attribute__((aligned(8)));
#endif
_Static_assert(sizeof(save_v22_t)==7792,"Legacy RTC budget must remain fixed");
_Static_assert(sizeof(save_t)<=SAVE_BANK_PAYLOAD_MAX,"World must fit a bank/backup segment");

// NVS 初始化。**存档必须自己负责这件事**，不能指望别人先做。
//
// 第一版没有这个函数 —— nvs_flash_init 藏在 world.c 的
// wifi_bring_up() 里，而 world_start 的顺序是「先读档、后起 WiFi」。
// 于是读档时 NVS 还没挂载，nvs_open 直接失败，
// **表现为「每次开机都是新游戏」而写入明明成功**。
//
// 教训是所有权：存档不依赖 WiFi，就不该等 WiFi 顺手把 NVS 带起来。
// 幂等 —— 重复调用返回 ESP_OK，所以 wifi_bring_up 那边不用改。
bool save_init(void)
{
    esp_err_t e = nvs_flash_init();
    // Initialization failure is not permission to erase a player's save.
    // Preserve the partition and surface the unavailable state to onboarding.
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "NVS 初始化失败: %s —— 存档不可用", esp_err_to_name(e));
        return false;
    }
    return true;
}

#define NS "pokewalk"      // NVS 命名空间
#define KEY "state"        // One versioned storage blob; decoded layout is save_t.
#define KEY_OPENING "opening"
#define KEY_GUARD "state_guard"

// 整块存而不是逐字段存 kv。
//
// 逐字段的好处是能单独更新（比如只改图鉴不动队列），
// 但那样**一次存档要 8 次 nvs_set + 8 次可能失败的点**，
// 而且字段加减时要同步维护键名表。
//
// V21 decoded state is 7792 bytes. NVS needs old and new blobs simultaneously;
// its theoretical blob limit does not imply our shared 24 KiB partition fits.
// V22 stores one losslessly encoded, checksummed blob, retaining NVS atomicity.
// 原子性也更好：要么整块新的，要么整块旧的，不会出现
// 「图鉴是新的而队列是旧的」这种半更新状态。


static bool fields_valid(const save_t *s);
static bool members_valid(const save_t *s);
static bool s_bank_reserved;
void save_bank_reserve(bool reserved) { s_bank_reserved=reserved; }
bool save_write(const save_t *s)
{
    if(s_bank_reserved || !s || s->version!=SAVE_VERSION || !fields_valid(s) || !members_valid(s))return false;
    nvs_handle_t h;
    if(nvs_open(NS,NVS_READWRITE,&h)!=ESP_OK)return false;
    const char *source=KEY;
    size_t len=0;esp_err_t e=nvs_get_blob(h,source,NULL,&len);
    if(e==ESP_ERR_NVS_NOT_FOUND){source=KEY_GUARD;e=nvs_get_blob(h,source,NULL,&len);}
    save_bank_ref_t old, next;const save_bank_ref_t *current=NULL;
    if(e!=ESP_OK && e!=ESP_ERR_NVS_NOT_FOUND){nvs_close(h);return false;}
    if(e==ESP_OK && len==sizeof(old)) {
        if(nvs_get_blob(h,source,&old,&len)!=ESP_OK || !save_bank_ref_valid(&old)){nvs_close(h);return false;}
        current=&old;
    } else if(e==ESP_OK && (len<sizeof(save_v5_t) || len>sizeof(save_v22_t))) {
        // PWZ1 may compress below the raw V5 size. Check its schema/magic via
        // a bounded read; the caller already validated the actual legacy world.
        if(len>SAVE_BANK_REF_SIZE && len<=sizeof(storage_buf)) {
            size_t n=len;
            if(nvs_get_blob(h,source,storage_buf,&n)!=ESP_OK || n!=len ||
               save_le16(storage_buf)!=22 || len<SAVE_STORAGE_HEADER || memcmp(storage_buf+2,"PWZ1",4)) {
                nvs_close(h);return false;
            }
        } else {nvs_close(h);return false;}
    }
    const save_bank_io_t *io=save_bank_platform();
    // Keep an independent old reference before recycling the inactive bank.
    // If a failed NVS update loses the primary key, boot can still find this
    // exact record. Never use an arbitrary newer/unreferenced bank as a save.
    if(current && (nvs_set_blob(h,KEY_GUARD,current,sizeof(*current))!=ESP_OK || nvs_commit(h)!=ESP_OK)){nvs_close(h);return false;}
    if(!save_bank_prepare(io,current,s,sizeof(*s),&next)){nvs_close(h);return false;}
    // The opening marker is monotonic. Write it before the authoritative ref,
    // so a marker failure cannot report a failed transaction after adoption.
    if(!current && (nvs_set_blob(h,KEY_GUARD,&next,sizeof(next))!=ESP_OK || nvs_commit(h)!=ESP_OK)){nvs_close(h);return false;}
    if(s->opening_seen)e=nvs_set_u8(h,KEY_OPENING,1);else e=ESP_OK;
    if(e==ESP_OK)e=nvs_set_blob(h,KEY,&next,sizeof(next));
    if(e==ESP_OK)e=nvs_commit(h);
    nvs_close(h);
    if(e!=ESP_OK){ESP_LOGE(TAG,"扩展存档提交失败: %s",esp_err_to_name(e));return false;}
    return true;
}

save_read_result_t save_read_status(save_t *out)
{
    if (!out) return SAVE_READ_ERROR;
    nvs_handle_t h;
    esp_err_t e = nvs_open(NS, NVS_READONLY, &h);
    if (e == ESP_ERR_NVS_NOT_FOUND) return SAVE_READ_EMPTY;
    if (e != ESP_OK) return SAVE_READ_ERROR;

    size_t len = 0;
    const char *source=KEY;
    e = nvs_get_blob(h, source, NULL, &len);
    if(e==ESP_ERR_NVS_NOT_FOUND){source=KEY_GUARD;e=nvs_get_blob(h,source,NULL,&len);}
    if (e == ESP_ERR_NVS_NOT_FOUND) {
        nvs_close(h);
        return SAVE_READ_EMPTY;
    }
    if (e != ESP_OK || len > sizeof(*out) || len < sizeof(uint16_t)) {
        nvs_close(h);
        return SAVE_READ_ERROR;
    }
    size_t expected_len = len;
    memset(out, 0, sizeof(*out));
    e = nvs_get_blob(h, source, out, &len);
    uint8_t opening_seen = 0;
    if (e == ESP_OK) (void)nvs_get_u8(h, KEY_OPENING, &opening_seen);
    nvs_close(h);
    if (e != ESP_OK || len != expected_len) return SAVE_READ_ERROR;
    return save_decode(out, out, len, opening_seen);
}


bool save_read(save_t *out) {
    save_read_result_t result = save_read_status(out);
    return result == SAVE_READ_OK || result == SAVE_READ_MIGRATED;
}

bool save_opening_seen(void)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) return false;
    uint8_t seen = 0;
    esp_err_t e = nvs_get_u8(h, KEY_OPENING, &seen);
    nvs_close(h);
    return e == ESP_OK && seen != 0;
}

bool save_mark_opening_seen(void)
{
    nvs_handle_t h;
    esp_err_t e = nvs_open(NS, NVS_READWRITE, &h);
    if (e != ESP_OK) return false;
    e = nvs_set_u8(h, KEY_OPENING, 1);
    if (e == ESP_OK) e = nvs_commit(h);
    nvs_close(h);
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "开场标记写入失败: %s", esp_err_to_name(e));
        return false;
    }
    return true;
}

bool save_exists(void)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) return false;
    size_t len = 0;
    esp_err_t e = nvs_get_blob(h, KEY, NULL, &len);
    if(e==ESP_ERR_NVS_NOT_FOUND)e=nvs_get_blob(h,KEY_GUARD,NULL,&len);
    nvs_close(h);
    // Presence is not validity, and a variable-length V22 is still an existing
    // save. Full validation remains in save_read_status; never offer to erase it.
    return e == ESP_OK;
}

bool save_erase(void)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READWRITE, &h) != ESP_OK) return false;
    esp_err_t state_e = nvs_erase_key(h, KEY);
    esp_err_t guard_e=nvs_erase_key(h,KEY_GUARD);
    esp_err_t opening_e = nvs_erase_key(h, KEY_OPENING);
    bool state_ok = (state_e == ESP_OK || state_e == ESP_ERR_NVS_NOT_FOUND) && (guard_e==ESP_OK || guard_e==ESP_ERR_NVS_NOT_FOUND);
    bool opening_ok = opening_e == ESP_OK || opening_e == ESP_ERR_NVS_NOT_FOUND;
    esp_err_t e = (state_ok && opening_ok) ? nvs_commit(h) : ESP_FAIL;
    nvs_close(h);
    return e == ESP_OK;
}

static bool saved_bool_valid(const bool *value)
{
    const bool no = false, yes = true;
    // Read the representation as bytes: evaluating a malformed persisted _Bool
    // before validation would itself be undefined behavior.
    return memcmp(value, &no, sizeof(no)) == 0 ||
           memcmp(value, &yes, sizeof(yes)) == 0;
}

static bool loaded_queue_valid(const enc_queue_t *queue)
{
    if (queue->count > ENC_QUEUE_CAP) return false;
    for (unsigned i = 0; i < queue->count; i++) {
        const encounter_t *entry = &queue->items[i];
        if (!entry->uid || entry->species_id < 1 || entry->species_id > DEX_SPECIES ||
            entry->rarity < 1 || entry->rarity > 5 || entry->hp_ratio > 100 ||
            entry->level > LEVEL_MAX || entry->activity > ENC_ACTIVITY_EXPLORATION ||
            !saved_bool_valid(&entry->is_shiny) ||
            !saved_bool_valid(&entry->is_transient) ||
            !saved_bool_valid(&entry->exp_granted)) return false;
        for (unsigned prior = 0; prior < i; prior++)
            if (queue->items[prior].uid == entry->uid) return false;
    }
    // next_uid == 0 is the valid state immediately after assigning UINT16_MAX.
    // Removed entries leave stale tail bytes; only the active prefix is owned.
    return true;
}


#include "save_legacy.inc"
static bool battle_traits_valid(const trainer_store_t *t){for(unsigned side=0;side<2;side++)for(unsigned i=0;i<t->session.sides[side].count&&i<6;i++){const combat_mon_t *b=&t->session.sides[side].mons[i];mon_t m={.species_id=b->species};memcpy(m.special.sketch,b->pp,4);if(!combat_individual_valid(&m))return false;}return true;}
static bool fields_valid(const save_t *s) {
    for(unsigned i=0;i<JOHTO_REWARD_COUNT;i++)if(s->research_rewards[i]>johto_reward_entitled(&s->johto,i))return false;
    return saved_bool_valid(&s->opening_seen) && loaded_queue_valid(&s->queue) &&
        items_inventory_valid(&s->inventory) && battle_traits_valid(&s->challenge) && battle_traits_valid(&s->activities.run.battle) && trainer_store_valid(&s->challenge) &&
        enc_refresh_valid(&s->refresh) && exploration_valid(&s->exploration) &&
        exploration_regions_valid(&s->regions) && exploration_updates_valid(&s->exploration_updates) &&
        rest_clock_valid(&s->rest_clock) && dungeon_progress_valid(&s->dungeon) && johto_valid(&s->johto) && activity_valid(&s->activities) && johto_story_valid(&s->story) && endgame_valid(&s->endgame) && endgame_battle_valid(&s->endgame,&s->challenge) && narrative_valid(&s->narrative) && field_state_valid(&s->field);
}
static bool members_valid(const save_t *s) {
    const party_t *p=&s->members;
    const activity_run_t *run=&s->activities.run;
    if(run->kind)for(unsigned i=0;i<run->count;i++){
        unsigned slot=run->slots[i];
        if(slot>=p->party_count||p->party[slot].species_id!=run->members[i].species_id||p->party[slot].flags!=run->members[i].flags)return false;
    }
    if(p->party_count>PARTY_MAX)return false;
    for(unsigned i=0;i<PARTY_MAX+BOX_CAPACITY;i++) {
        const mon_t *m=i<PARTY_MAX?&p->party[i]:&p->box[i-PARTY_MAX];
        bool active=i<PARTY_MAX?i<p->party_count:m->species_id!=0;
        if(!move_policy_valid(&p->policies[i]))return false;
        if(active) {
            if(!m->species_id||m->species_id>BOX_SPECIES||!m->level||m->level>LEVEL_MAX||!combat_individual_valid(m))return false;
        } else {
            const uint8_t *raw=(const uint8_t*)m;
            for(unsigned b=0;b<sizeof(*m);b++)if(raw[b])return false;
            for(unsigned b=0;b<MOVE_POLICY_BYTES;b++)if(p->policies[i].disabled[b])return false;
        }
    }
    if(!p->party_count) {
        for(unsigned i=0;i<DEX_BYTES;i++)if(s->dex.caught[i]||s->dex.shiny_caught[i])return false;
        return !party_total(p)&&!s->species&&!s->level&&!s->exp;
    }
    return true;
}
bool save_validate_world(const save_t *s,party_t *party) {
    if(!s||!party||s->version!=SAVE_VERSION||!fields_valid(s)||!members_valid(s))return false;
    if(party!=&s->members)*party=s->members;
    return true;
}
static void migrate_old_dex(dex_t *out,const dex_v23_t *in) {
    memset(out,0,sizeof(*out));
#define DEX_COPY(field) memcpy(out->field,in->field,19);out->field[18]&=0x7f
    DEX_COPY(seen);DEX_COPY(caught);DEX_COPY(shiny_seen);DEX_COPY(shiny_caught);
#undef DEX_COPY
}
static void migrate_inventory(inventory_t *out,const inventory_v25_t *in) {
    memset(out,0,sizeof(*out));memcpy(out->quantity,in->quantity,sizeof(in->quantity));
}
static void migrate_achievements(achievement_store_t *out,const achievement_v25_t *in) {
    *out=(achievement_store_t){.evolutions=in->evolutions,.claimed=in->claimed};
}
static void migrate_v23_tail(save_v27_t *out,const uint8_t *tail) {
    // V23 and V24 have identical relative offsets from queue through playtime.
#define COPY(field) memcpy(&out->field,tail+(offsetof(save_v23_t,field)-offsetof(save_v23_t,queue)),sizeof(out->field))
    COPY(queue);COPY(motion_q10);COPY(scans);COPY(last_uptime_us);COPY(opening_seen);
    COPY(challenge);COPY(refresh);COPY(exploration);
    COPY(dungeon);COPY(exploration_updates);COPY(rest_clock);COPY(regions);
    COPY(exploration_wins);COPY(playtime_s);
#undef COPY
    migrate_inventory(&out->inventory,(const inventory_v25_t*)(tail+(offsetof(save_v23_t,inventory)-offsetof(save_v23_t,queue))));
    migrate_achievements(&out->achievements,(const achievement_v25_t*)(tail+(offsetof(save_v23_t,achievements)-offsetof(save_v23_t,queue))));
    migrate_old_dex(&out->dex,(const dex_v23_t*)(tail+(offsetof(save_v23_t,dex)-offsetof(save_v23_t,queue))));
}
static bool historical_trainer_valid(const trainer_store_t *st) {
 const trainer_session_t *s=&st->session;
 if(!s->active&&!st->league_active&&!s->finished)return true;
 if(s->trainer>=26)return false;
 for(unsigned side=0;side<2;side++){
  if(s->sides[side].count>6)return false;
  for(unsigned i=0;i<s->sides[side].count;i++){
   const combat_mon_t *m=&s->sides[side].mons[i];
   if(m->species>151||m->transform_species>151)return false;
  }
 }
 return true;
}
static bool historical_species_valid(const mon_v27_t *party,unsigned count,const mon_v27_t *box,const enc_queue_t *queue) {
    if(count>6||queue->count>16)return false;
    for(unsigned i=0;i<count;i++)if(!party[i].species_id||party[i].species_id>151)return false;
    for(unsigned i=0;i<453;i++)if(box[i].species_id>151)return false;
    for(unsigned i=0;i<queue->count;i++)if(queue->items[i].species_id>151)return false;
    return true;
}
static save_read_result_t decode_v27(save_v27_t *out,const void *blob,size_t len,uint8_t opening_seen) {
    if(!out||!blob||len<2||len>sizeof(*out))return SAVE_READ_ERROR;
    unsigned version=save_le16(blob);
    if((version>=23&&version<=27)&&len==sizeof(save_bank_ref_t)) {
        save_bank_ref_t ref;memcpy(&ref,blob,sizeof(ref));
        size_t expected=version==23?sizeof(save_v23_t):version==24?sizeof(save_v24_t):version==25?sizeof(save_v25_t):version==26?sizeof(save_v26_t):sizeof(*out);
        if(save_bank_length(&ref)!=expected||!save_bank_read(save_bank_platform(),&ref,out,sizeof(*out)))return SAVE_READ_ERROR;
        blob=out;len=expected;
    }
    if(version==23) {
        if(len!=sizeof(save_v23_t))return SAVE_READ_ERROR;
        memmove(out,blob,len);
        save_v23_t *old23=(save_v23_t*)out;
        if(!historical_trainer_valid(&old23->challenge)||!historical_species_valid(old23->members.party,old23->members.party_count,old23->members.box,&old23->queue))return SAVE_READ_ERROR;
        for(unsigned i=0;i<459;i++)if(old23->members.policies[i].disabled[23]&0x80)return SAVE_READ_ERROR;
        const size_t tail=offsetof(save_v23_t,queue);
        _Static_assert(sizeof(save_v23_t)-offsetof(save_v23_t,queue)<=sizeof(storage_buf),"V23 migration tail exceeds RTC budget");
        memcpy(storage_buf,(uint8_t*)out+tail,sizeof(save_v23_t)-tail);
        // Preserve all 459 physical individuals and their old 191 assignments.
        // Descending order avoids overwriting an unread 24-byte policy.
        for(unsigned i=459;i-->0;){
            memmove(&out->members.policies[i],&old23->members.policies[i],24);
            memset(out->members.policies[i].disabled+24,0,8);
        }
        memset((uint8_t*)out+offsetof(save_v27_t,queue),0,sizeof(*out)-offsetof(save_v27_t,queue));
        migrate_v23_tail(out,storage_buf);
        out->version=27;johto_init(&out->johto);

        if(!saved_bool_valid(&out->opening_seen))return SAVE_READ_ERROR;
        out->opening_seen=out->opening_seen||opening_seen!=0;
        return SAVE_READ_MIGRATED;
    }
    if(version==24) {
        if(len!=sizeof(save_v24_t))return SAVE_READ_ERROR;
        memmove(out,blob,len);save_v24_t *old24=(save_v24_t*)out;
        if(!historical_trainer_valid(&old24->challenge)||!historical_species_valid(old24->members.party,old24->members.party_count,old24->members.box,&old24->queue))return SAVE_READ_ERROR;
        const size_t tail=offsetof(save_v24_t,queue);
        _Static_assert(sizeof(save_v24_t)-offsetof(save_v24_t,queue)<=sizeof(storage_buf),"V24 tail exceeds RTC budget");
        memcpy(storage_buf,(uint8_t*)out+tail,sizeof(save_v24_t)-tail);
        memset((uint8_t*)out+offsetof(save_v27_t,queue),0,sizeof(*out)-offsetof(save_v27_t,queue));
        migrate_v23_tail(out,storage_buf);
        memcpy(&out->johto,storage_buf+(offsetof(save_v24_t,johto)-tail),sizeof(out->johto));
        out->version=27;

        if(!saved_bool_valid(&out->opening_seen))return SAVE_READ_ERROR;
        out->opening_seen=out->opening_seen||opening_seen!=0;return SAVE_READ_MIGRATED;
    }
    if(version==25) {
        if(len!=sizeof(save_v25_t))return SAVE_READ_ERROR;
        memmove(out,blob,len);
        const size_t tail=offsetof(save_v25_t,queue);
        _Static_assert(sizeof(save_v25_t)-offsetof(save_v25_t,queue)<=sizeof(storage_buf),"V25 migration exceeds RTC budget");
        memcpy(storage_buf,(uint8_t*)out+tail,sizeof(save_v25_t)-tail);
        memset((uint8_t*)out+offsetof(save_v27_t,queue),0,sizeof(*out)-offsetof(save_v27_t,queue));
#define COPY25(field) memcpy(&out->field,storage_buf+(offsetof(save_v25_t,field)-tail),sizeof(out->field))
        COPY25(queue);COPY25(dex);COPY25(motion_q10);COPY25(scans);COPY25(last_uptime_us);COPY25(opening_seen);
        COPY25(challenge);COPY25(refresh);COPY25(exploration);COPY25(dungeon);COPY25(exploration_updates);
        COPY25(rest_clock);COPY25(regions);COPY25(exploration_wins);COPY25(playtime_s);COPY25(johto);
#undef COPY25
        migrate_inventory(&out->inventory,(const inventory_v25_t*)(storage_buf+(offsetof(save_v25_t,inventory)-tail)));
        migrate_achievements(&out->achievements,(const achievement_v25_t*)(storage_buf+(offsetof(save_v25_t,achievements)-tail)));
        out->version=27;

        if(!saved_bool_valid(&out->opening_seen))return SAVE_READ_ERROR;
        out->opening_seen=out->opening_seen||opening_seen!=0;return SAVE_READ_MIGRATED;
    }
    if(version==26) {
        if(len!=sizeof(save_v26_t))return SAVE_READ_ERROR;
        memmove(out,blob,len);memset((uint8_t*)out+len,0,sizeof(*out)-len);out->version=27;

        if(!saved_bool_valid(&out->opening_seen))return SAVE_READ_ERROR;
        out->opening_seen=out->opening_seen||opening_seen!=0;return SAVE_READ_MIGRATED;
    }
    if(version==27) {
        if(len==sizeof(save_bank_ref_t)) {
            save_bank_ref_t ref;memcpy(&ref,blob,sizeof(ref));
            if(save_bank_length(&ref)!=sizeof(*out)||!save_bank_read(save_bank_platform(),&ref,out,sizeof(*out)))return SAVE_READ_ERROR;
        } else if(len==sizeof(*out))memmove(out,blob,len);
        else return SAVE_READ_ERROR;
        if(out->version!=27)return SAVE_READ_ERROR;
        if(!saved_bool_valid(&out->opening_seen))return SAVE_READ_ERROR;
        out->opening_seen=out->opening_seen||opening_seen!=0;
        return SAVE_READ_OK;
    }
    if(len>sizeof(save_v22_t))return SAVE_READ_ERROR;
    save_v22_t *old=(save_v22_t*)out;
    save_read_result_t result=save_decode_legacy(old,blob,len,opening_seen);
    if((result!=SAVE_READ_OK&&result!=SAVE_READ_MIGRATED)||!historical_trainer_valid(&old->challenge)||!legacy_party_valid(old)||!loaded_queue_valid(&old->queue))return SAVE_READ_ERROR;
    for(unsigned i=0;i<old->queue.count;i++)if(old->queue.items[i].species_id>151)return SAVE_READ_ERROR;
    // The compressed input is no longer needed. Reuse the SAME fixed RTC area
    // for normalized legacy bytes, before expanding into the transaction buffer.
    memcpy(storage_buf,old,sizeof(*old));old=(save_v22_t*)storage_buf;
    memset(out,0,sizeof(*out));out->version=27;
    out->pet=old->pet;
    out->species=old->species;
    out->level=old->level;
    out->exp=old->exp;
    out->queue=old->queue;
    migrate_old_dex(&out->dex,&old->dex);
    out->motion_q10=old->motion_q10;
    out->scans=old->scans;
    out->last_uptime_us=old->last_uptime_us;
    out->opening_seen=old->opening_seen;
    migrate_inventory(&out->inventory,&old->inventory);
    out->challenge=old->challenge;
    migrate_achievements(&out->achievements,&old->achievements);
    out->refresh=old->refresh;
    out->exploration=old->exploration;
    out->dungeon=old->dungeon;
    out->exploration_updates=old->exploration_updates;
    out->rest_clock=old->rest_clock;
    out->regions=old->regions;
    out->exploration_wins=old->exploration_wins;
    out->playtime_s=old->playtime_s;
    out->members.party_count=old->party[0];
    for(unsigned i=0;i<157;i++){
        mon_v27_t *mon=i<6?&out->members.party[i]:&out->members.box[i-6];
        memcpy(mon,old->party+2+i*MON_BYTES,MON_BYTES);
    }
    for(unsigned i=0;i<157;i++)memcpy(out->members.policies[i].disabled,old->move_policies[i].disabled,24);
    johto_init(&out->johto);
    return SAVE_READ_MIGRATED;
}

static void expand_member(mon_t *out,const mon_v27_t *in) {
    mon_v27_t old;memcpy(&old,in,sizeof(old));memset(out,0,sizeof(*out));memcpy(out,&old,sizeof(old));
}
static void expand_v27(save_t *out) {
    save_v27_t *old=(save_v27_t*)out;
    const size_t at=offsetof(save_v27_t,queue);
    _Static_assert(sizeof(save_v27_t)-offsetof(save_v27_t,queue)<=sizeof(storage_buf),"Migration RTC budget");
    memcpy(storage_buf,(uint8_t*)out+at,sizeof(*old)-at);
    uint8_t count=old->members.party_count;
    for(unsigned i=459;i-->0;)memmove(&out->members.policies[i],&old->members.policies[i],32);
    memset(out->members.policies+459,0,(PARTY_MAX+BOX_CAPACITY-459)*sizeof(move_policy_t));
    for(unsigned i=453;i-->0;)expand_member(&out->members.box[i],&old->members.box[i]);
    for(unsigned i=6;i-->0;)expand_member(&out->members.party[i],&old->members.party[i]);
    out->members.party_count=count;
    memset(out->members.box+453,0,(BOX_CAPACITY-453)*sizeof(mon_t));
    memset((uint8_t*)out+offsetof(save_t,queue),0,sizeof(*out)-offsetof(save_t,queue));
#define COPY27(f) memcpy(&out->f,storage_buf+(offsetof(save_v27_t,f)-at),sizeof(out->f))
    COPY27(queue);COPY27(dex);COPY27(motion_q10);COPY27(scans);COPY27(last_uptime_us);COPY27(opening_seen);
    COPY27(inventory);COPY27(challenge);COPY27(achievements);COPY27(refresh);COPY27(exploration);COPY27(dungeon);
    COPY27(exploration_updates);COPY27(rest_clock);COPY27(regions);COPY27(exploration_wins);COPY27(playtime_s);
    COPY27(johto);COPY27(research_rewards);
#undef COPY27
    const activity_v27_t *a=(const activity_v27_t*)(storage_buf+(offsetof(save_v27_t,activities)-at));
    activity_store_t *b=&out->activities;
    b->run.battle=a->run.battle;memcpy(b->run.policies,a->run.policies,sizeof(b->run.policies));
    for(unsigned i=0;i<3;i++)expand_member(&b->run.members[i],&a->run.members[i]);
    expand_member(&b->run.found,&a->run.found);expand_member(&b->run.candidate,&a->run.candidate);
    // Identical scalar tails, whose offsets move only with the member extension.
    memcpy(&b->run.earned,&a->run.earned,sizeof(a->run)-offsetof(activity_run_v27_t,earned));
    memcpy(&b->pending,&a->pending,sizeof(*a)-offsetof(activity_v27_t,pending));
    // Preserve the previously locked egg outcome when the new egg rate changes.
    if(out->johto.egg_status&&out->johto.egg_seed%256&&!(out->johto.egg_seed%32))out->johto.egg_seed++;
    for(unsigned i=0;i<out->queue.count;i++)if(out->queue.items[i].species_id==201)out->queue.items[i].biome=0;
    out->version=SAVE_VERSION;
}
save_read_result_t save_decode(save_t *out,const void *blob,size_t len,uint8_t opening_seen) {
    if(!out||!blob||len<2||len>sizeof(*out))return SAVE_READ_ERROR;
    unsigned version=save_le16(blob);
    if(version==28||version==29||version==30||version==31){
        size_t historical_size=version==28?sizeof(save_v28_t):version==29?sizeof(save_v29_t):version==30?sizeof(save_v30_t):sizeof(save_v31_t);
        if(len==sizeof(save_bank_ref_t)){save_bank_ref_t ref;memcpy(&ref,blob,len);if(save_bank_length(&ref)!=historical_size||!save_bank_read(save_bank_platform(),&ref,out,sizeof(*out)))return SAVE_READ_ERROR;}
        else if(len==historical_size)memmove(out,blob,len);else return SAVE_READ_ERROR;
        if(out->version!=version)return SAVE_READ_ERROR;
        memset((uint8_t*)out+historical_size,0,sizeof(*out)-historical_size);out->version=SAVE_VERSION;
    }else if(version==SAVE_VERSION){
        if(len==sizeof(save_bank_ref_t)){
            save_bank_ref_t ref;memcpy(&ref,blob,sizeof(ref));
            if(save_bank_length(&ref)!=sizeof(*out)||!save_bank_read(save_bank_platform(),&ref,out,sizeof(*out)))return SAVE_READ_ERROR;
        }else if(len==sizeof(*out))memmove(out,blob,len);else return SAVE_READ_ERROR;
    }else{
        save_read_result_t result=decode_v27((save_v27_t*)out,blob,len,opening_seen);
        if(result!=SAVE_READ_OK&&result!=SAVE_READ_MIGRATED)return SAVE_READ_ERROR;
        expand_v27(out);
    }
    if(version<29){for(unsigned side=0;side<2;side++)for(unsigned i=0;i<6;i++){memset(out->challenge.session.sides[side].mons[i].pp,0,4);memset(out->activities.run.battle.session.sides[side].mons[i].pp,0,4);}}
    if(out->version!=SAVE_VERSION||!fields_valid(out)||!members_valid(out))return SAVE_READ_ERROR;
    if(!saved_bool_valid(&out->opening_seen))return SAVE_READ_ERROR;
    if(version<31){
        narrative_init(&out->narrative);
        out->narrative.bug_evidence=out->activities.bug_completed!=0;
        out->narrative.legacy_final=johto_story_final_ready(&out->story,&out->johto,out->challenge.defeated,out->activities.silver_feather);
    }
        out->opening_seen=out->opening_seen||opening_seen!=0;
    return version==SAVE_VERSION?SAVE_READ_OK:SAVE_READ_MIGRATED;
}

_Static_assert(SAVE_VERSION==SAVE_BANK_CURRENT_VERSION,"Update logical and bank version admission together");
