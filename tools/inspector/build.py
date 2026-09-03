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


def load_systems2(repo: pathlib.Path, mons: list[dict]) -> dict:
    """S4~S11 的验收数据。

    与 load_systems 同一取向：**导出参数与 Python 实测值，JS 侧重算一遍对照**。
    页面上每个系统都要能动手推进（推时间、翻页、掉道具、日切、播开场），
    而不是只看一张静态表 —— 静态表验收不了交互。

    每个 `expect` 字段都是 Python 侧算出的期望值，页面会拿 JS 结果去比。
    两边不一致就红色报警，这是真的一致性检验，不是装饰。
    """
    sys.path.insert(0, str(repo / "sim"))
    try:
        import gameplay as GP                              # noqa: E402
        import intro as IN                                 # noqa: E402
        from gameplay import PetState                      # noqa: E402
        from state import (                                # noqa: E402
            BIOME_ORDER, DEX_BYTES, ITEM_CAPS, TREND_DAYS,
            DailyCounters, Dex, DualBufferSave, Inventory, Records, SaveData,
        )
        from systems import (                              # noqa: E402
            SHINY_DENOM, STONE_BIOME, STONE_DWELL_SECONDS, TRADE_EXPLORE_MULT,
            TRADE_INTIMACY, TRIGGER_ITEM, TRIGGER_LEVEL_UP, TRIGGER_TRADE,
            check_evolution, do_evolve,
        )
    except ImportError as e:
        print(f"  注：S4-S11 导入失败（{e}），跳过", file=sys.stderr)
        return {}

    # ---- S4 养成：跑一条 72 小时无照料曲线 ----
    # 页面滑块会重算同一条，对照两边的 satiety/mood/stamina。
    #
    # 注意 advance() 首次调用只设时间基准点就返回（不知起点无法算 delta），
    # 所以必须先 advance(0) 立基准，再 advance(h*3600)。
    # 我第一版漏了这步，整条曲线是平的 —— 80/70/90 一动不动。
    curve = []
    for h in range(0, 73, 6):
        p = PetState(species_id=4, type_name="火")
        p.advance(0)                       # 立基准
        p.advance(h * 3600)
        curve.append({"h": h, "sat": round(p.satiety, 1), "mood": round(p.mood, 1),
                      "stam": round(p.stamina, 1), "low": p.is_despondent,
                      "af": round(p.ability_factor, 3),
                      "cw": round(p.catch_window_bonus, 3)})
    # 「不照料多久会饿到底」—— S4 那条「一天一次不够」推算的复核
    zero_h = next((c["h"] for c in curve if c["sat"] <= 0), None)

    s4 = {
        "decay": {"sat": GP.SATIETY_DECAY_PER_HOUR, "mood": GP.MOOD_DECAY_PER_HOUR,
                  "stamRec": GP.STAMINA_RECOVER_PER_HOUR,
                  "stamCost": GP.STAMINA_COST_PER_MOTION_EVENT},
        "low": GP.LOW_THRESHOLD, "penalty": GP.DESPONDENT_PENALTY,
        "bucket": GP.TIME_BUCKET_SECONDS,
        "curve": curve, "satZeroHour": zero_h,
    }

    # ---- S5 图鉴：用 S1 队列的真实捕获建一份图鉴 ----
    dex = Dex()
    for m in mons[:47]:            # 造一份「已收 47 只」的样本，够翻满 3 页
        dex.mark_caught(m["id"], shiny=(m["id"] % 37 == 0))
    for sid in (52, 63, 92, 130, 151):
        dex.mark_seen(sid)         # 见过没抓到 —— 剪影 + seen 标记要能区分
    s5 = {
        "bytes": len(dex.to_bytes()), "dexBytes": DEX_BYTES,
        "pages": dex.pages, "perPage": 20,
        "caught": dex.count("caught"), "seen": dex.count("seen"),
        "shinyCaught": dex.count("shiny_caught"),
        # 位图导出为 base64，页面自己解位 —— 与固件同一份数据
        "bits": {k: base64.b64encode(bytes(getattr(dex, k))).decode()
                 for k in ("seen", "caught", "shiny_seen", "shiny_caught")},
    }

    # ---- S6 存档：真实字节布局 + 双 buffer ----
    sd = SaveData()
    sd.dex = dex
    blob = sd.to_bytes()
    dual = DualBufferSave()
    dual.save(sd)
    dual.save(sd)
    ok_blob, src = dual.load()
    # 注入损坏：翻主槽一个 bit，应当回退到备份槽
    broken = bytearray(dual.slots[dual.active])
    broken[40] ^= 0xFF
    dual.slots[dual.active] = bytes(broken)
    _, src_after = dual.load()
    s6 = {
        "total": len(blob), "dual": len(blob) * 2,
        "layout": [
            {"n": "魔数+版本+CRC", "b": 10},
            {"n": "主宠（9 字段）", "b": 9},
            {"n": "图鉴 4 位图", "b": len(dex.to_bytes())},
            {"n": "背包 4 种", "b": len(sd.inventory.to_bytes())},
            {"n": "成绩纪录", "b": len(sd.records.to_bytes())},
            {"n": "biome 驻留 5×u32", "b": 20},
            {"n": "day_index", "b": 2},
        ],
        "verifyGood": SaveData.verify(blob),
        "verifyBroken": SaveData.verify(bytes(broken)),
        "srcBefore": src, "srcAfter": src_after,
        "placeTable": 512, "queue": 128,
    }

    # ---- S7 进化：三种触发各取样本 + 交互判定的期望值 ----
    evo_samples = []
    for m in mons:
        if not m["evo"] or not m["trig"]:
            continue
        trig = {"升级": TRIGGER_LEVEL_UP, "道具": TRIGGER_ITEM,
                "交换": TRIGGER_TRADE}.get(m["trig"])
        if trig is None:
            continue
        evo_samples.append({
            "id": m["id"], "zh": m["zh"] or m["slug"], "to": m["evo"],
            "toZh": mons[m["evo"] - 1]["zh"] or mons[m["evo"] - 1]["slug"],
            "trig": m["trig"], "trigCode": trig, "lv": m["lv"],
            "needInt": m["lv"] * 1.0 if trig == TRIGGER_LEVEL_UP else (
                TRADE_INTIMACY if trig == TRIGGER_TRADE else 0),
            "needExp": m["lv"] * 2 if trig == TRIGGER_LEVEL_UP else (
                m["lv"] * TRADE_EXPLORE_MULT if trig == TRIGGER_TRADE else 0),
            "biome": STONE_BIOME.get(_stone_of(m), "") if trig == TRIGGER_ITEM else "",
        })

    # 判定探针：每条都带 **期望值**，页面用它比对。
    #
    # 没有期望值的探针验收不了任何东西 —— 「2/6 通过」既可能是设计如此，
    # 也可能是实现坏了，看不出区别。带上 want 之后，红色就一定是 bug。
    #
    # 探针必须**隔离出要测的那一条**：测驻留就得先让 intimacy/explore 达标，
    # 否则 check_evolution 在亲密度那步就返回了，根本走不到驻留判定。
    # 我第一版皮卡丘给了 intimacy 50（通用门槛 60），两条驻留探针都卡在
    # 亲密度上，看起来「驻留判定没生效」，其实是探针没构造对。
    def _probe(sid: int, inti: float, expl: int, dwell: dict,
               want: bool, note: str) -> dict:
        m = mons[sid - 1]
        trig = {"升级": TRIGGER_LEVEL_UP, "道具": TRIGGER_ITEM,
                "交换": TRIGGER_TRADE}[m["trig"]]
        p = PetState(species_id=sid, type_name=m["t1"])
        p.intimacy, p.explore_value = inti, expl
        c = check_evolution(p, trig, m["evo"], m["lv"],
                            biome_dwell=dwell, item_hint=_stone_of(m))
        return {"id": sid, "zh": m["zh"] or m["slug"], "trig": m["trig"],
                "inti": inti, "expl": expl,
                "dwell": {k: v // 3600 for k, v in dwell.items()},
                "ok": c.can, "why": c.reason,
                "want": want, "pass": c.can == want, "note": note,
                "needInt": c.need_intimacy, "needExp": c.need_explore,
                "needBiome": c.need_biome}

    probes = [
        # 升级触发：妙蛙种子 @16 → 需 intimacy 60、explore 32
        _probe(1, 65, 40, {}, True, "升级线达标"),
        _probe(1, 20, 40, {}, False, "亲密度不足 → 拦住"),
        _probe(1, 65, 20, {}, False, "探索值不足（20/32）→ 拦住"),
        # 交换触发：勇基拉 需 intimacy 90（高门槛单机替代）
        _probe(64, 65, 40, {}, False, "交换线门槛更高，65 不够"),
        _probe(64, 95, 200, {}, True, "交换线达标"),
        # 道具触发：皮卡丘 需办公区驻留 6h。
        # 前两条先让 intimacy/explore 达标，才测得到驻留这一条。
        _probe(25, 65, 40, {"办公区": 6 * 3600}, True, "驻留 6h 达标"),
        _probe(25, 65, 40, {"办公区": 3600}, False, "驻留仅 1h → 拦住"),
        _probe(25, 65, 40, {"住宅区": 9 * 3600}, False, "驻留够但 biome 不对"),
    ]

    # 进化后不清零的证据
    pe = PetState(species_id=1, type_name="草")
    pe.intimacy, pe.explore_value, pe.mood = 70.0, 40, 60.0
    er = do_evolve(pe, 2, "草", 32)
    s7 = {
        "samples": evo_samples,
        "counts": {k: sum(1 for e in evo_samples if e["trig"] == k)
                   for k in ("升级", "道具", "交换")},
        "stoneBiome": STONE_BIOME, "dwellSec": STONE_DWELL_SECONDS,
        "tradeInt": TRADE_INTIMACY, "tradeMult": TRADE_EXPLORE_MULT,
        "probes": probes,
        "afterEvolve": {"inti": pe.intimacy, "expl": pe.explore_value,
                        "mood": pe.mood, "frames": len(er.frames)},
    }

    # ---- S8 闪光 ----
    s8 = {"denom": SHINY_DENOM,
          "expect1": round((1 - (1 - 1 / SHINY_DENOM) ** 100) * 100, 2),
          "expect500": round((1 - (1 - 1 / SHINY_DENOM) ** 500) * 100, 1)}

    # ---- S9 道具：掉落规则 + 切球跳空 ----
    inv = Inventory()
    drops = []
    for r in range(1, 6):
        i2 = Inventory(poke=0, great=0, ultra=0, berry=0)
        drops.append({"rarity": r, "normal": i2.drop_from_encounter(r),
                      "newPlace": Inventory(poke=0, great=0, ultra=0, berry=0)
                      .drop_from_encounter(r, is_new_place=True)})
    # 切球跳空：只有精灵球时循环应停在 poke
    only_poke = Inventory(poke=5, great=0, ultra=0)
    s9 = {
        "caps": ITEM_CAPS, "drops": drops,
        "skipEmpty": {"from_poke": only_poke.next_ball("poke"),
                      "from_great": only_poke.next_ball("great")},
        "bytes": len(inv.to_bytes()),
    }

    # ---- S10 成绩：跑 14 天日切 ----
    rec = Records()
    days = []
    import random as _rnd
    rr = _rnd.Random(20260901)
    for d in range(1, 15):
        dc = DailyCounters(encounters=rr.randint(4, 30), captures=rr.randint(0, 8),
                           motion_events=rr.randint(0, 40),
                           new_places=rr.randint(0, 2),
                           cared=rr.random() > 0.15, went_out=rr.random() > 0.3)
        broken = rec.roll_day(d, dc, intimacy=d * 5)
        days.append({"d": d, "enc": dc.encounters, "cap": dc.captures,
                     "mot": dc.motion_events, "newp": dc.new_places,
                     "cared": dc.cared, "out": dc.went_out,
                     "broken": broken, "careStreak": rec.care_streak,
                     "outStreak": rec.out_streak})
    s10 = {
        "days": days, "bytes": len(rec.to_bytes()), "trendDays": TREND_DAYS,
        "biomeOrder": BIOME_ORDER,
        "final": {"bestEnc": rec.best_encounters, "bestMot": rec.best_motion,
                  "bestNew": rec.best_new_places,
                  "careStreak": rec.longest_care_streak,
                  "outStreak": rec.longest_out_streak,
                  "totalEnc": rec.total_encounters, "days": rec.total_days},
    }

    # ---- S11 开场：帧序列 + 选择状态机 ----
    seq = IN.boot_sequence()
    sounds = [{"f": i + 1, "s": f.sound, "y": f.logo_y}
              for i, f in enumerate(seq) if f.sound]
    s11 = {
        "scrollSteps": IN.SCROLL_STEPS, "sound1": IN.SOUND_STEP_1,
        "sound2": IN.SOUND_STEP_2, "settle": IN.SETTLE_PAUSE_STEPS,
        "logo": {"w": IN.LOGO_W, "h": IN.LOGO_H, "x": IN.LOGO_X,
                 "y0": IN.LOGO_Y_START, "y1": IN.LOGO_Y_END},
        "frames": len(seq), "sounds": sounds,
        "ys": [f.logo_y for f in seq],
        "starters": IN.STARTERS, "ballY": IN.BALL_Y, "ballXs": list(IN.BALL_XS),
        "pika": list(IN.PIKA_POS),
        "cursorDx": IN.CURSOR_OFFSET_X, "cursorDy": IN.CURSOR_OFFSET_Y,
        "level": IN.STARTER_LEVEL, "items": IN.STARTER_ITEMS,
        "results": [IN.apply_choice(i) for i in range(len(IN.STARTERS))],
    }

    # ---- S13 音频 ----
    # 导出**音序数据**而非 WAV：页面用 WebAudio 现场合成，
    # 与固件同一份数据、同一套公式。塞 WAV 进 HTML 要 150 KB 且
    # 验收不了「固件也能算出同样的声音」。
    try:
        import audio as AU                     # noqa: E402
        sfx = {}
        for name, fn in AU.SFX.items():
            tracks = []
            for t in fn():
                tracks.append({
                    "kind": t.kind, "short": t.noise_short,
                    "notes": [{"m": x.midi, "d": x.dur_ms, "duty": x.duty,
                               "e0": x.env.start, "es": x.env.step,
                               "ems": x.env.step_ms,
                               "sw": x.sweep, "v": x.vol}
                              for x in t.notes],
                })
            sfx[name] = tracks
        bud = AU.budget()
        # 每条的实测峰值/直流/RMS —— 页面用 JS 重算后比对
        metrics = {}
        for name, fn in AU.SFX.items():
            buf = AU.render(fn())
            if not buf:
                continue
            pk = max(abs(v) for v in buf)
            dc = sum(buf) / len(buf)
            rms = (sum(v * v for v in buf) / len(buf)) ** 0.5
            metrics[name] = {"peak": round(pk, 4), "dc": round(dc, 5),
                             "rms": round(rms, 4), "n": len(buf)}
        s13 = {
            "sfx": sfx, "budget": bud, "metrics": metrics,
            "sr": AU.SAMPLE_RATE, "duties": list(AU.DUTIES),
            "master": AU.MASTER_VOL, "wave": AU.WAVE_TRIANGLE,
            "bytesPerNote": AU.BYTES_PER_NOTE,
        }
    except ImportError as e:
        print(f"  注：audio 导入失败（{e}）", file=sys.stderr)
        s13 = {}

    return {"s4": s4, "s5": s5, "s6": s6, "s7": s7,
            "s8": s8, "s9": s9, "s10": s10, "s11": s11, "s13": s13}


# 进化石反查：gen1.bin 只存「道具触发」，具体哪块石头要按物种查。
_STONES = {
    26: "thunder-stone", 36: "moon-stone", 40: "moon-stone",
    38: "fire-stone", 78: "fire-stone", 59: "fire-stone",
    62: "water-stone", 73: "water-stone", 87: "water-stone",
    91: "water-stone", 121: "water-stone", 134: "water-stone",
    135: "thunder-stone", 136: "fire-stone",
    45: "leaf-stone", 71: "leaf-stone", 103: "leaf-stone",
}


def _stone_of(m: dict) -> str:
    """该物种进化用哪块石头。按**进化后**的 id 查（表里存的是结果形态）。"""
    return _STONES.get(m.get("evo", 0), "fire-stone")


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
    systems2 = load_systems2(REPO, mons)
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
        "sys2": systems2,
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
    if systems2:
        print(f"  S4 饱食归零 {systems2['s4']['satZeroHour']}h　"
              f"S5 图鉴 {systems2['s5']['bytes']} B/{systems2['s5']['pages']} 页　"
              f"S6 存档 {systems2['s6']['total']} B")
        pr = systems2['s7']['probes']
        npass = sum(1 for x in pr if x['pass'])
        print(f"  S7 进化样本 {len(systems2['s7']['samples'])} 只"
              f"（{systems2['s7']['counts']}）　判定探针 {npass}/{len(pr)}"
              f"{' ✓' if npass == len(pr) else ' ✗ 有探针与期望不符'}")
        for x in pr:
            if not x['pass']:
                print(f"    ✗ #{x['id']} {x['zh']} 期望 {x['want']} 实得 "
                      f"{x['ok']}：{x['why']}", file=sys.stderr)
        print(f"  S11 开场 {systems2['s11']['frames']} 帧　"
              f"音效帧 {[x['f'] for x in systems2['s11']['sounds']]}")
        if systems2.get("s13"):
            b = systems2["s13"]["budget"]
            worst = max(systems2["s13"]["metrics"].items(),
                        key=lambda kv: abs(kv[1]["dc"]))
            print(f"  S13 音频 {len(systems2['s13']['sfx'])} 条音效　"
                  f"{b['total_bytes']} B（PCM 要 {b['as_pcm_bytes']//1024} KB，"
                  f"省 {b['as_pcm_bytes']//b['total_bytes']}×）")
            print(f"      最大直流偏移 {worst[0]} {worst[1]['dc']:+.5f}"
                  f"{' ✓' if abs(worst[1]['dc']) < 0.01 else ' ✗ 需去直流'}")
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
