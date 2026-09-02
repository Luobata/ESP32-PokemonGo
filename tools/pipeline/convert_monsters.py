#!/usr/bin/env python3
"""把 Tuxemon 的怪物 YAML 转成固件可直接 mmap 的紧凑二进制表。

用法：
    # 先拉数据（稀疏克隆，只要 db 和精灵图，约 20MB）
    tools/pipeline/fetch-tuxemon.sh

    # 转换
    python3 tools/pipeline/convert_monsters.py \
        --src /tmp/tuxemon/mods/tuxemon/db/monster \
        --out assets/monsters.bin

设计取向：定长记录 + 独立字符串池。定长让固件能 O(1) 按 id 索引、
无需解析、无需动态分配 —— 直接把 flash 地址当数组用。

零第三方依赖（自己解析用到的 YAML 子集，不引 PyYAML）。
"""

from __future__ import annotations

import argparse
import os
import re
import struct
import sys
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Tuxemon 的 13 属性系统
#
# 注意：这不是宝可梦的 18 属性，是 Tuxemon 自研的一套（wood/cosmic/metal…）。
# 对本项目是好事 —— 自研属性名天然规避了 IP 问题（docs/05-art-audio.md#54）。
# ---------------------------------------------------------------------------

TYPES = [
    "normal", "fire", "water", "wood", "earth", "metal",
    "lightning", "frost", "venom", "shadow", "cosmic", "sky", "heroic",
]
TYPE_ID = {t: i for i, t in enumerate(TYPES)}

# Tuxemon 的 terrains → 本项目的 biome（docs/03-spawning.md#33）
#
# 这个映射是素材管线里最有价值的一块：Tuxemon 已经为每只怪标注了栖息地形，
# 正好能挂到我们用 WiFi 聚合统计判定的 biome 上，省掉手工分配 411 只怪的工作。
BIOMES = ["wild", "residential", "office", "commercial", "transit"]
BIOME_ID = {b: i for i, b in enumerate(BIOMES)}

TERRAIN_TO_BIOME = {
    # 开阔自然 —— 纯野外，AP 稀疏
    "grassland": ["wild"],
    "desert": ["wild"],
    "boreal_snow": ["wild"],
    "mountains": ["wild"],
    "sea": ["wild"],
    "jungle": ["wild"],
    "swamp": ["wild"],
    "coastal": ["wild", "commercial"],       # 海岸线常有商业带
    "freshwater": ["wild", "residential"],   # 河湖多在城郊
    "woodland": ["wild", "residential"],     # 绿化好的居住区
    # 人造 / 地下
    "urban": ["residential", "commercial"],
    "ruins": ["office", "transit"],          # 废墟≈老楼，射频上是企业级部署
    "underground": ["transit", "office"],    # 地下≈地铁通道
    # 异界系 —— 稀有，挂到 AP 密集处
    "extraplanar": ["office", "commercial"],
    "extraterrestrial": ["office"],
    "other": ["wild"],
    "any": ["wild", "residential", "office", "commercial", "transit"],
}

STAGES = ["basic", "stage1", "stage2", "standalone"]
STAGE_ID = {s: i for i, s in enumerate(STAGES)}

SHAPES = [
    "blob", "humanoid", "flier", "serpent", "sprite", "hunter", "brute",
    "varmint", "dragon", "polliwog", "grub", "landrace", "piscine", "leviathan",
]
SHAPE_ID = {s: i for i, s in enumerate(SHAPES)}


# ---------------------------------------------------------------------------
# 极简 YAML 解析
#
# 只处理 Tuxemon monster 文件用到的子集：顶层 `key: value`、
# 顶层 `key:` 后跟 `- item` 列表。不处理嵌套字典列表（moveset/history），
# 那些字段我们不需要 —— 招式表要按自己的战斗系统重做。
# 引 PyYAML 只为这点用量不值得，且会给固件侧的对照实现添一层无谓依赖。
# ---------------------------------------------------------------------------

def parse_yaml_subset(text: str) -> dict:
    out: dict = {}
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line or line.startswith(" ") or line.startswith("#"):
            i += 1
            continue

        m = re.match(r"^([a-z_]+):\s*(.*)$", line)
        if not m:
            i += 1
            continue

        key, val = m.group(1), m.group(2).strip()

        if val:
            out[key] = val
            i += 1
            continue

        # 空值 → 看下一行是不是简单列表（`- word`，非 `- key: value`）
        items: list[str] = []
        j = i + 1
        while j < len(lines):
            im = re.match(r"^- ([A-Za-z_][A-Za-z0-9_]*)\s*$", lines[j])
            if not im:
                break
            items.append(im.group(1))
            j += 1

        if items:
            out[key] = items
            i = j
        else:
            i += 1
    return out


# ---------------------------------------------------------------------------
# 记录结构
#
# 定长 24 字节 —— 让固件能直接 (base + id*24) 索引。
#
#   off  size  field
#   0    2     name_offset      字符串池偏移（slug）
#   2    1     name_len
#   3    1     type_primary     TYPE_ID
#   4    1     type_secondary   0xFF = 无
#   5    1     stage            STAGE_ID
#   6    1     shape            SHAPE_ID
#   7    1     biome_mask       BIOMES 的位掩码
#   8    2     evolve_to        目标 id，0xFFFF = 不进化
#   10   1     evolve_level
#   11   1     catch_rate       0~255（原始是 float，×255/100 量化）
#   12   2     height           cm
#   14   2     weight           kg
#   16   2     sprite_index     精灵图序号
#   18   2     txmn_id          原始编号，便于回溯查证
#   20   4     reserved         预留：种族值、稀有度权重等
# ---------------------------------------------------------------------------

RECORD_SIZE = 24
MAGIC = b"TXMN"
VERSION = 1
NO_EVOLVE = 0xFFFF
NO_TYPE = 0xFF


@dataclass
class Monster:
    slug: str
    types: list[str] = field(default_factory=list)
    terrains: list[str] = field(default_factory=list)
    stage: str = "standalone"
    shape: str = "blob"
    evolve_to: str = ""
    evolve_level: int = 0
    catch_rate: float = 100.0
    height: int = 0
    weight: int = 0
    txmn_id: int = 0

    @property
    def biome_mask(self) -> int:
        mask = 0
        for t in self.terrains:
            for b in TERRAIN_TO_BIOME.get(t, []):
                mask |= 1 << BIOME_ID[b]
        return mask or (1 << BIOME_ID["wild"])   # 没标地形的兜底给野外


def load_monster(path: str) -> Monster | None:
    try:
        d = parse_yaml_subset(open(path, encoding="utf-8").read())
    except OSError as e:
        print(f"警告：读取失败 {path}: {e}", file=sys.stderr)
        return None

    slug = d.get("slug", "")
    if not slug or not isinstance(slug, str):
        return None

    # evolutions 是嵌套结构，简易解析器拿不到，单独用正则抓第一条
    raw = open(path, encoding="utf-8").read()
    evo_to, evo_lv = "", 0
    m = re.search(r"^evolutions:\n- at_level: (\d+)\n  monster_slug: (\w+)", raw, re.M)
    if m:
        evo_lv, evo_to = int(m.group(1)), m.group(2)
    else:
        # 有些条目字段顺序相反
        m = re.search(r"^evolutions:\n(?:.*\n)*?\s*monster_slug: (\w+)", raw, re.M)
        if m:
            evo_to = m.group(1)
            lv = re.search(r"at_level: (\d+)", raw)
            evo_lv = int(lv.group(1)) if lv else 0

    def as_int(key: str) -> int:
        v = d.get(key, "0")
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return 0

    types = d.get("types", [])
    if isinstance(types, str):
        types = [types]

    terrains = d.get("terrains", [])
    if isinstance(terrains, str):
        terrains = [terrains]

    try:
        catch = float(d.get("catch_rate", "100"))
    except (TypeError, ValueError):
        catch = 100.0

    return Monster(
        slug=slug,
        types=[t for t in types if t in TYPE_ID],
        terrains=terrains,
        stage=d.get("stage", "standalone") if isinstance(d.get("stage"), str) else "standalone",
        shape=d.get("shape", "blob") if isinstance(d.get("shape"), str) else "blob",
        evolve_to=evo_to,
        evolve_level=evo_lv,
        catch_rate=catch,
        height=as_int("height"),
        weight=as_int("weight"),
        txmn_id=as_int("txmn_id"),
    )


def build(monsters: list[Monster]) -> tuple[bytes, dict]:
    """产出 (二进制, 统计信息)。"""
    monsters.sort(key=lambda m: m.slug)
    slug_to_id = {m.slug: i for i, m in enumerate(monsters)}

    # 字符串池
    pool = bytearray()
    offsets: dict[str, tuple[int, int]] = {}
    for m in monsters:
        b = m.slug.encode("utf-8")
        offsets[m.slug] = (len(pool), len(b))
        pool += b

    records = bytearray()
    dangling = 0
    for i, m in enumerate(monsters):
        off, ln = offsets[m.slug]

        t1 = TYPE_ID.get(m.types[0], 0) if m.types else 0
        t2 = TYPE_ID.get(m.types[1], NO_TYPE) if len(m.types) > 1 else NO_TYPE

        if m.evolve_to:
            evo = slug_to_id.get(m.evolve_to, NO_EVOLVE)
            if evo == NO_EVOLVE:
                dangling += 1     # 进化目标不在数据集里
        else:
            evo = NO_EVOLVE

        records += struct.pack(
            "<HBBBBBBHBBHHHHI",
            off, min(ln, 255),
            t1, t2,
            STAGE_ID.get(m.stage, 3),
            SHAPE_ID.get(m.shape, 0),
            m.biome_mask,
            evo, min(m.evolve_level, 255),
            max(0, min(255, round(m.catch_rate * 255 / 100))),
            min(m.height, 65535), min(m.weight, 65535),
            i,                     # sprite_index 与记录序号一致
            min(m.txmn_id, 65535),
            0,                     # reserved
        )

    assert len(records) == len(monsters) * RECORD_SIZE, "记录长度与 RECORD_SIZE 不一致"

    header = struct.pack("<4sHHII", MAGIC, VERSION, RECORD_SIZE,
                         len(monsters), len(pool))
    blob = header + bytes(records) + bytes(pool)

    return blob, {
        "count": len(monsters),
        "header": len(header),
        "records": len(records),
        "pool": len(pool),
        "total": len(blob),
        "dangling_evolutions": dangling,
    }


def main() -> int:
    p = argparse.ArgumentParser(description="Tuxemon YAML → 紧凑二进制表")
    p.add_argument("--src", required=True, help="mods/tuxemon/db/monster 目录")
    p.add_argument("--out", default="assets/monsters.bin")
    p.add_argument("--index", help="同时输出人类可读的索引 txt（便于查证）")
    args = p.parse_args()

    if not os.path.isdir(args.src):
        print(f"错误：{args.src} 不是目录。先跑 fetch-tuxemon.sh", file=sys.stderr)
        return 1

    files = sorted(f for f in os.listdir(args.src) if f.endswith(".yaml"))
    if not files:
        print(f"错误：{args.src} 里没有 .yaml", file=sys.stderr)
        return 1

    monsters = []
    for f in files:
        m = load_monster(os.path.join(args.src, f))
        if m:
            monsters.append(m)

    print(f"解析 {len(monsters)} / {len(files)} 个条目")

    blob, st = build(monsters)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as fh:
        fh.write(blob)

    print(f"\n写入 {args.out}")
    print(f"  头部      {st['header']:>7} B")
    print(f"  记录      {st['records']:>7} B  ({st['count']} × {RECORD_SIZE})")
    print(f"  字符串池  {st['pool']:>7} B")
    print(f"  合计      {st['total']:>7} B  = {st['total']/1024:.1f} KB")
    if st["dangling_evolutions"]:
        print(f"\n  注：{st['dangling_evolutions']} 条进化指向数据集外的怪，已记为不进化")

    # biome 分布 —— 验证映射是否合理
    import collections
    dist: collections.Counter = collections.Counter()
    for m in monsters:
        for i, b in enumerate(BIOMES):
            if m.biome_mask & (1 << i):
                dist[b] += 1
    print("\nbiome 分布（一只怪可属多个）")
    for b, n in dist.most_common():
        print(f"  {b:<14}{n:>5}")

    tdist: collections.Counter = collections.Counter()
    for m in monsters:
        if m.types:
            tdist[m.types[0]] += 1
    print("\n主属性分布")
    for t, n in tdist.most_common():
        print(f"  {t:<14}{n:>5}")

    if args.index:
        with open(args.index, "w", encoding="utf-8") as fh:
            fh.write(f"{'id':>4}  {'slug':<20}{'type':<12}{'stage':<12}{'biome'}\n")
            for i, m in enumerate(monsters):
                bs = ",".join(b for j, b in enumerate(BIOMES)
                              if m.biome_mask & (1 << j))
                ty = "/".join(m.types) or "-"
                fh.write(f"{i:>4}  {m.slug:<20}{ty:<12}{m.stage:<12}{bs}\n")
        print(f"\n索引 → {args.index}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
