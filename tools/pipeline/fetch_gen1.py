#!/usr/bin/env python3
"""拉取初代 151 只宝可梦的数据与 sprite。

用法：
    python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1
    python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1 --version yellow

数据来自 PokeAPI (pokeapi.co)，sprite 来自 PokeAPI/sprites 仓库。
带本地缓存 —— 重跑不会重复请求，也方便离线迭代。

关于 sprite 的两个关键事实（均为实测）：

**① 原版就是 4 色（depth=2）**，索引/灰度值 0~3 直接对应 2bpp 四阶灰，
不需要转灰度或量化。默认用 gray 变体（colortype=0，无 PLTE，真 4 级灰阶）；
不带 gray 的路径是 SGB/GBC 的 4 色**彩色**版。

**② front 尺寸不固定**：40×40 有 44 只、48×48 有 43 只、56×56 有 50 只
（RBY 按 5×5/6×6/7×7 tile 存）。back 统一 32×32。
转换时必须按各自原生尺寸处理，否则大型宝可梦会被压小。

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

    # ---- 4. 汇总成一个 JSON ----
    mons = []
    missing_data = []
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
        })

    out_json = os.path.join(args.out, "gen1.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(mons, f, ensure_ascii=False, indent=1)

    print(f"\n写入 {out_json}（{len(mons)} 只）")
    if missing_data:
        print(f"⚠️  {len(missing_data)} 只数据缺失: {missing_data}")

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

    print(f"\n下一步：")
    print(f"  python3 tools/pipeline/convert_gen1.py --src {args.out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
