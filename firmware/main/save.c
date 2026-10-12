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
static bool fields_valid(const save_t *s) {
    return saved_bool_valid(&s->opening_seen) && loaded_queue_valid(&s->queue) &&
        items_inventory_valid(&s->inventory) && trainer_store_valid(&s->challenge) &&
        enc_refresh_valid(&s->refresh) && exploration_valid(&s->exploration) &&
        exploration_regions_valid(&s->regions) && exploration_updates_valid(&s->exploration_updates) &&
        rest_clock_valid(&s->rest_clock) && dungeon_progress_valid(&s->dungeon);
}
static bool members_valid(const save_t *s) {
    const party_t *p=&s->members;
    if(p->party_count>PARTY_MAX)return false;
    for(unsigned i=0;i<PARTY_MAX+BOX_CAPACITY;i++) {
        const mon_t *m=i<PARTY_MAX?&p->party[i]:&p->box[i-PARTY_MAX];
        bool active=i<PARTY_MAX?i<p->party_count:m->species_id!=0;
        if(!move_policy_valid(&p->policies[i]))return false;
        if(active) {
            if(!m->species_id||m->species_id>BOX_SPECIES||!m->level||m->level>LEVEL_MAX)return false;
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
save_read_result_t save_decode(save_t *out,const void *blob,size_t len,uint8_t opening_seen) {
    if(!out||!blob||len<2||len>sizeof(*out))return SAVE_READ_ERROR;
    unsigned version=save_le16(blob);
    if(version==SAVE_VERSION) {
        if(len==sizeof(save_bank_ref_t)) {
            save_bank_ref_t ref;memcpy(&ref,blob,sizeof(ref));
            if(save_bank_length(&ref)!=sizeof(*out)||!save_bank_read(save_bank_platform(),&ref,out,sizeof(*out)))return SAVE_READ_ERROR;
        } else if(len==sizeof(*out))memmove(out,blob,len);
        else return SAVE_READ_ERROR;
        if(out->version!=SAVE_VERSION||!fields_valid(out)||!members_valid(out))return SAVE_READ_ERROR;
        out->opening_seen=out->opening_seen||opening_seen!=0;
        return SAVE_READ_OK;
    }
    if(len>sizeof(save_v22_t))return SAVE_READ_ERROR;
    save_v22_t *old=(save_v22_t*)out;
    save_read_result_t result=save_decode_legacy(old,blob,len,opening_seen);
    if((result!=SAVE_READ_OK&&result!=SAVE_READ_MIGRATED)||!legacy_party_valid(old)||!loaded_queue_valid(&old->queue))return SAVE_READ_ERROR;
    // The compressed input is no longer needed. Reuse the SAME fixed RTC area
    // for normalized legacy bytes, before expanding into the transaction buffer.
    memcpy(storage_buf,old,sizeof(*old));old=(save_v22_t*)storage_buf;
    memset(out,0,sizeof(*out));out->version=SAVE_VERSION;
    out->pet=old->pet;
    out->species=old->species;
    out->level=old->level;
    out->exp=old->exp;
    out->queue=old->queue;
    out->dex=old->dex;
    out->motion_q10=old->motion_q10;
    out->scans=old->scans;
    out->last_uptime_us=old->last_uptime_us;
    out->opening_seen=old->opening_seen;
    out->inventory=old->inventory;
    out->challenge=old->challenge;
    out->achievements=old->achievements;
    out->refresh=old->refresh;
    out->exploration=old->exploration;
    out->dungeon=old->dungeon;
    out->exploration_updates=old->exploration_updates;
    out->rest_clock=old->rest_clock;
    out->regions=old->regions;
    out->exploration_wins=old->exploration_wins;
    out->playtime_s=old->playtime_s;
    if(!party_deserialize(&out->members,old->party,sizeof(old->party)))return SAVE_READ_ERROR;
    memcpy(out->members.policies,old->move_policies,sizeof(old->move_policies));
    return fields_valid(out)&&members_valid(out)?SAVE_READ_MIGRATED:SAVE_READ_ERROR;
}
