#!/usr/bin/env python3
"""Run the actual C move renderer against pixel/phase/guard invariants on host.

Tests all moves.bin entries, both attackers and 2x visible sprite bounds; asserts
visible coverage, distinct type fallback rasters, no missed-hit overlay, clean
recovery, immutable gameplay input, bounded actor displacement, and HUD guards.
This does not replace play_battle dirty/full redraw or device timing checks.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "battle_fx.h"
#include "render_scene.h"
#include "screen.h"

static uint16_t pixels[SCREEN_W * SCREEN_H]; // Host test only, not firmware.
static int current_band;
static unsigned phase_checks;
static bool top_stage_seen;
static const uint16_t MOVES[][2] = { @MOVES@ };
// Full 40/48/56 source squares at 2x, plus narrower visible bboxes.
// Only opaque bounds enter this API: top=30, right=232, source padding excluded.
static const battle_fx_rect_t WILD_BOUNDS[] = {
    {152, 30, 80, 80}, {136, 30, 96, 96}, {120, 30, 112, 112},
    {200, 30, 32, 32}, {168, 30, 64, 64},
};
// Visible height and width vary independently in the actual sprite assets.
static const battle_fx_rect_t TYPE_EXTRA_BOUNDS[] = {
    {184, 30, 48, 46}, {120, 30, 112, 46}, {184, 30, 48, 112},
};
#define COUNT(a) (sizeof(a) / sizeof((a)[0]))

static void require(bool ok, const char *reason) {
    if (!ok) { fprintf(stderr, "battle_fx failure: %s\n", reason); exit(1); }
}
void screen_px(int x, int y, uint16_t color) {
    require(x >= 0 && x < SCREEN_W && y >= 0 && y < SCREEN_BAND_H, "band write out of bounds");
    int py = current_band + y;
    require(py >= 30 && py < 236 && (py < 160 || x < 104), "effect overwrites HUD/message region");
    require(!(x >= 8 && x < 232 && py >= 8 && py < 24), "effect overwrites wild name");
    require(!(x >= 8 && x < 120 && py >= 30 && py < 46), "effect overwrites wild HP bar");
    require(!(x >= 8 && x < 88 && py >= 50 && py < 66), "effect overwrites wild rarity");
    require(!(x >= 96 && x < 110 && py >= 68 && py < 75), "effect overwrites wild shiny marker");
    pixels[py * SCREEN_W + x] = color;
}
static uint64_t render(const battle_round_t *r, unsigned frame, battle_fx_rect_t wild, unsigned *visible) {
    battle_round_t before = *r;
    for (unsigned i = 0; i < sizeof(pixels) / sizeof(pixels[0]); i++) pixels[i] = SCENE_P3_BG;
    battle_fx_rect_t pet = {8, 140, 96, 96};
    for (current_band = 0; current_band < SCREEN_H; current_band += SCREEN_BAND_H)
        battle_fx_draw_band(r, (uint8_t)frame, current_band, pet, wild);
    battle_fx_pose_t pose = battle_fx_pose_for_rects(r, (uint8_t)frame, pet, wild);
    require(pose.pet_dx >= -8 && pose.pet_dx <= 8, "pet crosses screen/HUD while moving");
    require(wild.x + pose.wild_dx >= 120, "wild visible bbox crosses left HUD boundary");
    require(wild.x + pose.wild_dx + wild.w <= 240, "wild visible bbox crosses right screen edge");
    if (!r->damage && !r->missed)
        require((r->by_pet ? pose.wild_dx : pose.pet_dx) == 0, "immune target takes hit shake");
    uint64_t h = UINT64_C(14695981039346656037);
    *visible = 0;
    for (unsigned i = 0; i < sizeof(pixels) / sizeof(pixels[0]); i++) {
        if (pixels[i] != SCENE_P3_BG) {
            (*visible)++;
            if (i < 40u * SCREEN_W) top_stage_seen = true;
        }
        h = (h ^ pixels[i]) * UINT64_C(1099511628211);
    }
    if (frame >= (unsigned)battle_fx_frames(r) - 2u)
        require(*visible == 0 && pose.pet_dx == 0 && pose.wild_dx == 0, "recovery leaves a pose/effect");
    require(memcmp(&before, r, sizeof(before)) == 0, "presentation changes gameplay result");
    phase_checks++;
    return h;
}
static void probe_enemy_hud_guards(void) {
    // Deliberately aim the public API's impact at each protected rectangle.
    // Normal-layout trajectories need not cross every HUD pixel; these probes
    // keep a missing guard detectable even if those trajectories change.
    const battle_fx_rect_t targets[] = {{24, 2, 80, 80}, {8, 18, 80, 80}, {63, 31, 80, 80}};
    battle_fx_rect_t pet = {8, 140, 96, 96};
    battle_round_t r = {0}; r.move_id = 165; r.move_type = TY_NORMAL;
    r.by_pet = 1; r.damage = 20;
    for (unsigned i = 0; i < sizeof(targets) / sizeof(targets[0]); i++) {
        for (current_band = 0; current_band < SCREEN_H; current_band += SCREEN_BAND_H)
            battle_fx_draw_band(&r, 6, current_band, pet, targets[i]);
        phase_checks++;
    }
}
static void probe_actor_overlay_alignment(void) {
    // These different resting boxes reach the same visible position after the
    // shared pose. Their overlay rasters must therefore be identical as well.
    battle_fx_rect_t pet = {8, 140, 96, 96};
    battle_fx_rect_t edge = {120, 30, 112, 112}, inset = {123, 30, 112, 112};
    battle_round_t r = {0}; r.move_id = 52; r.move_type = TY_FIRE; r.damage = 20;
    battle_fx_pose_t a = battle_fx_pose_for_rects(&r, 5, pet, edge);
    battle_fx_pose_t b = battle_fx_pose_for_rects(&r, 5, pet, inset);
    require(edge.x + a.wild_dx == inset.x + b.wild_dx && a.pet_dx == b.pet_dx,
            "actor alignment probe does not share a final position");
    unsigned visible;
    uint64_t first = render(&r, 5, edge, &visible);
    require(first == render(&r, 5, inset, &visible), "overlay disagrees with bounded actor placement");
}
static uint64_t sequence(battle_round_t r, battle_fx_rect_t wild) {
    uint64_t h = 0; unsigned total = 0;
    for (unsigned f = 0; f <= battle_fx_frames(&r); f++) {
        unsigned visible;
        h = (h ^ render(&r, f, wild, &visible)) * UINT64_C(1099511628211);
        total += visible;
    }
    require(total > 0, "new trajectory is blank");
    return h;
}
static void probe_new_trajectories(void) {
    const uint16_t moves[][2] = {
        {49, TY_NORMAL}, {69, TY_FIGHTING}, {82, TY_DRAGON}, {101, TY_GHOST},
        {162, TY_NORMAL}, {56, TY_WATER}, {63, TY_NORMAL}, {120, TY_NORMAL},
    };
    for (unsigned si = 0; si < COUNT(WILD_BOUNDS); si++) for (int by_pet = 0; by_pet < 2; by_pet++) {
        uint64_t hashes[COUNT(moves)];
        for (unsigned i = 0; i < COUNT(moves); i++) {
            battle_round_t r = {0}; r.move_id = moves[i][0]; r.move_type = moves[i][1];
            r.by_pet = by_pet; r.damage = 20;
            uint64_t h = sequence(r, WILD_BOUNDS[si]);
            r.move_id = 0;
            require(h != sequence(r, WILD_BOUNDS[si]), "new move reused its type fallback");
            for (unsigned j = 0; j < i; j++) require(h != hashes[j], "new trajectories are identical");
            hashes[i] = h;
        }
    }
}
int main(void) {
    unsigned moves = sizeof(MOVES) / sizeof(MOVES[0]), dedicated = 0;
    for (unsigned i = 0; i < moves; i++) {
        if (battle_fx_has_dedicated(MOVES[i][0])) dedicated++;
        for (int by_pet = 0; by_pet < 2; by_pet++) for (unsigned si = 0; si < COUNT(WILD_BOUNDS); si++) {
            battle_round_t r = {0};
            r.move_id = MOVES[i][0]; r.move_type = (uint8_t)MOVES[i][1];
            r.by_pet = (uint8_t)by_pet; r.damage = 20;
            unsigned n = battle_fx_frames(&r), total = 0;
            require(n >= 3 && n <= 18, "unbounded animation duration");
            for (unsigned f = 0; f <= n; f++) {
                unsigned visible;
                render(&r, f, WILD_BOUNDS[si], &visible);
                total += visible;
            }
            require(total > 0, "registered move renders no visible pixels");
            r.missed = true;
            for (unsigned f = 0; f <= battle_fx_frames(&r); f++) {
                unsigned visible;
                render(&r, f, WILD_BOUNDS[si], &visible);
                require(visible == 0, "missed move draws a damage overlay");
            }
            r.missed = false; r.damage = 0;
            for (unsigned f = 0; f <= battle_fx_frames(&r); f++) {
                unsigned visible;
                render(&r, f, WILD_BOUNDS[si], &visible);
            }
        }
    }
    unsigned minimum_type_pixels = UINT32_MAX;
    for (int by_pet = 0; by_pet < 2; by_pet++) for (unsigned si = 0; si < COUNT(WILD_BOUNDS) + COUNT(TYPE_EXTRA_BOUNDS); si++) {
        battle_fx_rect_t wild = si < COUNT(WILD_BOUNDS)
            ? WILD_BOUNDS[si] : TYPE_EXTRA_BOUNDS[si - COUNT(WILD_BOUNDS)];
        uint64_t hashes[BATTLE_TYPE_COUNT];
        for (int type = 0; type < BATTLE_TYPE_COUNT; type++) {
            battle_round_t r = {0}; r.move_type = (uint8_t)type; r.damage = 20; r.by_pet = (uint8_t)by_pet;
            uint64_t h = 0; unsigned total = 0;
            for (unsigned f = 0; f <= battle_fx_frames(&r); f++) {
                unsigned visible;
                h = (h ^ render(&r, f, wild, &visible)) * UINT64_C(1099511628211);
                total += visible;
            }
            require(total > 0, "type fallback is blank after HUD/top clipping");
            for (int prior = 0; prior < type; prior++) require(h != hashes[prior], "two type fallbacks have identical rasters");
            hashes[type] = h;
            if (total < minimum_type_pixels) minimum_type_pixels = total;
        }
    }
    unsigned visible;
    battle_round_t invalid = {0}; invalid.move_type = TY_NONE;
    render(&invalid, 255, WILD_BOUNDS[1], &visible);
    require(visible == 0, "completed unknown move renders pixels");
    require(top_stage_seen, "top stage y30..39 is blank");
    probe_enemy_hud_guards();
    probe_actor_overlay_alignment();
    probe_new_trajectories();
    puts("PASS new trajectories: 8 distinct sequences, separate from type fallback, both attackers across 5 bboxes");
    printf("PASS battle_fx: %u moves (%u ID-specific mappings), 15 visible/distinct type fallback rasters for both attackers across 8 visible bboxes (32..112 px), %u phase cases; name/HP/rarity/shiny and HUD/band guards, visible-bbox motion, actor/overlay alignment, top y30..39, miss/immunity, recovery, immutable input; minimum type pixel sum=%u\n", moves, dedicated, phase_checks, minimum_type_pixels);
    return 0;
}
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--negative-checks", action="store_true",
                    help="Also prove the check rejects miss/recovery, enemy HUD, bbox motion and clipping defects in temporary source copies")
    args = ap.parse_args()
    data = (ROOT / "assets/moves.bin").read_bytes()
    magic, version, record_size, count, *_ = struct.unpack_from("<4sHHHHHH", data)
    assert magic == b"MOVE" and version == 1 and record_size == 12
    moves = []
    for i in range(count):
        mid, _, _, typ, *_ = struct.unpack_from("<HHBBBBBBH", data, 16 + i * record_size)
        moves.append(f"{{{mid},{typ}}}")
    with tempfile.TemporaryDirectory(prefix="verify_battle_fx_") as td:
        directory = Path(td)
        source, executable = directory / "driver.c", directory / "driver"
        source.write_text(DRIVER.replace("@MOVES@", ",".join(moves)))
        command = ["/usr/bin/cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                   "-fsanitize=address,undefined", "-fno-omit-frame-pointer",
                   "-I", str(ROOT / "firmware/main"), str(source)]
        implementation = ROOT / "firmware/main/battle_fx.c"
        subprocess.run(command + [str(implementation), "-o", str(executable)], check=True)
        subprocess.run([str(executable)], check=True)
        if args.negative_checks:
            original = implementation.read_text()
            for name, token, replacement, failure in (
                ("miss", "if (!round || round->missed || band_y < 0", "if (!round || band_y < 0",
                 "missed move draws a damage overlay"),
                ("recovery", "return frame < active ? (int)frame * 12 / active : 12;",
                 "return frame < active ? (int)frame * 12 / active : 6;", "recovery leaves a pose/effect"),
                ("wild_hp", "if (x >= 8 && x < 120 && y >= 30 && y < 46) return true;",
                 "if (x >= 8 && x < 120 && y >= 30 && y < 46) return false;", "effect overwrites wild HP bar"),
                ("wild_rarity", "if (x >= 8 && x < 88 && y >= 50 && y < 66) return true;",
                 "if (x >= 8 && x < 88 && y >= 50 && y < 66) return false;", "effect overwrites wild rarity"),
                ("wild_shiny", "if (x >= 96 && x < 110 && y >= 68 && y < 75) return true;",
                 "if (x >= 96 && x < 110 && y >= 68 && y < 75) return false;", "effect overwrites wild shiny marker"),
                ("wild_motion", "pose.wild_dx = bounded_dx(pose.wild_dx, wild, SCENE_P3_WILD_HUD_RIGHT, SCREEN_W);",
                 "(void)wild;", "wild visible bbox crosses left HUD boundary"),
                ("overlay_pose", "battle_fx_pose_t pose = battle_fx_pose_for_rects(round, frame, pet, wild);",
                 "battle_fx_pose_t pose = battle_fx_pose(round, frame);", "overlay disagrees with bounded actor placement"),
                ("top_clip", "py < SCENE_P3_WILD_TOP", "py < 40", "top stage y30..39 is blank"),
                ("new_fallback", "{49, BATTLE_FX_SONIC_BOOM}", "{49, BATTLE_FX_IMPACT}",
                 "new move reused its type fallback"),
            ):
                assert original.count(token) == 1, f"mutation target drifted: {name}"
                mutant = directory / f"mutant_{name}.c"
                mutant.write_text(original.replace(token, replacement))
                subprocess.run(command + [str(mutant), "-o", str(executable)], check=True)
                result = subprocess.run([str(executable)], capture_output=True, text=True)
                assert result.returncode != 0 and failure in result.stderr, f"negative check not caught: {name}"
                print(f"PASS negative check: {name} defect rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
