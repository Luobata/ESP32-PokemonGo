#!/usr/bin/env python3
"""Movement slows while read holds, input, source assets and LCD cadence stay fixed."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / 'firmware/main'
C = r'''
#include <assert.h>
#include <stdio.h>
#include "battle_fx.h"
#include "capture_presentation.h"
int main(void) {
    assert(BATTLE_FX_TICK_MS == 45 && BATTLE_FX_LEAD_MS == 801);
    // Independent contract: every authored 45 ms sample arrives at 60 ms.
    // Source artwork/trajectories are retained, including the final sample.
    for (unsigned frame=1; frame<256; ++frame) {
        assert(battle_fx_elapsed_frame(801+60*frame-1)==frame-1);
        assert(battle_fx_elapsed_frame(801+60*frame)==frame);
    }
    for (unsigned period=1; period<=240; ++period) {
        unsigned accumulated=0;
        for (unsigned now=period; now<=12000; now+=period) {
            accumulated+=battle_motion_delta(now-period,now);
            assert(accumulated==(now*3)/4); // no per-callback truncation drift
        }
    }
    assert(battle_motion_ms(1080)==1440); // wild slide
    assert(battle_motion_ms(900)==1200);  // trainer throw/back motion
    assert(battle_motion_ms(1620)==2160); // experience movement
    assert(capture_frame_ms(37)==827);
    assert(capture_frame_ms(80)-capture_frame_ms(71)==492);
    assert(capture_frame_ms(322)-capture_frame_ms(287)==782);
    // Read/quiet intervals remain unchanged, including the gaps between shakes.
    for (unsigned f=37; f<71; ++f)
        assert(capture_frame_ms(f+1)-capture_frame_ms(f)==
               capture_base_frame_ms(f+1)-capture_base_frame_ms(f));
    for (unsigned f=225; f<287; ++f)
        assert(capture_frame_ms(f+1)-capture_frame_ms(f)==
               capture_base_frame_ms(f+1)-capture_base_frame_ms(f));
    for (unsigned f=0; f<600; ++f) {
        unsigned at=capture_frame_ms(f);
        assert(capture_source_frame(at)==f);
        if (f) assert(capture_source_frame(at-1)==f-1);
    }
    puts("PASS: 75% motion, fixed holds, exact inverse, 240 cadences, no drift");
}
'''
with tempfile.TemporaryDirectory() as tmp:
    p = Path(tmp)
    (p/'test.c').write_text(C)
    def run():
        subprocess.run(['cc', '-std=c11', '-fsanitize=address,undefined',
                        '-fno-sanitize-recover=all', '-I', str(p), '-I', str(MAIN),
                        str(p/'test.c'), '-o', str(p/'test')], check=True)
        return subprocess.run([str(p/'test')], capture_output=True, text=True)
    good = run()
    assert good.returncode == 0, good.stderr
    print(good.stdout.strip())
    # Negative control: extending whole-turn holds without slowing source motion
    # must fail, even if total battle duration is longer.
    (p/'battle_fx.h').write_text((MAIN/'battle_fx.h').read_text().replace(
        'battle_motion_source_ms(elapsed_ms - BATTLE_FX_LEAD_MS)',
        '(elapsed_ms - BATTLE_FX_LEAD_MS)'))
    assert run().returncode != 0
print(json.dumps({'motion_speed_percent': 75, 'source_sample_ms': 45,
                  'playback_sample_ms': 60, 'capture_result_ms': 9117,
                  'capture_end_ms': 9921, 'negative_controls': 1}))
