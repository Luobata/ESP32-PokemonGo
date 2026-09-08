#!/usr/bin/env python3
"""Native P2/P3/P4 lifecycle and presentation integration, using actual C pages.

World, clock and NVS are inspector fixtures. Durable removal, V5 migration and
concurrency are tested separately by verify_encounter_lifecycle.py against the
actual world/save sources. Neither test operates real ESP32 flash.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/inspector"))
from native import Renderer, build, png

INTRO_MS = 720


class Flow:
    def __init__(self, executable, *, page=3, pet=25, level=12, wild=19, rarity=1, seed=7):
        self.renderer = Renderer(executable)
        self.checks = 0
        self.command(f"boot {page} {pet} {level} {wild} {rarity} {seed} 0")
        self.uid = self.state()["uid"]

    def close(self):
        self.renderer.close()

    def state(self):
        return self.renderer.inspect()

    def command(self, command):
        self.frame = self.renderer.command(command)
        check = self.renderer.command("check")
        assert check["mismatch"] == 0, f"{command}: {check['mismatch']} stale pixels"
        self.checks += 1
        return self.frame

    def key(self, key):
        return self.command(f"key {'ABC'.index(key)} 1")

    def tick(self, milliseconds=60):
        return self.command(f"tick {milliseconds}")

    def ready(self):
        self.until(lambda: self.state()["presentation"]["phase"] == "choice", "slide and species entrance motion")

    def active(self):
        return self.state()["active"]

    def queued(self):
        return next((e for e in self.state()["queue"] if e["uid"] == self.uid), None)

    def encounter(self):
        return self.active() or self.queued()

    def until(self, predicate, label, ticks=1100):
        for _ in range(ticks):
            if predicate(): return
            self.tick()
        raise AssertionError(f"timed out: {label}; state={self.state()}")

    def victory(self):
        self.ready(); self.key("B")
        self.until(lambda: self.active() and self.active()["reward_settled"], "battle settlement")
        assert self.active()["won"], "victory fixture lost"
        self.until(lambda: self.state()["presentation"]["phase"] == "result", "EXP presentation")


def fifo(f):
    initial = f.state()["queue"]
    assert len(initial) == 4
    f.command("spawn 150 5 2000"); full = f.state()["queue"]
    assert len(full) == 5 and full[:-1] == initial
    f.command("spawn 10 1 2001"); after = f.state()["queue"]
    assert len(after) == 5 and after[:-1] == full[1:], "not strict FIFO"
    assert after[-1]["species"] == 10 and f.active() is None
    assert f.state()["dropped"] == 1


def list_refresh(f):
    initial = f.frame["pixels"]
    f.command("spawn 150 5 2100")
    assert f.frame["pixels"] == initial, "host spawn must not force a UI redraw"
    f.tick(200); filled = f.frame["pixels"]
    assert filled != initial, "P2 did not display a new pending encounter"
    f.command("spawn 10 1 2101")
    assert f.frame["pixels"] == filled
    f.tick(199); assert f.frame["pixels"] == filled
    f.tick(1)
    assert f.frame["pixels"] != filled, "same-count FIFO replacement was not refreshed"
    selected = f.state()["queue"][0]["uid"]
    f.key("A"); f.until(lambda: f.state()["page"] == 3, "select refreshed first row")
    assert f.state()["uid"] == selected


def list_stale_action(f):
    # Both arrivals occur before P2's next 200ms timer. The old visible uid is
    # evicted, so this A only refreshes; it must not select the new index zero.
    f.command("spawn 150 5 2200"); f.command("spawn 10 1 2201")
    remaining = f.state()["queue"]
    f.key("A"); f.tick(3000)
    assert f.state()["page"] == 2 and f.state()["queue"] == remaining and f.active() is None, \
        "stale row selected a replacement encounter"
    f.key("A"); f.until(lambda: f.state()["page"] == 3, "explicitly select replacement after refresh")
    assert f.state()["uid"] == remaining[0]["uid"]


def list_keeps_selection(f):
    chosen = f.state()["queue"][1]["uid"]
    f.key("B")
    f.command("spawn 150 5 2300"); f.command("spawn 10 1 2301"); f.tick(200)
    # The selected second item moved to the first row when its predecessor left.
    assert f.state()["queue"][0]["uid"] == chosen
    f.key("A"); f.until(lambda: f.state()["page"] == 3, "select retained uid after index shift")
    assert f.state()["uid"] == chosen


def list_stale_discard(f):
    f.command("spawn 150 5 2400"); f.command("spawn 10 1 2401")
    remaining = f.state()["queue"]
    f.command("key 1 3")  # B long: discard the displayed identity only.
    assert f.state()["queue"] == remaining and f.state()["page"] == 2
    f.command("key 1 3")
    assert f.state()["queue"] == remaining[1:] and f.state()["page"] == 2


def entry_and_cancel(f):
    before = f.state(); start = before["presentation"]
    assert f.active() is None and f.queued() is not None
    assert start["phase"] == "entry" and start["pet_dx"] > 0 and start["wild_dx"] < 0
    for key in "ABCABC":
        f.key(key)
        assert f.state()["page"] == 3 and f.active() is None and f.queued()["attacks"] == 0
    f.tick(360); middle = f.state()["presentation"]
    assert middle["phase"] == "entry" and 0 < middle["pet_dx"] < start["pet_dx"]
    assert start["wild_dx"] < middle["wild_dx"] < 0
    f.tick(360)
    assert f.state()["presentation"]["phase"] == "entrance-motion"
    f.ready(); end = f.state()["presentation"]
    assert end["phase"] == "choice" and end["pet_dx"] == end["wild_dx"] == 0
    f.key("A")
    assert f.state()["page"] == 4
    f.key("C"); assert f.state()["page"] == 3 and f.active() is None
    f.key("A")
    assert f.state()["page"] == 4, "P4 cancellation replayed the entry lock"


def direct_capture(f):
    f.ready(); before = f.state()
    f.key("A"); assert f.state()["page"] == 4 and f.active() is None
    f.tick(300); f.key("A"); after = f.state()
    assert f.queued() is None and after["active"] is None
    assert after["party_count"] == before["party_count"] + 1
    assert after["caught"] == before["caught"] + 1 and after["exp"] == before["exp"]
    assert len(after["queue"]) == len(before["queue"]) - 1
    for key in "ABCABC": f.key(key)
    f.tick(40)
    assert f.state()["page"] == 2
    assert all(f.state()[key] == after[key] for key in ("exp", "party_count", "caught"))


def pending_evicted(f):
    f.ready(); before = f.state()
    for i in range(6): f.command(f"spawn {40+i} {1+i%5} {2500+i}")
    assert f.queued() is None and f.active() is None
    remaining = f.state()["queue"]
    f.key("B")
    assert f.state()["page"] == 2 and f.active() is None
    assert f.state()["queue"] == remaining, "stale detail claimed a replacement encounter"
    assert all(f.state()[key] == before[key] for key in ("exp", "party_count", "caught"))


def begin_failure_retry(f):
    f.ready(); before = f.state()
    f.command("save_fail 1"); f.key("B"); failed = f.state()
    assert failed["page"] == 3 and failed["active"] is None
    assert failed["queue"] == before["queue"] and failed["exp"] == before["exp"]
    f.tick(6000)
    assert f.state()["queue"] == before["queue"] and f.active() is None
    f.key("B")
    assert f.active() and f.active()["auto_battle"] and f.queued() is None
    assert len(f.state()["queue"]) == len(before["queue"]) - 1


def single_reply(f):
    f.ready(); initial = f.encounter(); old_exp = f.state()["exp"]
    f.key("A"); f.key("A"); pending = f.active()
    assert f.queued() is None and pending and pending["uid"] == f.uid
    assert pending["retaliation"] and not pending["auto_battle"]
    for key in "ABCABC":
        f.key(key)
        assert f.state()["page"] == 4 and f.active() == pending
    f.tick(40); reply = f.active()
    assert f.state()["page"] == 3 and reply["attacks"] == 1
    assert reply["pet_hp"] < initial["pet_hp"] and reply["wild_hp"] == initial["wild_hp"]
    for key in "ACBAC":
        f.key(key)
        assert f.state()["page"] == 3 and f.active() == reply, "counter animation bypassed"
    f.tick(6000); paused = f.active()
    assert paused["attacks"] == 1 and not paused["finished"] and not paused["auto_battle"]
    assert f.state()["presentation"]["phase"] == "choice"
    f.tick(60000)
    assert f.active() == paused, "one retaliation silently became automatic battle"
    assert f.state()["exp"] == old_exp
    f.key("A"); assert f.state()["page"] == 4
    f.key("A"); f.key("C"); f.tick(40); f.tick(6000); second = f.active()
    assert second["attacks"] == 2 and second["wild_hp"] == paused["wild_hp"]
    assert second["pet_hp"] < paused["pet_hp"] and not second["auto_battle"]
    f.key("C")
    f.until(lambda: f.state()["page"] == 2, "successful escape finishes")
    assert f.state()["page"] == 2 and f.active() is None and f.queued() is None
    for page in (3, 4, 3):
        f.command(f"page {page}")
        assert f.state()["page"] == 2 and f.active() is None and f.queued() is None
    assert f.state()["exp"] == old_exp


def auto_and_fifo(f):
    f.ready(); f.key("B"); active = f.active()
    assert active and active["auto_battle"] and f.queued() is None
    for key in "ABAB":
        f.key(key)
        assert f.state()["page"] == 3 and f.active() == active, "automatic battle is escapable"
    for i in range(7):
        f.command(f"spawn {10+i} {1+i%5} {3000+i}")
        assert len(f.state()["queue"]) <= 5 and f.active() == active
    assert [e["species"] for e in f.state()["queue"]] == [12, 13, 14, 15, 16]
    f.until(lambda: f.active()["reward_settled"], "automatic battle settlement")
    assert f.active()["finished"] and f.active()["won"]
    f.until(lambda: f.state()["presentation"]["phase"] == "result", "EXP presentation")
    settled_exp = f.state()["exp"]; f.key("C")
    assert f.state()["page"] == 2 and f.active() is None and f.queued() is None
    f.command("page 3")
    assert f.state()["page"] == 2 and f.active() is None and f.state()["exp"] == settled_exp


def victory_miss(f):
    f.victory(); before = f.state()
    for _ in range(2):
        f.key("A"); assert f.state()["page"] == 4
        f.key("C"); assert f.state()["page"] == 3
        assert not f.active()["capture_used"] and f.state()["exp"] == before["exp"]
    f.key("A"); f.key("B"); f.key("A")
    assert f.active() is None and f.queued() is None
    assert all(f.state()[key] == before[key] for key in ("exp", "party_count", "caught"))
    for key in "ABCABC": f.key(key)
    f.tick(40)
    for page in (3, 4):
        f.command(f"page {page}")
        assert f.state()["page"] == 2 and f.active() is None


def victory_capture(f):
    f.victory(); before = f.state()
    f.key("A"); f.tick(300); f.key("A"); after = f.state()
    assert after["active"] is None and f.queued() is None
    assert after["party_count"] == before["party_count"] + 1
    assert after["caught"] == before["caught"] + 1 and after["exp"] == before["exp"]
    for key in "ABCABC": f.key(key)
    f.tick(40); f.command("page 4")
    assert f.state()["page"] == 2 and f.state()["active"] is None
    assert all(f.state()[key] == after[key] for key in ("exp", "party_count", "caught"))


def lethal_reply(f):
    f.ready(); f.key("A"); f.key("A"); f.key("C"); f.tick(40); active = f.active()
    assert active["attacks"] == 1 and active["pet_hp"] == 0 and active["finished"] and not active["won"]
    f.until(lambda: f.active()["reward_settled"], "defeat settlement")
    f.until(lambda: f.state()["presentation"]["phase"] == "result", "EXP presentation")
    reward = f.state()["exp"]; f.key("A")
    assert f.state()["page"] == 5 and f.state()["exp"] == reward
    assert f.active() is None and f.queued() is None
    f.command("page 4")
    assert f.state()["page"] == 2 and f.state()["exp"] == reward


def presentation(f):
    f.ready(); initial = f.state(); old_exp = initial["exp"]
    previous_target = (f.encounter()["pet_hp"], f.encounter()["wild_hp"])
    f.key("B")
    segment = None; segments = []; exp_samples = []; exp_targets = set(); levels = set()
    for _ in range(1100):
        state = f.state(); active, view = state["active"], state["presentation"]
        assert state["page"] == 3 and active
        target = (active["pet_hp"], active["wild_hp"])
        visible = (view["visible_pet_hp"], view["visible_wild_hp"])
        if active["attacks"]:
            if segment is None or active["attacks"] != segment["attack"]:
                if segment is not None:
                    assert segment["samples"][-1] == segment["to"], "HP never reached its target"
                    segments.append(segment)
                segment = {"attack": active["attacks"], "from": previous_target, "to": target, "samples": []}
                previous_target = target
            assert all(new <= shown <= old for old, new, shown in zip(segment["from"], segment["to"], visible))
            if segment["samples"]:
                assert all(a >= b for a, b in zip(segment["samples"][-1], visible)), "HP increased during damage"
            segment["samples"].append(visible)
        if state["exp"] != old_exp: exp_targets.add(state["exp"])
        if view["phase"] in ("exp", "result"):
            exp_samples.append(view["visible_exp"]); levels.add(view["visible_level"])
            assert old_exp <= view["visible_exp"] <= state["exp"]
        if view["phase"] == "result":
            assert active["reward_settled"] and active["finished"] and visible == target
            assert view["visible_exp"] == state["exp"] and view["visible_level"] == state["level"]
            break
        # Also lock the final damage and EXP intervals, after gameplay is final.
        for key in ("ACB" if active["finished"] else "AB"):
            f.key(key)
            assert f.state()["page"] == 3 and f.active() == active
        f.tick()
    else: raise AssertionError("presentation did not finish")
    if segment is not None:
        assert segment["samples"][-1] == segment["to"]; segments.append(segment)
    assert any(new < shown < old for item in segments for sample in item["samples"]
               for old, new, shown in zip(item["from"], item["to"], sample)), "HP only jumped to its endpoint"
    assert len(exp_targets) == 1, "gameplay EXP changed more than once or not at all"
    assert exp_samples == sorted(exp_samples)
    assert any(old_exp < value < f.state()["exp"] for value in exp_samples), "EXP had no intermediate frame"
    if f.state()["level"] > initial["level"]:
        assert initial["level"] in levels and f.state()["level"] in levels
    reward = f.state()["exp"]; f.tick(6000)
    assert f.state()["exp"] == reward and f.active()["reward_settled"]


def negative_probes():
    """Break private copies; compile/setup errors are not successful probes."""
    changes = [
        ("missing P2 refresh", "if (!s_trans_tick && refresh_list()) draw_all();",
         "if (false) draw_all();", "P2 did not display a new pending encounter"),
        ("selected current index instead of displayed identity",
         "const encounter_t *shown = &s_view.items[s_sel];\n    encounter_t current;",
         "const encounter_t *shown = &world_queue()->items[s_sel];\n    encounter_t current;",
         "stale row selected a replacement encounter"),
    ]
    proved = []
    with tempfile.TemporaryDirectory(prefix="encounter-preview-negative-") as folder:
        root = Path(folder)
        for path in ("firmware/main", "firmware/components/bsp/include", "tools/inspector/host"):
            shutil.copytree(ROOT / path, root / path)
        (root / "assets").mkdir()
        for asset in (ROOT / "assets").glob("*.bin"):
            shutil.copy2(asset, root / "assets" / asset.name)
        shutil.copy2(ROOT / "tools/inspector/native.py", root / "tools/inspector/native.py")
        script = root / "tools/pipeline" / Path(__file__).name
        script.parent.mkdir(parents=True)
        shutil.copy2(__file__, script)
        source = root / "firmware/main/play_enc.c"
        original = source.read_text()
        for label, old, new, expected_failure in changes:
            assert original.count(old) == 1, f"mutation anchor changed: {label}"
            source.write_text(original.replace(old, new))
            result = subprocess.run([sys.executable, str(script)], text=True, capture_output=True, timeout=60)
            source.write_text(original)
            assert result.returncode and "AssertionError" in result.stderr and expected_failure in result.stderr, \
                f"mutation escaped or infrastructure failed: {label}\n{result.stdout}\n{result.stderr}"
            proved.append(label)
    return proved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "reports/evidence/encounter-lifecycle-2026-09-08/preview.json")
    parser.add_argument("--negative", action="store_true", help="also prove two isolated broken P2 variants fail")
    args = parser.parse_args()
    executable, version = build()
    winner = dict(pet=139, level=100, wild=137, seed=3)
    lethal = dict(level=1, wild=150, rarity=5, seed=1)
    cases = [("FIFO independent of rarity", fifo, dict(page=2, rarity=5)),
             ("P2 asynchronously refreshes additions and same-count FIFO", list_refresh, dict(page=2)),
             ("A during FIFO refresh window cannot select a replacement", list_stale_action, dict(page=2)),
             ("P2 cursor follows retained uid when FIFO shifts indices", list_keeps_selection, dict(page=2)),
             ("discard during FIFO refresh window cannot drop a replacement", list_stale_discard, dict(page=2)),
             ("entry samples, input lock and unstarted cancellation", entry_and_cancel, {}),
             ("direct capture exactly once without battle EXP", direct_capture, {}),
             ("evicted pending detail cannot claim a replacement", pending_evicted, {}),
             ("failed begin save and safe retry", begin_failure_retry, {}),
             ("single retaliation then choice, including 60s idle", single_reply, {}),
             ("automatic battle lock and active survives FIFO", auto_and_fifo, winner),
             ("victory cancellation retains one chance, miss consumes it", victory_miss, winner),
             ("victory capture is committed once", victory_capture, winner),
             ("lethal retaliation cannot reopen capture or reward", lethal_reply, lethal),
             ("HP and EXP intermediate display samples", presentation, {}),
             ("lethal HP and multiple EXP level boundaries", presentation, lethal)]
    completed = []; checks = 0
    for label, test, configuration in cases:
        flow = Flow(executable, **configuration)
        try:
            test(flow); completed.append(label)
        except Exception:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            (args.output.parent / "preview-failure.png").write_bytes(png(flow.frame["pixels"]))
            (args.output.parent / "preview-failure-state.json").write_text(json.dumps(flow.state(), indent=2) + "\n")
            raise
        finally:
            checks += flow.checks; flow.close()
    result = {"status": "PASS", "build": version, "cases": completed, "dirty_full_checks": checks,
              "scope": "actual C pages/nav/battle/capture/encounter/rendering; fixture world/clock/NVS",
              "storage_test": "verify_encounter_lifecycle.py exercises actual world/save separately"}
    if args.negative:
        result["negative_probes"] = negative_probes()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
