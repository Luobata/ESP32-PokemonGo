// Synthetic progress only. Compile against the selected HISTORICAL headers and
// party.c, never today's save_t with a downgraded version. See manifest.json.
#include "save.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stddef.h>

int main(int argc, char **argv) {
    assert(argc == 2);
    FIXTURE_TYPE s;
    memset(&s, 0, sizeof(s));
    s.version = FIXTURE_VERSION;
    s.opening_seen = true;
    s.species = 25; s.level = 32; s.exp = 32768;
    s.pet.satiety = 70 * NURT_Q; s.pet.mood = 80 * NURT_Q;
    s.pet.stamina = 45 * NURT_Q; s.pet.intimacy = 30 * NURT_Q;
    s.pet.last_us = 120000000;
    s.scans = 19; s.motion_q10 = 7890; s.last_uptime_us = 120000000;
    party_t party; party_init(&party);
    mon_t mon = {.species_id=25,.level=32,.hp=75,.intimacy=30,.exp=32768};
    assert(party_receive(&party, &mon));
    mon.species_id=1; mon.level=16; mon.exp=4096;
    assert(party_receive(&party, &mon));
    mon.species_id=149; mon.level=60; mon.exp=216000; mon.flags=1;
    party.box[FIXTURE_VERSION < 12 ? 148 : 3] = mon;
    party_serialize(&party, s.party);
    const unsigned ids[] = {25,1,149};
    for (unsigned i=0; i<3; i++) {
        unsigned n=ids[i]-1; s.dex.seen[n/8] |= 1u<<(n%8); s.dex.caught[n/8] |= 1u<<(n%8);
    }
    s.dex.shiny_seen[148/8] = s.dex.shiny_caught[148/8] = 1u<<(148%8);
    s.queue.count=1; s.queue.next_uid=43; s.queue.dropped=3;
    s.queue.items[0]=(encounter_t){.uid=42,.ts=120,.species_id=133,.rarity=3,.hp_ratio=64,.is_shiny=true};
#if FIXTURE_VERSION < 16
    // V5-V15 owned no fields at these bytes; nonzero C padding is legal.
    ((unsigned char*)&s.queue.items[0])[2]=0xa5;
    ((unsigned char*)&s.queue.items[0])[3]=0xa5;
#else
    s.queue.items[0].level=28; s.queue.items[0].activity=2;
#endif
#if FIXTURE_VERSION >= 6
    s.inventory.quantity[ITEM_POKE]=42; s.inventory.quantity[ITEM_LEAF_STONE]=2;
    s.inventory.quantity[ITEM_MILK]=3;
#endif
#if FIXTURE_VERSION >= 7
    s.challenge.wild_wins=27; s.challenge.defeated=3;
    s.challenge.session.rng=0x12345678;
    s.challenge.session.turns=7; s.challenge.session.ability=1024;
    s.challenge.session.trainer=2; s.challenge.session.active=1;
    s.challenge.session.participated=1;
    for (unsigned side=0; side<2; side++) {
        __typeof__(s.challenge.session.sides[side]) *t=&s.challenge.session.sides[side];
        t->count=2; t->reflect=2;
        for (unsigned i=0; i<2; i++) {
            __typeof__(t->mons[i]) *m=&t->mons[i];
            m->species=side ? 74 : (i ? 1 : 25); m->level=32;
            m->max_hp=100; m->hp=i ? 0 : 60;
            m->special=2; m->defense=-1;
            m->moves[0]=33; m->pp[0]=20;
        }
    }
#endif
#if FIXTURE_VERSION >= 8
    s.achievements.evolutions=4; s.achievements.claimed=5;
#endif
#if FIXTURE_VERSION >= 10
    s.refresh.online_s=120; s.refresh.next_base_s=15000;
    s.refresh.serial=9; s.refresh.discoveries=8; s.refresh.base_started=1;
    s.refresh.history_count=1; s.refresh.history_next=1;
    s.refresh.history[0].key=123; s.refresh.history[0].last_s=100;
#endif
#if FIXTURE_VERSION >= 11
    s.exploration.route=2; s.exploration.energy=13;
    s.exploration.clues[2]=2; s.exploration.pulse[1]=1;
    s.exploration.steps=234;
#if FIXTURE_VERSION == 11
    s.exploration.reserved[0]=0xa5;
#else
    s.exploration.tracked_species=133;
#endif
#endif
#if FIXTURE_VERSION >= 14
    s.exploration.research_flags=0x12;
#endif
#if FIXTURE_VERSION >= 15
    s.dungeon.run_id=23; s.dungeon.clears=2; s.dungeon.paid_nodes=0x13;
    s.dungeon.last_node=4; s.dungeon.elite_seen=1;
    s.dungeon.receipt.xp=310; s.dungeon.receipt.items.quantity[ITEM_GREAT]=2;
    s.dungeon.receipt.first_elite=1;
#if FIXTURE_VERSION < 17
    // These old schemas predate partner rewards. Tail padding has no meaning.
    memset((unsigned char*)&s.dungeon.receipt + offsetof(dungeon_receipt_t,full)+1,
           0xa5, sizeof(dungeon_receipt_t)-offsetof(dungeon_receipt_t,full)-1);
#endif
#endif
#if FIXTURE_VERSION >= 16
    s.exploration_updates.rounds[2]=3; s.exploration_updates.targets[2]=133;
    s.exploration_updates.chapters[2]=2; s.exploration_updates.activity_progress[1]=2;
    s.exploration_updates.activity_runs[1]=3; s.exploration_updates.activity_uid[1]=42;
#endif
#if FIXTURE_VERSION >= 17
    s.rest_clock.epoch_us=1728000000000000LL; s.rest_clock.online_us=120000000;
#endif
#if FIXTURE_VERSION >= 18
    s.regions.selected=4;
    s.regions.region[0]=(exploration_region_progress_t){.steps=57,.clears=2,.clues=2,.pulse=1,.target=131,.pity=4,.deep=1,.traced=1,.claimed=1,.challenge_clear=1};
    s.regions.dungeon_pity=3; s.regions.expedition_clears=1;
    s.regions.pending_items.quantity[ITEM_WATER_STONE]=1;
    s.regions.pending_partner=(encounter_t){.species_id=131,.rarity=5,.level=42,.biome=2,.hp_ratio=100,.is_transient=true,.is_shiny=true};
#endif
    FILE *f=fopen(argv[1], "wb"); assert(f);
    assert(fwrite(&s, 1, sizeof(s), f)==sizeof(s)); assert(!fclose(f));
    printf("%zu\n", sizeof(s));
}
