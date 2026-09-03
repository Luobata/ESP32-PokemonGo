#!/usr/bin/env python3
"""玩法原型 —— 用真实采集数据驱动养成 + 遭遇逻辑。

用法：
    python3 sim/prototype.py data/raw/day1.ndjson
    python3 sim/prototype.py data/raw/day1.ndjson --only-24g --speed 60
    python3 sim/prototype.py --synthetic --days 7      # 无采集数据时用合成节律

价值：状态下降速率、遭遇频率这些参数，在硬件上迭代一轮要一天，
在这里是几秒（docs/07-roadmap.md#71）。
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gameplay import (  # noqa: E402
    SPECIES_COUNT, Encounter, PetState, classify_biome, roll_encounter,
)
from sensing import (  # noqa: E402
    AP, MOVING, Scan, SensingCore, load_ndjson,
)


def fmt_ts(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def is_night(ts: int) -> bool:
    h = datetime.fromtimestamp(ts).hour
    return h >= 23 or h < 7


# 基地遭遇间隔（秒）。驻留时按时间排程，保证窝在家里也有产出。
# 4 小时 ≈ 一天 6 次，配合猎场的密集遭遇，总量落在 10~30 次/天的目标区间。
BASE_SPAWN_INTERVAL = 4 * 3600


# ---------------------------------------------------------------------------
# 合成数据 —— 没有真实采集时用来跑通逻辑
# ---------------------------------------------------------------------------

def synthetic_scans(days: int, interval: int = 300) -> list[Scan]:
    """合成一份「家 → 通勤 → 公司 → 通勤 → 家」的日节律。

    这不能替代真实采集（AP 分布是编的），但足以验证养成曲线与遭遇频率。
    """
    rng = random.Random(42)
    scans: list[Scan] = []
    ts = int(datetime(2026, 9, 1, 0, 0).timestamp())

    def make_aps(prefix: str, n: int, auth: str, ssid: str) -> list[AP]:
        return [
            AP(bssid=f"{prefix}:{i:02x}:{i*7%256:02x}:{i*13%256:02x}",
               ssid=ssid, rssi=-45 - rng.randint(0, 35),
               channel=rng.choice([1, 6, 11]), auth=auth)
            for i in range(n)
        ]

    home = make_aps("50:64:2b", 4, "wpa2", "HomeWiFi")
    office = make_aps("00:74:9c", 12, "wpa2-ent", "Corp-Net")

    for d in range(days):
        for hour in range(24):
            for _ in range(3600 // interval):
                if 9 <= hour < 10 or 19 <= hour < 20:
                    # 通勤：每次扫到一批完全不同的 AP（猎场）
                    aps = make_aps(f"a4:83:{rng.randint(0,255):02x}",
                                   rng.randint(3, 8), "wpa2", "")
                elif 10 <= hour < 19:
                    aps = office
                else:
                    aps = home
                scans.append(Scan(ts=ts, aps=list(aps)))
                ts += interval
    return scans


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description="玩法原型：养成 + 遭遇")
    p.add_argument("files", nargs="*", help="NDJSON 采集文件")
    p.add_argument("--synthetic", action="store_true",
                   help="用合成日节律代替真实采集")
    p.add_argument("--days", type=int, default=7, help="合成模式的天数（默认 7）")
    p.add_argument("--only-24g", action="store_true", help="只保留 2.4GHz")
    p.add_argument("--auto-care", action="store_true", default=True,
                   help="模拟玩家每天照料（默认开启）")
    p.add_argument("--no-care", dest="auto_care", action="store_false",
                   help="不照料 —— 看消沉机制是否如预期不清零")
    p.add_argument("--verbose", "-v", action="store_true", help="打印每次遭遇")
    args = p.parse_args()

    # 数据来源
    if args.synthetic or not args.files:
        if not args.synthetic:
            print("未指定采集文件，使用合成数据。真实采集见 tools/collector/\n",
                  file=sys.stderr)
        scans = synthetic_scans(args.days)
        print(f"合成 {args.days} 天日节律：{len(scans)} 次扫描\n", file=sys.stderr)
    else:
        scans = []
        for f in args.files:
            if not os.path.exists(f):
                print(f"错误：找不到 {f}", file=sys.stderr)
                return 1
            scans.extend(load_ndjson(f))
        scans.sort(key=lambda s: s.ts)
        print(f"读取 {len(scans)} 次扫描\n", file=sys.stderr)

    if not scans:
        print("错误：没有数据", file=sys.stderr)
        return 1

    # 初始化
    core = SensingCore(only_24g=args.only_24g)
    pet = PetState(species_id=4, type_name="火")   # 初代 #4，未命名 → 显示物种名

    encounters: list[Encounter] = []
    prev_motion_events = 0
    last_care_slot: tuple = ()
    last_base_bucket = -1
    despondent_spans = 0
    was_despondent = False
    daily_log: list[tuple[str, int, int, float]] = []
    cur_day = None
    day_enc = 0

    for scan in scans:
        r = core.feed(scan)

        # 推进养成
        new_events = r.motion_events - prev_motion_events
        prev_motion_events = r.motion_events
        pet.advance(r.ts, motion_events=new_events, is_night=is_night(r.ts))
        for _ in range(new_events):
            pet.on_motion_event()

        if r.is_new_place:
            pet.on_new_place()

        # 消沉统计
        if pet.is_despondent and not was_despondent:
            despondent_spans += 1
        was_despondent = pet.is_despondent

        # 模拟玩家照料：一天摸设备三次（早/午/晚），符合 30 秒会话的设定。
        # 一天一次抵不过衰减 —— 这是原型跑出来的结论，不是拍的。
        dt = datetime.fromtimestamp(r.ts)
        day = dt.timetuple().tm_yday
        care_slot = (day, dt.hour // 8)   # 每 8 小时一个照料窗口
        if args.auto_care and care_slot != last_care_slot:
            pet.feed()
            pet.play()
            last_care_slot = care_slot

        # 日切记录
        if cur_day is None:
            cur_day = day
        elif day != cur_day:
            daily_log.append((fmt_ts(r.ts)[:5], day_enc, pet.explore_value, pet.mood))
            cur_day, day_enc = day, 0

        # 遭遇判定
        aps = scan.only_24g().aps if args.only_24g else scan.aps
        biome = classify_biome(aps)

        # 猎场（移动中）：瞬现 AP 直接映射为遭遇，密集
        # 基地（驻留）：按时间排程，稀少但永不断流
        #
        # 基地必须按时间而非移动量驱动 —— 这是 docs/02-sensing.md#20 的核心取向：
        # 让时间生产内容、空间调制内容。否则窝在家里一整天将毫无产出，
        # 而「设备永远不会没东西可看」正是这个设计要保证的事。
        trigger = None
        if r.state == MOVING and r.transient_aps > 0 and aps:
            trigger = (aps[r.ts % len(aps)], True)
        elif aps and r.ts // BASE_SPAWN_INTERVAL != last_base_bucket:
            last_base_bucket = r.ts // BASE_SPAWN_INTERVAL
            trigger = (aps[r.ts % len(aps)], False)

        if trigger:
            ap, transient = trigger
            enc = roll_encounter(
                bssid=ap.bssid, ssid=ap.ssid, rssi=ap.rssi, auth=ap.auth,
                ts=r.ts, biome=biome, is_transient=transient,
                pet_type=pet.type_name,
            )
            encounters.append(enc)
            day_enc += 1
            if args.verbose:
                tag = "猎场" if transient else "基地"
                print(f"{fmt_ts(r.ts)}  [{tag}] {biome:<6} "
                      f"#{enc.species_id:<4} {enc.type_name:<3} {enc.rarity_stars}")

    # ---- 报告 ----
    span_days = (scans[-1].ts - scans[0].ts) / 86400.0

    print("=" * 62)
    print("玩法原型结果")
    print("=" * 62)

    print(f"\n模拟时长      {span_days:.1f} 天")
    print(f"扫描次数      {len(scans)}")

    from naming import display_name
    name = display_name(pet.nickname_idx, "小火龙")
    print(f"\n【主宠】{name}（#{pet.species_id} {pet.type_name}系）")
    print(f"  {pet.bars()}")
    print(f"  状态 {pet.mood_label}　亲密度 {pet.intimacy:.1f}　"
          f"探索值 {pet.explore_value}")
    print(f"  能力系数 {pet.ability_factor:.2f}　"
          f"捕获窗口 ×{pet.catch_window_bonus:.2f}")
    print(f"  可进化 {'是' if pet.can_evolve() else '否'}"
          f"（需亲密度 60 且探索值 50）")

    print(f"\n【遭遇】共 {len(encounters)} 次"
          f"（{len(encounters)/max(span_days,0.01):.1f} 次/天）")
    hunt = sum(1 for e in encounters if e.is_transient)
    print(f"  猎场 {hunt}　基地 {len(encounters)-hunt}")

    if encounters:
        by_rarity: dict[int, int] = {}
        by_type: dict[str, int] = {}
        by_biome: dict[str, int] = {}
        for e in encounters:
            by_rarity[e.rarity] = by_rarity.get(e.rarity, 0) + 1
            by_type[e.type_name] = by_type.get(e.type_name, 0) + 1
            by_biome[e.biome] = by_biome.get(e.biome, 0) + 1

        print("\n  稀有度分布")
        for r_ in sorted(by_rarity):
            n = by_rarity[r_]
            print(f"    {'★'*r_+'☆'*(5-r_)}  {n:>4}（{n/len(encounters)*100:>4.1f}%）")

        print("\n  属性 TOP5")
        for t, n in sorted(by_type.items(), key=lambda kv: -kv[1])[:5]:
            mark = " ←主宠属性" if t == pet.type_name else ""
            print(f"    {t:<4} {n:>4}{mark}")

        print("\n  biome 分布")
        for b, n in sorted(by_biome.items(), key=lambda kv: -kv[1]):
            print(f"    {b:<8} {n:>4}")

        uniq = len({e.species_id for e in encounters})
        print(f"\n  不同种类 {uniq} / {SPECIES_COUNT}")

    print(f"\n【感知】地点 {len(core.memory.places)} 个　"
          f"转换 {core.motion.transitions} 次　"
          f"移动量事件 {core.motion_events} 次")

    print(f"\n【消沉】进入 {despondent_spans} 次"
          f"（当前{'消沉中' if pet.is_despondent else '正常'}）")
    if not args.auto_care:
        print("  未照料模式：验证「能力打折但不清零」——"
              f"探索值仍为 {pet.explore_value}，存档完好")

    if daily_log:
        print(f"\n【每日】{'日期':<7}{'遭遇':>5}{'探索值':>7}{'心情':>7}")
        for d, e, ev, mo in daily_log[:14]:
            print(f"       {d:<7}{e:>5}{ev:>7}{mo:>7.1f}")

    print("\n" + "-" * 62)
    print("怎么读（调参入口在 sim/gameplay.py 顶部常量）：")
    print("  · 遭遇 10~30 次/天较合适。太多会腻，太少会闲")
    print("  · 照料模式下不该长期消沉；不照料时应能消沉但探索值不清零")
    print("  · 主宠属性应在 TOP5 里 —— 验证「带谁出门」的决策有效")
    print("  · ★★★★★ 应当罕见（< 5%）")
    print("-" * 62)

    return 0


if __name__ == "__main__":
    sys.exit(main())
