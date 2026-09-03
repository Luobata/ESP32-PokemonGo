#!/usr/bin/env python3
"""把固件二进制资产打包进验收页面。

用法：
    python3 tools/inspector/build.py --src /tmp/gen1

读 tools/pipeline 的产物（gen1.bin / gen1_front.bin / gen1_back.bin），
解码成 JSON 内嵌进 template.html，输出 index.html。

**页面读的是固件真实产物，不是另画一份** —— 否则验收就没意义。
解码逻辑（2bpp 解包、分段寻址）与固件侧必须一致，
页面里的 JS 实现就是那份逻辑的对照参考。

零第三方依赖。
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import pathlib
import struct
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent.parent

TYPES_CN = ["一般", "火", "水", "电", "草", "冰", "格斗", "毒",
            "地面", "飞行", "超能", "虫", "岩石", "幽灵", "龙"]
BIOMES_CN = ["野外", "住宅区", "办公区", "商业区", "交通枢纽"]
TRIGGERS = {0: "升级", 1: "道具", 2: "交换", 255: ""}
FRONT_SIZES = [40, 48, 56]


def load_data(path: pathlib.Path) -> list[dict]:
    d = path.read_bytes()
    magic, ver, rsz, cnt, poolsz = struct.unpack("<4sHHII", d[:16])
    if magic != b"GEN1":
        raise ValueError(f"{path.name} magic 不对：{magic!r}")

    recs = d[16:16 + cnt * rsz]
    pool = d[16 + cnt * rsz:]

    out = []
    for i in range(cnt):
        o = i * rsz
        (off, ln, t1, t2, bm, cr, tg, ev, el,
         hp, at, df, sp, spd, fl, h, w, zo, zl, pi, _rv) = struct.unpack(
            "<HBBBBBBBBBBBBBBHHHBB8s", recs[o:o + rsz])
        out.append({
            "id": i + 1,
            "slug": pool[off:off + ln].decode("utf-8"),
            "zh": pool[zo:zo + zl].decode("utf-8") if zl else "",
            "pal": pi & 0x0F,
            "t1": TYPES_CN[t1] if t1 < len(TYPES_CN) else "?",
            "t2": TYPES_CN[t2] if t2 < len(TYPES_CN) else None,
            "biomes": [BIOMES_CN[j] for j in range(5) if bm >> j & 1],
            "catch": cr,
            "trig": TRIGGERS.get(tg, ""),
            "evo": ev, "lv": el,
            "st": [hp, at, df, sp, spd],     # 第 4 项是初代单一 Special
            "legend": bool(fl & 1), "myth": bool(fl & 2),
            "fsize": FRONT_SIZES[(fl >> 2) & 3],
            "h": h, "w": w,
        })
    return out


def load_palettes(path: pathlib.Path) -> dict:
    """调色板表：10 套普通 + 10 套闪光 + 每只索引。

    彩色屏用，且闪光就是换调色板（S8）—— 位图完全相同。
    """
    if not path.exists():
        return {}
    d = path.read_bytes()
    magic, ver, nsets, ncolors, count = struct.unpack("<4sHHHH", d[:12])
    if magic != b"PALS":
        raise ValueError(f"{path.name} magic 不对：{magic!r}")

    body = d[12:]
    per_set = ncolors * 2
    normal, shiny = [], []
    for i in range(nsets * 2):
        o = i * per_set
        colors = []
        for c in range(ncolors):
            (rgb565,) = struct.unpack("<H", body[o + c * 2:o + c * 2 + 2])
            r = ((rgb565 >> 11) & 0x1F) << 3
            g = ((rgb565 >> 5) & 0x3F) << 2
            b = (rgb565 & 0x1F) << 3
            colors.append(f"#{r:02x}{g:02x}{b:02x}")
        (normal if i < nsets else shiny).append(colors)

    idx_off = nsets * 2 * per_set
    per_mon = list(body[idx_off:idx_off + count])
    return {"normal": normal, "shiny": shiny, "perMon": per_mon}


def load_front(path: pathlib.Path) -> tuple[dict[int, str], list[dict], int]:
    """分段图集：三档尺寸各一段，段内定长，每项带显式 id。"""
    fd = path.read_bytes()
    magic, ver, nseg = struct.unpack("<4sHH", fd[:8])
    if magic != b"FRNT":
        raise ValueError(f"{path.name} magic 不对：{magic!r}")

    segs = []
    p = 8
    for _ in range(nseg):
        size, per, n, doff = struct.unpack("<HHII", fd[p:p + 12])
        p += 12
        segs.append((size, per, n, doff))

    base = p
    sprites: dict[int, str] = {}
    for size, per, n, doff in segs:
        q = base + doff
        for _ in range(n):
            pid, = struct.unpack("<H", fd[q:q + 2])
            q += 2
            sprites[pid] = base64.b64encode(fd[q:q + per]).decode("ascii")
            q += per

    meta = [{"size": s, "per": pp, "n": n} for s, pp, n, _ in segs]
    return sprites, meta, len(fd)


def load_back(path: pathlib.Path) -> tuple[dict[int, str], int, int]:
    bd = path.read_bytes()
    magic, ver, w, h, per, cnt = struct.unpack("<4sHHHHI", bd[:16])
    if magic != b"BACK":
        raise ValueError(f"{path.name} magic 不对：{magic!r}")

    sprites: dict[int, str] = {}
    for i in range(cnt):
        o = 16 + i * per
        sprites[i + 1] = base64.b64encode(bd[o:o + per]).decode("ascii")
    return sprites, w, len(bd)


def load_sensing(repo: pathlib.Path) -> dict:
    """把 data/raw/*.ndjson 跑一遍感知层，打包判定结果供页面可视化。

    页面上能直接对比「单帧 vs 窗口 4」的判定差异 ——
    这是验收 docs/02-sensing.md#241 那个修复的唯一直观方式。
    """
    raw = repo / "data" / "raw"
    if not raw.is_dir():
        return {}

    sys.path.insert(0, str(repo / "sim"))
    try:
        from sensing import SensingCore, load_ndjson  # noqa: E402
    except ImportError:
        return {}

    import collections
    out: dict[str, dict] = {}
    for f in sorted(raw.glob("*.ndjson")):
        scans = load_ndjson(str(f))
        if not scans:
            continue

        # 两种窗口各跑一遍，页面上可切换对比
        runs = {}
        for w in (1, 4):
            core = SensingCore(only_24g=True, smooth_window=w)
            results = core.run(scans)
            runs[str(w)] = {
                "rows": [
                    {"ts": r.ts, "n": r.ap_count, "st": r.state[0],
                     "d": round(r.distance, 3), "tr": r.transient_aps,
                     "new": 1 if r.is_new_place else 0}
                    for r in results
                ],
                "trans": core.motion.transitions,
                "places": len(core.memory.places),
                "moving": sum(1 for r in results if r.state == "moving"),
                "biomeDwell": dict(core.memory.biome_dwell),
            }

        # AP 出现率 —— 一眼看出「稳定核心 + 噪声」的分布
        counts: collections.Counter = collections.Counter()
        rssi: dict[str, list[int]] = {}
        for sc in scans:
            for ap in sc.only_24g().aps:
                counts[ap.bssid] += 1
                rssi.setdefault(ap.bssid, []).append(ap.rssi)

        n = len(scans)
        aps = [
            {"b": b[-8:], "ssid": "", "n": c, "pct": round(c / n * 100),
             "avg": round(sum(rssi[b]) / len(rssi[b]))}
            for b, c in counts.most_common()
        ]
        # 补 SSID（取最后一次见到的）
        ssid_of = {}
        for sc in scans:
            for ap in sc.only_24g().aps:
                if ap.ssid:
                    ssid_of[ap.bssid[-8:]] = ap.ssid
        for a in aps:
            a["ssid"] = ssid_of.get(a["b"], "")

        out[f.name] = {"scans": n, "runs": runs, "aps": aps,
                       "span": scans[-1].ts - scans[0].ts}
    return out


def load_systems(repo: pathlib.Path, mons: list[dict]) -> dict:
    """跑 S1/S2/S3 产出验收数据。

    页面上要能**交互式**验收捕获判定（拖指针、换球、看窗口变化），
    所以这里导出的是参数与查找表，而非固定结果 —— JS 侧重算一遍，
    与 Python 实现对照。两边算出同一个数才算验收通过。
    """
    sys.path.insert(0, str(repo / "sim"))
    try:
        from systems import (  # noqa: E402
            BALL_FACTOR, BALL_NAME_CN, BAR_WIDTH, BASE_SCALE, FLEE_CHANCE,
            GEN1_OVERRIDES, POINTER_PERIOD_MS, QUEUE_CAP, STRENGTH_TIERS,
            WINDOW_MAX, WINDOW_MIN, EncounterAccumulator, auto_battle,
            effectiveness, species_pool, wild_level, window_width,
        )
        from sensing import SensingCore, load_ndjson  # noqa: E402
        from gameplay import TYPES, PetState  # noqa: E402
    except ImportError as e:
        print(f"  注：systems 导入失败（{e}），跳过系统面板", file=sys.stderr)
        return {}

    stats_sum = {m["id"]: sum(m["st"]) for m in mons}

    # ---- S1：用真实采集数据跑一遍 ----
    raw = repo / "data" / "raw"
    queue_rows: list[dict] = []
    s1_stat = {}
    if raw.is_dir():
        scans = []
        for f in sorted(raw.glob("*.ndjson")):
            scans += load_ndjson(str(f))
        scans.sort(key=lambda x: x.ts)
        if scans:
            core = SensingCore(only_24g=True)
            acc = EncounterAccumulator(stats_sum=stats_sum)
            pet = PetState(species_id=4, type_name="火", mood=78.0)
            for sc in scans:
                acc.feed(core.feed(sc), sc.only_24g(), pet)

            pm = mons[3]      # 小火龙
            for q in acc.queue.items:
                m = mons[q.species_id - 1]
                lv = wild_level(q.rarity, 12)
                b = auto_battle(
                    [pm["t1"]] + ([pm["t2"]] if pm["t2"] else []), pm["st"], 12,
                    [m["t1"]] + ([m["t2"]] if m["t2"] else []), m["st"], lv,
                    pet.ability_factor)
                queue_rows.append({
                    "id": q.species_id, "rarity": q.rarity,
                    "shiny": q.is_shiny, "biome": q.enc.biome,
                    "transient": q.enc.is_transient, "ts": q.enc.ts,
                    "lv": lv, "won": b.won, "rounds": len(b.rounds),
                    "hp": b.wild_hp_ratio, "exp": b.exp,
                    "labels": [r.label for r in b.rounds if r.label][:3],
                })
            s1_stat = {"scans": len(scans), "hunt": acc.hunt_count,
                       "base": acc.base_count, "dropped": acc.queue.dropped,
                       "bytes": len(acc.queue.to_bytes()), "cap": QUEUE_CAP}

    # ---- S3：相克表 ----
    eff = {a: {b: effectiveness(a, [b]) for b in TYPES} for a in TYPES}

    # ---- 物种池分档 ----
    tiers = []
    for r in range(1, 6):
        pool = species_pool(r, stats_sum)
        tiers.append({"rarity": r, "n": len(pool),
                      "range": list(STRENGTH_TIERS[r - 1]),
                      "sample": [mons[i - 1]["zh"] or mons[i - 1]["slug"]
                                 for i in sorted(pool)[:5]]})

    return {
        "s1": {"stat": s1_stat, "queue": queue_rows},
        "s2": {"barWidth": BAR_WIDTH, "period": POINTER_PERIOD_MS,
               "baseScale": BASE_SCALE, "wmin": WINDOW_MIN, "wmax": WINDOW_MAX,
               "balls": BALL_FACTOR, "ballNames": BALL_NAME_CN,
               "flee": {str(k): v for k, v in FLEE_CHANCE.items()}},
        "s3": {"eff": eff, "types": TYPES,
               "gen1": [list(x) for x in GEN1_OVERRIDES],
               "levelDelta": {str(r): wild_level(r, 12) - 12 for r in range(1, 6)}},
        "tiers": tiers,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="构建验收页面")
    ap.add_argument("--src", default="/tmp/gen1",
                    help="fetch_gen1.py 的输出目录（用于必要时重跑转换）")
    ap.add_argument("--assets", default="",
                    help="已有的 .bin 目录；留空则临时转换到 /tmp")
    ap.add_argument("--out", default=str(HERE / "index.html"))
    args = ap.parse_args()

    assets = pathlib.Path(args.assets) if args.assets else pathlib.Path("/tmp/_inspect_assets")

    need = ["gen1.bin", "gen1_front.bin", "gen1_back.bin"]
    if not all((assets / f).exists() for f in need):
        print(f"资产不全，从 {args.src} 转换到 {assets} ...")
        assets.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [sys.executable, str(REPO / "tools/pipeline/convert_gen1.py"),
             "--src", args.src, "--out", str(assets)],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(r.stdout + r.stderr, file=sys.stderr)
            print("\n转换失败。先确认已拉取数据：", file=sys.stderr)
            print(f"  python3 tools/pipeline/fetch_gen1.py --out {args.src}",
                  file=sys.stderr)
            return 1

    mons = load_data(assets / "gen1.bin")
    palettes = load_palettes(assets / "palettes.bin")
    sensing = load_sensing(REPO)
    systems = load_systems(REPO, mons)
    front, seg_meta, front_bytes = load_front(assets / "gen1_front.bin")
    back, back_size, back_bytes = load_back(assets / "gen1_back.bin")

    missing = [m["id"] for m in mons if m["id"] not in front or m["id"] not in back]
    if missing:
        print(f"⚠️  {len(missing)} 只缺 sprite：{missing[:8]}", file=sys.stderr)

    payload = {
        "meta": {
            "count": len(mons),
            "recSize": 32,
            "dataBytes": (assets / "gen1.bin").stat().st_size,
            "frontBytes": front_bytes,
            "backBytes": back_bytes,
            "backSize": back_size,
            "segs": seg_meta,
        },
        "palettes": palettes,
        "sensing": sensing,
        "systems": systems,
        "mons": mons,
        "front": {str(k): v for k, v in sorted(front.items())},
        "back": {str(k): v for k, v in sorted(back.items())},
    }

    tpl = (HERE / "template.html").read_text(encoding="utf-8")
    if "ASSETS_JSON" not in tpl:
        print("错误：template.html 里找不到 ASSETS_JSON 占位符", file=sys.stderr)
        return 1

    html = tpl.replace("ASSETS_JSON",
                       json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    out = pathlib.Path(args.out)
    out.write_text(html, encoding="utf-8")

    total = payload["meta"]["dataBytes"] + front_bytes + back_bytes
    print(f"\n{out}  {out.stat().st_size/1024:.0f} KB")
    print(f"  {len(mons)} 只　front {len(front)}　back {len(back)}")
    print(f"  资产合计 {total/1024:.1f} KB（占 8MB 的 {total/8/1024/1024*100:.2f}%）")
    if systems and systems.get("s1", {}).get("stat"):
        st = systems["s1"]["stat"]
        print(f"  系统 S1: {st['scans']} 次扫描 → 队列 {len(systems['s1']['queue'])} 条"
              f"（猎场{st['hunt']} 基地{st['base']}）{st['bytes']} B")
    if sensing:
        for name, d in sensing.items():
            w1, w4 = d["runs"]["1"], d["runs"]["4"]
            print(f"  感知层 {name}: {d['scans']} 次扫描　"
                  f"窗口1 转换{w1['trans']}/移动{w1['moving']}　"
                  f"窗口4 转换{w4['trans']}/移动{w4['moving']}")
    print(f"\n启动：./tools/inspector/serve.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
