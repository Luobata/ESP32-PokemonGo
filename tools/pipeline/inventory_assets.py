#!/usr/bin/env python3
"""实测清点 assets/ 里每个二进制文件的真实内容。

用法：
    python3 tools/pipeline/inventory_assets.py
    python3 tools/pipeline/inventory_assets.py --json      # 机器可读

这个脚本**只读**，不改任何素材。它存在的理由是：
文档里写的格式与产物的真实内容会漂移，而漂移只有实际解析才发现。

所以这里不复用 tools/inspector/build.py 的 loader —— 那些 loader 已经
假定了格式正确（magic 不对就抛异常）。清点需要的是**独立重解**：
按 convert_*.py 写死的头部布局硬解，然后拿解出来的数字与文档对账。

同理，各段的格式常量在本文件里**独立写死**而不是 import
convert_*.py —— import 过去只能验证「自己和自己一致」，
写死才能在两边漂移时报出来。

零第三方依赖。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import struct
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(REPO, "assets")

# 与 convert_gen1.py 一致
FRONT_SIZES = [40, 48, 56]
BACK_SIZE = 32
GEN1_TYPES_CN = ["一般", "火", "水", "电", "草", "冰", "格斗", "毒",
                 "地面", "飞行", "超能", "虫", "岩石", "幽灵", "龙"]
BIOMES_CN = ["野外", "住宅区", "办公区", "商业区", "交通枢纽"]


def blank_ratio(blob: bytes) -> float:
    """全零字节占比 —— 用来识别空洞条目。

    2bpp 里 0x00 表示「4 个像素都是 0 号色」，而 0 号色按
    convert_palettes.sorted_palette 的约定是**最暗**（描边色）。
    所以整张全 0x00 = 纯黑，这在真实 sprite 里不可能出现，
    是「转换失败后 bytearray(per) 占位」的特征。
    """
    return sum(1 for b in blob if b == 0) / len(blob) if blob else 1.0


# ---------------------------------------------------------------------------
# gen1.bin —— 定长记录 + 字符串池
# ---------------------------------------------------------------------------

def parse_gen1(path: str) -> dict:
    d = open(path, "rb").read()
    magic, ver, rsz, cnt, poolsz = struct.unpack("<4sHHII", d[:16])
    recs = d[16:16 + cnt * rsz]
    pool = d[16 + cnt * rsz:]

    mons = []
    for i in range(cnt):
        o = i * rsz
        (off, ln, t1, t2, bm, cr, tg, ev, el,
         hp, at, df, sp, spd, fl, h, w, zo, zl, pi, rv) = struct.unpack(
            "<HBBBBBBBBBBBBBBHHHBB8s", recs[o:o + rsz])
        mons.append({
            "id": i + 1,
            "slug": pool[off:off + ln].decode("utf-8", "replace"),
            "zh": pool[zo:zo + zl].decode("utf-8", "replace") if zl else "",
            "t1": t1, "t2": t2, "biome_mask": bm, "catch": cr,
            "trigger": tg, "evolve_to": ev, "evolve_level": el,
            "stats": [hp, at, df, sp, spd],
            "flags": fl, "legend": bool(fl & 1), "myth": bool(fl & 2),
            "fsize_tier": (fl >> 2) & 3,
            "height_dm": h, "weight_hg": w,
            "pal": pi & 0x0F, "pal_hi": (pi >> 4) & 0x0F,
            "reserved_nonzero": rv != b"\x00" * 8,
        })

    # 头部声明的 pool 大小与实际尾部长度是否一致
    return {
        "file": os.path.basename(path), "bytes": len(d),
        "magic": magic.decode("ascii", "replace"), "version": ver,
        "record_size": rsz, "count": cnt,
        "pool_declared": poolsz, "pool_actual": len(pool),
        "header_bytes": 16, "record_bytes": len(recs),
        "mons": mons,
    }


def audit_gen1(g: dict) -> dict:
    mons = g["mons"]
    zh_missing = [m["id"] for m in mons if not m["zh"]]
    slug_missing = [m["id"] for m in mons if not m["slug"]]
    zh_chars: set = set()
    for m in mons:
        zh_chars |= set(m["zh"])
    dup_slug = [s for s, n in collections.Counter(
        m["slug"] for m in mons).items() if n > 1]
    # 种族值全 0 = 记录没填
    zero_stats = [m["id"] for m in mons if sum(m["stats"]) == 0]
    bad_t1 = [m["id"] for m in mons if m["t1"] >= len(GEN1_TYPES_CN)]
    bad_t2 = [m["id"] for m in mons
              if m["t2"] != 0xFF and m["t2"] >= len(GEN1_TYPES_CN)]
    no_biome = [m["id"] for m in mons if m["biome_mask"] == 0]
    biome_dist = collections.Counter()
    for m in mons:
        for j, b in enumerate(BIOMES_CN):
            if m["biome_mask"] >> j & 1:
                biome_dist[b] += 1
    tier_dist = collections.Counter(FRONT_SIZES[m["fsize_tier"]] for m in mons)
    return {
        "zh_missing": zh_missing, "slug_missing": slug_missing,
        "zh_char_count": len(zh_chars), "zh_chars": "".join(sorted(zh_chars)),
        "dup_slug": dup_slug, "zero_stats": zero_stats,
        "bad_type_primary": bad_t1, "bad_type_secondary": bad_t2,
        "no_biome": no_biome, "biome_dist": dict(biome_dist),
        "front_tier_dist": dict(tier_dist),
        "legendary": [m["id"] for m in mons if m["legend"]],
        "mythical": [m["id"] for m in mons if m["myth"]],
        "palettes_used": sorted({m["pal"] for m in mons}),
        "pal_hi_nonzero": [m["id"] for m in mons if m["pal_hi"]],
        "reserved_dirty": [m["id"] for m in mons if m["reserved_nonzero"]],
        "evolving": sum(1 for m in mons if m["evolve_to"]),
    }


# ---------------------------------------------------------------------------
# moves.bin —— 四段：招式表 / 物种索引 / 学习表 / 字符串池
# ---------------------------------------------------------------------------

# 与 convert_moves.py 一致。这里**独立写死**而不是 import ——
# 清点的价值就在于用另一套代码重解，import 过去等于只验证了自己和自己一致。
MOVE_HEADER_FMT = "<4sHHHHHH"
MOVE_REC_FMT = "<HHBBBBBB2s"
MOVE_SPECIES_FMT = "<HBB"
MOVE_LEARN_FMT = "<BB"
DAMAGE_CLASS_CN = {0: "物理", 1: "特殊"}
ACC_ALWAYS_HIT = 255


def parse_moves(path: str) -> dict:
    d = open(path, "rb").read()
    hsz = struct.calcsize(MOVE_HEADER_FMT)
    magic, ver, rsz, mcnt, scnt, lcnt, poolsz = struct.unpack(
        MOVE_HEADER_FMT, d[:hsz])

    msz = struct.calcsize(MOVE_REC_FMT)
    ssz = struct.calcsize(MOVE_SPECIES_FMT)
    lsz = struct.calcsize(MOVE_LEARN_FMT)

    # 头部声明的定长与本文件独立写死的 struct 不一致时**提前退出**。
    # 这正是 convert_gen1.py 那次「注释写 28、实际 32」的场景：
    # 继续往下解会在某条记录上抛 struct.error，给出的是一行栈回溯 ——
    # 而真正该说的是「头部说 N 字节，实际布局是 M 字节，照头部写固件会错位」。
    # 错位是本格式最危险的缺陷（读出来全是合法数值，不崩只是全错），
    # 所以它必须得到最清楚的一句话，而不是最晦涩的一句。
    if rsz != msz:
        return {
            "file": os.path.basename(path), "bytes": len(d),
            "magic": magic.decode("ascii", "replace"), "version": ver,
            "move_rec_size": rsz, "move_rec_expected": msz,
            "move_count": mcnt, "species_count": scnt,
            "learn_count_declared": lcnt, "learn_count_actual": -1,
            "pool_declared": poolsz, "pool_actual": -1,
            "header_bytes": hsz,
            "species_rec_size": ssz, "learn_rec_size": lsz,
            "moves": [], "species": [], "trailing_bytes": -1,
            "aborted": f"头部声明记录 {rsz} B，实际布局 {msz} B —— 不再往下解析",
        }

    p = hsz
    mrecs = d[p:p + mcnt * rsz]
    p += mcnt * rsz
    srecs = d[p:p + scnt * ssz]
    p += scnt * ssz
    lrecs = d[p:p + lcnt * lsz]
    p += lcnt * lsz
    pool = d[p:p + poolsz]
    consumed = p + poolsz

    moves = []
    for i in range(mcnt):
        o = i * rsz
        (mid, zo, zl, ty, pw, ac, pp, dc, rv) = struct.unpack(
            MOVE_REC_FMT, mrecs[o:o + rsz])
        moves.append({
            "slot": i, "move_id": mid,
            "zh": pool[zo:zo + zl].decode("utf-8", "replace") if zl else "",
            "zh_off": zo, "zh_len": zl,
            "type": ty, "power": pw, "accuracy": ac, "pp": pp,
            "damage_class": dc,
            "reserved_nonzero": rv != b"\x00" * 2,
        })

    species = []
    for i in range(scnt):
        o = i * ssz
        (loff, lcount, rv) = struct.unpack(MOVE_SPECIES_FMT, srecs[o:o + ssz])
        entries = []
        for k in range(lcount):
            q = (loff + k) * lsz
            if q + lsz > len(lrecs):
                break
            lv, slot = struct.unpack(MOVE_LEARN_FMT, lrecs[q:q + lsz])
            entries.append((lv, slot))
        species.append({
            "id": i + 1, "learn_offset": loff, "learn_count": lcount,
            "entries": entries, "reserved_nonzero": rv != 0,
            "truncated": len(entries) != lcount,
        })

    return {
        "file": os.path.basename(path), "bytes": len(d),
        "magic": magic.decode("ascii", "replace"), "version": ver,
        "move_rec_size": rsz, "move_rec_expected": msz,
        "move_count": mcnt, "species_count": scnt,
        "learn_count_declared": lcnt,
        "learn_count_actual": len(lrecs) // lsz,
        "pool_declared": poolsz, "pool_actual": len(pool),
        "header_bytes": hsz,
        "species_rec_size": ssz, "learn_rec_size": lsz,
        "moves": moves, "species": species,
        "trailing_bytes": len(d) - consumed,
    }


def audit_moves(mv: dict) -> dict:
    if mv.get("aborted"):
        # 解析已中止，没有记录可审。返回全空，让断言区只报那一条根因，
        # 不要再叠加几十条由错位派生出来的假问题。
        return {"aborted": mv["aborted"]}

    moves, species = mv["moves"], mv["species"]

    ids = [m["move_id"] for m in moves]
    dup_id = [i for i, n in collections.Counter(ids).items() if n > 1]
    # 段① 必须按 move_id 升序 —— 否则「已知 move_id 二分查记录」不成立
    sorted_ok = ids == sorted(ids)

    bad_type = [m["move_id"] for m in moves if m["type"] >= len(GEN1_TYPES_CN)]
    bad_dc = [m["move_id"] for m in moves if m["damage_class"] not in DAMAGE_CLASS_CN]
    # 只收伤害招，威力为 0 说明混进了变化招
    zero_power = [m["move_id"] for m in moves if m["power"] == 0]
    zero_pp = [m["move_id"] for m in moves if m["pp"] == 0]
    # 命中 0 会被固件读成永不命中；必中招约定用 255
    bad_acc = [m["move_id"] for m in moves
               if not (1 <= m["accuracy"] <= 100 or m["accuracy"] == ACC_ALWAYS_HIT)]
    zh_missing = [m["move_id"] for m in moves if not m["zh"]]
    zh_chars: set = set()
    for m in moves:
        zh_chars |= set(m["zh"])

    # 字符串池完整性：每条记录的 (off, len) 必须落在池内，
    # 且解码不能产生替换字符（U+FFFD 说明偏移把多字节汉字切断了）
    pool_oob = [m["move_id"] for m in moves
                if m["zh_off"] + m["zh_len"] > mv["pool_actual"]]
    pool_garbled = [m["move_id"] for m in moves if "�" in m["zh"]]

    # 学习表：slot 必须落在段①范围内，等级必须升序
    n = len(moves)
    bad_slot, unsorted_lv, bad_level = [], [], []
    covered = 0
    total_entries = 0
    for s in species:
        if s["entries"]:
            covered += 1
        total_entries += len(s["entries"])
        lvs = [lv for lv, _ in s["entries"]]
        if lvs != sorted(lvs):
            unsorted_lv.append(s["id"])
        for lv, slot in s["entries"]:
            if not 0 <= slot < n:
                bad_slot.append((s["id"], slot))
            if not 1 <= lv <= 100:
                bad_level.append((s["id"], lv))

    # 段③ 是否被完整引用 —— 没有任何物种指向的区间说明有空洞
    referenced = set()
    for s in species:
        for k in range(s["learn_count"]):
            referenced.add(s["learn_offset"] + k)
    orphan = mv["learn_count_actual"] - len(referenced)

    return {
        "duplicate_move_id": dup_id,
        "move_ids_sorted": sorted_ok,
        "bad_type": bad_type, "bad_damage_class": bad_dc,
        "zero_power": zero_power, "zero_pp": zero_pp, "bad_accuracy": bad_acc,
        "always_hit": [m["move_id"] for m in moves
                       if m["accuracy"] == ACC_ALWAYS_HIT],
        "zh_missing": zh_missing,
        "zh_char_count": len(zh_chars), "zh_chars": "".join(sorted(zh_chars)),
        "pool_out_of_bounds": pool_oob, "pool_garbled": pool_garbled,
        "species_covered": covered,
        "species_empty": [s["id"] for s in species if not s["entries"]],
        "learn_entries_walked": total_entries,
        "bad_slot": bad_slot, "unsorted_levels": unsorted_lv,
        "bad_level": bad_level,
        "truncated_species": [s["id"] for s in species if s["truncated"]],
        "orphan_learn_entries": orphan,
        "reserved_dirty": [m["move_id"] for m in moves if m["reserved_nonzero"]],
        "type_dist": dict(collections.Counter(
            GEN1_TYPES_CN[m["type"]] if m["type"] < len(GEN1_TYPES_CN)
            else f"?{m['type']}" for m in moves)),
        "dc_dist": dict(collections.Counter(
            DAMAGE_CLASS_CN.get(m["damage_class"], f"?{m['damage_class']}")
            for m in moves)),
        "power_range": (min((m["power"] for m in moves), default=0),
                        max((m["power"] for m in moves), default=0)),
    }


# ---------------------------------------------------------------------------
# gen1_front.bin —— 分段图集，段内定长，每项带显式 id
# ---------------------------------------------------------------------------

def parse_front(path: str) -> dict:
    d = open(path, "rb").read()
    magic, ver, nseg = struct.unpack("<4sHH", d[:8])
    p = 8
    segs = []
    for _ in range(nseg):
        size, per, n, doff = struct.unpack("<HHII", d[p:p + 12])
        p += 12
        segs.append({"size": size, "per": per, "n": n, "data_off": doff})

    base = p
    ids_by_seg: dict[int, list[int]] = {}
    blanks: list[dict] = []
    consumed = base
    for s in segs:
        q = base + s["data_off"]
        ids = []
        for _ in range(s["n"]):
            (pid,) = struct.unpack("<H", d[q:q + 2])
            q += 2
            blob = d[q:q + s["per"]]
            q += s["per"]
            ids.append(pid)
            br = blank_ratio(blob)
            if br > 0.99:
                blanks.append({"id": pid, "size": s["size"], "zero_ratio": br})
        ids_by_seg[s["size"]] = ids
        consumed = max(consumed, q)
        # 段内单张字节数是否与尺寸自洽
        s["per_expected"] = (s["size"] * s["size"] * 2 + 7) // 8
        s["per_ok"] = s["per"] == s["per_expected"]
        s["ids_sorted"] = ids == sorted(ids)

    all_ids = sorted(i for ids in ids_by_seg.values() for i in ids)
    return {
        "file": os.path.basename(path), "bytes": len(d),
        "magic": magic.decode("ascii", "replace"), "version": ver,
        "segments": segs, "ids_by_size": ids_by_seg,
        "total_sprites": len(all_ids),
        "ids": all_ids,
        "missing_1_151": [i for i in range(1, 152) if i not in set(all_ids)],
        "duplicate_ids": [i for i, n in collections.Counter(all_ids).items() if n > 1],
        "out_of_range_ids": [i for i in all_ids if not 1 <= i <= 151],
        "blank_entries": blanks,
        "trailing_bytes": len(d) - consumed,
    }


# ---------------------------------------------------------------------------
# gen1_back.bin —— 定长，按 id 直接索引（无显式 id 字段）
# ---------------------------------------------------------------------------

def parse_back(path: str) -> dict:
    d = open(path, "rb").read()
    magic, ver, w, h, per, cnt = struct.unpack("<4sHHHHI", d[:16])
    per_expected = (w * h * 2 + 7) // 8
    blanks = []
    for i in range(cnt):
        o = 16 + i * per
        br = blank_ratio(d[o:o + per])
        if br > 0.99:
            blanks.append({"id": i + 1, "zero_ratio": br})
    return {
        "file": os.path.basename(path), "bytes": len(d),
        "magic": magic.decode("ascii", "replace"), "version": ver,
        "width": w, "height": h, "per": per, "count": cnt,
        "per_expected": per_expected, "per_ok": per == per_expected,
        "blank_entries": blanks,
        "trailing_bytes": len(d) - (16 + cnt * per),
    }


# ---------------------------------------------------------------------------
# palettes.bin —— N 套普通 + N 套闪光 + 每只索引
# ---------------------------------------------------------------------------

def parse_palettes(path: str) -> dict:
    d = open(path, "rb").read()
    magic, ver, nsets, ncolors, count = struct.unpack("<4sHHHH", d[:12])
    body = d[12:]
    per_set = ncolors * 2

    def to_hex(rgb565: int) -> str:
        r = ((rgb565 >> 11) & 0x1F) << 3
        g = ((rgb565 >> 5) & 0x3F) << 2
        b = (rgb565 & 0x1F) << 3
        return f"#{r:02x}{g:02x}{b:02x}"

    normal, shiny = [], []
    for i in range(nsets * 2):
        o = i * per_set
        cols = [to_hex(struct.unpack("<H", body[o + c * 2:o + c * 2 + 2])[0])
                for c in range(ncolors)]
        (normal if i < nsets else shiny).append(cols)

    idx_off = nsets * 2 * per_set
    per_mon = list(body[idx_off:idx_off + count])
    dist = collections.Counter(v & 0x0F for v in per_mon)
    return {
        "file": os.path.basename(path), "bytes": len(d),
        "magic": magic.decode("ascii", "replace"), "version": ver,
        "sets_normal": nsets, "sets_shiny": len(shiny),
        "colors_per_set": ncolors, "mon_count": count,
        "bytes_per_color": 2, "color_format": "RGB565 little-endian",
        "normal": normal, "shiny": shiny,
        "per_mon_index": per_mon,
        "usage": dict(sorted(dist.items())),
        "index_out_of_range": sorted({v for v in per_mon if (v & 0x0F) >= nsets}),
        "expected_bytes": 12 + nsets * 2 * per_set + count,
        "trailing_bytes": len(d) - (12 + nsets * 2 * per_set + count),
        "shiny_differs": sum(1 for a, b in zip(normal, shiny) if a != b),
    }


# ---------------------------------------------------------------------------
# font16.bin —— 头部 + 码点索引(u16 升序) + 字形(1bpp)
# ---------------------------------------------------------------------------

def parse_font(path: str) -> dict:
    d = open(path, "rb").read()
    magic, ver, size, per, n = struct.unpack("<4sHHHI", d[:14])
    per_expected = size * ((size + 7) // 8)
    idx = d[14:14 + n * 2]
    glyphs = d[14 + n * 2:]
    codes = [struct.unpack("<H", idx[i * 2:i * 2 + 2])[0] for i in range(n)]
    chars = [chr(c) for c in codes]

    blank = [chars[i] for i in range(n)
             if not any(glyphs[i * per:(i + 1) * per])]
    ink = []
    for i in range(n):
        g = glyphs[i * per:(i + 1) * per]
        bits = sum(bin(b).count("1") for b in g)
        ink.append(bits / (size * size))

    cjk = [c for c in chars if "一" <= c <= "鿿"]
    ascii_ = [c for c in chars if ord(c) < 128]
    other = [c for c in chars if c not in cjk and ord(c) >= 128]
    return {
        "file": os.path.basename(path), "bytes": len(d),
        "magic": magic.decode("ascii", "replace"), "version": ver,
        "glyph_size": size, "bytes_per_glyph": per,
        "per_expected": per_expected, "per_ok": per == per_expected,
        "count": n, "bpp": 1,
        "header_bytes": 14, "index_bytes": len(idx), "glyph_bytes": len(glyphs),
        "glyph_bytes_expected": n * per,
        "sorted": codes == sorted(codes),
        "duplicates": [c for c, k in collections.Counter(codes).items() if k > 1],
        "chars": "".join(chars),
        "cjk_count": len(cjk), "ascii_count": len(ascii_),
        "other_count": len(other), "other": "".join(other),
        "blank_glyphs": blank,
        "ink_min": min(ink) if ink else 0, "ink_max": max(ink) if ink else 0,
        "ink_avg": sum(ink) / len(ink) if ink else 0,
        "trailing_bytes": len(d) - (14 + n * 2 + n * per),
    }


# ---------------------------------------------------------------------------
# eye_regions.json
# ---------------------------------------------------------------------------

def parse_eye(path: str) -> dict:
    """实测结构：顶层是 {_meta, regions}，regions 以字符串 id 为键。"""
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    meta = raw.get("_meta", {}) if isinstance(raw, dict) else {}
    regions = raw.get("regions", {}) if isinstance(raw, dict) else {}

    ids, status = [], collections.Counter()
    conf = collections.Counter()
    with_boxes, box_count = [], 0
    for k, v in regions.items():
        try:
            ids.append(int(k))
        except (TypeError, ValueError):
            continue
        status[v.get("status", "?")] += 1
        conf[v.get("confidence", "?")] += 1
        boxes = v.get("boxes") or []
        if boxes:
            with_boxes.append(int(k))
            box_count += len(boxes)

    declared = meta.get("counts", {})
    return {
        "file": os.path.basename(path), "bytes": os.path.getsize(path),
        "top_keys": sorted(raw.keys()) if isinstance(raw, dict) else None,
        "kind": "dict", "n_entries": len(regions),
        "ids": sorted(ids),
        "missing_1_151": [i for i in range(1, 152) if i not in set(ids)],
        "status_dist": dict(status), "confidence_dist": dict(conf),
        "ids_with_boxes": sorted(with_boxes), "total_boxes": box_count,
        "meta_counts_declared": declared,
        # 声明与实测是否一致 —— _meta 是手写的，会与 regions 漂移
        "meta_matches": all(status.get(k, 0) == v for k, v in declared.items()),
        "meta_sprite": meta.get("sprite"), "meta_size": meta.get("size"),
    }


# ---------------------------------------------------------------------------
# 交叉验证：字库是否覆盖所有会上屏的字
# ---------------------------------------------------------------------------

def collect_display_chars(gen1: dict) -> dict:
    """收集所有**会显示在屏幕上**的字符，按来源分组。

    这里要点是：不能只问 convert_font.py 收了哪些字，
    而要独立地把所有文案来源列出来 —— 二者的差就是缺字。
    """
    sim = os.path.join(REPO, "sim")
    if sim not in sys.path:
        sys.path.insert(0, sim)

    sources: dict[str, set] = {}

    # 物种中文名（gen1.bin 实测）
    zh: set = set()
    for m in gen1["mons"]:
        zh |= set(m["zh"])
    sources["物种中文名 (gen1.bin)"] = zh

    # convert_font.py 声明的来源。这张表漏登记过两轮 ——
    # gyms 漏了 29 字（馆主/城市/徽章名），
    # party/systems/state 漏了 16 字（队伍菜单/判定提示/存档槽）。
    # **这里必须与 convert_font.py 的 SOURCES 同步**，否则清点会漏报。
    for mod, label in (("strings", "UI 文案 (sim/strings.py)"),
                       ("naming", "昵称 (sim/naming.py)"),
                       ("opening", "开场台词 (sim/opening.py)"),
                       ("gyms", "道馆/徽章 (sim/gyms.py)"),
                       ("party", "队伍/仓库菜单 (sim/party.py)"),
                       ("systems", "捕获/进化提示 (sim/systems.py)"),
                       ("state", "存档槽说明 (sim/state.py)")):
        try:
            m = __import__(mod)
            sources[label] = set(m.charset())
        except Exception as e:
            sources[label] = set()
            print(f"  ⚠️  {mod}.charset() 不可用: {type(e).__name__} {e}",
                  file=sys.stderr)

    # convert_font.py 硬编码补的符号 —— **从源码里抓**而不是抄一份。
    # 抄一份的后果实测过：队友把 ✦ 从符号集移走（它只出现在 CLI 日志与
    # inspector 网页，不上屏），我这边的副本还留着，于是虚报一个缺字。
    sym = set()
    cf = os.path.join(REPO, "tools", "pipeline", "convert_font.py")
    try:
        import re
        src = open(cf, encoding="utf-8").read()
        for m in re.finditer(r'ui_chars \|= set\("([^"]*)"\)', src):
            sym |= set(m.group(1))
    except Exception as e:
        print(f"  ⚠️  读不到 convert_font.py 的符号集: {e}", file=sys.stderr)
    sources["数字与符号 (convert_font.py 硬编码)"] = sym

    # 道馆 dataclass 的**字段实测** —— 独立于 gyms.charset()。
    # 两者比对能查出 charset() 是否漏了某个上屏字段。
    try:
        import gyms
        import dataclasses
        gym_chars: set = set()
        fields: list[str] = []
        names = [f.name for f in dataclasses.fields(gyms.Gym)]
        # 日文原名（片假名）只用于文档对照，不上屏也不该进汉字库。
        # 字段名两个 dataclass 不一样：Gym 用 leader_ja，EliteMember 用
        # name_ja —— 两个都排除，免得改错一个就漏过 18 个片假名。
        names = [n for n in names if not n.endswith("_ja")]
        for g in gyms.GYMS:
            for attr in names:
                v = getattr(g, attr, None)
                if isinstance(v, str):
                    fields.append(v)
                    gym_chars |= set(v)
        sources["道馆字段实测 (Gym dataclass)"] = gym_chars
        sources["_gym_fields"] = set(fields)
    except Exception as e:
        print(f"  ⚠️  gyms 字段读取失败: {type(e).__name__} {e}", file=sys.stderr)

    # 道馆门槛提示语 —— GymCheck.reason 会显示给玩家（见 sim/gyms.py
    # check_gym / check_elite / check_red 的 return）。
    # 剔除 f-string 占位与数字：占位符本身不上屏，算进去会虚报缺字。
    try:
        import gyms as _gy
        rc: set = set()
        for s in ("要先取得第枚徽章", "图鉴见闻不足", "要先打完四天王",
                  "队伍至少要只能战斗", "需要八枚徽章"):
            rc |= set(s)
        for g in _gy.GYMS:
            rc |= set(f"已取得{g.badge}")
        sources["道馆门槛提示 (GymCheck.reason)"] = rc
    except Exception:
        pass

    # 队伍/仓库菜单项 —— party.actions() 的返回值直接是菜单文字（S14）
    try:
        import party as _pt
        pc: set = set()
        for s in ("设为主宠", "存入仓库", "加入队伍", "与队伍交换",
                  "查看详情", "取名", "返回",
                  _pt.REASON_BOX_FULL, _pt.REASON_EMPTY, "队伍满了"):
            pc |= set(s)
        sources["队伍/仓库菜单 (sim/party.py)"] = pc
    except Exception as e:
        print(f"  ⚠️  party 读取失败: {type(e).__name__} {e}", file=sys.stderr)

    # 存档槽提示与照料结果 —— 同样会上屏
    try:
        import systems as _sy  # noqa: F401
        sc: set = set()
        for s in ("喂食完成", "玩耍完成", "休息完成", "这只不会进化",
                  "队伍", "仓库", "主槽", "备份槽", "两份都损坏"):
            sc |= set(s)
        sources["照料结果/存档槽 (sim/systems.py, state.py)"] = sc
    except Exception:
        pass

    return sources


def crosscheck(font: dict, sources: dict) -> dict:
    have = set(font["chars"])
    report = {}
    all_need: set = set()
    for label, chars in sources.items():
        if label.startswith("_"):
            continue
        miss = sorted(chars - have)
        all_need |= chars
        report[label] = {
            "need": len(chars), "missing": len(miss),
            "missing_chars": "".join(miss),
        }
    unused = sorted(have - all_need)
    return {
        "per_source": report,
        "total_need": len(all_need),
        "font_has": len(have),
        "total_missing": len(all_need - have),
        "missing_chars": "".join(sorted(all_need - have)),
        "font_unused": "".join(unused),
        "font_unused_count": len(unused),
    }


def shade_histogram(blob: bytes) -> collections.Counter:
    """2bpp 位图的四阶色号分布。

    结构合法（长度对、magic 对）不代表内容是图 —— 单色块也能通过。
    真实 sprite 必须**四档都用到**且没有哪一档占满。
    """
    h: collections.Counter = collections.Counter()
    for b in blob:
        for k in range(4):
            h[(b >> (6 - k * 2)) & 3] += 1
    return h


def content_check(path_front: str, path_back: str) -> dict:
    """逐张统计色号分布，找出「结构合法但内容可疑」的条目。"""
    suspicious = []
    stats = {}

    fd = open(path_front, "rb").read()
    _m, _v, nseg = struct.unpack("<4sHH", fd[:8])
    p = 8
    segs = []
    for _ in range(nseg):
        segs.append(struct.unpack("<HHII", fd[p:p + 12]))
        p += 12
    base = p
    shades_used = collections.Counter()
    for size, per, n, doff in segs:
        q = base + doff
        for _ in range(n):
            (pid,) = struct.unpack("<H", fd[q:q + 2])
            q += 2
            blob = fd[q:q + per]
            q += per
            hist = shade_histogram(blob)
            used = sum(1 for v in hist.values() if v)
            shades_used[used] += 1
            top = max(hist.values()) / sum(hist.values())
            if used < 3 or top > 0.97:
                suspicious.append({"file": "front", "id": pid, "size": size,
                                   "shades_used": used, "dominant": round(top, 4)})
    stats["front_shades_used_dist"] = dict(sorted(shades_used.items()))

    bd = open(path_back, "rb").read()
    _m, _v, w, h, per, cnt = struct.unpack("<4sHHHHI", bd[:16])
    su = collections.Counter()
    for i in range(cnt):
        blob = bd[16 + i * per:16 + (i + 1) * per]
        hist = shade_histogram(blob)
        used = sum(1 for v in hist.values() if v)
        su[used] += 1
        top = max(hist.values()) / sum(hist.values())
        if used < 3 or top > 0.97:
            suspicious.append({"file": "back", "id": i + 1, "size": w,
                               "shades_used": used, "dominant": round(top, 4)})
    stats["back_shades_used_dist"] = dict(sorted(su.items()))
    stats["suspicious"] = suspicious
    return stats


def diagnose_blank_glyphs(blank: list[str]) -> dict:
    """空字形的成因 —— 是字库漏渲染，还是字体本身没这个字。

    起因：convert_font.py 曾用 `ImageFont.truetype(path, size)` **不传 index**，
    于是拿到 PingFang.ttc 的第 0 面 = PingFang **HK**（繁体子集）。
    简体字形若只在 SC 面里，HK 面渲染出零高度 bbox → 整字全零。

    这个函数把这条因果链实测出来：逐面渲染，报告哪一面有字。
    （该缺陷已修 —— convert_font.py 现在固定 index=2 并做简体自检，
    但这个诊断保留：换字体或换机器时它是第一道排查。）

    空白符（空格等）**不算异常** —— 它们本来就该是空字形，
    渲染器直接查表推进宽度即可，不需要特例分支。
    """
    blank = [ch for ch in blank if not ch.isspace()]
    if not blank:
        return {"checked": False, "reason": "无空字形（空白符不计）"}
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        return {"checked": False, "reason": "无 PIL，跳过成因诊断"}

    path = "/System/Library/Fonts/PingFang.ttc"
    if not os.path.exists(path):
        return {"checked": False, "reason": f"{path} 不存在"}

    out: dict = {"checked": True, "font": path, "per_char": {}}
    for ch in blank:
        faces = []
        for i in range(8):
            try:
                f = ImageFont.truetype(path, 16, index=i)
            except Exception:
                break
            try:
                name = "/".join(f.getname())
            except Exception:
                name = f"face{i}"
            img = Image.new("L", (16, 16), 255)
            bb = ImageDraw.Draw(img).textbbox((0, 0), ch, font=f)
            faces.append({"index": i, "name": name,
                          "has_glyph": (bb[3] - bb[1]) > 0, "bbox": list(bb)})
        out["per_char"][ch] = {
            "faces": faces,
            "faces_with_glyph": [f["index"] for f in faces if f["has_glyph"]],
        }
    # 两类成因要分开报：
    #   ① 某些面有字形 → 脚本选错了面（index 没传），换面即可修
    #   ② 所有面都没有 → 字体根本不含这个字，必须改用点阵生成或换符号
    out["wrong_face"] = [c for c, v in out["per_char"].items()
                         if v["faces_with_glyph"]]
    out["no_glyph_anywhere"] = [c for c, v in out["per_char"].items()
                                if not v["faces_with_glyph"]]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="实测清点 assets/ 二进制内容")
    ap.add_argument("--assets", default=ASSETS)
    ap.add_argument("--json", action="store_true", help="输出完整 JSON")
    args = ap.parse_args()

    A = args.assets
    r: dict = {}
    r["gen1"] = parse_gen1(os.path.join(A, "gen1.bin"))
    r["gen1_audit"] = audit_gen1(r["gen1"])
    r["front"] = parse_front(os.path.join(A, "gen1_front.bin"))
    r["back"] = parse_back(os.path.join(A, "gen1_back.bin"))
    r["palettes"] = parse_palettes(os.path.join(A, "palettes.bin"))
    r["font"] = parse_font(os.path.join(A, "font16.bin"))
    r["eye"] = parse_eye(os.path.join(A, "eye_regions.json"))
    moves_path = os.path.join(A, "moves.bin")
    if os.path.exists(moves_path):
        r["moves"] = parse_moves(moves_path)
        r["moves_audit"] = audit_moves(r["moves"])
    r["content"] = content_check(os.path.join(A, "gen1_front.bin"),
                                 os.path.join(A, "gen1_back.bin"))

    charset_txt = os.path.join(A, "font16_charset.txt")
    if os.path.exists(charset_txt):
        txt = open(charset_txt, encoding="utf-8").read()
        r["font"]["charset_txt_chars"] = len(txt)
        r["font"]["charset_txt_matches_bin"] = txt == r["font"]["chars"]

    sources = collect_display_chars(r["gen1"])
    r["crosscheck"] = crosscheck(r["font"], sources)
    r["crosscheck"]["gym_fields"] = sorted(sources.get("_gym_fields", []))
    r["blank_diagnosis"] = diagnose_blank_glyphs(r["font"]["blank_glyphs"])

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
        return 0

    # ---- 人读摘要 ----
    g, ga, f, b, p, ft, ey, cc = (r["gen1"], r["gen1_audit"], r["front"],
                                  r["back"], r["palettes"], r["font"],
                                  r["eye"], r["crosscheck"])
    print(f"\n== gen1.bin ==  {g['bytes']} B  magic={g['magic']} v{g['version']}")
    print(f"  {g['count']} 条 × {g['record_size']} B  池 {g['pool_actual']} B"
          f"（头声明 {g['pool_declared']}）")
    print(f"  中文名缺失 {len(ga['zh_missing'])}　slug 缺失 "
          f"{len(ga['slug_missing'])}　零种族值 {len(ga['zero_stats'])}")
    print(f"  中文名用字 {ga['zh_char_count']} 个　配色索引 {ga['palettes_used']}")
    print(f"  front 尺寸档分布 {ga['front_tier_dist']}")
    print(f"  biome 分布（一只可属多个）{ga['biome_dist']}")
    print(f"  传说 {len(ga['legendary'])}　幻兽 {len(ga['mythical'])}"
          f"　可进化 {ga['evolving']}")

    print(f"\n== gen1_front.bin ==  {f['bytes']} B  magic={f['magic']}"
          f" v{f['version']}  {f['total_sprites']} 张")
    for s in f["segments"]:
        print(f"  {s['size']}×{s['size']}  {s['n']:>3} 只  单张 {s['per']} B"
              f"  per_ok={s['per_ok']}  id 有序={s['ids_sorted']}")
    print(f"  缺 id {f['missing_1_151']}　重复 {f['duplicate_ids']}"
          f"　越界 {f['out_of_range_ids']}")
    print(f"  空白条目 {len(f['blank_entries'])}　尾部余 {f['trailing_bytes']} B")

    print(f"\n== gen1_back.bin ==  {b['bytes']} B  magic={b['magic']}"
          f" v{b['version']}")
    print(f"  {b['count']} 张 @ {b['width']}×{b['height']}  单张 {b['per']} B"
          f"  per_ok={b['per_ok']}")
    print(f"  空白条目 {len(b['blank_entries'])}"
          f" {[e['id'] for e in b['blank_entries']][:12]}"
          f"　尾部余 {b['trailing_bytes']} B")

    ct = r["content"]
    print(f"\n== 位图内容抽检（色号分布）==")
    print(f"  front 用到几档色的分布 {ct['front_shades_used_dist']}")
    print(f"  back  用到几档色的分布 {ct['back_shades_used_dist']}")
    print(f"  可疑条目（<3 档色或单档 >97%）{len(ct['suspicious'])}"
          f" {ct['suspicious'][:5]}")

    print(f"\n== palettes.bin ==  {p['bytes']} B  magic={p['magic']}"
          f" v{p['version']}")
    print(f"  普通 {p['sets_normal']} 套 + 闪光 {p['sets_shiny']} 套"
          f"  × {p['colors_per_set']} 色 × 2 B（{p['color_format']}）")
    print(f"  每只索引 {p['mon_count']} B　使用分布 {p['usage']}")
    print(f"  越界索引 {p['index_out_of_range']}　闪光与普通不同的套数 "
          f"{p['shiny_differs']}/{p['sets_normal']}　尾部余 {p['trailing_bytes']} B")

    print(f"\n== font16.bin ==  {ft['bytes']} B  magic={ft['magic']}"
          f" v{ft['version']}")
    print(f"  {ft['count']} 字形 @ {ft['glyph_size']}×{ft['glyph_size']}"
          f" {ft['bpp']}bpp  单字 {ft['bytes_per_glyph']} B"
          f"  per_ok={ft['per_ok']}")
    print(f"  汉字 {ft['cjk_count']}　ASCII {ft['ascii_count']}"
          f"　其他 {ft['other_count']}「{ft['other']}」")
    print(f"  码点升序={ft['sorted']}　重复 {ft['duplicates']}"
          f"　空字形 {len(ft['blank_glyphs'])} {ft['blank_glyphs'][:10]}")
    print(f"  着墨率 min={ft['ink_min']:.3f} avg={ft['ink_avg']:.3f}"
          f" max={ft['ink_max']:.3f}")
    print(f"  charset.txt 与 bin 一致={ft.get('charset_txt_matches_bin')}")

    bd = r["blank_diagnosis"]
    if bd.get("checked"):
        print(f"  空字形成因（{os.path.basename(bd['font'])} 逐面实测）：")
        for ch, v in bd["per_char"].items():
            ok = v["faces_with_glyph"]
            names = [f["name"] for f in v["faces"] if f["has_glyph"]]
            why = f"选错字面，index={ok} {names} 有" if ok else "该字体全部面均无此字形"
            print(f"    「{ch}」{why}")
        if bd["wrong_face"]:
            print(f"    → 可修：给 truetype() 传 index 即可拿到"
                  f" 「{''.join(bd['wrong_face'])}」")
        if bd["no_glyph_anywhere"]:
            print(f"    → 需换方案（点阵生成或换符号）："
                  f"「{''.join(bd['no_glyph_anywhere'])}」")
    elif bd.get("reason"):
        print(f"  空字形成因：{bd['reason']}")

    print(f"\n== eye_regions.json ==  {ey['bytes']} B  {ey['n_entries']} 条"
          f"  （sprite={ey['meta_sprite']} size={ey['meta_size']}）")
    mi = ey["missing_1_151"]
    print(f"  覆盖 id {len(ey['ids'])}/151　缺 {len(mi)} 只 {mi[:20]}")
    print(f"  status 分布 {ey['status_dist']}　置信度 {ey['confidence_dist']}")
    print(f"  实际有框的 {ey['ids_with_boxes']}（共 {ey['total_boxes']} 个框）")
    print(f"  _meta 声明 {ey['meta_counts_declared']}"
          f"　与实测一致={ey['meta_matches']}")

    mv, mva = r.get("moves"), r.get("moves_audit")
    if mv and mv.get("aborted"):
        print(f"\n== moves.bin ==  {mv['bytes']} B  magic={mv['magic']}"
              f" v{mv['version']}")
        print(f"  ❌ {mv['aborted']}")
    elif mv:
        print(f"\n== moves.bin ==  {mv['bytes']} B  magic={mv['magic']}"
              f" v{mv['version']}")
        print(f"  段① {mv['move_count']} 招 × {mv['move_rec_size']} B"
              f"  (struct 实测 {mv['move_rec_expected']} B)"
              f"  move_id 升序={mva['move_ids_sorted']}"
              f"  重复 {mva['duplicate_move_id']}")
        print(f"  段② {mv['species_count']} 只 × {mv['species_rec_size']} B"
              f"　段③ {mv['learn_count_declared']} 条 × {mv['learn_rec_size']} B"
              f"（实测 {mv['learn_count_actual']}）")
        print(f"  段④ 池 {mv['pool_actual']} B（头声明 {mv['pool_declared']}）"
              f"　尾部余 {mv['trailing_bytes']} B")
        print(f"  威力区间 {mva['power_range']}　必中招 {mva['always_hit']}")
        print(f"  属性分布 {mva['type_dist']}")
        print(f"  物理/特殊 {mva['dc_dist']}")
        print(f"  学习表覆盖 {mva['species_covered']}/{mv['species_count']} 只"
              f"　走表 {mva['learn_entries_walked']} 条"
              f"　孤儿条目 {mva['orphan_learn_entries']}")
        if mva["species_empty"]:
            print(f"  无伤害招的物种 {mva['species_empty']}")
        print(f"  中文名缺失 {len(mva['zh_missing'])}"
              f"　用字 {mva['zh_char_count']} 个")

        # 招式名要上屏，所以必须进字库。字库重建是下一步，
        # 这里只报差集，不算断言失败 —— 否则本轮永远过不了。
        have = set(ft["chars"])
        need = set(mva["zh_chars"])
        miss = sorted(need - have)
        print(f"  招式名用字进字库：{len(need)-len(miss)}/{len(need)}"
              + (f"　**缺 {len(miss)} 字**：{''.join(miss)}" if miss else " ✓"))
        r["moves_audit"]["font_missing"] = "".join(miss)

    print(f"\n== 字库交叉验证 ==")
    for label, v in cc["per_source"].items():
        flag = "❌" if v["missing"] else "✅"
        print(f"  {flag} {label}: 需 {v['need']}　缺 {v['missing']}"
              f" 「{v['missing_chars']}」")
    print(f"\n  合计需 {cc['total_need']} 字，字库有 {cc['font_has']}，"
          f"缺 {cc['total_missing']} 字")
    if cc["total_missing"]:
        print(f"  缺字：{cc['missing_chars']}")
    print(f"  字库中无人使用的字 {cc['font_unused_count']} 个："
          f"{cc['font_unused']}")

    # ---- 断言区：非零退出码，可直接当 CI 门禁 -------------------------------
    #
    # 「上屏文案来源 − 字库 = 空集」这条在一轮开发里**重现了两次**：
    # 先是 S17 道馆漏 29 字，修完又发现 S14/S2·S7/S18 漏 16 字，
    # 再修完又发现 strings.charset() 自己漏了 KEYS 的键名（A/B/C 与方括号，
    # 九处三键提示行的键位标签全空白）。
    #
    # 三次的共同点：**所有常规指标都正常** —— 字数在涨、文件大小对、
    # magic 对、码点升序、charset.txt 与 bin 一致。缺陷只在做差集时才现形，
    # 而在真机上表现为「那一片文字是空白」，且要点亮走到那个页面才发现。
    #
    # 所以这不是一次性疏漏，是缺少守护。让脚本用退出码说话。
    #
    # 这里枚举来源时**不读 convert_font.py 的 SOURCES 清单** ——
    # 而是自己去 import 各模块取 charset()。这样才能查出
    # 「新模块忘了登记」这类 convert_font.py 自己查不到的问题。
    fails = []
    if cc["total_missing"]:
        fails.append(f"字库缺 {cc['total_missing']} 字：{cc['missing_chars']}")
    blank_real = [c for c in ft.get("blank_glyphs", []) if not c.isspace()]
    if blank_real:
        fails.append(f"{len(blank_real)} 个空白字形：「{''.join(blank_real)}」"
                     f"（字体没有该字形，需换符号或改用点阵生成）")
    # sprite 完整性：front 带显式 id（能查缺号/重号），back 按序号排（只能查空条目）
    fr, bk = r["front"], r["back"]
    if fr["missing_1_151"]:
        fails.append(f"front 缺 {len(fr['missing_1_151'])} 只："
                     f"{fr['missing_1_151'][:10]}")
    if fr["duplicate_ids"] or fr["out_of_range_ids"]:
        fails.append(f"front id 异常：重复 {fr['duplicate_ids']}"
                     f" 越界 {fr['out_of_range_ids']}")
    for label, d in (("front", fr), ("back", bk)):
        if d["blank_entries"]:
            fails.append(f"{label} 有 {len(d['blank_entries'])} 个全零条目："
                         f"{d['blank_entries'][:10]}")
    if bk["count"] != 151:
        fails.append(f"back 只有 {bk['count']} 张，应为 151")
    if not bk["per_ok"] or not ft["per_ok"]:
        fails.append(f"定长不符：back per_ok={bk['per_ok']}"
                     f" font per_ok={ft['per_ok']}")
    if not ft["charset_txt_matches_bin"]:
        fails.append("font16_charset.txt 与 font16.bin 不一致 —— 需重跑 convert_font.py")

    # ---- moves.bin ----
    #
    # 这里查的都是「结构合法但内容错」那一类。特别是 slot 越界与等级乱序：
    # 二者都不会让解析抛异常，但会让固件在战斗时读到别的招 ——
    # 而读出来的仍是一条合法招式记录，玩家只会觉得「这只怎么会用火焰喷射」。
    if mv:
        if mv["magic"] != "MOVE":
            fails.append(f"moves.bin magic={mv['magic']}，应为 MOVE")
        if mv["move_rec_size"] != mv["move_rec_expected"]:
            fails.append(f"moves.bin 定长不符：头声明 {mv['move_rec_size']} B，"
                         f"struct 实测 {mv['move_rec_expected']} B"
                         f"（照头部写固件会整体错位）")
    if mv and not mv.get("aborted"):
        if mv["learn_count_declared"] != mv["learn_count_actual"]:
            fails.append(f"moves.bin 学习表条数不符：头声明 "
                         f"{mv['learn_count_declared']}，实测 {mv['learn_count_actual']}")
        if mv["pool_declared"] != mv["pool_actual"]:
            fails.append(f"moves.bin 字符串池不符：头声明 {mv['pool_declared']}，"
                         f"实测 {mv['pool_actual']}")
        if mv["trailing_bytes"] != 0:
            fails.append(f"moves.bin 尾部多余 {mv['trailing_bytes']} B")
        if mv["species_count"] != 151:
            fails.append(f"moves.bin 物种索引 {mv['species_count']} 条，应为 151")
        if not mva["move_ids_sorted"]:
            fails.append("moves.bin 段① move_id 非升序")
        if mva["duplicate_move_id"]:
            fails.append(f"moves.bin move_id 重复：{mva['duplicate_move_id']}")
        if mva["bad_type"]:
            fails.append(f"moves.bin {len(mva['bad_type'])} 招属性越界"
                         f"（应 0~14）：{mva['bad_type'][:10]}")
        if mva["bad_damage_class"]:
            fails.append(f"moves.bin {len(mva['bad_damage_class'])} 招"
                         f"物理/特殊标记非法：{mva['bad_damage_class'][:10]}")
        if mva["zero_power"]:
            fails.append(f"moves.bin {len(mva['zero_power'])} 招威力为 0"
                         f"（只该收伤害招）：{mva['zero_power'][:10]}")
        if mva["zero_pp"]:
            fails.append(f"moves.bin {len(mva['zero_pp'])} 招 PP 为 0："
                         f"{mva['zero_pp'][:10]}")
        if mva["bad_accuracy"]:
            fails.append(f"moves.bin {len(mva['bad_accuracy'])} 招命中非法"
                         f"（应 1~100 或 255 必中）：{mva['bad_accuracy'][:10]}")
        if mva["zh_missing"]:
            fails.append(f"moves.bin {len(mva['zh_missing'])} 招缺中文名："
                         f"{mva['zh_missing'][:10]}")
        if mva["pool_out_of_bounds"]:
            fails.append(f"moves.bin {len(mva['pool_out_of_bounds'])} 招"
                         f"名字偏移越出字符串池：{mva['pool_out_of_bounds'][:10]}")
        if mva["pool_garbled"]:
            fails.append(f"moves.bin {len(mva['pool_garbled'])} 招名字解码出乱码"
                         f"（偏移把汉字切断了）：{mva['pool_garbled'][:10]}")
        if mva["bad_slot"]:
            fails.append(f"moves.bin 学习表 slot 越界 {mva['bad_slot'][:10]}"
                         f"（会读到别的招）")
        if mva["unsorted_levels"]:
            fails.append(f"moves.bin {len(mva['unsorted_levels'])} 只的学习表"
                         f"未按等级升序：{mva['unsorted_levels'][:10]}"
                         f"（固件靠升序扫到 Lv>N 为止）")
        if mva["bad_level"]:
            fails.append(f"moves.bin 学习等级越界（应 1~100）："
                         f"{mva['bad_level'][:10]}")
        if mva["truncated_species"]:
            fails.append(f"moves.bin {len(mva['truncated_species'])} 只的学习表"
                         f"区间超出段③：{mva['truncated_species'][:10]}")
        if mva["orphan_learn_entries"]:
            fails.append(f"moves.bin 段③ 有 {mva['orphan_learn_entries']} 条"
                         f"无人引用的孤儿条目")
        if mva["reserved_dirty"]:
            fails.append(f"moves.bin {len(mva['reserved_dirty'])} 招 reserved 非零")

    if fails:
        print("\n❌ 断言失败：")
        for f in fails:
            print(f"   · {f}")
        return 1
    print("\n✅ 全部断言通过（字库覆盖、无空白字形、sprite 齐全、定长自洽"
          + ("、招式表自洽" if mv else "") + "）")
    if mv and mva.get("font_missing"):
        # 不是断言失败：字库重建是招式入库之后的下一步。
        # 但必须显眼 —— 否则真机上招式名会整片空白，且要打到那一屏才发现。
        print(f"⚠️  但招式名还缺 {len(mva['font_missing'])} 个字未进字库："
              f"{mva['font_missing']}")
        print(f"   → 下一步跑 convert_font.py 把招式名收进 font16.bin")
    return 0


if __name__ == "__main__":
    sys.exit(main())
