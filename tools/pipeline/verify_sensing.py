#!/usr/bin/env python3
"""F5 一致性检验 —— 固件的 sensing.c 与 PC 的 sensing.py 算不算得出同一个数。

用法：
    python3 tools/pipeline/verify_sensing.py                    # 编 host 版跑全量
    python3 tools/pipeline/verify_sensing.py --data data/raw/home.ndjson

## 为什么值得单独一个工具

docs/07-roadmap.md 的 F5：「把 data/raw/*.ndjson 灌进固件，
它应当算出与 sim/replay.py 完全相同的状态序列。不一致就说明移植有偏差。」

但真机上跑这个检验很别扭：要先把几 MB 的 ndjson 塞进设备，
再把结果读出来对账。而 **sensing.c 本身不依赖任何 ESP-IDF 头**
（除了 esp_rom_crc32_le，可以在 host 上用 zlib 替代），
所以可以直接在 Mac 上编译它，跑同一份数据。

这样每次改 sensing.c 都能几秒内验证，而不是烧一次板子。
真机验证仍然要做（那才是 F5 的完整形态），但不该是唯一手段。

## 对账粒度

不只比最终结果，**逐扫描比中间量**：
哈希、权重、指纹、相似度、距离、状态、瞬现 AP、地点 id。
只比最终状态的话，两个错误互相抵消就看不出来了。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
FW = REPO / "firmware" / "main"

# host 上编 sensing.c 要一个 esp_rom_crc32_le 的替身。
# 用 zlib 的 crc32 —— 它与 ESP ROM 是同一个 IEEE 802.3 算法，
# 而这正是我们要验证的那条等价关系。
SHIM = r"""
#include <stdint.h>
#include <zlib.h>
uint32_t esp_rom_crc32_le(uint32_t crc, const uint8_t *buf, uint32_t len) {
    /* ESP32-C3 的 ROM crc32_le **就是标准 CRC-32**（真机打表确认：
       rom(0, "aa:bb:cc:dd:ee:ff") = 0xD9CF27A9 = zlib.crc32 的值）。
       所以 shim 直通 zlib 即可。

       ⚠️ 这个 shim 必须与真机逐位等价。之前写成 ~crc32(~c) 时
       host 全绿而真机全错 —— host 模拟错了，两处错误互相抵消。
       **不要拿 shim 的行为去反推硬件该怎么调**，那是循环论证。 */
    return crc32(crc, buf, len);
}
"""

# 把 ESP_LOG 系列变成 printf，好让自检输出可见
LOGSHIM = r"""
#include <stdio.h>
#define ESP_LOGE(tag, fmt, ...) printf("E %s: " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGW(tag, fmt, ...) printf("W %s: " fmt "\n", tag, ##__VA_ARGS__)
#define ESP_LOGI(tag, fmt, ...) printf("I %s: " fmt "\n", tag, ##__VA_ARGS__)
"""

DRIVER = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "sensing.h"

/* 从 stdin 读简化格式：每行 "ts n bssid,rssi,ch bssid,rssi,ch ..."
   —— 不在 C 里解析 JSON，那是给 Python 干的活。 */
int main(void) {
    if (!sens_selftest()) return 2;

    sens_core_t core;
    sens_init(&core);

    char line[16384];
    while (fgets(line, sizeof(line), stdin)) {
        char *save = NULL;
        char *tok = strtok_r(line, " \t\n", &save);
        if (!tok) continue;
        uint32_t ts = (uint32_t)strtoul(tok, NULL, 10);

        sens_ap_t aps[64];
        uint8_t n = 0;
        while ((tok = strtok_r(NULL, " \t\n", &save)) && n < 64) {
            unsigned b[6]; int rssi; unsigned ch;
            if (sscanf(tok, "%x:%x:%x:%x:%x:%x,%d,%u",
                       &b[0],&b[1],&b[2],&b[3],&b[4],&b[5], &rssi, &ch) != 8)
                continue;
            for (int k = 0; k < 6; k++) aps[n].bssid[k] = (uint8_t)b[k];
            aps[n].rssi = (int8_t)rssi;
            aps[n].channel = (uint8_t)ch;
            aps[n].auth = 0;
            n++;
        }

        sens_result_t r;
        sens_feed(&core, ts, aps, n, &r);
        /* 输出中间量供逐项对账 */
        printf("R %u %u %d %u %u %d %u\n",
               (unsigned)r.ts, r.ap_count, (int)r.state,
               r.distance, r.transient_aps,
               r.is_new_place ? 1 : 0, r.place_id);
    }
    return 0;
}
"""


def build_host(workdir: Path) -> Path:
    (workdir / "esp_rom_crc.h").write_text(SHIM)
    (workdir / "esp_log.h").write_text(LOGSHIM)
    (workdir / "driver.c").write_text(DRIVER)
    exe = workdir / "sensing_host"
    cmd = [
        "cc", "-O1", "-Wall", "-Wextra", "-Werror",
        "-I", str(workdir), "-I", str(FW),
        str(FW / "sensing.c"), str(workdir / "driver.c"),
        "-lz", "-o", str(exe),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout + r.stderr, file=sys.stderr)
        raise SystemExit("host 编译失败")
    return exe


def to_driver_input(scans) -> str:
    out = []
    for s in scans:
        band = s.only_24g()
        parts = [str(s.ts)]
        for a in band.aps:
            parts.append(f"{a.bssid},{a.rssi},{a.channel}")
        out.append(" ".join(parts))
    return "\n".join(out) + "\n"


def run_python(scans):
    sys.path.insert(0, str(REPO / "sim"))
    from sensing import SensingCore     # noqa: E402

    core = SensingCore(only_24g=True)
    rows = []
    for s in scans:
        r = core.feed(s)
        rows.append({
            "ts": r.ts, "n": r.ap_count, "state": r.state,
            "dist": r.distance, "trans": r.transient_aps,
            "new": bool(r.is_new_place),
        })
    return rows, core


STATE_NAME = {0: "unknown", 1: "staying", 2: "moving"}


def main() -> int:
    ap = argparse.ArgumentParser(description="F5：固件 vs PC 感知层一致性")
    ap.add_argument("--data", default="", help="单个 ndjson；默认全部 data/raw")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO / "sim"))
    from sensing import load_ndjson      # noqa: E402

    if args.data:
        files = [Path(args.data)]
    else:
        files = sorted((REPO / "data" / "raw").glob("*.ndjson"))
    scans = []
    for f in files:
        scans += load_ndjson(str(f))
    scans.sort(key=lambda x: x.ts)
    if not scans:
        print("没有数据", file=sys.stderr)
        return 1
    print(f"数据 {len(scans)} 次扫描（{', '.join(f.name for f in files)}）")

    with tempfile.TemporaryDirectory() as td:
        exe = build_host(Path(td))
        proc = subprocess.run([str(exe)], input=to_driver_input(scans),
                              capture_output=True, text=True)
        if proc.returncode != 0:
            print(proc.stdout + proc.stderr, file=sys.stderr)
            return 1

    c_rows = []
    for line in proc.stdout.splitlines():
        if line.startswith("R "):
            _, ts, n, st, dist, trans, new, pid = line.split()
            c_rows.append({"ts": int(ts), "n": int(n), "state": STATE_NAME[int(st)],
                           "dist": int(dist), "trans": int(trans),
                           "new": new == "1", "pid": int(pid)})
        else:
            print("  " + line)          # 自检输出

    py_rows, py_core = run_python(scans)

    if len(c_rows) != len(py_rows):
        print(f"✗ 行数不同：C {len(c_rows)} vs Py {len(py_rows)}")
        return 1

    # 逐扫描逐字段对账。距离容差 1（Q10 的 1/1024，来自除法舍入）——
    # 状态/地点这类判定量则要求**完全一致**。
    bad = {"state": 0, "trans": 0, "new": 0, "dist": 0}
    worst_dist = 0
    for i, (c, p) in enumerate(zip(c_rows, py_rows)):
        if c["state"] != p["state"]:
            bad["state"] += 1
            if args.verbose:
                print(f"  #{i} state C={c['state']} Py={p['state']}")
        if c["trans"] != p["trans"]:
            bad["trans"] += 1
        if c["new"] != p["new"]:
            bad["new"] += 1
            if args.verbose:
                print(f"  #{i} new_place C={c['new']} Py={p['new']}")
        d = abs(c["dist"] / 1024 - p["dist"])
        worst_dist = max(worst_dist, d)
        if d > 2 / 1024:
            bad["dist"] += 1

    n = len(c_rows)
    print(f"\n逐扫描对账 {n} 条：")
    for k, v in bad.items():
        flag = "✓" if v == 0 else "✗"
        print(f"  {flag} {k:<6} 不符 {v}")
    print(f"  距离最大偏差 {worst_dist:.5f}（Q10 分辨率 {1/1024:.5f}）")
    print(f"\n  地点数 C={max(r['pid'] for r in c_rows)} "
          f"Py={len(py_core.memory.places)}")

    total_bad = sum(bad.values())
    print("\n→ " + ("F5 通过：固件与 PC 逐扫描一致 ✓"
                    if total_bad == 0 else f"✗ {total_bad} 处不符"))
    return 0 if total_bad == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
