#!/usr/bin/env python3
"""Exercise actual firmware pages and compare dirty bands with a full redraw.

Also run the browser's production RGB565 decoder under Node against the serial
screenshot color contract. Browser Canvas readback is a separate UI check.
"""
from __future__ import annotations
import json
import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools/inspector"))
from native import Renderer, build, png, rgb888


def main():
    exe, version = build()
    checks = 0
    evidence = ROOT / ".build/firmware-preview/evidence"
    evidence.mkdir(parents=True, exist_ok=True)

    def check(renderer, label):
        nonlocal checks
        result = renderer.command("check")
        assert result["mismatch"] == 0, f"{label}: {result['mismatch']} stale pixels at {result['ms']}ms"
        checks += 1
        return result

    def finish_entry(renderer, label):
        # P2's transition and each species' original frame script have their
        # own durations. Keep checking every 60 ms until real P3 offers choice.
        for tick in range(180):
            state = renderer.inspect()
            if state['page'] == 3 and state['presentation']['phase'] == 'choice':
                return
            assert state['page'] == 2 or (state['page'] == 3 and
                state['presentation']['phase'] in ('entry', 'entrance-motion')), (
                    label, state['page'], state['presentation'])
            renderer.command('tick 60')
            check(renderer, f'{label} {tick}')
        raise AssertionError(f'{label}: transition/entry/motion did not reach choice')

    for page in (*range(7), 9):
        r = Renderer(exe)
        try:
            frame = r.command(f"boot {page} 25 12 74 3 1 0")
            # A valid black/white/gray page can have only four distinct bytes.
            # Detect a blank framebuffer from RGB565 pixels, not byte diversity.
            assert len(set(struct.iter_unpack(">H", frame["pixels"]))) > 1, f"P{page}: empty output"
            (evidence / f"P{page}.png").write_bytes(png(frame["pixels"]))
            check(r, f"P{page} enter")
            if page == 3:
                finish_entry(r, 'P3 entry')
                r.command("key 1 1")
            for tick in range(48):
                r.command("tick 60")
                check(r, f"P{page} tick {tick}")
            # Same key interface and lifecycle as the device, including transitions.
            r.command("key 0 1")
            for tick in range(24):
                r.command("tick 60")
                check(r, f"P{page} A/transition {tick}")
            if page == 2:
                finish_entry(r, 'P2 to P3 entry')
        finally:
            r.close()

    # Long B on the actual encounter page is gameplay (discard), unlike the
    # serial screenshot shortcut on other pages. Keep host input routing honest.
    r = Renderer(exe)
    try:
        before = r.command("boot 2 25 12 74 3 1 0")
        after = r.command("key 1 3")
        assert after["page"] == "P2" and after["pixels"] != before["pixels"], "P2 long-B discard was swallowed"
        check(r, "P2 long-B discard")
        for _ in range(3):
            r.command("key 1 3")
            check(r, "P2 long-B empty queue")
        empty = r.command("key 1 3")
        assert empty["pixels"] == r.command("key 1 3")["pixels"], "empty queue discard is unstable"
    finally:
        r.close()

    # Wide species names, levels and both attack directions; animation must be
    # observable in the pixel stream, and must settle without stale upper bands.
    for pet, level, wild, rarity, seed in [(139,100,103,5,3),(25,12,19,1,7),(1,20,7,3,11)]:
        r = Renderer(exe)
        try:
            r.command(f"boot 3 {pet} {level} {wild} {rarity} {seed} 1")
            check(r, "P3 boundary")
            finish_entry(r, 'P3 boundary entry')
            r.command("key 1 1")
            frames = set()
            for tick in range(110):
                result = r.command("tick 60")
                frames.add(result["pixels"])
                check(r, "P3 boundary battle")
            assert len(frames) > 3, "battle animation did not reach framebuffer"
        finally:
            r.close()

    # All 65536 wire colors, including endpoints and bit replication.
    colors = b"".join((i % 65536).to_bytes(2, "big") for i in range(240 * 320))
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "wire.bin"
        source.write_bytes(colors)
        js = """const fs=require('fs'),decode=require(process.argv[1]);
const rgba=decode(new Uint8Array(fs.readFileSync(process.argv[2])));
const rgb=Buffer.alloc(240*320*3);
for(let i=0,j=0;i<rgba.length;i+=4,j+=3){
  if(rgba[i+3]!==255)throw Error('alpha');
  rgb[j]=rgba[i];rgb[j+1]=rgba[i+1];rgb[j+2]=rgba[i+2];
}process.stdout.write(rgb);"""
        output = subprocess.check_output(["node", "-e", js,
                    str(ROOT / "tools/inspector/firmware-pixels.js"), str(source)])
        assert output == rgb888(colors), "browser decoder differs from serial screenshots"
        assert output[65535*3:65536*3] == b"\xff\xff\xff"

    # A missing production DMA wait must fail, rather than producing a green
    # gate against a convenient synchronous framebuffer stub. Mutate a private
    # copy; never change the developer's checkout for a negative test.
    with tempfile.TemporaryDirectory() as tmp:
        mutant = Path(tmp)
        shutil.copytree(ROOT / "firmware/main", mutant / "firmware/main")
        shutil.copytree(ROOT / "firmware/components/bsp/include", mutant / "firmware/components/bsp/include")
        shutil.copytree(ROOT / "tools/inspector/host", mutant / "tools/inspector/host")
        shutil.copy2(ROOT / "tools/inspector/native.py", mutant / "tools/inspector/native.py")
        (mutant / "assets").symlink_to(ROOT / "assets", target_is_directory=True)
        screen = mutant / "firmware/main/screen.c"
        source = screen.read_text()
        assert source.count("    wait_dma_done();") == 1
        screen.write_text(source.replace("    wait_dma_done();", "    /* negative: DMA barrier removed */"))
        spec = importlib.util.spec_from_file_location("negative_native", mutant / "tools/inspector/native.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        mutant_exe, _ = module.build()
        result = subprocess.run([str(mutant_exe)], input=b"boot 3 25 12 74 3 1 0\n", capture_output=True, timeout=10)
        assert result.returncode != 0 and b"unsynchronized LCD transfer" in result.stderr, "missing DMA barrier was not detected"
        screen.write_text(source)
        battle = mutant / "firmware/main/play_battle.c"
        source = battle.read_text()
        assert source.count("            draw_band(BAND_H * 2);") == 1
        battle.write_text(source.replace("            draw_band(BAND_H * 2);", "            /* negative: skip player dirty band */"))
        mutant_exe, _ = module.build()
        r = module.Renderer(mutant_exe)
        try:
            r.command("boot 3 25 12 19 1 7 0")
            finish_entry(r, 'negative dirty-band entry')
            r.command("key 1 1")
            found_stale = False
            for _ in range(36):
                r.command("tick 60")
                if r.command("check")["mismatch"] > 0:
                    found_stale = True
                    break
            assert found_stale, "missing player dirty band was not detected"
        finally:
            r.close()
    print(json.dumps({"build": version, "pages": 8, "dirty_redraw_checks": checks,
                      "wire_colors": 65536, "negative_dma": "caught", "negative_dirty_band": "caught",
                      "long_press_discard": "passed", "evidence": str(evidence)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
