#!/usr/bin/env python3
"""初代 151 只 → 固件用的紧凑二进制表 + 双视图 2bpp 精灵图。

用法：
    python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1
    python3 tools/pipeline/convert_gen1.py --src /tmp/gen1 --out assets/

产出：
    gen1.bin        151 条定长记录 + 名字字符串池
    gen1_front.bin  151 张正面（遭遇/图鉴用）
    gen1_back.bin   151 张背面（主宠待机用）

关于双视图：原版每只只有 front 和 back 两张，没有侧面或多角度。
这恰好匹配本项目 —— 遭遇看正面，主宠待机看背面（你在它身后），
图鉴翻页看正面。见 docs/05-art-audio.md。
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from convert_sprites import (  # noqa: E402
    box_downscale, quantize_2bpp, read_png, read_png_full, split_frames_by_gaps,
)
from convert_palettes import indices_to_2bpp, sorted_palette  # noqa: E402

# ---------------------------------------------------------------------------
# 初代 15 属性。没有 dark(恶)/steel(钢)/fairy(妖精) —— 那些是二代和六代加的。
# ---------------------------------------------------------------------------

GEN1_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic",
    "bug", "rock", "ghost", "dragon",
]
TYPE_ID = {t: i for i, t in enumerate(GEN1_TYPES)}
NO_TYPE = 0xFF

# PokeAPI 返回的是**现代**属性，需要还原成初代。
#
# 妖精系是第六代引入的，之后官方把一批初代宝可梦追认为妖精系。
# 要做初代情怀就得改回去 —— 实测受影响的正好这 5 只：
#   35 皮皮、36 皮可西、39 胖丁、40 胖可丁 → 初代是纯一般系
#   122 魔墙人偶 → 初代是纯超能系
FAIRY_RETCON = {
    35: ["normal"],
    36: ["normal"],
    39: ["normal"],
    40: ["normal"],
    122: ["psychic"],
}


def gen1_types(mon: dict) -> list[str]:
    """把现代属性还原成初代。"""
    if mon["id"] in FAIRY_RETCON:
        return FAIRY_RETCON[mon["id"]]
    return [t for t in mon["types"] if t in TYPE_ID]


# ---------------------------------------------------------------------------
# habitat → biome（docs/03-spawning.md#33）
#
# PokeAPI 的 habitat 只对初代有效，恰好 9 种，而且这套分类比 Tuxemon 的
# terrains 更贴合本项目 —— urban / cave / waters-edge 能直接对上射频环境特征，
# 不需要像 Tuxemon 那样硬掰（那次直译导致 wild 吃掉 88%、commercial 为 0）。
# ---------------------------------------------------------------------------

BIOMES = ["wild", "residential", "office", "commercial", "transit"]
BIOME_ID = {b: i for i, b in enumerate(BIOMES)}

HABITAT_TO_BIOME = {
    # 自然环境 —— AP 稀疏
    "grassland": ["wild"],
    "forest": ["wild"],
    "mountain": ["wild"],
    "sea": ["wild"],
    "rough-terrain": ["wild"],
    "waters-edge": ["wild", "residential"],   # 河湖岸多在城郊
    # 人造环境
    "urban": ["residential", "commercial"],   # 城市 = 住宅 + 商圈
    "cave": ["transit", "office"],            # 洞穴≈地下通道/地库，企业级 AP
    # 传说 —— 稀有，挂到 AP 最密处（企业级部署本身就是稀有刷新点）
    "rare": ["office", "commercial"],
}

# habitat 之外，再用**属性**细分一层。
#
# 只靠 habitat 会让 office/transit 存量过少（实测 13 和 8 只，全靠 cave 那 8 只撑），
# 而 urban 的 22 只其实天然分得开：超能系（凯西线、魔墙人偶）与电系
# （霹雳弹、多边兽）明显更像"机房 / 办公区"，喵喵、吉利蛋更像"住宅"。
#
# 这一层同时呼应 docs/03-spawning.md#32 的 OUI 语义：企业级 AP → 钢/超能，
# 运营商网关 → 电。属性与场所的对应关系在两处保持一致。
TYPE_BIOME_HINT = {
    "psychic": ["office"],        # 超能 ↔ 企业级部署
    "electric": ["office", "transit"],   # 电 ↔ 机房、地铁供电
    "steel": ["office"],          # 初代没有，留着以防将来扩展
    "ghost": ["transit"],         # 幽灵 ↔ 地下通道、夜间
    "poison": ["transit"],        # 毒 ↔ 下水道、地下
    "fighting": ["commercial"],   # 格斗 ↔ 道场、人流密集处
}

# 进化触发方式
TRIGGER_LEVEL = 0
TRIGGER_ITEM = 1
TRIGGER_TRADE = 2
TRIGGER_NONE = 0xFF

TRIGGER_ID = {
    "level-up": TRIGGER_LEVEL,
    "use-item": TRIGGER_ITEM,
    "trade": TRIGGER_TRADE,
}

# ---------------------------------------------------------------------------
# 记录结构：定长 28 字节，固件可 (base + id*28) 直接索引
#
#   off  size  field
#   0    2     name_offset      字符串池偏移
#   2    1     name_len
#   3    1     type_primary     初代 15 属性之一
#   4    1     type_secondary   0xFF = 无
#   5    1     biome_mask       5 个 biome 的位掩码
#   6    1     capture_rate     0~255，原版数值直接用
#   7    1     evolve_trigger   0=升级 1=道具 2=交换 0xFF=不进化
#   8    1     evolve_to        目标 id（1~151），0 = 不进化
#   9    1     evolve_level
#   10   1     hp               种族值，原版 0~255 直接用
#   11   1     attack
#   12   1     defense
#   13   1     special          初代只有一个「特殊」，不分特攻特防
#   14   1     speed
#   15   1     flags            bit0=传说 bit1=幻兽
#                                bit2-3=front 尺寸档（0:40 1:48 2:56）
#   16   2     height           dm
#   18   2     weight           hg
#   20   8     reserved         预留：招式表偏移、图鉴描述偏移等
# ---------------------------------------------------------------------------

RECORD_SIZE = 28
MAGIC = b"GEN1"
VERSION = 1

FLAG_LEGENDARY = 1 << 0
FLAG_MYTHICAL = 1 << 1
FLAG_SIZE_SHIFT = 2          # bit2-3 存 front 尺寸档

# front sprite 的三档原生尺寸。RBY 按 5×5 / 6×6 / 7×7 tile 存精灵，
# 实测分布：40×40 有 48 只、48×48 有 48 只、56×56 有 55 只。
# **必须按各自原生尺寸处理** —— 早期版本统一缩到 40×40，
# 等于把 56×56 的大型宝可梦压小了 30%，破坏了原版的体型对比。
FRONT_SIZES = [40, 48, 56]
BACK_SIZE = 32               # back 实测 151 只全部统一 32×32


def biome_mask(habitat: str, types: list[str] | None = None) -> int:
    """habitat 定基调，属性再补一层 —— 见 TYPE_BIOME_HINT 的说明。"""
    mask = 0
    for b in HABITAT_TO_BIOME.get(habitat, []):
        mask |= 1 << BIOME_ID[b]

    # 属性提示只在"人造环境"里生效。野生栖息地的怪不该因为是超能系
    # 就跑到写字楼里去 —— 那会让 wild 和 office 的界限消失。
    if types and habitat in ("urban", "cave", "rare"):
        for t in types:
            for b in TYPE_BIOME_HINT.get(t, []):
                mask |= 1 << BIOME_ID[b]

    return mask or (1 << BIOME_ID["wild"])


def build_data(mons: list[dict],
               tier_of: dict[int, int] | None = None) -> tuple[bytes, dict]:
    mons = sorted(mons, key=lambda m: m["id"])
    slug_to_id = {m["slug"]: m["id"] for m in mons}

    pool = bytearray()
    offsets: dict[str, tuple[int, int]] = {}
    for m in mons:
        b = m["slug"].encode("utf-8")
        offsets[m["slug"]] = (len(pool), len(b))
        pool += b

    retconned = []
    records = bytearray()
    for m in mons:
        off, ln = offsets[m["slug"]]
        types = gen1_types(m)
        if m["id"] in FAIRY_RETCON:
            retconned.append(m["slug"])

        t1 = TYPE_ID.get(types[0], 0) if types else 0
        t2 = TYPE_ID.get(types[1], NO_TYPE) if len(types) > 1 else NO_TYPE

        evo_to = slug_to_id.get(m["evolve_to"], 0) if m["evolve_to"] else 0
        trig = TRIGGER_ID.get(m["evolve_trigger"], TRIGGER_NONE) if evo_to else TRIGGER_NONE

        st = m["stats"]
        # 初代只有一个 Special。fetch_gen1.py 已从 past_stats[generation-i]
        # 取到原值存在 st["special"] —— 不要用现代的 special_attack 替代，
        # 二者并非总是相等。
        special = st.get("special", st["special_attack"])

        flags = 0
        if m.get("is_legendary"):
            flags |= FLAG_LEGENDARY
        if m.get("is_mythical"):
            flags |= FLAG_MYTHICAL
        if tier_of:
            flags |= (tier_of.get(m["id"], 0) & 0x3) << FLAG_SIZE_SHIFT

        records += struct.pack(
            "<HBBBBBBBBBBBBBBHH8s",
            off, min(ln, 255),
            t1, t2,
            biome_mask(m.get("habitat", ""), types),
            min(m.get("capture_rate", 45), 255),
            trig,
            min(evo_to, 255),
            min(m.get("evolve_level") or 0, 255),
            min(st["hp"], 255), min(st["attack"], 255), min(st["defense"], 255),
            min(special, 255), min(st["speed"], 255),
            flags,
            min(m.get("height", 0), 65535), min(m.get("weight", 0), 65535),
            b"\x00" * 8,
        )

    assert len(records) == len(mons) * RECORD_SIZE, \
        f"记录长度 {len(records)} != {len(mons)}×{RECORD_SIZE}"

    header = struct.pack("<4sHHII", MAGIC, VERSION, RECORD_SIZE, len(mons), len(pool))
    return header + bytes(records) + bytes(pool), {
        "count": len(mons),
        "records": len(records),
        "pool": len(pool),
        "total": len(header) + len(records) + len(pool),
        "retconned": retconned,
    }


def png_native_size(path: str) -> tuple[int, int]:
    """只读 IHDR 拿尺寸，不解整张图。"""
    with open(path, "rb") as f:
        head = f.read(26)
    w, h = struct.unpack(">II", head[16:24])
    return w, h


def to_2bpp_native(path: str) -> tuple[bytearray, int]:
    """读 PNG，按**原生尺寸**直接转 2bpp，不缩放。

    两条路径都零有损：

    **彩色**（colortype=3，depth=2）：原始索引按亮度重排后直接打包。
    索引顺序必须重排 —— PNG 里的顺序是任意的，实测每只都不同
    （皮卡丘 [1,2,3,0]、超梦 [3,0,1,2]），不重排明暗会反。

    **灰阶**（colortype=0，depth=2）：灰度值 0~3 已经是 2bpp，
    read_png 把它们映射到 0/85/170/255，quantize_2bpp 的阈值
    (60,120,190) 能准确还原。
    """
    w, h, rows, pal, indices = read_png_full(path)

    if pal and indices:
        # 彩色索引图 —— 重排后直接打包，不经过灰度
        _new_pal, remap = sorted_palette(pal)
        return indices_to_2bpp(indices, remap), w

    gray = [[px[0] for px in row] for row in rows]
    return quantize_2bpp(gray), w


def build_front_atlas(src_dir: str, ids: list[int]) -> tuple[bytes, dict[int, int], list[str]]:
    """front 图集：按尺寸分三段存放，各段内定长。

    返回 (二进制, {id: 尺寸档}, 失败列表)。

    为什么分段而不是统一 pad 到 56×56：pad 会浪费约 28KB，
    而分段只需在记录里存 2 bit 档位。固件按档位算段内偏移即可，
    依然是 O(1) 寻址。
    """
    buckets: dict[int, list[tuple[int, bytearray]]] = {s: [] for s in FRONT_SIZES}
    tier_of: dict[int, int] = {}
    failed: list[str] = []

    for i in ids:
        path = os.path.join(src_dir, f"{i:03d}.png")
        try:
            w, h = png_native_size(path)
            if w != h or w not in FRONT_SIZES:
                raise ValueError(f"意外尺寸 {w}×{h}")
            blob, _ = to_2bpp_native(path)
            expect = (w * w * 2 + 7) // 8
            if len(blob) != expect:
                raise ValueError(f"长度 {len(blob)} != {expect}")
            buckets[w].append((i, blob))
            tier_of[i] = FRONT_SIZES.index(w)
        except Exception as e:
            failed.append(f"{i:03d}: {type(e).__name__} {e}")

    # 段头：每段记录 尺寸 / 单张字节 / 数量，随后是 (id, 位图) 序列。
    # id 显式存下来，因为分段后 id 不再等于段内下标。
    out = bytearray()
    out += struct.pack("<4sHH", b"FRNT", VERSION, len(FRONT_SIZES))
    seg_meta = bytearray()
    seg_data = bytearray()
    for size in FRONT_SIZES:
        items = sorted(buckets[size])
        per = (size * size * 2 + 7) // 8
        seg_meta += struct.pack("<HHII", size, per, len(items), len(seg_data))
        for i, blob in items:
            seg_data += struct.pack("<H", i) + bytes(blob)
    out += seg_meta + seg_data
    return bytes(out), tier_of, failed


def build_back_atlas(src_dir: str, ids: list[int]) -> tuple[bytes, int, list[str]]:
    """back 图集：151 只全部 32×32，定长，可直接按 id 索引。"""
    per = (BACK_SIZE * BACK_SIZE * 2 + 7) // 8
    blobs: list[bytearray] = []
    failed: list[str] = []

    for i in ids:
        path = os.path.join(src_dir, f"{i:03d}.png")
        try:
            w, h = png_native_size(path)
            if (w, h) != (BACK_SIZE, BACK_SIZE):
                raise ValueError(f"意外尺寸 {w}×{h}（预期 {BACK_SIZE}²）")
            blob, _ = to_2bpp_native(path)
            if len(blob) != per:
                raise ValueError(f"长度 {len(blob)} != {per}")
            blobs.append(blob)
        except Exception as e:
            failed.append(f"{i:03d}: {type(e).__name__} {e}")
            blobs.append(bytearray(per))     # 占位保持 id 对齐

    header = struct.pack("<4sHHHHI", b"BACK", VERSION,
                         BACK_SIZE, BACK_SIZE, per, len(blobs))
    return header + b"".join(bytes(b) for b in blobs), per, failed


def preview_raw(bmp: bytes, size: int, label: str) -> None:
    """把单张 2bpp 位图以 ASCII 画出来，用于目检。

    转换器必须能目检 —— 统计数字（"151 张成功"）完全看不出图是错的。
    """
    shades = " .oO"
    row_bytes = (size * 2 + 7) // 8
    print(f"\n{label}")
    for y in range(size):
        line = ""
        for x in range(size):
            byte = bmp[y * row_bytes + (x * 2) // 8]
            shift = 6 - ((x * 2) % 8)
            line += shades[3 - ((byte >> shift) & 3)]
        print("  " + line)


def main() -> int:
    p = argparse.ArgumentParser(description="初代 151 只 → 固件二进制")
    p.add_argument("--src", default="/tmp/gen1", help="fetch_gen1.py 的输出目录")
    p.add_argument("--out", default="assets", help="输出目录")
    p.add_argument("--front-size", type=int, default=40,
                   help="正面尺寸（原版 40×40）")
    p.add_argument("--back-size", type=int, default=32,
                   help="背面尺寸（原版 32×32）")
    p.add_argument("--preview", type=int, default=-1,
                   help="以 ASCII 预览第 N 号（1~151）的 front 与 back")
    args = p.parse_args()

    json_path = os.path.join(args.src, "gen1.json")
    if not os.path.exists(json_path):
        print(f"错误：找不到 {json_path}。先跑 fetch_gen1.py", file=sys.stderr)
        return 1

    with open(json_path, encoding="utf-8") as f:
        mons = json.load(f)

    print(f"读取 {len(mons)} 只")
    os.makedirs(args.out, exist_ok=True)

    # ---- 数据 ----
    blob, st = build_data(mons)
    data_path = os.path.join(args.out, "gen1.bin")
    with open(data_path, "wb") as f:
        f.write(blob)

    print(f"\n{data_path}")
    print(f"  记录      {st['records']:>7} B  ({st['count']} × {RECORD_SIZE})")
    print(f"  字符串池  {st['pool']:>7} B")
    print(f"  合计      {st['total']:>7} B = {st['total']/1024:.1f} KB")
    if st["retconned"]:
        print(f"\n  属性已还原为初代（妖精系是六代才加的）：")
        print(f"    {', '.join(st['retconned'])}")

    # ---- 精灵图（原生尺寸，不缩放）----
    ids = [m["id"] for m in sorted(mons, key=lambda m: m["id"])]

    front_src = os.path.join(args.src, "front")
    back_src = os.path.join(args.src, "back")

    tier_of: dict[int, int] = {}
    total_sprite = 0

    if os.path.isdir(front_src):
        fblob, tier_of, ffail = build_front_atlas(front_src, ids)
        fpath = os.path.join(args.out, "gen1_front.bin")
        with open(fpath, "wb") as f:
            f.write(fblob)
        total_sprite += len(fblob)

        import collections
        tiers: collections.Counter = collections.Counter(
            FRONT_SIZES[t] for t in tier_of.values())
        print(f"\n{fpath}")
        for size in FRONT_SIZES:
            n = tiers.get(size, 0)
            per = (size * size * 2 + 7) // 8
            print(f"  {size}×{size}  {n:>4} 只  单张 {per:>4} B  段计 {n*per/1024:>6.1f} KB")
        print(f"  合计 {len(fblob)/1024:.1f} KB")
        if ffail:
            print(f"  ⚠️  {len(ffail)} 张失败：{ffail[:3]}")
    else:
        print(f"\n⚠️  跳过 front：{front_src} 不存在")

    if os.path.isdir(back_src):
        bblob, bper, bfail = build_back_atlas(back_src, ids)
        bpath = os.path.join(args.out, "gen1_back.bin")
        with open(bpath, "wb") as f:
            f.write(bblob)
        total_sprite += len(bblob)
        print(f"\n{bpath}")
        print(f"  {len(ids)} 张 @ {BACK_SIZE}×{BACK_SIZE}  单张 {bper} B")
        print(f"  合计 {len(bblob)/1024:.1f} KB")
        if bfail:
            print(f"  ⚠️  {len(bfail)} 张失败：{bfail[:3]}")
    else:
        print(f"\n⚠️  跳过 back：{back_src} 不存在")

    # 数据表要带上 sprite 尺寸档，所以放在 sprite 之后重建
    blob, st = build_data(mons, tier_of)
    with open(data_path, "wb") as f:
        f.write(blob)

    if 1 <= args.preview <= len(ids):
        m = next(x for x in mons if x["id"] == args.preview)
        fp = os.path.join(front_src, f"{args.preview:03d}.png")
        bp = os.path.join(back_src, f"{args.preview:03d}.png")
        for path, label in ((fp, "front"), (bp, "back")):
            if os.path.exists(path):
                w, _ = png_native_size(path)
                bmp, _ = to_2bpp_native(path)
                preview_raw(bmp, w, f"#{args.preview} {m['slug']} ({label} {w}×{w})")

    print(f"\n总计 {(st['total'] + total_sprite)/1024:.1f} KB"
          f"　占 8MB flash 的 {(st['total']+total_sprite)/(8*1024*1024)*100:.2f}%")

    # 分布核对
    import collections
    bd: collections.Counter = collections.Counter()
    for m in mons:
        bm = biome_mask(m.get("habitat", ""), gen1_types(m))
        for i, b in enumerate(BIOMES):
            if bm & (1 << i):
                bd[b] += 1
    print("\nbiome 分布（一只可属多个）")
    for b, n in bd.most_common():
        print(f"  {b:<14}{n:>5}")

    td: collections.Counter = collections.Counter()
    for m in mons:
        t = gen1_types(m)
        if t:
            td[t[0]] += 1
    print("\n初代主属性分布")
    for t, n in td.most_common():
        bad = "" if t in TYPE_ID else "  ⚠️"
        print(f"  {t:<14}{n:>5}{bad}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
