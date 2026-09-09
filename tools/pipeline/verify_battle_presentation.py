#!/usr/bin/env python3
"""Exercise the production P3 presentation sampler without screen/world stubs.

Checks timed hit/HP sequences, missed attacks, both defenders, cumulative EXP
across level boundaries/caps and uint32 overflow, opposite entry directions,
and deterministic redraws. --negative must reject five compilable mutations.
This is a pure-module test; actual P3 navigation/dirty-band checks are separate.
"""
from __future__ import annotations

import argparse
from bisect import bisect_right
from pathlib import Path
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[2]
MAIN = REPO / "firmware/main"

DRIVER = r"""
#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include "battle_presentation.h"

_Static_assert(BATTLE_PRESENTATION_HP_FRAMES == 6, "HP timing contract");
_Static_assert(BATTLE_PRESENTATION_EXP_FRAMES == 18, "EXP timing contract");
_Static_assert(BATTLE_PRESENTATION_ENTRY_FRAMES == 12, "entry timing contract");

int main(void)
{
    char command[16];
    while (scanf("%15s", command) == 1) {
        if (!strcmp(command, "hit")) {
            unsigned frames;
            if (scanf("%u", &frames) != 1) return 2;
            printf("%u\n", battle_presentation_hit_frame((uint16_t)frames));
        } else if (!strcmp(command, "hp")) {
            unsigned from, to, missed, frame;
            if (scanf("%u %u %u %u", &from, &to, &missed, &frame) != 4) return 2;
            printf("%u\n", battle_presentation_hp(from, to, missed != 0, frame));
        } else if (!strcmp(command, "exp")) {
            uint32_t from, to;
            unsigned cap, frame;
            if (scanf("%" SCNu32 " %" SCNu32 " %u %u", &from, &to, &cap, &frame) != 4) return 2;
            battle_presentation_exp_t value = battle_presentation_exp(from, to, cap, frame);
            printf("%" PRIu32 " %" PRIu32 " %" PRIu32 " %u\n",
                   value.total, value.got, value.need, value.level);
        } else if (!strcmp(command, "entry")) {
            unsigned frame;
            int pet, wild;
            if (scanf("%u %d %d", &frame, &pet, &wild) != 3) return 2;
            battle_presentation_entry_t value = battle_presentation_entry(frame, pet, wild);
            printf("%d %d\n", value.pet_dx, value.wild_dx);
        } else return 2;
    }
    return 0;
}
"""


def build(directory: Path, source: Path) -> Path:
    driver = directory / "driver.c"
    driver.write_text(DRIVER)
    binary = directory / "driver"
    subprocess.run(["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                    "-I", str(MAIN), str(driver), str(source),
                    str(MAIN / "exp.c"), "-o", str(binary)],
                   check=True, capture_output=True, text=True)
    return binary


class Samples:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.values: list[tuple[int, ...]] = []

    def add(self, command: str) -> int:
        index = len(self.commands)
        self.commands.append(command)
        return index

    def run(self, binary: Path) -> None:
        # The reverse pass revisits old frames after unrelated HP/EXP/entry
        # calls. Rendering/dumping an old frame must neither advance nor reset it.
        commands = self.commands + list(reversed(self.commands))
        result = subprocess.run([str(binary)], input="\n".join(commands) + "\n",
                                check=True, capture_output=True, text=True)
        rows = [tuple(map(int, line.split())) for line in result.stdout.splitlines()]
        assert len(rows) == len(commands), "missing presentation samples"
        length = len(self.commands)
        self.values = rows[:length]
        assert rows[length:] == list(reversed(self.values)), "redraw mutated animation state"

    def __getitem__(self, index: int) -> tuple[int, ...]:
        return self.values[index]


# Existing exp.c's curve is separately exhaustively verified by verify_exp.py.
# Here boundaries independently test that the animation derives the right bar.
THRESHOLDS = [0] + [3 * level**3 // 2 for level in range(2, 101)]


def verify(binary: Path) -> int:
    samples = Samples()
    hits = {length: samples.add(f"hit {length}")
            for length in (0, 1, 2, 12, 14, 16, 18, 65535)}
    hp_cases = []
    hp_frames = list(range(8)) + [65535]
    for before in (0, 1, 2, 17, 91, 320, 65535):
        targets = {0, before, before // 2, min(65535, before + 1)}
        for after in sorted(targets):
            for missed in (0, 1):
                indexes = [samples.add(f"hp {before} {after} {missed} {frame}")
                           for frame in hp_frames]
                hp_cases.append((before, after, missed, indexes))
    hp_anchor = [samples.add(f"hp 100 40 0 {frame}") for frame in (0, 3, 6)]
    # A player hit changes wild HP only; the next wild hit changes player HP.
    # Feeding a stale changed target with missed=true must still keep both old HPs.
    defenders = []
    for before, after, missed in (((91, 83), (91, 53), 0),
                                  ((91, 53), (71, 53), 0),
                                  ((71, 53), (51, 33), 1)):
        indexes = [[samples.add(f"hp {old} {new} {missed} {frame}")
                    for old, new in zip(before, after)] for frame in range(7)]
        defenders.append((before, after, missed, indexes))

    exp_cases = []
    exp_frames = list(range(20)) + [65535]
    paths = [(0, 0), (0, 60), (40, 180), (312, 2500), (2500, 2501),
             (THRESHOLDS[-1] - 12, THRESHOLDS[-1] + 48),
             (0, 0xFFFFFFFF), (0xFFFFFFE0, 0xFFFFFFFF), (1000, 100)]
    for before, after in paths:
        for cap in (0, 1, 2, 20, 99, 100, 101, 255):
            indexes = [samples.add(f"exp {before} {after} {cap} {frame}")
                       for frame in exp_frames]
            exp_cases.append((before, after, cap, indexes))
    boundaries = [(level, total, samples.add(f"exp {total} {total} 100 0"))
                  for level, threshold in enumerate(THRESHOLDS[1:], 2)
                  for total in (threshold - 1, threshold, threshold + 1)]

    entry_cases = []
    entry_frames = list(range(14)) + [65535]
    for pet_start, wild_start in ((232, -232), (232, -217), (0, 0),
                                  (-32768, 32767), (32767, -32768)):
        indexes = [samples.add(f"entry {frame} {pet_start} {wild_start}")
                   for frame in entry_frames]
        entry_cases.append((pet_start, wild_start, indexes))

    samples.run(binary)
    for length, expected in ((0, 0), (1, 0), (2, 0), (12, 5), (14, 6),
                             (16, 7), (18, 8), (65535, 32767)):
        assert samples[hits[length]] == (expected,), f"wrong impact onset for {length} frames"
    for before, after, missed, indexes in hp_cases:
        values = [samples[index][0] for index in indexes]
        target = before if missed else min(before, after)
        assert values[0] == before, "HP deducted before the impact clock starts"
        assert all(target <= value <= before for value in values), "HP overshoot/revival"
        assert all(a >= b for a, b in zip(values, values[1:])), "HP increased during damage"
        assert values[6:] == [target] * len(values[6:]), "HP endpoint or missed guard failed"
    assert [samples[index][0] for index in hp_anchor] == [100, 70, 40], "HP did not animate"
    for length in (12, 14, 16, 18):
        onset = samples[hits[length]][0]
        assert onset + 6 <= length - 1, "next move can start before HP reaches its target"
        assert onset * 12 // (length - 2) >= 6, "HP starts before the FX impact phase"
        assert (onset - 1) * 12 // (length - 2) < 6, "HP starts after the FX impact phase"
    for before, after, missed, indexes in defenders:
        assert tuple(samples[index][0] for index in indexes[0]) == before
        target = before if missed else after
        assert tuple(samples[index][0] for index in indexes[-1]) == target
        for frame_indexes in indexes:
            for side, index in enumerate(frame_indexes):
                if missed or before[side] == after[side]:
                    assert samples[index][0] == before[side], "wrong combatant lost HP"

    for before, after, cap, indexes in exp_cases:
        values = [samples[index] for index in indexes]
        totals = [row[0] for row in values]
        target = max(before, after)
        actual_cap = min(100, max(1, cap))
        assert totals[0] == before and totals[18:] == [target] * len(totals[18:]), "EXP endpoint"
        assert all(before <= total <= target for total in totals), "EXP overflow/overshoot"
        assert all(a <= b for a, b in zip(totals, totals[1:])), "EXP moved backward"
        assert totals[9] == before + (target - before) // 2, "EXP midpoint overflow or no animation"
        for total, got, need, level in values:
            expected_level = min(actual_cap, bisect_right(THRESHOLDS, total))
            assert level == expected_level, f"EXP level {level}, expected {expected_level} at {total}"
            if level == actual_cap:
                assert (got, need) == (1, 1), f"EXP at cap {actual_cap} points at a nonexistent next level"
            else:
                assert got == total - THRESHOLDS[level - 1], "EXP bar did not reset at level-up"
                assert need == THRESHOLDS[level] - THRESHOLDS[level - 1], "wrong EXP bar range"
                assert 0 <= got < need, "EXP bar out of bounds"
    for level, total, index in boundaries:
        row = samples[index]
        expected_level = level - 1 if total < THRESHOLDS[level - 1] else level
        assert row[3] == expected_level, f"level {level} boundary at EXP {total}"
        if total == THRESHOLDS[level - 1]:
            assert row[1] == (1 if level == 100 else 0), "level-up did not reset/full-cap the bar"

    for pet_start, wild_start, indexes in entry_cases:
        values = [samples[index] for index in indexes]
        assert values[0] == (pet_start, wild_start), "entry starts at wrong edge"
        assert values[12:] == [(0, 0)] * len(values[12:]), "entry left residual displacement"
        for side, start in enumerate((pet_start, wild_start)):
            offsets = [value[side] for value in values]
            assert all(min(0, start) <= x <= max(0, start) for x in offsets), "entry overshoot"
            assert all(abs(a) >= abs(b) for a, b in zip(offsets, offsets[1:])), "entry reversed direction"
            if abs(start) > 12:
                assert 0 < abs(offsets[6]) < abs(start), "entry snapped instead of sliding"
    return len(samples.commands) * 2


MUTATIONS = {
    "miss still removes HP": (
        "if (missed || to_hp >= from_hp) return from_hp;",
        "(void)missed; if (to_hp >= from_hp) return from_hp;"),
    "EXP multiply overflows uint32": (
        "(uint64_t)(to_total - from_total)", "(uint32_t)(to_total - from_total)"),
    "cap still draws next-level progress": (
        "if (out.level == cap)", "if (out.level > cap)"),
    "entry ends one pixel short": (
        "if (frame >= BATTLE_PRESENTATION_ENTRY_FRAMES) return 0;",
        "if (frame >= BATTLE_PRESENTATION_ENTRY_FRAMES) return start > 0 ? 1 : -1;"),
    "HP starts during charge": (
        "return (uint16_t)((active + 1u) / 2u);",
        "return (uint16_t)(active * 0u);"),
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, default=MAIN / "battle_presentation.c")
    parser.add_argument("--negative", action="store_true")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="battle-presentation-") as name:
        directory = Path(name)
        count = verify(build(directory, args.source.resolve()))
        print(f"PASS battle presentation: {count} real C samples, HP/EXP/entry boundaries and redraws")
        if args.negative:
            original = args.source.read_text()
            for label, (old, new) in MUTATIONS.items():
                assert original.count(old) == 1, f"mutation anchor changed: {label}"
                mutant = directory / "mutant.c"
                mutant.write_text(original.replace(old, new))
                binary = build(directory, mutant)  # A compiler error cannot count as a caught defect.
                try:
                    verify(binary)
                except AssertionError as error:
                    print(f"  caught {label}: {error}")
                else:
                    raise AssertionError(f"negative test stayed green: {label}")
            print(f"PASS negative probes: {len(MUTATIONS)} compilable defects rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
