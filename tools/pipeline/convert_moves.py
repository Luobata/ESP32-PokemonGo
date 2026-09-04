#!/usr/bin/env python3
"""初代伤害招 + 红蓝升级学习表 → 固件用的紧凑二进制。

用法：
    python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1c
    python3 tools/pipeline/convert_moves.py --src /tmp/gen1c --out assets/

产出：
    moves.bin   招式定长表 + 学习表 + 中文名字符串池（一个文件三段）

## 为什么三段放同一个文件

学习表本可以单独一个文件，但固件的访问模式决定了不该拆：
战斗开始时要做的事是「给定 species_id 与等级，算出这只现在会哪几招」——
这需要**先查学习表拿到 move_id，再立刻查招式表拿威力/属性**，
两段总是一起用。放同一个文件意味着一次 mmap / 一次 flash 分区映射，
拆开则要维护两个 base 指针，且两者版本可能漂移（改了一个忘改另一个）。

一个文件里用「段目录」隔开，各段仍可独立定长索引，没有损失。

## 布局（全部小端）

    off   size  field
    ---- 文件头 16 B ----
    0     4     magic          "MOVE"
    4     2     version        = 1
    6     2     move_rec_size  单条招式记录字节数 = 12
    8     2     move_count     伤害招条数
    10    2     species_count  学习表覆盖的物种数 = 151
    12    2     learn_count    学习表条目总数
    14    2     pool_size      中文名字符串池字节数

    ---- 段① 招式表：move_count × 12 B，按 move_id 升序**紧密排列** ----
    off   size  field
    0     2     move_id        PokeAPI 的招式 id（1~165，有缺号）
    2     2     zh_offset      中文名在字符串池的偏移
    4     1     zh_len         中文名 UTF-8 字节数
    5     1     type           属性编号，与 sim/gameplay.py TYPES 下标一致
    6     1     power          威力 1~255（初代最大 200 self-destruct→130）
    7     1     accuracy       命中 0~100；**255 = 必中**（swift 电光）
    8     1     pp             1~40
    9     1     damage_class   0=物理 1=特殊
    10    2     reserved       预留：附加效果 id、优先度

    ---- 段② 物种索引：species_count × 4 B，按 (species_id-1) 直接索引 ----
    off   size  field
    0     2     learn_offset   该物种在段③的**起始条目下标**
    2     1     learn_count    该物种的学习表条目数
    3     1     reserved

    ---- 段③ 学习表：learn_count × 2 B，同一物种内按 level 升序 ----
    off   size  field
    0     1     level          学会等级 1~100
    1     1     move_slot      该招在**段①里的下标**（不是 move_id）

    ---- 段④ 字符串池：pool_size B，UTF-8 中文名紧密排列 ----

## 三个寻址决策，都为了固件那一个访问模式

**① 段①按 move_id 紧密排列，而不是 (base + move_id*12) 稀疏索引。**
初代 165 招里只有 ~一半是伤害招，稀疏表要按最大 move_id 开数组，
一半的槽位是空洞。改成紧密排列 + 段③存**段内下标**，
固件拿到 slot 就是 `moves_base + slot*12`，仍然是 O(1)，且没有空洞。
代价是「已知 move_id 反查记录」要二分 —— 但固件不需要这个方向，
它永远是从学习表出发。

**② 段②按 species_id 直接索引**，这是访问模式的入口：
`idx = species_base + (species_id-1)*4` 一步拿到 (offset, count)。

**③ 段③同一物种内按 level 升序**，所以「Lv≤N 的全部招式」
就是从 learn_offset 开始**顺序扫到 level > N 为止**，
不需要读完整段再过滤，也不需要二分。这正是战斗开始时要做的事。

## 属性编号与 gen1.bin 同一套

type 字段直接用 sim/gameplay.py TYPES 的下标（一般=0 火=1 ... 龙=14），
与 gen1.bin 的 type_primary **同一套编号**，固件算属性相克时
两边的值可以直接比较，不做二次映射。

## 关于字节数

convert_gen1.py 有过教训：标题注释把 32 字节写成 28，照抄那个寻址公式
会让固件记录错位，而错位后读出的仍是合法数值（威力、属性都在 0~255 内），
不会崩，只会全都是错的。所以本文件的每个 size 都由 struct.calcsize
在运行时断言过（见 MOVE_REC_FMT 下方），注释与实际不可能漂移。
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import struct
import sys

# ---------------------------------------------------------------------------
# 属性编号 —— **必须与 sim/gameplay.py 的 TYPES 下标一致**
#
# 不 import sim/gameplay.py 是有意的：那边是中文名列表，这边要英文 slug
# 做键。但两者的**顺序**必须一致，所以下面用一个断言把它钉死 ——
# 顺序一旦漂移，转换直接失败，而不是产出错误编号的二进制。
# ---------------------------------------------------------------------------

GEN1_TYPES = [
    "normal", "fire", "water", "electric", "grass", "ice",
    "fighting", "poison", "ground", "flying", "psychic",
    "bug", "rock", "ghost", "dragon",
]
TYPE_ID = {t: i for i, t in enumerate(GEN1_TYPES)}

# 与 sim/gameplay.py TYPES 的对应中文名，顺序必须逐项相同
GEN1_TYPES_CN = [
    "一般", "火", "水", "电", "草", "冰",
    "格斗", "毒", "地面", "飞行", "超能",
    "虫", "岩石", "幽灵", "龙",
]

DAMAGE_CLASS_ID = {"physical": 0, "special": 1}

# 初代必中招（swift 电光）在 PokeAPI 里 accuracy=null。
# 存 0 会被固件读成「永远打不中」，所以用 255 显式表示必中。
ACC_ALWAYS_HIT = 255

MAGIC = b"MOVE"
VERSION = 1

MOVE_REC_FMT = "<HHBBBBBB2s"      # move_id zh_off zh_len type power acc pp dc rsv
SPECIES_REC_FMT = "<HBB"          # learn_offset learn_count reserved
LEARN_REC_FMT = "<BB"             # level move_slot
HEADER_FMT = "<4sHHHHHH"

MOVE_REC_SIZE = struct.calcsize(MOVE_REC_FMT)
SPECIES_REC_SIZE = struct.calcsize(SPECIES_REC_FMT)
LEARN_REC_SIZE = struct.calcsize(LEARN_REC_FMT)
HEADER_SIZE = struct.calcsize(HEADER_FMT)

# 标题注释里写的字节数必须与 struct 实际一致 —— 见文件头「关于字节数」。
# 这几行就是防 convert_gen1.py 那次「注释写 28、实际 32」重演的守护。
assert MOVE_REC_SIZE == 12, f"招式记录应为 12 B，实际 {MOVE_REC_SIZE}"
assert SPECIES_REC_SIZE == 4, f"物种索引应为 4 B，实际 {SPECIES_REC_SIZE}"
assert LEARN_REC_SIZE == 2, f"学习表条目应为 2 B，实际 {LEARN_REC_SIZE}"
assert HEADER_SIZE == 16, f"文件头应为 16 B，实际 {HEADER_SIZE}"

SPECIES_COUNT = 151


def check_type_order() -> None:
    """确认属性顺序与 sim/gameplay.py 一致。

    任务书要求「属性编码必须与 sim/gameplay.py 的 TYPES 列表下标一致」。
    这个要求靠人对着看是守不住的 —— 两个文件相距很远，改一个不会提醒另一个。
    所以每次转换都实测校验：读不到就跳过（sim/ 是队友在改的，不该硬依赖），
    读得到就逐项比对，不一致直接中止。
    """
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    sim = os.path.join(repo, "sim")
    if sim not in sys.path:
        sys.path.insert(0, sim)
    try:
        import gameplay
    except Exception as e:
        print(f"  注：读不到 sim/gameplay.py（{type(e).__name__}），"
              f"跳过属性顺序校验", file=sys.stderr)
        return

    actual = list(getattr(gameplay, "TYPES", []))
    if actual != GEN1_TYPES_CN:
        raise SystemExit(
            f"❌ 属性顺序与 sim/gameplay.py 不一致，产出的 type 编号会全错。\n"
            f"   gameplay.TYPES = {actual}\n"
            f"   本脚本预期      = {GEN1_TYPES_CN}")


def build_moves(moves: list[dict]) -> tuple[bytes, bytes, dict[str, int], dict]:
    """段① + 字符串池。返回 (记录, 池, {slug: slot}, 统计)。"""
    moves = sorted(moves, key=lambda m: m["id"])

    pool = bytearray()
    zh_pos: dict[str, tuple[int, int]] = {}
    # 中文名去重 —— 初代没有同名招，但去重是零成本的，
    # 且能让「池大小 == 去重后名字总长」这条断言成立。
    for m in moves:
        zh = m.get("zh") or ""
        if zh not in zh_pos:
            b = zh.encode("utf-8")
            zh_pos[zh] = (len(pool), len(b))
            pool += b

    slot_of: dict[str, int] = {}
    recs = bytearray()
    zh_missing: list[str] = []
    bad_type: list[str] = []
    clamped: list[str] = []

    for slot, m in enumerate(moves):
        slot_of[m["slug"]] = slot
        zh = m.get("zh") or ""
        if not zh:
            zh_missing.append(m["slug"])
        zoff, zlen = zh_pos[zh]

        t = m.get("type", "")
        if t not in TYPE_ID:
            # 还原后仍非初代属性 = fetch 的 retcon 逻辑没覆盖到，
            # 不能默默塞 0（那会让恶系招变成一般系，静默错误）。
            bad_type.append(f"{m['slug']}: {t}")

        power = m.get("power") or 0
        pp = m.get("pp") or 0
        acc = m.get("accuracy")
        acc = ACC_ALWAYS_HIT if acc is None else acc
        if power > 255 or pp > 255:
            clamped.append(f"{m['slug']}: power={power} pp={pp}")

        recs += struct.pack(
            MOVE_REC_FMT,
            m["id"], zoff, min(zlen, 255),
            TYPE_ID.get(t, 0xFF),
            min(power, 255),
            min(acc, 255),
            min(pp, 255),
            DAMAGE_CLASS_ID.get(m.get("damage_class", ""), 0xFF),
            b"\x00" * 2,
        )

    assert len(recs) == len(moves) * MOVE_REC_SIZE, \
        f"招式段长度 {len(recs)} != {len(moves)}×{MOVE_REC_SIZE}"

    return bytes(recs), bytes(pool), slot_of, {
        "count": len(moves),
        "zh_missing": zh_missing,
        "bad_type": bad_type,
        "clamped": clamped,
        "pool": len(pool),
        "zh_unique": len(zh_pos),
    }


def build_learnsets(mons: list[dict],
                    slot_of: dict[str, int]) -> tuple[bytes, bytes, dict]:
    """段② + 段③。返回 (物种索引, 学习表, 统计)。"""
    by_id = {m["id"]: m for m in mons}

    species_recs = bytearray()
    learn_recs = bytearray()
    dropped_status: collections.Counter = collections.Counter()
    empty_species: list[int] = []
    over_255: list[str] = []
    total_kept = 0

    for sid in range(1, SPECIES_COUNT + 1):
        mon = by_id.get(sid)
        entries: list[tuple[int, int]] = []

        for lv, slug in (mon or {}).get("learnset", []):
            slot = slot_of.get(slug)
            if slot is None:
                # 变化招 —— fetch 保真存了全部，这里才丢。
                dropped_status[slug] += 1
                continue
            if lv > 255 or slot > 255:
                # move_slot 是 1 字节。初代伤害招约 80 个，远小于 255，
                # 但如果将来扩到二代就会溢出 —— 显式报出来而不是静默截断。
                over_255.append(f"#{sid} {slug} lv={lv} slot={slot}")
                continue
            entries.append((lv, slot))

        # 同一物种内按 level 升序 —— 固件靠这个顺序做「扫到 level>N 为止」
        entries.sort()

        start = len(learn_recs) // LEARN_REC_SIZE
        if len(entries) > 255:
            # learn_count 是 1 字节
            over_255.append(f"#{sid} 学习表 {len(entries)} 条超 255")
            entries = entries[:255]
        for lv, slot in entries:
            learn_recs += struct.pack(LEARN_REC_FMT, lv, slot)
        total_kept += len(entries)

        if not entries:
            empty_species.append(sid)

        species_recs += struct.pack(SPECIES_REC_FMT, start, len(entries), 0)

    assert len(species_recs) == SPECIES_COUNT * SPECIES_REC_SIZE, \
        f"物种索引段长度 {len(species_recs)} != {SPECIES_COUNT}×{SPECIES_REC_SIZE}"
    assert len(learn_recs) == total_kept * LEARN_REC_SIZE, \
        f"学习表段长度 {len(learn_recs)} != {total_kept}×{LEARN_REC_SIZE}"

    return bytes(species_recs), bytes(learn_recs), {
        "learn_count": total_kept,
        "dropped_status_kinds": len(dropped_status),
        "dropped_status_total": sum(dropped_status.values()),
        "dropped_top": dropped_status.most_common(10),
        "empty_species": empty_species,
        "over_255": over_255,
        "covered": SPECIES_COUNT - len(empty_species),
    }


def build(moves: list[dict], mons: list[dict]) -> tuple[bytes, dict]:
    mrecs, pool, slot_of, mstat = build_moves(moves)
    srecs, lrecs, lstat = build_learnsets(mons, slot_of)

    header = struct.pack(
        HEADER_FMT, MAGIC, VERSION, MOVE_REC_SIZE,
        mstat["count"], SPECIES_COUNT, lstat["learn_count"], len(pool))

    blob = header + mrecs + srecs + lrecs + pool
    expect = (HEADER_SIZE + len(mrecs) + len(srecs) + len(lrecs) + len(pool))
    assert len(blob) == expect, f"总长 {len(blob)} != {expect}"

    st = dict(mstat)
    st.update(lstat)
    st.update({
        "header_bytes": HEADER_SIZE,
        "move_bytes": len(mrecs),
        "species_bytes": len(srecs),
        "learn_bytes": len(lrecs),
        "pool_bytes": len(pool),
        "total": len(blob),
    })
    return blob, st


def crosscheck(blob: bytes, moves: list[dict], mons: list[dict],
               ids: list[int]) -> list[str]:
    """独立重解二进制，与源 json 对账。

    这里**不复用 build 的中间变量**，而是按文件头声明的偏移硬解 ——
    复用中间变量只能验证"我写的和我想的一致"，硬解才能验证
    "写出去的和源数据一致"。错位这类缺陷只有硬解才抓得到。
    """
    out: list[str] = []
    (magic, ver, rsz, mcnt, scnt, lcnt, poolsz) = struct.unpack(
        HEADER_FMT, blob[:HEADER_SIZE])

    p = HEADER_SIZE
    mrecs = blob[p:p + mcnt * rsz]
    p += mcnt * rsz
    srecs = blob[p:p + scnt * SPECIES_REC_SIZE]
    p += scnt * SPECIES_REC_SIZE
    lrecs = blob[p:p + lcnt * LEARN_REC_SIZE]
    p += lcnt * LEARN_REC_SIZE
    pool = blob[p:p + poolsz]

    # 段① 逐条与源 json 对
    src_by_id = {m["id"]: m for m in moves}
    slot_to_id: dict[int, int] = {}
    for i in range(mcnt):
        (mid, zo, zl, ty, pw, ac, pp, dc, _r) = struct.unpack(
            MOVE_REC_FMT, mrecs[i * rsz:(i + 1) * rsz])
        slot_to_id[i] = mid
        s = src_by_id.get(mid)
        if not s:
            out.append(f"段① slot{i} move_id={mid} 源数据里没有")
            continue
        zh = pool[zo:zo + zl].decode("utf-8", "replace")
        if zh != (s.get("zh") or ""):
            out.append(f"段① {s['slug']} 中文名 {zh!r} != {s.get('zh')!r}")
        if pw != min(s["power"], 255):
            out.append(f"段① {s['slug']} 威力 {pw} != {s['power']}")
        if ty != TYPE_ID.get(s["type"], 0xFF):
            out.append(f"段① {s['slug']} 属性 {ty} != {s['type']}")
        want_acc = s["accuracy"] if s["accuracy"] is not None else ACC_ALWAYS_HIT
        if ac != min(want_acc, 255):
            out.append(f"段① {s['slug']} 命中 {ac} != {want_acc}")
        if pp != min(s["pp"], 255):
            out.append(f"段① {s['slug']} PP {pp} != {s['pp']}")

    # 段②③ 抽查指定物种，与源 json 的 learnset 对
    damage_slugs = {m["slug"] for m in moves}
    by_id = {m["id"]: m for m in mons}
    for sid in ids:
        mon = by_id.get(sid)
        if not mon:
            out.append(f"源数据里没有 #{sid}")
            continue
        o = (sid - 1) * SPECIES_REC_SIZE
        (loff, lcount, _rv) = struct.unpack(
            SPECIES_REC_FMT, srecs[o:o + SPECIES_REC_SIZE])

        got = []
        for k in range(lcount):
            q = (loff + k) * LEARN_REC_SIZE
            lv, slot = struct.unpack(LEARN_REC_FMT, lrecs[q:q + LEARN_REC_SIZE])
            mid = slot_to_id.get(slot)
            got.append((lv, (src_by_id.get(mid) or {}).get("slug", f"?{mid}")))

        want = sorted((lv, nm) for lv, nm in mon.get("learnset", [])
                      if nm in damage_slugs)
        # 二进制里同级招式的顺序由 slot 决定，源 json 由名字决定，
        # 所以比对时两边都按 (等级, 名字) 归一化
        if sorted(got) != want:
            out.append(f"#{sid} {mon['slug']} 学习表不符\n"
                       f"      解出 {sorted(got)}\n"
                       f"      源   {want}")
        # 只校验**等级**升序，不要求同级内的名字有序 ——
        # 同级招式在二进制里按 slot 排，在源 json 里按名字排，
        # 拿 (等级,名字) 元组整体比较会把「喷火龙 Lv1 学 scratch 与 ember」
        # 这种完全正确的数据判成乱序（实测踩过）。
        # 固件只依赖等级升序（扫到 Lv>N 为止），同级顺序无所谓。
        levels = [lv for lv, _ in got]
        if levels != sorted(levels):
            out.append(f"#{sid} {mon['slug']} 学习表等级未升序：{got}")

    return out


def main() -> int:
    p = argparse.ArgumentParser(description="初代招式 + 学习表 → 固件二进制")
    p.add_argument("--src", default="/tmp/gen1c", help="fetch_gen1.py 的输出目录")
    p.add_argument("--out", default="assets", help="输出目录")
    p.add_argument("--verify", default="1,4,7,6,25,143,150,132",
                   help="交叉验证这几只的学习表（逗号分隔的图鉴号）。"
                        "默认含 #6 喷火龙（有同级招）与 #132 百变怪（零伤害招）"
                        "—— 这两个边界各抓过一次缺陷")
    args = p.parse_args()

    check_type_order()

    moves_json = os.path.join(args.src, "moves.json")
    gen1_json = os.path.join(args.src, "gen1.json")
    for path in (moves_json, gen1_json):
        if not os.path.exists(path):
            print(f"错误：找不到 {path}。先跑 fetch_gen1.py", file=sys.stderr)
            return 1

    with open(moves_json, encoding="utf-8") as f:
        moves = json.load(f)
    with open(gen1_json, encoding="utf-8") as f:
        mons = json.load(f)

    print(f"读取 {len(moves)} 招伤害招、{len(mons)} 只")

    blob, st = build(moves, mons)

    os.makedirs(args.out, exist_ok=True)
    out_path = os.path.join(args.out, "moves.bin")
    with open(out_path, "wb") as f:
        f.write(blob)

    print(f"\n{out_path}")
    print(f"  文件头      {st['header_bytes']:>7} B")
    print(f"  段① 招式    {st['move_bytes']:>7} B  ({st['count']} × {MOVE_REC_SIZE})")
    print(f"  段② 物种索引 {st['species_bytes']:>6} B  "
          f"({SPECIES_COUNT} × {SPECIES_REC_SIZE})")
    print(f"  段③ 学习表  {st['learn_bytes']:>7} B  "
          f"({st['learn_count']} × {LEARN_REC_SIZE})")
    print(f"  段④ 字符串池 {st['pool_bytes']:>6} B  "
          f"（{st['zh_unique']} 个中文名）")
    print(f"  合计        {st['total']:>7} B = {st['total']/1024:.1f} KB")
    print(f"  占 8MB flash 的 {st['total']/(8*1024*1024)*100:.3f}%")

    print(f"\n学习表覆盖 {st['covered']}/{SPECIES_COUNT} 只")
    if st["empty_species"]:
        print(f"  ⚠️  无伤害招：{st['empty_species']}")
    print(f"  丢弃变化招条目 {st['dropped_status_total']} 条"
          f"（{st['dropped_status_kinds']} 种）")
    if st["dropped_top"]:
        print(f"  最常见：{', '.join(f'{k}×{v}' for k, v in st['dropped_top'][:6])}")

    if st["zh_missing"]:
        print(f"\n⚠️  中文名缺失 {len(st['zh_missing'])} 招：{st['zh_missing']}")
    else:
        print(f"\n中文名 {st['count']}/{st['count']} ✓")
    if st["bad_type"]:
        print(f"❌ 非初代属性 {len(st['bad_type'])} 招：{st['bad_type']}")
    if st["clamped"]:
        print(f"❌ 数值溢出被截断：{st['clamped']}")
    if st["over_255"]:
        print(f"❌ 学习表字段溢出：{st['over_255'][:5]}")

    # ---- 交叉验证 ----
    ids = [int(x) for x in args.verify.split(",") if x.strip()]
    print(f"\n== 交叉验证（独立重解二进制 vs 源 json）==")
    problems = crosscheck(blob, moves, mons, ids)
    if problems:
        print(f"❌ {len(problems)} 处不符：")
        for pr in problems[:20]:
            print(f"   · {pr}")
        return 1
    print(f"  段① {st['count']} 招逐条比对：威力/属性/命中/PP/中文名 全部一致 ✓")
    print(f"  段②③ 抽查 {ids}：学习表内容与等级顺序 全部一致 ✓")

    # 中文名用字 —— 下一步要进字库
    chars: set = set()
    for m in moves:
        chars |= set(m.get("zh") or "")
    print(f"\n中文名用字 {len(chars)} 个（需进 font16.bin）")
    print(f"  {''.join(sorted(chars))}")

    import collections as _c
    td: _c.Counter = _c.Counter(m["type"] for m in moves)
    print(f"\n伤害招属性分布")
    for t, n in td.most_common():
        bad = "" if t in TYPE_ID else "  ⚠️"
        print(f"  {t:<12}{n:>4}  (id={TYPE_ID.get(t, '?')}){bad}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
