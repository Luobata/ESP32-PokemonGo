#!/usr/bin/env python3
"""从设备抓采集数据，存成 .ndjson，并可直接喂给 sim/ 跑一遍。

用法：
    python3 tools/device/collect.py --seconds 300           # 抓 5 分钟
    python3 tools/device/collect.py --seconds 300 --out data/raw/park.ndjson
    python3 tools/device/collect.py --replay data/raw/park.ndjson  # 只回放已有文件

## 这个脚本存在的理由

设备串口吐出的每行就是一条 NDJSON，键名与 `tools/collector` 完全一致
（`b/s/r/c/a`）—— 所以抓下来存成文件就能直接用，不需要任何格式转换。
**格式一致是 F5 一致性检验的前提**（docs/07-roadmap.md）。

这里做的三件事：
  ① 抓 —— 从串口收，滤掉日志行只留 JSON
  ② 补时间戳 —— 设备没有 RTC，ts 是开机秒数；这里加上主机的墙钟基准
  ③ 对账 —— 立刻喂给 sim/sensing.py 与 orchestrate.py 跑一遍，
     看感知层判出什么。采完就知道这份数据有没有用，
     而不是回来发现全是 UNKNOWN

## 采户外数据时看什么

野外 biome 是死代码（docs/00-handoff.md P0-②），修它需要知道
**真实户外的 AP 数分布**。采的时候盯 `--replay` 输出的两列：

    2.4G AP=N        户外应当明显低于室内（室内实测 6~65）
    biome=...        现在一定判不出野外（那是死代码），
                     但要看它判成了什么、AP 数在什么区间

采够公园/街道各半小时，就能定出「空旷」的判据。
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent


def capture(seconds: float, port: str = "") -> list[dict]:
    """从串口抓 NDJSON 行。复用 monitor.py 的端口识别与读取。"""
    sys.path.insert(0, str(HERE))
    import monitor

    p = monitor.find_port(port)
    print(f"从 {p} 抓 {seconds:.0f} 秒 —— 设备上要处于 RUNNING 状态",
          file=sys.stderr)
    # 不复位：复位会打断正在进行的采集
    log = monitor.capture(p, seconds, do_reset=False)

    rows = []
    bad = 0
    for line in log.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue          # 日志行，跳过
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            bad += 1          # 半行（抓取开始/结束时截断），正常
    if bad:
        print(f"  {bad} 行不完整（抓取边界截断，正常）", file=sys.stderr)
    return rows


def add_wallclock(rows: list[dict]) -> list[dict]:
    """把开机秒数换成 Unix 时间戳。

    设备没有 RTC 对时（NFC 对时那条还没结论），`ts` 是开机秒数。
    主机知道现在几点 —— 用「抓取结束时刻」对齐最后一条，往前倒推。

    这样得到的绝对时间有几秒误差（串口缓冲），但对感知层无所谓：
    它只用 `ts` 的**差值**算驻留时长（见 sim/gameplay.py 的
    `PetState.advance`，「只需要过了多久而非现在几点」）。
    """
    if not rows:
        return rows
    now = int(time.time())
    last_uptime = rows[-1]["ts"]
    base = now - last_uptime
    for r in rows:
        r["ts"] = base + r["ts"]
    return rows


def replay(path: Path) -> None:
    """把一份 .ndjson 喂给 sim/ 跑一遍，看感知层判出什么。"""
    sys.path.insert(0, str(REPO / "sim"))
    from sensing import SensingCore, load_ndjson       # noqa: E402
    from gameplay import classify_biome, ssid_family   # noqa: E402
    import orchestrate as O                            # noqa: E402

    scans = load_ndjson(str(path))
    if not scans:
        print("没有可用扫描", file=sys.stderr)
        return

    print(f"\n══ {path.name}  {len(scans)} 次扫描 ══")
    core = SensingCore(only_24g=True)
    n_aps = []
    for s in scans:
        r = core.feed(s)
        aps = s.only_24g().aps
        n_aps.append(len(aps))
        fam: dict = {}
        for a in aps:
            if a.ssid:
                k = ssid_family(a.ssid)
                fam[k] = fam.get(k, 0) + 1
        fr = max(fam.values()) / len(aps) if fam and aps else 0
        print("  2.4G AP=%-3d %-8s biome=%-6s family_ratio=%.2f%s"
              % (len(aps), r.state, classify_biome(aps) or "UNKNOWN", fr,
                 "  ← 新地点" if r.is_new_place else ""))

    if n_aps:
        print(f"\n  AP 数 {min(n_aps)}~{max(n_aps)}  均 {sum(n_aps)/len(n_aps):.1f}")
        print(f"  地点记忆 {len(core.memory.places)} 个")
        print("  驻留 " + "  ".join(f"{k} {v/60:.1f}min"
                                    for k, v in core.memory.biome_dwell.items()))

    # 跑完整流程 —— 19 个系统同时工作
    sm = O.summary(O.play_through(scans, choice=3, press_offset_ms=300))
    print(f"\n  完整流程：遭遇 {sm['encounters']} 捕获 {sm['captures']} "
          f"图鉴 {sm['caught']} 日志 {sm['log_entries']} 条")


def main() -> int:
    ap = argparse.ArgumentParser(description="设备采集 → ndjson → 对账")
    ap.add_argument("--seconds", type=float, default=300)
    ap.add_argument("--out", default="", help="存到哪，默认 /tmp 带时间戳")
    ap.add_argument("--port", default="")
    ap.add_argument("--replay", default="", help="只回放已有文件，不抓")
    ap.add_argument("--no-replay", action="store_true", help="抓完不对账")
    args = ap.parse_args()

    if args.replay:
        replay(Path(args.replay))
        return 0

    rows = capture(args.seconds, args.port)
    if not rows:
        print("没抓到数据。检查设备是否在 Collect 页且已按 OK 开始采集。",
              file=sys.stderr)
        return 1

    rows = add_wallclock(rows)
    out = Path(args.out) if args.out else Path(
        f"/tmp/devcap-{time.strftime('%Y%m%d-%H%M%S')}.ndjson")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")))
            f.write("\n")

    span = rows[-1]["ts"] - rows[0]["ts"] if len(rows) > 1 else 0
    bats = [r.get("bat", -1) for r in rows if r.get("bat", -1) >= 0]
    print(f"{len(rows)} 次扫描 → {out}  跨度 {span}s", file=sys.stderr)
    if bats and bats[0] != bats[-1]:
        print(f"  电量 {bats[0]}% → {bats[-1]}%（{span/60:.0f} 分钟）",
              file=sys.stderr)

    if not args.no_replay:
        replay(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
