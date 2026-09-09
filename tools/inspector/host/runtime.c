/* Deterministic desktop harness. Page/render/asset/logic code is compiled from
 * firmware/main unchanged. WiFi, NVS, audio and wall clock are fixture services;
 * this is a rendering/interaction preview, not an emulation of those devices. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "lvgl.h"
#include "bsp_display.h"
#include "assets.h"
#include "exp.h"
#include "evolution.h"
#include "nav.h"
#include "play.h"
#include "pokemon_names.h"
#include "render.h"
#include "save.h"
#include "screen.h"
#include "screen_idle.h"
#include "sfx.h"
#include "audio_settings.h"
#include "sound_mixer.h"
#include "music_director.h"
#include "world.h"

static uint64_t now_ms;
static uint8_t backlight = 100;
void bsp_display_backlight(uint8_t percent) { backlight = percent; }
static lv_timer_t timers[16];
static uint8_t lcd[SCREEN_W * SCREEN_H * 2];
static const uint8_t *pending_pixels;
static int pending_y;
static uint64_t last_presented_ms;
static world_t world;
static enc_queue_t queue;
static dex_t dex;
static party_t party;
static inventory_t inventory;
static bool opening_seen;
static unsigned starter_save_failures;
static trainer_store_t challenge;
static achievement_store_t achievements;
static exploration_state_t exploration;
static enc_refresh_state_t refresh;
static int save_failure_after = -1;
static unsigned save_delay_ms; // Fault fixture: blocking NVS with no UI timer ticks.
static bool host_save_fails(void)
{
    now_ms += save_delay_ms;
    save_delay_ms = 0;
    if (starter_save_failures) { --starter_save_failures; return true; }
    if (save_failure_after == 0) { save_failure_after = -1; return true; }
    if (save_failure_after > 0) --save_failure_after;
    return false;
}
static bool active_valid;
static encounter_t active_enc;
static battle_session_t active_battle;
static struct {
    uint16_t uid;
    uint32_t ts;
    battle_session_t value;
} battles[ENC_QUEUE_CAP];
uint32_t dbg_battle_seed = 1;
extern void host_redraw(void);

int64_t esp_timer_get_time(void) { return (int64_t)now_ms * 1000; }
lv_timer_t *lv_timer_create(void (*cb)(lv_timer_t *), uint32_t period, void *data)
{
    for (size_t i = 0; i < sizeof(timers) / sizeof(*timers); i++) {
        if (!timers[i].active) {
            timers[i] = (lv_timer_t){cb, now_ms + period, period, data, true};
            return &timers[i];
        }
    }
    fputs("preview timer capacity exceeded\n", stderr);
    exit(2);
}
void lv_timer_delete(lv_timer_t *t) { if (t) t->active = false; }
static void advance(uint32_t ms)
{
    uint64_t end = now_ms + ms;
    for (;;) {
        lv_timer_t *next = NULL;
        for (size_t i = 0; i < sizeof(timers) / sizeof(*timers); i++)
            if (timers[i].active && timers[i].due <= end &&
                (!next || timers[i].due < next->due)) next = &timers[i];
        if (!next) break;
        now_ms = next->due;
        next->due += next->period;
        next->callback(next);
    }
    now_ms = end;
}

int esp_lcd_panel_draw_bitmap(esp_lcd_panel_handle_t p, int x0, int y0,
                             int x1, int y1, const void *pixels)
{
    (void)p;
    if (pending_pixels || x0 != 0 || x1 != SCREEN_W || y0 < 0 ||
        y1 > SCREEN_H || y1 - y0 != SCREEN_BAND_H) {
        fputs("invalid or unsynchronized LCD transfer\n", stderr); exit(3);
    }
    /* Retain the pointer until production screen.c issues its DMA barrier. */
    pending_pixels = pixels;
    pending_y = y0;
    return 0;
}
int esp_lcd_panel_io_tx_param(esp_lcd_panel_io_handle_t io, int cmd,
                             const void *data, size_t size)
{
    (void)io; (void)cmd; (void)data; (void)size;
    if (pending_pixels) {
        memcpy(lcd + pending_y * SCREEN_W * 2, pending_pixels,
               SCREEN_W * SCREEN_BAND_H * 2);
        pending_pixels = NULL;
        last_presented_ms = now_ms;
    }
    return 0;
}

void world_snapshot(world_t *out) { world.pending = queue.count; *out = world; }
bool world_needs_starter(void) { return !party.party_count; }
static void normalize_party_exp(party_t *value)
{
    for (unsigned i = 0; i < PARTY_MAX + BOX_SPECIES; i++) {
        mon_t *member = i < PARTY_MAX ? &value->party[i] : &value->box[i - PARTY_MAX];
        if ((i < PARTY_MAX && i >= value->party_count) || !member->species_id) continue;
        uint32_t floor = exp_for_level(member->level);
        if (member->exp < floor) member->exp = floor;
    }
}
void world_party_snapshot(world_party_t *out)
{
    if (!out) return;
    memset(out, 0, sizeof(*out));
    out->count = party.party_count;
    memcpy(out->members, party.party, sizeof(out->members));
    if (out->count) {
        mon_t *leader = &out->members[0];
        leader->level = world.level;
        leader->exp = world.exp;
        leader->explore_value = world.explore_value;
        int32_t intimacy = world.pet.intimacy / NURT_Q;
        leader->intimacy = (uint8_t)(intimacy < 0 ? 0 : intimacy > 100 ? 100 : intimacy);
    }
    out->box_count = (uint8_t)(party_total(&party) - party.party_count);
    out->switch_locked = active_valid || challenge.session.active || challenge.league_active || world_needs_starter();
}
world_switch_result_t world_set_leader(uint8_t index, const mon_t *expected,
                                      world_party_t *out)
{
    if (!expected || index >= PARTY_MAX) return WORLD_SWITCH_INVALID;
    const mon_t wanted = *expected;
    if (out) memset(out, 0, sizeof(*out));
    if (active_valid || challenge.session.active || challenge.league_active) return WORLD_SWITCH_BUSY;
    if (world_needs_starter()) return WORLD_SWITCH_STORAGE_UNAVAILABLE;
    if (index >= party.party_count) return WORLD_SWITCH_INVALID;
    world_party_t current;
    world_party_snapshot(&current);
    if (memcmp(&wanted, &current.members[index], sizeof(wanted))) return WORLD_SWITCH_STALE;
    if (!index) {
        if (out) *out = current;
        return WORLD_SWITCH_ALREADY_LEADER;
    }
    party_t candidate = party;
    candidate.party[0] = current.members[0];
    normalize_party_exp(&candidate);
    if (!party_set_leader(&candidate, index)) return WORLD_SWITCH_INVALID;
    if (host_save_fails()) return WORLD_SWITCH_SAVE_FAILED;
    party = candidate;
    const mon_t *leader = &party.party[0];
    world.species = leader->species_id;
    world.level = leader->level;
    world.exp = leader->exp;
    world.explore_value = leader->explore_value;
    world.pet.intimacy = leader->intimacy * NURT_Q;
    memset(battles, 0, sizeof(battles));
    if (out) world_party_snapshot(out);
    return WORLD_SWITCH_OK;
}
world_starter_result_t world_choose_starter(uint16_t species)
{
    if (!world_needs_starter()) return WORLD_STARTER_ALREADY_CHOSEN;
    if (species != 1 && species != 4 && species != 7 && species != 25)
        return WORLD_STARTER_INVALID;
    if (host_save_fails()) {
        return WORLD_STARTER_SAVE_FAILED;
    }
    mon_t starter = {.species_id = species, .level = exp_to_level(0, LEVEL_MAX),
                      .hp = 100, .nickname_idx = 0xFF};
    party_receive(&party, &starter);
    world.species = species;
    world.exp = 0;
    world.level = starter.level;
    dex_mark_caught(&dex, species, false);
    opening_seen = true;
    return WORLD_STARTER_OK;
}
static encounter_t *find_encounter(uint16_t uid)
{
    if (active_valid && active_enc.uid == uid) return &active_enc;
    return enc_queue_find(&queue, uid);
}
bool world_get_encounter_uid(uint16_t uid, encounter_t *out)
{
    encounter_t *e = find_encounter(uid);
    if (!e || !out) return false;
    *out = *e;
    return true;
}
void world_end_active_encounter(void)
{
    active_valid = false;
    memset(&active_enc, 0, sizeof(active_enc));
    memset(&active_battle, 0, sizeof(active_battle));
}
bool world_battle_get_uid(uint16_t uid, battle_session_t *out)
{
    if (active_valid && active_enc.uid == uid) {
        if (!out) return false;
        *out = active_battle;
        return true;
    }
    encounter_t *e = enc_queue_find(&queue, uid);
    if (!e || !out) return false;
    *out = (battle_session_t){0};
    for (unsigned i = 0; i < ENC_QUEUE_CAP; i++)
        if (battles[i].uid == uid && battles[i].ts == e->ts) {
            *out = battles[i].value;
            break;
        }
    return true;
}
bool world_battle_set_uid(uint16_t uid, const battle_session_t *value)
{
    if(challenge.session.active||challenge.league_active)return false;
    if (active_valid && active_enc.uid == uid) {
        if (!value || !value->started) return false;
        bool checked = active_battle.loot_checked;
        bool defeat_applied = active_battle.defeat_applied;
        item_loot_t loot = {active_battle.loot_item, active_battle.loot_qty, active_battle.loot_full};
        active_battle = *value;
        if (defeat_applied) active_battle.defeat_applied = true;
        if (checked) {
            active_battle.loot_checked = true; active_battle.loot_item = loot.item_id;
            active_battle.loot_qty = loot.quantity; active_battle.loot_full = loot.full;
        }
        return true;
    }
    encounter_t *e = enc_queue_find(&queue, uid);
    if (!e || !value) return false;
    if (value->started) {
        if (active_valid) return false;
        if (host_save_fails()) return false;
        active_enc = *e;
        active_battle = *value;
        active_valid = true;
        enc_queue_take_uid(&queue, uid, NULL);
        return true;
    }
    int slot = -1;
    for (unsigned i = 0; i < ENC_QUEUE_CAP; i++) {
        if (battles[i].uid == uid && battles[i].ts == e->ts) { slot = i; break; }
        encounter_t *other = enc_queue_find(&queue, battles[i].uid);
        if (!other || other->ts != battles[i].ts) slot = i;
    }
    if (slot < 0) return false;
    battles[slot].uid = uid;
    battles[slot].ts = e->ts;
    battles[slot].value = *value;
    return true;
}
const enc_queue_t *world_queue(void) { return &queue; }
void world_queue_snapshot(enc_queue_t *out) { if (out) *out = queue; }
const dex_t *world_dex(void) { return &dex; }
void world_feed(void) { item_use_result_t out; (void)world_item_use(world.species, ITEM_BERRY, &out); }
void world_play(void) { nurture_play(&world.pet); }
void world_rest(void) { nurture_rest(&world.pet); }
void world_inventory_snapshot(inventory_t *out) { if (out) *out = inventory; }
item_use_status_t world_item_use(uint16_t expected, uint8_t id, item_use_result_t *out)
{
    if (active_valid || challenge.session.active || challenge.league_active) return ITEM_USE_BUSY;
    if (expected != world.species || !party.party_count) return ITEM_USE_WRONG_TARGET;
    if (id >= ITEM_COUNT) return ITEM_USE_INVALID;
    if (!inventory.quantity[id]) return ITEM_USE_EMPTY;
    item_use_result_t candidate;
    item_use_status_t status = items_apply(id, expected, world.level, &world.pet, &candidate);
    if (status != ITEM_USE_OK) return status;
    if (host_save_fails()) return ITEM_USE_SAVE_FAILED;
    candidate.remaining = --inventory.quantity[id];
    if(candidate.species_after!=expected && achievements.evolutions<UINT16_MAX)achievements.evolutions++;
    world.pet = candidate.after;
    world.species = candidate.species_after;
    party.party[0].species_id = world.species;
    party.party[0].intimacy = nurture_pct(world.pet.intimacy);
    party.party[0].explore_value = world.explore_value;
    dex_mark_caught(&dex, world.species, (party.party[0].flags & 1) != 0);
    if (out) *out = candidate;
    return ITEM_USE_OK;
}
bool world_capture_ball_spend_uid(uint16_t uid, uint8_t ball, const battle_session_t *value)
{
    battle_session_t previous;
    if (challenge.session.active || challenge.league_active || ball >= ITEM_BALL_COUNT || !inventory.quantity[ball] || !value ||
        !value->initialized || (active_valid && active_enc.uid != uid) ||
        !world_battle_get_uid(uid, &previous) || !battle_session_can_capture(&previous) ||
        !value->started || value->pet_species != world.species ||
        value->wild_species != previous.wild_species || value->rng != previous.rng ||
        value->attack_count != previous.attack_count || value->pet_hp != previous.pet_hp ||
        value->wild_hp != previous.wild_hp || value->finished != previous.finished ||
        value->won != previous.won ||
        (previous.won && (!previous.loot_checked || !value->capture_used_after_win))) return false;
    if (host_save_fails()) return false;
    if (!active_valid) {
        encounter_t *entry = enc_queue_find(&queue, uid);
        if (!entry) return false;
        active_enc = *entry;
        active_valid = true;
        enc_queue_take_uid(&queue, uid, NULL);
    }
    active_battle = *value;
    if (previous.loot_checked) {
        active_battle.loot_checked = true; active_battle.loot_item = previous.loot_item;
        active_battle.loot_qty = previous.loot_qty; active_battle.loot_full = previous.loot_full;
    }
    inventory.quantity[ball]--;
    return true;
}
bool world_battle_loot_uid(uint16_t uid, item_loot_t *out)
{
    if (out) *out = (item_loot_t){.item_id = 255};
    if (!active_valid || active_enc.uid != uid || !active_battle.finished ||
        !active_battle.won || active_battle.pet_species != world.species) return false;
    if (active_battle.loot_checked) {
        if (out) *out = (item_loot_t){active_battle.loot_item, active_battle.loot_qty, active_battle.loot_full};
        return true;
    }
    item_loot_t candidate = items_roll_loot(active_enc.rarity,
        items_loot_seed(uid, active_enc.ts, active_enc.species_id, active_enc.rarity));
    if (candidate.item_id < ITEM_COUNT) {
        unsigned remaining = items_capacity(candidate.item_id) - inventory.quantity[candidate.item_id];
        if (candidate.quantity > remaining) { candidate.quantity = remaining; candidate.full = true; }
    }
    if (host_save_fails()) return false;
    if (candidate.item_id < ITEM_COUNT) inventory.quantity[candidate.item_id] += candidate.quantity;
    if(challenge.wild_wins<UINT16_MAX)challenge.wild_wins++;
    active_battle.loot_checked = true;
    active_battle.loot_item = candidate.item_id;
    active_battle.loot_qty = candidate.quantity;
    active_battle.loot_full = candidate.full;
    if (out) *out = candidate;
    return true;
}
bool world_apply_defeat_uid(uint16_t uid)
{
    if (!active_valid || active_enc.uid != uid || !active_battle.finished ||
        active_battle.won || active_battle.pet_species != world.species) return false;
    if (!active_battle.defeat_applied) {
        if(host_save_fails())return false;
        nurture_defeat(&world.pet);
        active_battle.defeat_applied = true;
    }
    return true;
}
void world_grant_exp(uint16_t amount)
{
    uint32_t floor = exp_for_level(world.level);
    if (world.exp < floor) world.exp = floor;
    world.exp = amount > UINT32_MAX - world.exp ? UINT32_MAX : world.exp + amount;
    world.level = exp_to_level(world.exp, LEVEL_MAX);
    if (party.party_count) {
        party.party[0].exp = world.exp;
        party.party[0].level = world.level;
    }
}
bool world_take_encounter(uint8_t i, encounter_t *out) { return enc_queue_take(&queue, i, out); }
bool world_take_uid(uint16_t uid, encounter_t *out)
{
    if (active_valid && active_enc.uid == uid) {
        if (out) *out = active_enc;
        world_end_active_encounter();
        return true;
    }
    return enc_queue_take_uid(&queue, uid, out);
}
void world_update_hp_uid(uint16_t uid, uint8_t hp)
{
    encounter_t *e = find_encounter(uid);
    if (e) e->hp_ratio = hp;
}
bool world_mark_exp_granted_uid(uint16_t uid)
{
    encounter_t *e = find_encounter(uid);
    if (!e || e->exp_granted) return false;
    e->exp_granted = true; return true;
}
void world_mark_seen(uint16_t id, bool shiny) { dex_mark_seen(&dex, id, shiny); }
bool world_capture_uid(uint16_t uid, const mon_t *m)
{
    if(challenge.session.active||challenge.league_active)return false;
    if (!m || m->species_id < 1 || m->species_id > BOX_SPECIES) return false;
    encounter_t *e = find_encounter(uid);
    if (!e || e->species_id != m->species_id) return false;
    party_t next = party;
    if (!party_receive(&next, m)) return false;
    next.party[0].exp=world.exp;next.party[0].level=world.level;
    normalize_party_exp(&next);
    uint16_t gain=exp_scaled(exp_scaled(m->level*8+20,60),nurture_exp_percent(&world.pet));
    next.party[0].exp=next.party[0].exp>UINT32_MAX-gain?UINT32_MAX:next.party[0].exp+gain;next.party[0].level=exp_to_level(next.party[0].exp,LEVEL_MAX);
    if (host_save_fails()) return false;
    party = next;world.exp=party.party[0].exp;world.level=party.party[0].level;
    dex_mark_caught(&dex, m->species_id, (m->flags & 1) != 0);
    world_take_uid(uid, NULL);
    return true;
}
bool world_evolve_leader(uint16_t from, uint16_t to)
{
    species_t sp;
    evo_check_t check;
    if (active_valid || from < 1 || from > BOX_SPECIES || to < 1 || to > BOX_SPECIES ||
        !party.party_count || party.party[0].species_id != from ||
        world.species != from || !assets_species(from, &sp) || sp.evolve_to != to ||
        sp.evolve_trigger != EVO_TRIGGER_LEVEL) return false;
    evo_check(nurture_pct(world.pet.intimacy), world.explore_value,
              sp.evolve_trigger, sp.evolve_to, sp.evolve_level, &check);
    if (!check.can || host_save_fails()) return false;
    if(achievements.evolutions<UINT16_MAX)achievements.evolutions++;
    party.party[0].species_id = to;
    party.party[0].intimacy = nurture_pct(world.pet.intimacy);
    party.party[0].explore_value = world.explore_value;
    world.species = to;
    world.pet.mood += 15 * NURT_Q;
    if (world.pet.mood > NURT_MAX) world.pet.mood = NURT_MAX;
    dex_mark_caught(&dex, to, (party.party[0].flags & 1) != 0);
    return true;
}
bool save_opening_seen(void) { return opening_seen; }
bool save_mark_opening_seen(void) { opening_seen = true; return true; }
static sound_mixer_t host_mixer;
static bool host_muted = true;
static uint8_t host_volume=AUDIO_VOLUME_DEFAULT;
static unsigned host_alert;
static bool host_notifying;
uint8_t audio_settings_volume(void){return host_volume;}
bool audio_settings_set_volume(uint8_t v){if(v>100||host_save_fails())return false;host_volume=v;return true;}
void sfx_encounter(uint8_t rarity,bool shiny){if(host_muted)return;unsigned priority=shiny?3:rarity>=4?2:1;if(priority>host_alert)host_alert=priority;}
bool audio_settings_muted(void) {return host_muted;}
void audio_settings_init(void) {host_muted=true;}
bool audio_settings_set_muted(bool muted) {if(host_save_fails())return false;host_muted=muted;host_mixer.active=false;host_alert=0;return true;}
void sfx_play(sfx_id_t id) { if(host_muted)return; sound_mixer_effect(&host_mixer,id); }
void sfx_music_play(music_id_t id) { sound_mixer_music(&host_mixer,id); }
void sfx_move(uint16_t id, uint8_t type, bool missed) { if(host_muted)return; sound_mixer_move(&host_mixer,id,type,missed); }

static const page_id_t page_ids[] = {
    PAGE_OPENING, PAGE_IDLE, PAGE_ENCOUNTER, PAGE_BATTLE,
    PAGE_CAPTURE, PAGE_CARE, PAGE_DEX, PAGE_COUNT, PAGE_COUNT, PAGE_STARTER, PAGE_BAG,
    PAGE_MENU, PAGE_PARTY, PAGE_TRAINER, PAGE_ACHIEVEMENTS, PAGE_EXPLORATION,
};
static bool valid_page(unsigned page)
{
    return page < sizeof(page_ids) / sizeof(*page_ids) && page_ids[page] != PAGE_COUNT;
}
static int page_number(void)
{
    for (unsigned i = 0; i < sizeof(page_ids) / sizeof(*page_ids); i++)
        if (page_ids[i] == nav_current()) return (int)i;
    return -1;
}
static void nurture_clock(lv_timer_t *timer){(void)timer;nurture_tick(&world.pet,esp_timer_get_time(),0,false);}
static void fixture(unsigned pet, unsigned level, unsigned wild, unsigned rarity,
                    unsigned seed, unsigned shiny, bool new_game, bool full_team)
{
    host_muted=true;host_volume=AUDIO_VOLUME_DEFAULT;host_alert=0;host_notifying=false;
    memset(&achievements,0,sizeof(achievements));
    exploration_init(&exploration);memset(&refresh,0,sizeof(refresh));
    memset(&world, 0, sizeof(world));
    nurture_init(&world.pet);nurture_tick(&world.pet,esp_timer_get_time(),0,false);lv_timer_create(nurture_clock,60000,NULL);
    world.species = pet;
    world.level = level;
    world.exp = exp_for_level(level);
    world.progress = 70;
    world.place_id = 1;
    enc_queue_init(&queue);
    dex_init(&dex);
    party_init(&party);
    items_inventory_init(&inventory);
    memset(battles, 0, sizeof(battles));
    world_end_active_encounter();
    memset(&challenge,0,sizeof(challenge));
    challenge.wild_wins = !new_game;
    opening_seen = !new_game;
    starter_save_failures = 0;
    save_failure_after = -1;
    if (new_game) {
        world.species = world.exp = world.level = 0;
    } else {
        dex_mark_caught(&dex, pet, false);
        mon_t leader = {.species_id = pet, .level = level, .hp = 100, .exp = world.exp};
        party_receive(&party, &leader);
        if (full_team) {
            static const uint8_t partners[] = {1, 4, 7, 133, 147, 39};
            for (unsigned i = 0; i < sizeof(partners) && party.party_count < PARTY_MAX; i++) {
                if (partners[i] == pet) continue;
                uint8_t partner_level = (uint8_t)(5 + i * 2);
                mon_t partner = {.species_id = partners[i], .level = partner_level,
                                 .hp = 100, .exp = exp_for_level(partner_level),
                                 .intimacy = (uint8_t)(12 + i * 9), .explore_value = (uint16_t)(i * 8),
                                 .nickname_idx = 0xFF};
                party_receive(&party, &partner);
                dex_mark_caught(&dex, partners[i], false);
            }
        }
    }
    for (unsigned i = 0; i < 4; i++) {
        encounter_t e = {.species_id = i ? (uint16_t[]){19, 74, 133}[i - 1] : wild,
                          .rarity = i ? i : rarity, .ts = 1234 + i,
                          .hp_ratio = 100, .is_shiny = i == 0 && shiny};
        enc_queue_push(&queue, &e);
        dex_mark_seen(&dex, e.species_id, e.is_shiny);
    }
    nav_ctx_t *ctx = nav_ctx();
    memset(ctx, 0, sizeof(*ctx));
    ctx->enc = queue.items[0];
    ctx->uid = queue.items[0].uid;
    dbg_battle_seed = seed;
}

static void frame(int mismatch)
{
    if (pending_pixels) { fputs("LCD frame was not flushed\n", stderr); exit(3); }
    printf("FRAME %d %llu %d\n", page_number(), (unsigned long long)now_ms, mismatch);
    if (screen_idle_is_off()) {
        static const uint8_t dark[sizeof(lcd)];
        fwrite(dark, 1, sizeof(dark), stdout);
    } else fwrite(lcd, 1, sizeof(lcd), stdout);
    fflush(stdout);
}

// Read-only test observability; excluded from the browser HTTP action surface.
static void encounter_state(const encounter_t *e)
{
    battle_session_t b;
    world_battle_get_uid(e->uid, &b);
    printf("{\"uid\":%u,\"ts\":%lu,\"species\":%u,\"hp_ratio\":%u,\"exp_granted\":%s,"
           "\"initialized\":%s,\"started\":%s,\"auto_battle\":%s,\"pet_hp\":%u,\"wild_hp\":%u,"
           "\"pet_level\":%u,\"wild_level\":%u,\"attacks\":%u,\"finished\":%s,\"won\":%s,\"retaliation\":%s,"
           "\"capture_used\":%s,\"reward_settled\":%s,\"escape_attempts\":%u,"
           "\"escape_retaliation\":%s,\"defeat_applied\":%s,\"ability_factor\":%u,"
           "\"loot_checked\":%s,\"loot_item\":%u,\"loot_qty\":%u,\"loot_full\":%s}",
           e->uid, (unsigned long)e->ts, e->species_id, e->hp_ratio,
           e->exp_granted ? "true" : "false", b.initialized ? "true" : "false",
           b.started ? "true" : "false", b.auto_battle ? "true" : "false", b.pet_hp, b.wild_hp, b.pet_level, b.wild_level, b.attack_count,
           b.finished ? "true" : "false", b.won ? "true" : "false",
           b.retaliation_pending ? "true" : "false",
           b.capture_used_after_win ? "true" : "false", b.reward_settled ? "true" : "false",
           b.escape_attempts, b.escape_retaliation ? "true" : "false",
           b.defeat_applied ? "true" : "false", b.ability_factor_q10,
           b.loot_checked ? "true" : "false", b.loot_item, b.loot_qty, b.loot_full ? "true" : "false");
}
static void state(void)
{
    printf("STATE {\"page\":%d,\"pet\":%u,\"level\":%u,\"exp\":%lu,"
           "\"party_count\":%u,\"caught\":%u,\"needs_starter\":%s,"
           "\"opening_seen\":%s,\"uid\":%u,\"queue\":[",
           page_number(), world.species, world.level, (unsigned long)world.exp,
           party.party_count, dex_count_caught(&dex), world_needs_starter() ? "true" : "false",
           opening_seen ? "true" : "false", nav_ctx()->uid);
    for (unsigned i = 0; i < queue.count; i++) {
        if (i) putchar(',');
        encounter_state(&queue.items[i]);
    }
    printf("],\"dropped\":%u,\"active\":", queue.dropped);
    if (active_valid) encounter_state(&active_enc); else printf("null");
    extern unsigned play_battle_move_preview_frames(void);
    printf(",\"move_animation_frames\":%u", nav_current() == PAGE_BATTLE ? play_battle_move_preview_frames() : 0);
    printf(",\"presentation\":");
    if (nav_current() == PAGE_BATTLE) {
        play_battle_view_t view;
        play_battle_presentation_snapshot(&view);
        printf("{\"phase\":\"%s\",\"visible_pet_hp\":%u,\"visible_wild_hp\":%u,"
               "\"visible_exp\":%lu,\"visible_level\":%u,\"pet_dx\":%d,\"wild_dx\":%d,\"wild_frame\":%u,\"move_id\":%u,\"by_pet\":%s}",
               view.phase, view.pet_hp, view.wild_hp, (unsigned long)view.exp,
               view.level, view.pet_dx, view.wild_dx, view.wild_frame, view.move_id,
               view.by_pet ? "true" : "false");
    } else printf("null");
    printf(",\"nurture\":{\"satiety\":%u,\"mood\":%u,\"stamina\":%u,\"intimacy\":%u}",
           nurture_pct(world.pet.satiety), nurture_pct(world.pet.mood),
           nurture_pct(world.pet.stamina), nurture_pct(world.pet.intimacy));
    printf(",\"can_leave\":%s", nav_can_leave() ? "true" : "false");
    printf(",\"display\":{\"off\":%s,\"timeout_ms\":%u,\"backlight\":%u,\"busy\":%s}",
           screen_idle_is_off() ? "true" : "false", screen_idle_timeout_ms(), backlight,
           nav_screen_busy() ? "true" : "false");
    printf(",\"names\":%u", (unsigned)pokemon_names_get_style());
    if (nav_current() == PAGE_BAG) printf(",\"bag_selected\":%u", play_bag_selected_item());
    else printf(",\"bag_selected\":null");
    printf(",\"menu_view\":");
    if (nav_current() == PAGE_MENU) {
        play_menu_view_t view;
        play_menu_presentation_snapshot(&view);
        printf("{\"selected\":%u,\"options\":%s,\"option_selected\":%u}",
               view.selected, view.options ? "true" : "false", view.option_selected);
    } else printf("null");
    printf(",\"party_view\":");
    if (nav_current() == PAGE_PARTY) {
        play_party_view_t view;
        play_party_presentation_snapshot(&view);
        printf("{\"selected\":%u,\"details\":%s,\"species\":%u,\"feedback\":\"%s\"}",
               view.selected, view.details ? "true" : "false", view.species,
               view.feedback ? view.feedback : "");
    } else printf("null");
    printf(",\"inventory\":[");
    for (unsigned i = 0; i < ITEM_COUNT; i++) printf("%s%u", i ? "," : "", inventory.quantity[i]);
    printf("],\"party\":[");
    world_party_t party_view;
    world_party_snapshot(&party_view);
    for (unsigned i = 0; i < party_view.count; i++) {
        const mon_t *m = &party_view.members[i];
        printf("%s{\"species\":%u,\"level\":%u,\"exp\":%lu,\"hp\":%u,\"intimacy\":%u,\"explore\":%u,\"flags\":%u}",
               i ? "," : "", m->species_id, m->level, (unsigned long)m->exp,
               m->hp, m->intimacy, m->explore_value, m->flags);
    }
    printf("],\"box_count\":%u,\"party_switch_locked\":%s", party_view.box_count,
           party_view.switch_locked ? "true" : "false");
    printf(",\"challenge\":{\"mode\":%u,\"sendout_mask\":%u,\"defeated\":%u,\"league\":%u,\"trainer\":%u,\"active\":%u,\"finished\":%u,\"won\":%u,\"turns\":%u,\"rng\":%lu,\"sides\":[",
        play_trainer_mode(),play_trainer_sendout_mask(),challenge.defeated,challenge.league_stage,challenge.session.trainer,
        challenge.session.active,challenge.session.finished,challenge.session.won,challenge.session.turns,(unsigned long)challenge.session.rng);
    for(unsigned side=0;side<2;side++) {
        trainer_side_t *s=&challenge.session.sides[side];printf("%s{\"active\":%u,\"mons\":[",side?",":"",s->active);
        for(unsigned i=0;i<s->count;i++){trainer_mon_t *m=&s->mons[i];printf("%s{\"species\":%u,\"hp\":%u,\"max_hp\":%u,\"status\":%u,\"pp\":[%u,%u,%u,%u]}",i?",":"",m->species,m->hp,m->max_hp,m->status,m->pp[0],m->pp[1],m->pp[2],m->pp[3]);}
        printf("]}");
    }
    printf("]},\"exploration\":{\"route\":%u,\"energy\":%u,\"steps\":%lu,\"clues\":[%u,%u,%u,%u],\"pulse\":[%u,%u,%u,%u],\"rare_left\":%u,\"elite_left\":%u}",exploration.route,exploration.energy,(unsigned long)exploration.steps,exploration.clues[0],exploration.clues[1],exploration.clues[2],exploration.clues[3],exploration.pulse[0],exploration.pulse[1],exploration.pulse[2],exploration.pulse[3],8-refresh.since_rare,30-refresh.since_elite);
    printf(",\"music\":%u,\"muted\":%s,\"volume\":%u,\"achievement_claimed\":%u,\"evolutions\":%u,\"encounter_alert\":%u}", (unsigned)music_director_current(), host_muted?"true":"false",host_volume,achievements.claimed,achievements.evolutions,host_alert);
    putchar('\n');
    fflush(stdout);
}

extern bool play_battle_move_preview(unsigned,unsigned,unsigned,unsigned);
int main(void)
{
    if (!assets_init() || !render_init()) return 2;
    char line[256], cmd[24];
    bool booted = false;
    while (fgets(line, sizeof(line), stdin)) {
        if (sscanf(line, "%23s", cmd) != 1) return 2;
        unsigned a, b, c, d = 0, e, f, g, names = POKEMON_NAMES_OFFICIAL, team = 0;
        int mismatch = -1;
        if (!strcmp(cmd, "boot") && !booted &&
            sscanf(line, "%*s %u %u %u %u %u %u %u %u %u", &a,&b,&c,&d,&e,&f,&g,&names,&team) >= 7 &&
            valid_page(a) && b >= 1 && b <= 151 && c >= 1 && c <= 100 &&
            d >= 1 && d <= 151 && e >= 1 && e <= 5 && g <= 1 && names < POKEMON_NAMES_STYLE_COUNT && team <= 1) {
            pokemon_names_set_style((pokemon_name_style_t)names);
            fixture(b, c, d, e, f, g, a == 0 || a == 9, team != 0); nav_go(page_ids[a]); booted = true;
            if (!screen_idle_init(nav_screen_busy)) return 2;
        } else if(booted&&!strcmp(cmd,"move_preview")&&sscanf(line,"%*s %u %u %u %u",&a,&b,&c,&d)==4){
            if(!play_battle_move_preview(a,b,c,d)){fputs("invalid move fixture\n",stderr);return 2;}
        } else if (booted && !strcmp(cmd, "page") && sscanf(line, "%*s %u", &a) == 1 && valid_page(a)) {
            nav_go(page_ids[a]);
        } else if (booted && !strcmp(cmd,"nurture_fixture") && sscanf(line,"%*s %u %u %u %u",&a,&b,&c,&d)==4 && a<=100 && b<=100 && c<=100 && d<=100) {
            world.pet.satiety=a*NURT_Q;world.pet.mood=b*NURT_Q;world.pet.stamina=c*NURT_Q;world.pet.intimacy=d*NURT_Q;world.pet.last_us=esp_timer_get_time();host_redraw();
        } else if (booted && !strcmp(cmd, "exploration_fixture") && sscanf(line,"%*s %u %u %u %u",&a,&b,&c,&d)==4 && a<4 && b<=24 && c<=3 && d<=1) {
            exploration.route=a;exploration.energy=b;exploration.clues[a]=c;exploration.pulse[a]=d;
            if(nav_current()==PAGE_EXPLORATION)nav_go(PAGE_EXPLORATION);
        } else if (booted && !strcmp(cmd, "names") && sscanf(line, "%*s %u", &a) == 1 && a < POKEMON_NAMES_STYLE_COUNT) {
            pokemon_names_set_style((pokemon_name_style_t)a);
            host_redraw();
        } else if (booted && !strcmp(cmd, "spawn") &&
                   sscanf(line, "%*s %u %u %u %u", &a, &b, &c, &d) >= 3 &&
                   a >= 1 && a <= 151 && b >= 1 && b <= 5 && d <= 1) {
            encounter_t spawned = {.species_id = a, .rarity = b, .ts = c, .hp_ratio = 100, .is_shiny = d != 0};
            // Mirror the active-uid reservation used by production world.
            for (;;) {
                if (!queue.next_uid) queue.next_uid = 1;
                if ((!active_valid || queue.next_uid != active_enc.uid) &&
                    !enc_queue_find(&queue, queue.next_uid)) break;
                queue.next_uid++;
            }
            enc_queue_push(&queue, &spawned);
            sfx_encounter(spawned.rarity,spawned.is_shiny);
            dex_mark_seen(&dex, a, false);
        } else if (booted && !strcmp(cmd, "exit")) {
            nav_exit_current();
        } else if (booted && !strcmp(cmd, "audio") && sscanf(line,"%*s %u",&a)==1 && a<=11025) {
            static int16_t pcm[11025];
            bool off=screen_idle_is_off();
            if(host_notifying&&!host_mixer.active)host_notifying=false;
            if(off&&!host_notifying)host_mixer.active=false;
            if(host_muted) {memset(pcm,0,a*sizeof(pcm[0]));host_alert=0;host_notifying=false;host_mixer.active=false;}
            else if(off&&!host_alert&&!host_notifying)memset(pcm,0,a*sizeof(pcm[0]));
            else {
                if(host_alert&&!host_mixer.active){sound_mixer_effect(&host_mixer,audio_encounter_alert(host_alert==2?4:1,host_alert==3));host_alert=0;host_notifying=true;}
                sound_mixer_music(&host_mixer,off?MUSIC_NONE:music_director_current());
                sound_mixer_render(&host_mixer,a,pcm);
                // Preview approximation of codec gain; hardware uses the codec's percent curve.
                for(unsigned i=0;i<a;i++)pcm[i]=(int32_t)pcm[i]*host_volume/100;
            }
            printf("AUDIO %u\n",a);
            for(unsigned i=0;i<a;i++) { putchar((uint16_t)pcm[i]&255);putchar(((uint16_t)pcm[i]>>8)&255); }
            fflush(stdout);continue;
        } else if (booted && !strcmp(cmd, "state")) {
            state(); continue;
        } else if (booted && !strcmp(cmd, "save_delay") && sscanf(line, "%*s %u", &a) == 1 && a <= 2000) {
            save_delay_ms = a;
        } else if (booted && !strcmp(cmd, "save_fail") && sscanf(line, "%*s %u", &a) == 1 && a <= 10) {
            starter_save_failures = a;
        } else if (booted && !strcmp(cmd, "save_fail_after") && sscanf(line, "%*s %u", &a) == 1 && a <= 10) {
            save_failure_after = a;
        } else if (booted && !strcmp(cmd, "challenge_unlock") && sscanf(line,"%*s %u",&a)==1 && a<16384) {
            challenge.defeated=a;challenge.wild_wins=1;
            if(nav_current()==PAGE_TRAINER)nav_go(PAGE_TRAINER);
         } else if(booted&&!strcmp(cmd,"challenge_hp_fixture")&&sscanf(line,"%*s %u %u %u",&a,&b,&c)==3&&a<2&&b<challenge.session.sides[a].count&&c<=challenge.session.sides[a].mons[b].max_hp){
            challenge.session.sides[a].mons[b].hp=c;host_redraw();
        } else if(booted&&!strcmp(cmd,"audio_fixture")&&sscanf(line,"%*s %u",&a)==1&&a<=1){
            audio_settings_set_muted(a!=0);
        } else if (booted && !strcmp(cmd, "party_add") &&
                   sscanf(line, "%*s %u %u %u %u %u", &a, &b, &c, &d, &e) == 5 &&
                   a >= 1 && a <= BOX_SPECIES && b >= 1 && b <= LEVEL_MAX &&
                   c <= 100 && d <= 65535 && e <= 1) {
            mon_t member = {.species_id = (uint8_t)a, .level = (uint8_t)b, .hp = 100,
                            .exp = exp_for_level(b), .intimacy = (uint8_t)c,
                            .explore_value = (uint16_t)d, .flags = (uint8_t)e,
                            .nickname_idx = 0xFF};
            party_receive(&party, &member);
            dex_mark_caught(&dex, a, e != 0);
            host_redraw();
        } else if (booted && !strcmp(cmd, "party_exp") &&
                   sscanf(line, "%*s %u %u", &a, &b) == 2 && a < party.party_count) {
            // Reproduce legacy capture records that stored LvN with EXP=0.
            party.party[a].exp = b;
            if (!a) world.exp = b;
            host_redraw();
        } else if (booted && !strcmp(cmd, "inventory") && sscanf(line, "%*s %u %u", &a, &b) == 2 &&
                   a < ITEM_COUNT && b <= items_capacity(a)) {
            inventory.quantity[a] = b;
            host_redraw();
        } else if (booted && !strcmp(cmd, "care_progress") && sscanf(line, "%*s %u %u", &a, &b) == 2 &&
                   a <= 100 && b <= 65535) {
            world.pet.intimacy = a * NURT_Q;
            world.explore_value = b;
            host_redraw();
        } else if (booted && !strcmp(cmd, "nurture") &&
                   sscanf(line, "%*s %u %u %u %u", &a, &b, &c, &d) >= 3 && a <= 100 && b <= 100 && c <= 100) {
            world.pet.satiety = a * NURT_Q;
            world.pet.mood = b * NURT_Q;
            world.pet.stamina = c * NURT_Q;
            host_redraw();
        } else if (booted && !strcmp(cmd, "tick") && sscanf(line, "%*s %u", &a) == 1 && a <= 60000) {
            advance(a);
        } else if (booted && !strcmp(cmd, "key") && sscanf(line, "%*s %u %u", &a, &b) == 2 &&
                   a < 3 && b <= BSP_BTN_GESTURE_END) {
            /* Forward gameplay holds; omit debug screenshot and demo-shell exits. */
            if (b != BSP_BTN_LONG || a == BSP_BTN_UP ||
                (a == BSP_BTN_DOWN && (nav_current() == PAGE_ENCOUNTER || nav_current() == PAGE_BAG ||
                                      nav_current() == PAGE_MENU || nav_current() == PAGE_PARTY ||
                                      nav_current() == PAGE_TRAINER || nav_current() == PAGE_ACHIEVEMENTS ||
                                      nav_current() == PAGE_EXPLORATION))) nav_key(a, b);
            else screen_idle_filter_key(a, b);
        } else if (booted && !strcmp(cmd, "check")) {
            uint8_t before[sizeof(lcd)]; memcpy(before, lcd, sizeof(lcd));
            /* P4 computes its pointer from the clock when drawing. Compare at
             * the last presented timestamp, not between two 40ms timer ticks. */
            uint64_t current_ms = now_ms;
            now_ms = last_presented_ms;
            host_redraw();
            now_ms = current_ms;
            mismatch = 0;
            for (size_t i = 0; i < sizeof(lcd); i += 2)
                mismatch += before[i] != lcd[i] || before[i + 1] != lcd[i + 1];
        } else { fputs("invalid preview command\n", stderr); return 2; }
        frame(mismatch);
    }
    nav_exit_current();
    return 0;
}

void world_challenge_snapshot(trainer_store_t *out) { *out=challenge; }
bool world_challenge_begin(uint8_t id) {
 trainer_store_t candidate=challenge;
 if(active_valid||!trainer_begin(&candidate,id,party.party,party.party_count,nurture_ability_factor(&world.pet),dbg_battle_seed)||host_save_fails())return false;
 challenge=candidate;return true;
}
bool world_challenge_step(trainer_event_t *out) {
 trainer_store_t candidate=challenge;trainer_event_t event;
 if(!trainer_step(&candidate,&event)||host_save_fails())return false;
 challenge=candidate;*out=event;return true;
}
bool world_challenge_move(uint8_t slot) {
 trainer_store_t candidate=challenge;if(!trainer_choose_move(&candidate,slot)||host_save_fails())return false;challenge=candidate;return true;
}
bool world_challenge_switch(uint8_t slot,bool forced) {
 trainer_store_t candidate=challenge;if(!trainer_switch(&candidate,slot,forced)||host_save_fails())return false;challenge=candidate;return true;
}
bool world_challenge_retire(void) {
 if(!challenge.session.active||host_save_fails())return false;trainer_retire(&challenge);return true;
}
bool world_challenge_settle(void) {
 if(!challenge.session.active)return true;
 if(!challenge.session.finished||host_save_fails())return false;
 unsigned n=0,reward=exp_scaled(trainer_reward(&challenge),nurture_exp_percent(&world.pet));
 for(unsigned i=0;i<party.party_count;i++)n+=!!(challenge.session.participated&(1u<<i));
 unsigned remainder=n?reward%n:0;
 if(n)for(unsigned i=0;i<party.party_count;i++)if(challenge.session.participated&(1u<<i)){
 unsigned amount=reward/n;if(remainder){amount++;remainder--;}
 if(party.party[i].exp<exp_for_level(party.party[i].level))party.party[i].exp=exp_for_level(party.party[i].level);
 party.party[i].exp=party.party[i].exp>UINT32_MAX-amount?UINT32_MAX:party.party[i].exp+amount;
 party.party[i].level=exp_to_level(party.party[i].exp,100);}
 world.exp=party.party[0].exp;world.level=party.party[0].level;
 if(challenge.session.won&&!(challenge.defeated&(1u<<challenge.session.trainer))){unsigned milk=inventory.quantity[ITEM_MILK]+2;inventory.quantity[ITEM_MILK]=milk>items_capacity(ITEM_MILK)?items_capacity(ITEM_MILK):milk;}
 if(!challenge.session.won&&!challenge.session.retired){world.pet.stamina=world.pet.stamina>20*NURT_Q?world.pet.stamina-20*NURT_Q:0;world.pet.mood=world.pet.mood>15*NURT_Q?world.pet.mood-15*NURT_Q:0;}
 trainer_settle(&challenge);return true;
}
bool world_challenge_recover(uint8_t slot) {
 if(!(challenge.session.active||challenge.league_active)||!inventory.quantity[ITEM_MILK]||slot>=challenge.session.sides[0].count)return false;
 trainer_mon_t *m=&challenge.session.sides[0].mons[slot];if(!m->hp||(m->hp==m->max_hp&&!m->status)||host_save_fails())return false;
 unsigned hp=m->hp+50;m->hp=hp>m->max_hp?m->max_hp:hp;m->status=m->sleep=0;inventory.quantity[ITEM_MILK]--;if(challenge.session.active){challenge.session.next=1;challenge.session.acted=1;}return true;
}

void world_achievements_snapshot(achievement_view_t *out){achievement_view(out,&achievements,&dex,challenge.defeated);}
achievement_claim_t world_achievement_claim(unsigned id){
 achievement_view_t v;world_achievements_snapshot(&v);
 achievement_store_t candidate=achievements;inventory_t bag=inventory;
 achievement_claim_t status=achievement_claim(&candidate,&bag,&v,id);
 if(status!=ACH_CLAIM_OK)return status;
 if(host_save_fails())return ACH_CLAIM_FAILED;
 achievements=candidate;inventory=bag;return ACH_CLAIM_OK;
}

void world_exploration_snapshot(exploration_view_t *out){
 if(out)*out=(exploration_view_t){.state=exploration,.discoveries=refresh.discoveries,.defeated=challenge.defeated,
 .rare_left=8-refresh.since_rare,.elite_left=30-refresh.since_elite,.pending=queue.count,.stamina=nurture_pct(world.pet.stamina),.exp_percent=nurture_exp_percent(&world.pet),.rare_bonus=nurture_rare_bonus(&world.pet)};
}
exploration_kind_t world_exploration_select(uint8_t route){
 if(route>=4)return EXPLORE_BLOCKED;
 if(active_valid||challenge.session.active||challenge.league_active)return EXPLORE_BUSY;
 if(world_needs_starter())return EXPLORE_SAVE_FAILED;
 if(route==exploration.route)return EXPLORE_NONE;
 if(host_save_fails())return EXPLORE_SAVE_FAILED;
 exploration.route=route;return EXPLORE_NONE;
}
exploration_event_t world_explore(void){
 if(active_valid||challenge.session.active||challenge.league_active)return (exploration_event_t){.kind=EXPLORE_BUSY};
 if(world_needs_starter())return (exploration_event_t){.kind=EXPLORE_SAVE_FAILED};
 exploration_state_t x=exploration;enc_refresh_state_t r=refresh;enc_queue_t q=queue;dex_t d=dex;
 if(world.pet.stamina<NURT_EXPLORE_COST)return (exploration_event_t){.kind=EXPLORE_NO_STAMINA};
 inventory_t bag=inventory;
 exploration_event_t e=exploration_step_nurtured(&x,&r,&q,&d,active_valid?active_enc.uid:0,challenge.defeated,&bag,&world.pet);
 if(e.kind!=EXPLORE_ENCOUNTER&&e.kind!=EXPLORE_CLUE&&e.kind!=EXPLORE_TARGET)return e;
 if(host_save_fails()){e.kind=EXPLORE_SAVE_FAILED;return e;}
 exploration=x;refresh=r;queue=q;dex=d;inventory=bag;world.pet.stamina-=NURT_EXPLORE_COST;
 if(world.explore_value<UINT16_MAX)world.explore_value++;
 party.party[0].explore_value=world.explore_value;
 for(unsigned i=0;i<ENC_QUEUE_CAP;i++)if(battles[i].uid&&!enc_queue_find(&queue,battles[i].uid))memset(&battles[i],0,sizeof(battles[i]));
 if(e.species)sfx_encounter(e.rarity,e.shiny);
 return e;
}

bool world_battle_reward_uid(uint16_t uid,uint16_t *amount){
 if(amount)*amount=0;
 if(!active_valid||active_enc.uid!=uid||!active_battle.finished)return false;
 if(active_battle.reward_settled||active_enc.exp_granted)return true;
 uint16_t gain=exp_scaled(battle_session_exp(&active_battle),nurture_exp_percent(&world.pet));
 if(host_save_fails())return false;
 world.exp=world.exp>UINT32_MAX-gain?UINT32_MAX:world.exp+gain;world.level=exp_to_level(world.exp,LEVEL_MAX);
 party.party[0].exp=world.exp;party.party[0].level=world.level;active_battle.reward_settled=true;active_enc.exp_granted=true;
 if(amount)*amount=gain;
 return true;
}
void world_box_snapshot(mon_t out[BOX_SPECIES]){if(out)memcpy(out,party.box,sizeof(party.box));}
world_switch_result_t world_box_exchange(uint8_t slot,const mon_t *outgoing,const mon_t *incoming){
 if(!outgoing||!incoming||slot>=party.party_count||incoming->species_id<1||incoming->species_id>BOX_SPECIES)return WORLD_SWITCH_INVALID;
 if(active_valid||challenge.session.active||challenge.league_active)return WORLD_SWITCH_BUSY;
 world_party_t v;world_party_snapshot(&v);
 if(memcmp(outgoing,&v.members[slot],sizeof(mon_t))||memcmp(incoming,&party.box[incoming->species_id-1],sizeof(mon_t)))return WORLD_SWITCH_STALE;
 party_t next=party;memcpy(next.party,v.members,sizeof(next.party));
 if(!party_exchange(&next,slot,incoming->species_id))return WORLD_SWITCH_INVALID;
 normalize_party_exp(&next);if(host_save_fails())return WORLD_SWITCH_SAVE_FAILED;
 party=next;world.species=party.party[0].species_id;world.level=party.party[0].level;world.exp=party.party[0].exp;
 if(!slot){world.pet.intimacy=party.party[0].intimacy*NURT_Q;world.explore_value=party.party[0].explore_value;}
 memset(battles,0,sizeof(battles));return WORLD_SWITCH_OK;
}
