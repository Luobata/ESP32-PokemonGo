"""S19 全流程编排 —— 把 18 个系统串成一局游戏。

对应 docs/systems/S19-orchestration.md。

## 为什么需要它

盘点模块引用关系发现：**8 个模块从未被任何代码调用过** ——
systems / state / gyms / autosave / intro / opening / transitions / audio
全是孤岛。它们只被验收平台的 build.py 读参数，
从没在一次运行里协同过。

`prototype.py` 是唯一的「跑一局」入口，但它只串了
gameplay + sensing + naming 三个。

后果不是「代码不整洁」，而是**系统之间的接缝从未被走过**：
时序错了、状态不一致、事件漏派，这些只有真的跑一遍才会暴露。

这个模块就是那一遍。

## 它做什么

    ① 开场：GB 启动动画 → 博士台词 → 选伙伴 → 建档
    ② 循环：喂扫描数据 → 感知 → 遭遇 → 战斗/捕获 → 收容 → 存档
    ③ 长线：徽章解锁判定、进化检查、日切结算
    ④ 收尾：关机存档

每一步都派发 autosave 事件 —— 这是 S18 唯一的接入点，
不派事件的系统就等于不存档。

## 设计取向

**编排层不含规则**。它只负责调用顺序与事件派发；
所有判定仍在各自系统里。这样固件移植时可以照抄这个顺序，
而不用重新推导「先算掉落还是先收容」这类问题。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Optional

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import gyms as GY                                       # noqa: E402
import intro as IN                                      # noqa: E402
import opening as OP                                    # noqa: E402
import transitions as TR                                # noqa: E402
from autosave import AutoSave                           # noqa: E402
from gameplay import Encounter, PetState, classify_biome  # noqa: E402
from naming import display_name                         # noqa: E402
from party import Mon, Party                            # noqa: E402
from sensing import SensingCore, Scan                   # noqa: E402
from state import DailyCounters, Dex, DualBufferSave, Inventory, Records, SaveData  # noqa: E402
from systems import (                                   # noqa: E402
    BALL_NAME_CN, CaptureResult, EncounterAccumulator, attempt_capture,
    auto_battle, check_evolution, consume_ball, do_evolve, feed_pet,
    grant_berry, pointer_position, resolve_capture, wild_level, window_width,
)

# ---------------------------------------------------------------------------
# 一局游戏的完整状态
# ---------------------------------------------------------------------------

# 判为「一次访问」所需的连续扫描次数。
# 10 次 × 30 秒 ≈ 5 分钟 —— 实测这个阈值把访问数从 222 段降到
# 住宅区 2 / 办公区 19，与直觉相符（一天进出办公区十几次：
# 会议室、楼层、楼下咖啡）。
#
# 阈值太低（≤4）会把抖动算进来；太高（≥20）会漏掉真实的短途访问。
VISIT_MIN_SCANS = 10

PHASE_BOOT = "boot"            # GB 启动动画
PHASE_STORY = "story"          # 博士台词
PHASE_CHOOSE = "choose"        # 选伙伴
PHASE_PLAY = "play"            # 日常循环
PHASE_OVER = "over"            # 关机


@dataclass
class LogEntry:
    """一条流程日志 —— 验收平台按它渲染时间线。"""

    ts: int
    kind: str                  # 事件类别
    text: str                  # 人读的说明
    detail: dict = field(default_factory=dict)


@dataclass
class Session:
    """一局游戏。

    这个类持有**全部**可变状态。固件侧对应一个全局结构体 ——
    刻意不用模块级全局变量，那会让「哪些状态要存档」变得不明确。
    """

    # 系统实例
    core: SensingCore = field(default_factory=lambda: SensingCore(only_24g=True))
    acc: Optional[EncounterAccumulator] = None
    party: Party = field(default_factory=Party)
    dex: Dex = field(default_factory=Dex)
    inventory: Inventory = field(default_factory=Inventory)
    records: Records = field(default_factory=Records)
    day: DailyCounters = field(default_factory=DailyCounters)
    pet: Optional[PetState] = None
    dual: DualBufferSave = field(default_factory=DualBufferSave)
    auto: Optional[AutoSave] = None

    # 进度
    phase: str = PHASE_BOOT
    badges: int = 0
    elite_done: bool = False
    red_done: bool = False
    day_index: int = 0
    berry_last_grant: int = 0
    ts: int = 0
    # 各 biome 的**访问次数** —— S17 第 6、7 馆用它而非累计驻留。
    #
    # 感知层不提供这个（它只管驻留时长），所以在编排层数。
    # 但**不能简单地「biome 变了就 +1」** —— 实测那样一天能刷出
    # 野外 103 次、办公区 107 次访问，而实际驻留只有 0.9h / 5.2h。
    #
    # 原因：classify_biome 是逐帧判定，边界会抖动。实测 1061 次扫描
    # 产生 222 个连续段，其中 **66% 只持续 1 次扫描** ——
    # 那些是抖动，不是真的去了那个地方（日志里能看到 ('野外',1)
    # ('商业区',1) 反复穿插在办公区中间）。
    #
    # 修法与感知层当初修移动误报同源：**瞬时判定不可信，要看持续性**。
    # 连续 VISIT_MIN_SCANS 次扫描判为同一 biome 才算一次访问。
    biome_visits: dict = field(default_factory=dict)
    cand_biome: str = ""            # 候选 biome（还没确认成访问）
    cand_count: int = 0
    confirmed_biome: str = ""       # 已确认的当前 biome

    # 日志
    log: list = field(default_factory=list)

    def say(self, kind: str, text: str, **detail) -> None:
        self.log.append(LogEntry(ts=self.ts, kind=kind, text=text,
                                 detail=detail))

    # -- 存档数据视图 -------------------------------------------------------

    def snapshot(self) -> SaveData:
        """当前状态打包成 SaveData。

        注意 pet_* 字段与 party[0] 的关系：**party[0] 是权威**，
        pet_* 只是它的镜像 + 三条轴。每次快照都从 party[0] 重新取，
        避免两者漂移（S14 的设计要点）。
        """
        sd = SaveData()
        leader = self.party.leader
        if leader:
            sd.pet_species = leader.species_id
            sd.pet_level = leader.level
            sd.pet_hp = leader.hp
            sd.nickname_idx = leader.nickname_idx
        if self.pet:
            sd.satiety = int(self.pet.satiety)
            sd.mood = int(self.pet.mood)
            sd.stamina = int(self.pet.stamina)
            sd.intimacy = int(self.pet.intimacy)
            sd.explore_value = self.pet.explore_value
        sd.dex = self.dex
        sd.inventory = self.inventory
        sd.records = self.records
        sd.party = self.party
        sd.day_index = self.day_index
        sd.biome_dwell = [self.core.memory.biome_dwell.get(b, 0)
                          for b in ("野外", "住宅区", "办公区", "商业区",
                                    "交通枢纽")]
        return sd

    def fire(self, event: str) -> bool:
        """派发存档事件。**每个改变状态的动作都要调它** ——
        不派事件的系统就等于不存档（S18）。"""
        if not self.auto:
            return False
        return self.auto.on_event(event, self.ts, self.snapshot())


# ---------------------------------------------------------------------------
# ① 开场
# ---------------------------------------------------------------------------

def run_intro(s: Session, choice: int = 3, skip_story: bool = False) -> None:
    """开场三段：启动动画 → 台词 → 选伙伴。

    choice 是 IN.STARTERS 的下标（默认 3 = 皮卡丘）。
    """
    boot = IN.boot_sequence()
    sounds = [f.step for f in boot if f.sound]
    s.say("boot", f"GB 启动动画 {len(boot)} 帧，音效在第 {sounds} 步落定",
          frames=len(boot), sounds=sounds)

    s.phase = PHASE_STORY
    if skip_story:
        s.say("story", "跳过台词（C 键）")
    else:
        flow = OP.OpeningFlow()
        for i, box in enumerate(OP.SCRIPT):
            s.say("story", " / ".join(box.lines), box=i + 1)
        s.say("story", f"共 {len(OP.SCRIPT)} 框 "
                       f"{OP.total_frames() / 30:.1f} 秒")

    s.phase = PHASE_CHOOSE
    st = IN.STARTERS[choice]
    init = IN.apply_choice(choice)

    # 建档：伙伴入队伍 + 三条轴起点 + 初始道具 + 图鉴
    mon = Mon(species_id=init["pet_species"], level=init["pet_level"],
              hp=100, nickname_idx=init["nickname_idx"])
    s.party.receive(mon)
    s.pet = PetState(species_id=mon.species_id, type_name=init["pet_type"],
                     satiety=float(init["satiety"]), mood=float(init["mood"]),
                     stamina=float(init["stamina"]))
    s.pet.advance(s.ts)                      # 立时间基准
    for k, v in init["items"].items():
        setattr(s.inventory, k, v)
    for sid in init["dex_caught"]:
        s.dex.mark_caught(sid)

    s.acc = EncounterAccumulator(stats_sum=_stats_sum())
    s.auto = AutoSave(s.dual)
    s.auto.last_periodic_ts = s.ts
    s.auto.last_write_ts = s.ts

    s.say("choose", f"选定 {st['zh']}（{st['type']}系 Lv{mon.level}）",
          species=mon.species_id)
    s.fire("starter_chosen")                 # 存档的诞生
    s.phase = PHASE_PLAY


_STATS_CACHE: dict = {}


def _stats_sum() -> dict:
    """151 只的种族值总和 —— species_pool 分档要用。

    从 assets/gen1.bin 读（入库产物），不依赖 /tmp 中间文件 ——
    那个教训见 convert_font.py 的注释。
    """
    if _STATS_CACHE:
        return _STATS_CACHE
    import pathlib
    import struct
    p = pathlib.Path(__file__).resolve().parent.parent / "assets" / "gen1.bin"
    if not p.exists():
        # 没有资产时给个均匀分布，让流程仍能跑
        return {i: 300 for i in range(1, 152)}
    d = p.read_bytes()
    magic, ver, rsz, cnt, poolsz = struct.unpack("<4sHHII", d[:16])
    recs = d[16:16 + cnt * rsz]
    for i in range(cnt):
        o = i * rsz
        hp, at, df, sp, spd = struct.unpack("<BBBBB", recs[o + 9:o + 14])
        _STATS_CACHE[i + 1] = hp + at + df + sp + spd
    return _STATS_CACHE


# ---------------------------------------------------------------------------
# ② 日常循环
# ---------------------------------------------------------------------------

def feed_scan(s: Session, scan: Scan) -> None:
    """喂一次扫描。这是整个游戏的心跳。

    顺序照固件的实际流程：
      感知 → 遭遇累积 → 三条轴推进 → 浆果产出 → 存档 tick
    """
    s.ts = scan.ts
    res = s.core.feed(scan)
    # biome 要自己算 —— SensingResult 不含它（感知层只管「这是哪」，
    # 不管「这是什么地方」）。第一次串联就撞在这个假设上。
    band = scan.only_24g()
    raw_biome = classify_biome(band.aps)
    # BIOME_UNKNOWN（AP 太少判不了）→ 沿用上次结果。
    # 这是 classify_biome 的契约：它宁可说「不知道」也不猜。
    biome = raw_biome or s.confirmed_biome or s.cand_biome

    # 三条轴：advance 只需要「过了多久」（S4）
    if s.pet:
        s.pet.advance(scan.ts, motion_events=1 if res.state == "moving" else 0)

    # 浆果：驻留时按时间产出（S9）
    if res.state == "staying":
        dwell = sum(s.core.memory.biome_dwell.values())
        s.berry_last_grant, got = grant_berry(s.inventory, dwell,
                                              s.berry_last_grant)
        if got:
            s.say("item", f"驻留产出浆果 ×{got}")
            s.fire("item_drop")

    # biome 访问计数 —— 要连续 VISIT_MIN_SCANS 次才算，见 Session 的注释
    if biome:
        if biome == s.cand_biome:
            s.cand_count += 1
        else:
            s.cand_biome, s.cand_count = biome, 1
        if (s.cand_count >= VISIT_MIN_SCANS
                and s.cand_biome != s.confirmed_biome):
            s.confirmed_biome = s.cand_biome
            s.biome_visits[s.cand_biome] = \
                s.biome_visits.get(s.cand_biome, 0) + 1
            s.say("biome", f"进入{s.cand_biome}"
                           f"（连续 {s.cand_count} 次扫描确认）")

    if res.is_new_place:
        s.day.new_places += 1
        s.say("place", f"发现新地点（{biome}）", biome=biome)
        s.fire("place")

    if res.state == "moving":
        s.day.motion_events += 1
        s.fire("motion")

    # 遭遇
    if s.acc and s.pet:
        before = len(s.acc.queue.items)
        s.acc.feed(res, scan.only_24g(), s.pet)
        if len(s.acc.queue.items) > before:
            qe = s.acc.queue.items[-1]
            s.records.on_encounter(qe.enc.biome, qe.rarity, qe.is_shiny, s.day)
            tag = "✦闪光 " if qe.is_shiny else ""
            s.say("encounter",
                  f"{tag}遭遇 #{qe.species_id} "
                  f"{'★' * qe.rarity} @{qe.enc.biome}",
                  species=qe.species_id, rarity=qe.rarity,
                  shiny=qe.is_shiny)
            if qe.is_shiny:
                s.dex.mark_seen(qe.species_id, shiny=True)
                s.fire("shiny_seen")         # 立即存 —— 那份运气不能丢
            else:
                s.fire("encounter")

    if s.auto:
        s.auto.tick(s.ts, s.snapshot())


def handle_encounter(s: Session, index: int = 0, do_battle: bool = True,
                     ball: str = "poke", press_offset_ms: int = 0) -> dict:
    """处理队列里第 index 条遭遇：转场 → 战斗 → 投球 → 收容。

    这是玩家的一次完整交互（30 秒会话的核心）。
    """
    if not s.acc or not s.acc.queue.items or not s.pet:
        return {"ok": False, "why": "队列是空的"}
    if not (0 <= index < len(s.acc.queue.items)):
        return {"ok": False, "why": "越界"}

    qe = s.acc.queue.items[index]
    leader = s.party.leader
    lv = wild_level(qe.rarity)

    # 转场：确定性选择（S15）—— 玩家能从转场认出对手强弱
    tr_name, tr_idx = TR.pick_transition(
        is_trainer=False, wild_level=lv,
        pet_level=leader.level if leader else 5, biome=qe.enc.biome)
    s.say("transition",
          f"转场「{TR.TRANSITIONS[tr_name]['zh']}」"
          f"（{TR.TRANSITIONS[tr_name]['frames']} 帧，bits={tr_idx:03b}）",
          name=tr_name)

    out = {"species": qe.species_id, "rarity": qe.rarity, "level": lv,
           "shiny": qe.is_shiny, "transition": tr_name}

    # 战斗（可选）—— 打残后捕获窗口加宽（S3 的削弱机制）
    if do_battle and leader:
        mons = _stats_sum()
        pet_stats = _base_stats(leader.species_id)
        wild_stats = _base_stats(qe.species_id)
        b = auto_battle([s.pet.type_name], pet_stats, leader.level,
                        [_type_of(qe.species_id)], wild_stats, lv,
                        s.pet.ability_factor)
        qe.hp_ratio = b.wild_hp_ratio
        out["battle"] = {"won": b.won, "rounds": len(b.rounds),
                         "wild_hp": b.wild_hp_ratio}
        s.say("battle",
              f"战斗 {len(b.rounds)} 回合 → {'胜' if b.won else '败'}"
              f"，野怪 HP {b.wild_hp_ratio}%")
        s.fire("battle")

    # 投球：**先扣球再判定**（S9）—— 投出去的球无论命中都消耗掉了
    if not consume_ball(s.inventory, ball):
        out["ok"] = False
        out["why"] = f"没有{BALL_NAME_CN.get(ball, ball)}了"
        s.say("capture", out["why"])
        return out

    cap_rate = _capture_rate(qe.species_id)
    w = window_width(cap_rate, s.pet.catch_window_bonus, ball, qe.hp_ratio)
    ptr = pointer_position(press_offset_ms)
    cap = attempt_capture(qe, cap_rate, s.pet, ball, press_offset_ms)

    o = resolve_capture(qe, cap, s.party, s.dex, s.inventory, level=lv,
                        is_new_place=False)
    out["window"] = w
    out["pointer"] = ptr
    out["caught"] = cap.caught
    out["stored"] = o.stored
    out["drops"] = o.drops

    if cap.caught and o.stored:
        s.records.on_capture(qe.species_id, qe.rarity, qe.is_shiny, s.day)
        s.say("capture",
              f"捕获 #{qe.species_id} Lv{lv} → {o.where}"
              f"{'（图鉴首次）' if o.dex_new else ''}")
        s.fire("capture")                    # 立即存
    elif cap.caught and not o.stored:
        s.say("capture", f"抓到了但收容失败：{o.store_note}")
    else:
        s.say("capture", f"未命中（指针 {ptr}，窗口 {w}px）"
                         f"{'，跑掉了' if cap.fled else ''}")

    if o.drops:
        s.say("item", f"掉落 {o.drops}")

    # 出队
    s.acc.queue.items.pop(index)
    return out


def care(s: Session, action: str = "feed") -> dict:
    """照料 —— 喂食消耗浆果（S9 + S4 的衔接）。"""
    if not s.pet:
        return {"ok": False, "why": "还没有伙伴"}
    if action == "feed":
        ok, why = feed_pet(s.inventory, s.pet)
    elif action == "play":
        s.pet.play()
        ok, why = True, "玩耍完成"
    elif action == "rest":
        s.pet.rest()
        ok, why = True, "休息完成"
    else:
        return {"ok": False, "why": "未知动作"}

    if ok:
        s.day.cared = True
        s.say("care", f"{action} → 饱食{s.pet.satiety:.0f} "
                      f"心情{s.pet.mood:.0f} 体能{s.pet.stamina:.0f}")
        s.fire("care")
    else:
        s.say("care", why)
    return {"ok": ok, "why": why}


def check_progress(s: Session) -> dict:
    """长线判定：进化条件 + 徽章解锁。

    这两件事都是「攒够了才告诉玩家」，所以每次交互后检查一次，
    而不是等玩家去某个页面查。
    """
    out: dict = {"evolve": None, "gym": None}

    # 进化（S7）
    leader = s.party.leader
    if leader and s.pet:
        info = _evo_info(leader.species_id)
        if info["to"]:
            c = check_evolution(s.pet, info["trigger"], info["to"],
                                info["level"],
                                biome_dwell=s.core.memory.biome_dwell,
                                item_hint=info["stone"])
            out["evolve"] = {"can": c.can, "why": c.reason,
                             "to": info["to"]}
            if c.can:
                s.say("evolve", f"可以进化 → #{info['to']}（{c.reason}）")

    # 徽章（S17）
    if s.badges < len(GY.GYMS):
        g = GY.GYMS[s.badges]
        c = GY.check_gym(g, s.badges, s.core.memory.biome_dwell,
                         s.records.total_encounters, s.dex.count("seen"),
                         biome_visits=s.biome_visits)
        out["gym"] = {"order": g.order, "leader": g.leader,
                      "can": c.can, "why": c.reason,
                      "progress": c.progress}
        if c.can:
            s.say("gym", f"可以挑战{g.leader}（{g.badge}）")
    return out


def challenge_gym(s: Session) -> dict:
    """挑战当前可打的道馆。

    简化：不逐只模拟对战，用队伍最强等级 vs 馆主最强等级判定。
    完整对战要等固件侧的 UI，而那不影响这里要验证的**串联**。
    """
    if s.badges >= len(GY.GYMS):
        return {"ok": False, "why": "八馆已通关"}
    g = GY.GYMS[s.badges]
    c = GY.check_gym(g, s.badges, s.core.memory.biome_dwell,
                     s.records.total_encounters, s.dex.count("seen"),
                     biome_visits=s.biome_visits)
    if not c.can:
        return {"ok": False, "why": c.reason, "progress": c.progress}

    strongest = s.party.strongest()
    my_lv = strongest.level if strongest else 5
    boss_lv = max(l for _, l in g.team)
    cap = GY.level_cap(s.badges)

    # 等级上限：超过的不听指挥（S17）
    usable = [m for m in s.party.party if m.level <= cap]
    if not usable:
        return {"ok": False,
                "why": f"队伍里没有 Lv{cap} 以下的（超过上限不听指挥）"}

    won = my_lv >= boss_lv - 6          # 留一点属性相克的余量
    if won:
        s.badges += 1
        s.say("gym", f"击败{g.leader}，取得{g.badge}！"
                     f"等级上限 → Lv{g.level_cap}")
        s.fire("badge")                  # 立即存
    else:
        s.say("gym", f"挑战{g.leader}失败（我方 Lv{my_lv} vs Lv{boss_lv}）")
    return {"ok": won, "badge": g.badge if won else None,
            "my_level": my_lv, "boss_level": boss_lv}


def roll_day(s: Session) -> dict:
    """日切结算（S10）。"""
    s.day_index += 1
    broken = s.records.roll_day(s.day_index, s.day,
                               s.pet.intimacy if s.pet else 0)
    ms = s.records.milestone()
    if ms and s.pet:
        s.pet.mood = min(100.0, s.pet.mood + 8.0)
    s.say("day", f"第 {s.day_index} 天结算："
                 f"遭遇{s.day.encounters} 捕获{s.day.captures} "
                 f"移动{s.day.motion_events}"
                 + (f"　打破纪录 {broken}" if broken else "")
                 + (f"　里程碑 {ms} 天" if ms else ""))
    s.day = DailyCounters()
    s.fire("care")            # 日切算延迟事件
    return {"day": s.day_index, "broken": broken, "milestone": ms}


def shutdown(s: Session) -> dict:
    """关机 —— 必存（S18）。"""
    s.phase = PHASE_OVER
    s.fire("sleep")
    blob, src = s.dual.load()
    s.say("save", f"关机存档　读回验证：{src}　"
                  f"{len(blob) if blob else 0} B")
    return {"src": src, "bytes": len(blob) if blob else 0,
            "writes": s.auto.stats.writes if s.auto else 0}


# ---------------------------------------------------------------------------
# 物种数据查询 —— 从 assets/gen1.bin 读
# ---------------------------------------------------------------------------

_MON_CACHE: dict = {}

TYPES_CN = ["一般", "火", "水", "电", "草", "冰", "格斗", "毒",
            "地面", "飞行", "超能", "虫", "岩石", "幽灵", "龙"]
_STONES = {26: "thunder-stone", 36: "moon-stone", 40: "moon-stone",
           38: "fire-stone", 78: "fire-stone", 59: "fire-stone",
           62: "water-stone", 73: "water-stone", 87: "water-stone",
           91: "water-stone", 121: "water-stone", 134: "water-stone",
           135: "thunder-stone", 136: "fire-stone",
           45: "leaf-stone", 71: "leaf-stone", 103: "leaf-stone"}


def _load_mons() -> dict:
    if _MON_CACHE:
        return _MON_CACHE
    import pathlib
    import struct
    p = pathlib.Path(__file__).resolve().parent.parent / "assets" / "gen1.bin"
    if not p.exists():
        return {}
    d = p.read_bytes()
    magic, ver, rsz, cnt, poolsz = struct.unpack("<4sHHII", d[:16])
    recs = d[16:16 + cnt * rsz]
    for i in range(cnt):
        o = i * rsz
        (off, ln, t1, t2, bm, cr, tg, ev, el,
         hp, at, df, sp, spd) = struct.unpack("<HBBBBBBBBBBBBB",
                                              recs[o:o + 15])
        _MON_CACHE[i + 1] = {
            "t1": TYPES_CN[t1] if t1 < 15 else "一般",
            "catch": cr, "trigger": tg, "evo": ev, "evo_level": el,
            "stats": [hp, at, df, sp, spd],
        }
    return _MON_CACHE


def _base_stats(sid: int) -> list:
    m = _load_mons().get(sid)
    return m["stats"] if m else [50, 50, 50, 50, 50]


def _type_of(sid: int) -> str:
    m = _load_mons().get(sid)
    return m["t1"] if m else "一般"


def _capture_rate(sid: int) -> int:
    m = _load_mons().get(sid)
    return m["catch"] if m else 100


def _evo_info(sid: int) -> dict:
    m = _load_mons().get(sid, {})
    return {"to": m.get("evo", 0), "trigger": m.get("trigger", 0xFF),
            "level": m.get("evo_level", 0),
            "stone": _STONES.get(m.get("evo", 0), "fire-stone")}


# ---------------------------------------------------------------------------
# 一键跑通：给验收平台与回归测试用
# ---------------------------------------------------------------------------

def play_through(scans: list, choice: int = 3, auto_capture: bool = True,
                 care_hours: tuple = (8, 13, 21)) -> Session:
    """喂一串真实扫描数据，跑完整局。

    这是**唯一一处**会让 18 个系统同时工作的地方 ——
    也就是系统之间的接缝唯一会被走到的地方。
    """
    s = Session()
    if scans:
        s.ts = scans[0].ts
    run_intro(s, choice=choice, skip_story=True)

    last_day = -1
    cared_this_hour = set()
    for sc in scans:
        feed_scan(s, sc)

        # 玩家行为：有遭遇就处理（模拟玩家掏出设备）
        if auto_capture and s.acc and s.acc.queue.items:
            handle_encounter(s, 0, do_battle=True, press_offset_ms=600)
            check_progress(s)
            # 够条件就挑战道馆
            r = challenge_gym(s)
            if r.get("ok"):
                check_progress(s)

        # 照料：每天三次
        h = (sc.ts // 3600) % 24
        key = (sc.ts // 86400, h)
        if h in care_hours and key not in cared_this_hour:
            cared_this_hour.add(key)
            care(s, "feed")

        # 日切
        d = sc.ts // 86400
        if last_day >= 0 and d != last_day:
            roll_day(s)
        last_day = d

    shutdown(s)
    return s


def summary(s: Session) -> dict:
    """一局的结果概览。"""
    prog = GY.progress_summary(s.badges, s.elite_done, s.red_done)
    leader = s.party.leader
    return {
        "phase": s.phase,
        "days": s.day_index,
        "leader": (display_name(leader.nickname_idx, f"#{leader.species_id}")
                   if leader else None),
        "leader_level": leader.level if leader else 0,
        "party": len(s.party.party),
        "box": len(s.party.box),
        "caught": s.dex.count("caught"),
        "seen": s.dex.count("seen"),
        "shiny": s.dex.count("shiny_caught"),
        "badges": s.badges,
        "stage": prog["stage"],
        "level_cap": prog["level_cap"],
        "encounters": s.records.total_encounters,
        "captures": s.records.total_captures,
        "items": {"poke": s.inventory.poke, "great": s.inventory.great,
                  "ultra": s.inventory.ultra, "berry": s.inventory.berry},
        "saves": s.auto.stats.writes if s.auto else 0,
        "save_detail": (dict(s.auto.stats.by_reason) if s.auto else {}),
        "log_entries": len(s.log),
        "biome_visits": dict(s.biome_visits),
        "biome_dwell_h": {k: round(v / 3600, 1)
                          for k, v in s.core.memory.biome_dwell.items()},
        "pet": ({"satiety": round(s.pet.satiety, 1),
                 "mood": round(s.pet.mood, 1),
                 "stamina": round(s.pet.stamina, 1),
                 "intimacy": round(s.pet.intimacy, 1),
                 "despondent": s.pet.is_despondent} if s.pet else None),
    }
