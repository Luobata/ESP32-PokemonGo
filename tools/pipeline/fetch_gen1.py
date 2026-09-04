#!/usr/bin/env python3
"""拉取初代 151 只宝可梦的数据、sprite 与招式。

用法：
    python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1
    python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1 --version yellow
    python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1 --no-moves

数据来自 PokeAPI (pokeapi.co)，sprite 来自 PokeAPI/sprites 仓库。
带本地缓存 —— 重跑不会重复请求，也方便离线迭代。

关于 sprite 的两个关键事实（均为实测）：

**① 原版就是 4 色（depth=2）**，索引/灰度值 0~3 直接对应 2bpp 四阶灰，
不需要转灰度或量化。默认用 gray 变体（colortype=0，无 PLTE，真 4 级灰阶）；
不带 gray 的路径是 SGB/GBC 的 4 色**彩色**版。

**② front 尺寸不固定**：40×40 有 44 只、48×48 有 43 只、56×56 有 50 只
（RBY 按 5×5/6×6/7×7 tile 存）。back 统一 32×32。
转换时必须按各自原生尺寸处理，否则大型宝可梦会被压小。

关于招式的一个关键事实：

**③ PokeAPI 返回的招式数值是现代的，必须还原成初代**。这与物种的妖精系
retcon 是同类问题，但更隐蔽 —— 妖精系人尽皆知，招式的改动却零散无人记得。
实测「咬住」现在是恶系（初代一般系）、「挖洞」现在威力 80（初代 100）。
恶系在本项目的 15 属性表里不存在，直接用现代值会让属性编号越界。
还原逻辑见 gen1_move_values()。

零第三方依赖（urllib 在标准库里）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

API = "https://pokeapi.co/api/v2"
SPRITES = ("https://raw.githubusercontent.com/PokeAPI/sprites/master"
           "/sprites/pokemon/versions/generation-i")

# 用 gray 变体而非默认的彩色 palette 版。
# 实测：red-blue/{id}.png 是 4 色**彩色**调色板（SGB/GBC 着色版），
# 而 red-blue/gray/{id}.png 是 colortype=0、无 PLTE 的**真 4 级灰阶** ——
# 正是 DMG 的原生表现，不需要再做彩色→灰度转换。
GRAY = True

GEN1_COUNT = 151

# 初代 15 属性。没有恶(dark)/钢(steel)/妖精(fairy) —— 那是后来加的。
GEN1_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic",
    "bug", "rock", "ghost", "dragon",
]

# 招式的版本组与学习方式。红蓝的升级学习表就是初代原版。
MOVE_VERSION_GROUP = "red-blue"
MOVE_LEARN_METHOD = "level-up"

# PokeAPI 的 version_group 是按世代升序排的（实测下标 0=red-blue、
# 1=yellow、2=gold-silver...）。past_values[i] 的含义是
# 「**直到** 该 version_group 为止，这个字段还是旧值」，
# 所以要还原初代值，就取第一条**在 red-blue 之后**的 past_values ——
# 也就是数组里的第一条（初代之后最早的一次改动）。
# 这个顺序假设由 verify_past_values_order() 在运行时校验，不靠人记。
PAST_VALUE_FIELDS = ("power", "accuracy", "pp")

# 版本组的世代顺序。**从 API 拉**而不是手抄 —— 手抄的清单会随
# 新世代发布而过期，而过期的表会让 verify_past_values_order() 把
# 未知版本组当成 -1 跳过，等于校验静默失效。
VERSION_GROUP_ORDER: list[str] = []


def load_version_group_order(cache: str) -> list[str]:
    """拉取版本组的世代顺序，供 past_values 的顺序校验使用。"""
    global VERSION_GROUP_ORDER
    data = fetch_json(f"{API}/version-group/?limit=200", cache)
    if data and data.get("results"):
        VERSION_GROUP_ORDER = [r["name"] for r in data["results"]]
    return VERSION_GROUP_ORDER


def fetch_json(url: str, cache_dir: str, retries: int = 3) -> dict | None:
    """带缓存的 JSON 拉取。"""
    key = url.replace(API + "/", "").rstrip("/").replace("/", "_") + ".json"
    path = os.path.join(cache_dir, key)

    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            pass        # 缓存坏了就重拉

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ESP32-PokemonGo/1.0 (personal project)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return data
        except Exception as e:
            # 捕获宽泛是有意的：socket.timeout 是 OSError 子类而非 URLError，
            # ssl 层还会抛别的。单个条目失败不该炸掉整批拉取。
            if attempt == retries - 1:
                print(f"  失败 {url}: {type(e).__name__}", file=sys.stderr)
                return None
            time.sleep(2.0 * (attempt + 1))     # 退避，别把公共 API 打爆
    return None


def fetch_binary(url: str, dest: str, retries: int = 3) -> bool:
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "ESP32-PokemonGo/1.0 (personal project)"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = r.read()
            if not data.startswith(b"\x89PNG"):
                return False
            with open(dest, "wb") as f:
                f.write(data)
            return True
        except Exception as e:
            if attempt == retries - 1:
                print(f"  失败 {os.path.basename(dest)}: {type(e).__name__}",
                      file=sys.stderr)
                return False
            time.sleep(2.0 * (attempt + 1))
    return False


def parse_evolution_chain(chain: dict, valid: set[str]) -> dict[str, dict]:
    """把进化链树展开成 {from_slug: {to, trigger, level, item}}。

    两个坑：
      · **分支进化** —— 走走可以进化成臭臭花或美丽花，一个 from 对多个 to。
        这里只保留第一条（初代分支很少，且 133 号伊布的分支靠道具区分）。
      · **跨世代污染** —— 美丽花(bellossom)是二代的，链里却挂在初代的走走下面。
        必须用 valid 集合过滤，否则会指向不存在的 id。
    """
    out: dict[str, dict] = {}

    def walk(node: dict) -> None:
        me = node["species"]["name"]
        for child in node.get("evolves_to") or []:
            target = child["species"]["name"]
            if target not in valid:
                continue        # 跨世代，丢掉
            dets = child.get("evolution_details") or []
            d = dets[0] if dets else {}
            if me not in out:   # 分支只留第一条
                out[me] = {
                    "to": target,
                    "trigger": (d.get("trigger") or {}).get("name", ""),
                    "level": d.get("min_level") or 0,
                    "item": (d.get("item") or {}).get("name", "") or "",
                }
            walk(child)

    walk(chain)
    return out


def verify_past_values_order(moves: list[dict]) -> list[str]:
    """校验 past_values 确实按世代升序排列。

    gen1_move_values() 依赖「数组第一条 = 初代之后最早的改动」这个假设。
    假设一旦不成立，还原出来的初代数值会静默错掉 —— 数值仍在合法范围，
    不会抛异常，只是全都不对。所以这里用**已知版本组顺序**实测校验。

    返回违例描述列表，空列表表示假设成立。
    """
    order = {vg: i for i, vg in enumerate(VERSION_GROUP_ORDER)}
    bad = []
    for m in moves:
        seen = [order.get((pv.get("version_group") or {}).get("name", ""), -1)
                for pv in m.get("past_values") or []]
        known = [s for s in seen if s >= 0]
        if known != sorted(known):
            bad.append(f"{m['name']}: past_values 非升序 {seen}")
        # red-blue 自己不该出现在 past_values 里 —— 它是初代，没有"更早"
        if order.get(MOVE_VERSION_GROUP, 0) in known:
            bad.append(f"{m['name']}: past_values 含 {MOVE_VERSION_GROUP} 本身")
    return bad


def gen1_move_values(move: dict) -> tuple[dict, list[str]]:
    """把**现代**招式数值还原成初代原版。

    这是 convert_gen1.py 里 FAIRY_RETCON 的同类问题，但更隐蔽：
    物种属性的改动人尽皆知（妖精系），招式的改动却零散且无人记得。
    实测初代 165 招里有几十招被改过，典型的：

      · bite 咬住      —— 现在是恶系，初代是**一般系**（恶系二代才有）
      · gust 起风      —— 现在是飞行系，初代是**一般系**
      · dig 挖洞       —— 现在威力 80，初代是 **100**
      · self-destruct  —— 现在威力 200，初代是 **130**

    如果直接用现代值，游戏里「咬住」会打出恶系相性 —— 而恶系在本项目的
    15 属性表里根本不存在，属性编号会越界。

    还原规则：past_values 按世代升序，每条的含义是「到该版本组为止仍是旧值」。
    所以第一条（初代之后最早的改动）里的非 null 字段就是初代原值。
    数值不手填，全部从 past_values 取 —— 项目惯例。
    """
    vals = {
        "power": move.get("power"),
        "accuracy": move.get("accuracy"),
        "pp": move.get("pp"),
        "type": (move.get("type") or {}).get("name", ""),
    }
    changed: list[str] = []

    past = move.get("past_values") or []
    if not past:
        return vals, changed

    first = past[0]
    for field in PAST_VALUE_FIELDS:
        old = first.get(field)
        if old is not None and old != vals[field]:
            changed.append(f"{field} {vals[field]}→{old}")
            vals[field] = old
    old_type = (first.get("type") or {}).get("name")
    if old_type and old_type != vals["type"]:
        changed.append(f"type {vals['type']}→{old_type}")
        vals["type"] = old_type

    return vals, changed


def move_zh_name(move: dict) -> tuple[str, str]:
    """取中文名，简体优先、繁体兜底。

    返回 (名字, 来源)。来源要报出来 —— 繁简混排在 16×16 字库里
    是能看出来的（笔画密度不同），得知道有多少条走了兜底。
    """
    names = {(n.get("language") or {}).get("name"): n.get("name", "")
             for n in move.get("names") or []}
    for lang in ("zh-Hans", "zh-hans"):
        if names.get(lang):
            return names[lang], lang
    for lang in ("zh-Hant", "zh-hant"):
        if names.get(lang):
            return names[lang], lang
    return "", ""


def fetch_moves(cache: str, jobs: int) -> tuple[list[dict], dict]:
    """拉初代全部招式，只保留伤害招（power > 0）。

    变化招（吼叫/高速移动/电磁波等 power=null）全部丢弃 —— 见
    docs/_review-moves.md 的取舍说明：本项目的战斗不实现状态效果，
    存了也用不上，白占 flash。
    """
    gen = fetch_json(f"{API}/generation/1/", cache)
    if not gen:
        print("  ⚠️  拉不到 generation/1，跳过招式", file=sys.stderr)
        return [], {}

    listing = sorted(gen.get("moves") or [], key=lambda m: m["name"])
    print(f"  初代共 {len(listing)} 招，逐个拉详情...")

    def get(entry: dict) -> dict | None:
        return fetch_json(entry["url"], cache)

    raw: list[dict] = []
    with ThreadPoolExecutor(max_workers=jobs) as ex:
        for k, d in enumerate(ex.map(get, listing), 1):
            if d:
                raw.append(d)
            if k % 40 == 0:
                print(f"    ...{k}/{len(listing)}")

    order_violations = verify_past_values_order(raw)

    moves: list[dict] = []
    dropped_status: list[str] = []
    retconned: list[str] = []
    zh_fallback: list[str] = []
    zh_missing: list[str] = []
    bad_type: list[str] = []

    for d in sorted(raw, key=lambda m: m["id"]):
        vals, changed = gen1_move_values(d)

        # 只收伤害招。变化招在初代是 power=null。
        if not vals["power"]:
            dropped_status.append(d["name"])
            continue

        zh, src = move_zh_name(d)
        if not zh:
            zh_missing.append(d["name"])
        elif not src.lower().startswith("zh-hans"):
            zh_fallback.append(f"{d['name']}({zh})")

        if changed:
            retconned.append(f"{d['name']}: {', '.join(changed)}")
        if vals["type"] not in GEN1_TYPES:
            bad_type.append(f"{d['name']}: {vals['type']}")

        moves.append({
            "id": d["id"],
            "slug": d["name"],
            "zh": zh,
            "zh_source": src,
            "power": vals["power"],
            # 初代 swift 必中，PokeAPI 用 accuracy=null 表示 —— 存 0 会被
            # 误读成「永远打不中」，所以显式记 255 表示必中。
            "accuracy": vals["accuracy"] if vals["accuracy"] is not None else 255,
            "pp": vals["pp"] or 0,
            "type": vals["type"],
            "damage_class": (d.get("damage_class") or {}).get("name", ""),
        })

    return moves, {
        "total": len(listing),
        "fetched": len(raw),
        "damage": len(moves),
        "dropped_status": dropped_status,
        "retconned": retconned,
        "zh_fallback": zh_fallback,
        "zh_missing": zh_missing,
        "bad_type": bad_type,
        "order_violations": order_violations,
    }


def rb_learnset(mon: dict) -> list[tuple[int, str]]:
    """从物种详情里筛出红蓝的升级学习表。

    一只可能在同一版本组里用多种方式学同一招（升级 + 招式机器），
    所以必须同时筛 version_group 与 move_learn_method 两个条件。
    """
    out: list[tuple[int, str]] = []
    for entry in mon.get("moves") or []:
        name = (entry.get("move") or {}).get("name", "")
        for d in entry.get("version_group_details") or []:
            if ((d.get("version_group") or {}).get("name") != MOVE_VERSION_GROUP
                    or (d.get("move_learn_method") or {}).get("name")
                    != MOVE_LEARN_METHOD):
                continue
            out.append((d.get("level_learned_at", 0), name))
    # 按等级排序，同级按招式名 —— 固件要按「Lv≤N」顺序扫，必须有序
    return sorted(set(out))


def main() -> int:
    p = argparse.ArgumentParser(description="拉取初代 151 只的数据与 sprite")
    p.add_argument("--out", default="/tmp/gen1", help="输出目录")
    p.add_argument("--version", default="red-blue",
                   choices=["red-blue", "yellow"],
                   help="sprite 版本（yellow 的调色板偏黄）")
    p.add_argument("--jobs", type=int, default=4,
                   help="并发数。太高会触发 GitHub raw 限流（实测 8 并发有约 5%% 失败）")
    p.add_argument("--gray", dest="gray", action="store_true",
                   help="用 gray 变体（4 级灰阶，DMG 观感）")
    p.add_argument("--color", dest="gray", action="store_false", default=False,
                   help="用彩色 palette 变体（SGB/GBC 官方着色，默认）")
    p.add_argument("--count", type=int, default=GEN1_COUNT, help="拉前 N 只")
    p.add_argument("--no-moves", dest="moves", action="store_false", default=True,
                   help="跳过招式（招式约 165 个请求，已有缓存时很快）")
    args = p.parse_args()

    cache = os.path.join(args.out, "cache")
    front_dir = os.path.join(args.out, "front")
    back_dir = os.path.join(args.out, "back")
    for d in (cache, front_dir, back_dir):
        os.makedirs(d, exist_ok=True)

    n = args.count
    ids = list(range(1, n + 1))

    # ---- 1. 数据 ----
    print(f"拉取 {n} 只的数据（并发 {args.jobs}，有缓存）...")

    def get_one(i: int) -> tuple[int, dict | None, dict | None]:
        return (i,
                fetch_json(f"{API}/pokemon/{i}/", cache),
                fetch_json(f"{API}/pokemon-species/{i}/", cache))

    results: dict[int, tuple[dict | None, dict | None]] = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for k, (i, mon, sp) in enumerate(ex.map(get_one, ids), 1):
            results[i] = (mon, sp)
            if k % 25 == 0:
                print(f"  ...{k}/{n}")

    valid_slugs = {sp["name"] for mon, sp in results.values() if sp}

    # ---- 2. 进化链 ----
    print("\n拉取进化链...")
    chain_urls = {sp["evolution_chain"]["url"]
                  for mon, sp in results.values()
                  if sp and sp.get("evolution_chain")}
    evolutions: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for data in ex.map(lambda u: fetch_json(u, cache), sorted(chain_urls)):
            if data and data.get("chain"):
                evolutions.update(parse_evolution_chain(data["chain"], valid_slugs))
    print(f"  {len(chain_urls)} 条链，{len(evolutions)} 个进化关系")

    # ---- 3. sprite ----
    print(f"\n拉取 sprite（{args.version}）...")

    def get_sprite(i: int) -> tuple[bool, bool]:
        sub = "gray/" if args.gray else ""
        f = fetch_binary(f"{SPRITES}/{args.version}/{sub}{i}.png",
                         os.path.join(front_dir, f"{i:03d}.png"))
        b = fetch_binary(f"{SPRITES}/{args.version}/back/{sub}{i}.png",
                         os.path.join(back_dir, f"{i:03d}.png"))
        return f, b

    nf = nb = 0
    with ThreadPoolExecutor(max_workers=args.jobs) as ex:
        for k, (f, b) in enumerate(ex.map(get_sprite, ids), 1):
            nf += f
            nb += b
            if k % 25 == 0:
                print(f"  ...{k}/{n}")
    print(f"  front {nf}/{n}　back {nb}/{n}")

    # ---- 4. 招式 ----
    moves: list[dict] = []
    mstat: dict = {}
    if args.moves:
        print(f"\n拉取初代招式（版本组 {MOVE_VERSION_GROUP} / {MOVE_LEARN_METHOD}）...")
        load_version_group_order(cache)
        moves, mstat = fetch_moves(cache, args.jobs)

    # ---- 5. 汇总成一个 JSON ----
    mons = []
    missing_data = []
    learn_total = 0
    learn_empty = []
    for i in ids:
        mon, sp = results[i]
        if not mon or not sp:
            missing_data.append(i)
            continue

        slug = sp["name"]
        types = [t["type"]["name"] for t in
                 sorted(mon["types"], key=lambda t: t["slot"])]

        stats = {s["stat"]["name"]: s["base_stat"] for s in mon["stats"]}

        # 初代只有一个 Special，现代拆成了特攻/特防。
        # PokeAPI 把初代原值放在 past_stats[generation-i] 里 ——
        # 必须读它，而不是拿现代的 special_attack 当初代 Special。
        # 实测胡地：现代 SpA=135 / SpD=95，初代 Special=135（此例恰好等于 SpA，
        # 但并非所有宝可梦都如此，不能假设）。
        gen1_special = None
        for past in mon.get("past_stats") or []:
            if (past.get("generation") or {}).get("name") == "generation-i":
                for st in past.get("stats") or []:
                    if st["stat"]["name"] == "special":
                        gen1_special = st["base_stat"]
                        break
        if gen1_special is None:
            gen1_special = stats.get("special-attack", 0)

        evo = evolutions.get(slug, {})

        # 红蓝升级学习表。这里**保留全部**（含变化招），
        # 丢弃变化招的过滤留给 convert_moves.py ——
        # 因为「这只有几招被丢掉」是转换期才需要报的统计，
        # 而 json 作为中间产物应该保真，方便交叉验证时对原始 API。
        learn = rb_learnset(mon) if args.moves else []
        learn_total += len(learn)
        if args.moves and not learn:
            learn_empty.append(i)

        # 中文名在 species.names 里（zh-hans 简体 / zh-hant 繁体）。
        # 实测 151 只全都有，不需要另找数据源。
        zh = ""
        for nm in sp.get("names") or []:
            if (nm.get("language") or {}).get("name") == "zh-hans":
                zh = nm.get("name", "")
                break

        mons.append({
            "id": i,
            "slug": slug,
            "zh": zh,
            "types": types,
            "habitat": (sp.get("habitat") or {}).get("name", ""),
            "capture_rate": sp.get("capture_rate", 45),
            "height": mon.get("height", 0),      # 单位 dm
            "weight": mon.get("weight", 0),      # 单位 hg
            "is_legendary": sp.get("is_legendary", False),
            "is_mythical": sp.get("is_mythical", False),
            "stats": {
                "hp": stats.get("hp", 0),
                "attack": stats.get("attack", 0),
                "defense": stats.get("defense", 0),
                "special": gen1_special,      # 初代单一 Special
                "special_attack": stats.get("special-attack", 0),
                "special_defense": stats.get("special-defense", 0),
                "speed": stats.get("speed", 0),
            },
            "evolve_to": evo.get("to", ""),
            "evolve_trigger": evo.get("trigger", ""),
            "evolve_level": evo.get("level", 0),
            "evolve_item": evo.get("item", ""),
            # [[level, move_slug], ...] 已按等级排序
            "learnset": [[lv, nm] for lv, nm in learn],
        })

    out_json = os.path.join(args.out, "gen1.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(mons, f, ensure_ascii=False, indent=1)

    print(f"\n写入 {out_json}（{len(mons)} 只）")
    if missing_data:
        print(f"⚠️  {len(missing_data)} 只数据缺失: {missing_data}")

    if args.moves:
        moves_json = os.path.join(args.out, "moves.json")
        with open(moves_json, "w", encoding="utf-8") as f:
            json.dump(moves, f, ensure_ascii=False, indent=1)
        print(f"写入 {moves_json}（{len(moves)} 招伤害招）")

    # 分布统计 —— 便于核对 habitat 映射是否合理
    import collections
    hab: collections.Counter = collections.Counter(m["habitat"] or "(无)" for m in mons)
    ty: collections.Counter = collections.Counter(m["types"][0] for m in mons)
    trig: collections.Counter = collections.Counter(
        m["evolve_trigger"] for m in mons if m["evolve_trigger"])

    print("\nhabitat 分布")
    for h, c in hab.most_common():
        print(f"  {h:<16}{c:>4}")
    print("\n主属性分布")
    for t, c in ty.most_common():
        mark = "" if t in GEN1_TYPES else "  ⚠️ 非初代属性"
        print(f"  {t:<16}{c:>4}{mark}")
    print("\n进化触发方式")
    for t, c in trig.most_common():
        print(f"  {t:<16}{c:>4}")

    no_zh = [m["id"] for m in mons if not m["zh"]]
    print(f"\n中文名: {len(mons)-len(no_zh)}/{len(mons)}"
          + (f"　缺失 {no_zh}" if no_zh else " ✓"))
    print(f"\n有进化: {sum(1 for m in mons if m['evolve_to'])} 只")

    if args.moves and mstat:
        print(f"\n== 招式 ==")
        print(f"  初代 {mstat['total']} 招，拉到 {mstat['fetched']}，"
              f"伤害招 {mstat['damage']}，丢弃变化招 "
              f"{len(mstat['dropped_status'])}")

        # 顺序假设失效是**静默**的：还原出来的数值仍然合法，只是全错。
        # 所以必须显式报出来，不能只在断言里。
        if mstat["order_violations"]:
            print(f"  ❌ past_values 顺序假设不成立（{len(mstat['order_violations'])} 例）"
                  f"，初代还原值不可信：")
            for v in mstat["order_violations"][:5]:
                print(f"     {v}")

        if mstat["retconned"]:
            print(f"\n  已还原为初代原值（{len(mstat['retconned'])} 招）：")
            for r in mstat["retconned"]:
                print(f"     {r}")

        if mstat["bad_type"]:
            print(f"\n  ⚠️  还原后仍是非初代属性（{len(mstat['bad_type'])} 招）：")
            for b in mstat["bad_type"]:
                print(f"     {b}")

        print(f"\n  中文名：缺 {len(mstat['zh_missing'])}"
              f"　繁体兜底 {len(mstat['zh_fallback'])}")
        if mstat["zh_missing"]:
            print(f"     缺失：{mstat['zh_missing']}")
        if mstat["zh_fallback"]:
            print(f"     繁体：{mstat['zh_fallback']}")

        import collections as _c
        mt: _c.Counter = _c.Counter(m["type"] for m in moves)
        dc: _c.Counter = _c.Counter(m["damage_class"] for m in moves)
        print(f"\n  伤害招属性分布")
        for t, c in mt.most_common():
            mark = "" if t in GEN1_TYPES else "  ⚠️ 非初代属性"
            print(f"     {t:<12}{c:>4}{mark}")
        print(f"  物理/特殊 {dict(dc)}")

        print(f"\n  升级学习表：{learn_total} 条，"
              f"覆盖 {len(mons)-len(learn_empty)}/{len(mons)} 只")
        if learn_empty:
            print(f"     ⚠️  无学习表：{learn_empty}")

    print(f"\n下一步：")
    print(f"  python3 tools/pipeline/convert_gen1.py --src {args.out}")
    if args.moves:
        print(f"  python3 tools/pipeline/convert_moves.py --src {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
