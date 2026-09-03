"""S17 道馆 / 四天王 / 最终对手 —— 长线目标。

对应 docs/systems/S17-gyms.md。

## 为什么需要它

在它之前这个游戏没有**终点**。S1~S16 组成一个可以无限循环的日常
（出门→遭遇→捕获→养成），但没有任何东西告诉玩家「你走到哪了」。
Tamagotchi 靠「养了多久」就够，而加了捕获与对战之后，
玩家会问「我练这些是为了什么」。

八个道馆 + 四天王 + 最终对手回答这个问题。

## 核心设计：解锁挂在探索上，不是等级上

原版道馆的门槛是**走到那座城市**。这台设备没有地图，
但有真实世界的 biome 与地点 —— 所以门槛用它们替代：

    每个道馆绑定一个 biome，解锁要求在那种环境里累计驻留够久
    + 累计遭遇数（时间轴）+ 已见物种数（收集轴）

挂等级会退化成刷怪 —— 而这个项目的立项理由是真实世界探索。
挂纯时间（累计遭遇）也不行：窝在家里也涨。
**必须双轴**，且空间轴是主的。

馆主属性专精 → biome 的映射是原版没有、这个设备天然有的联动：
比如电系馆主绑办公区（企业级 AP → 电系，见 docs/03-spawning.md#32），
玩家想打它就得去办公环境待着。

## 徽章的机制作用照原版

原版徽章不只是通行证，还给：
  · 可指挥的宝可梦等级上限（防止用高级怪碾压前期）
  · 属性加成
  · 场外招式许可（居合斩、冲浪 —— 本项目没有地图，不做）

等级上限这条本项目**保留**：它让「练级」与「推进度」互相咬合，
而不是各走各的。没有它，玩家可以先把一只练到 Lv50 再一口气打完八馆。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 八个道馆
#
# **队伍数据从 pret/pokered 的 data/trainers/parties.asm 脚本提取**，
# 不是手填的。物种常量经 constants/pokedex_constants.asm 转成图鉴序
# （Gen 1 内部序号与图鉴序不同 —— RHYDON 是内部 #1）。
#
# 我第一版凭记忆手填，坂木那场就错了两处（尼多王 Lv45 写成 50、
# 最后一只犀牛王 #112 写成袋兽），阿渡的第三只 Lv56 写成 54。
# 这种数据必须从源头取。
#
# 坂木有三场（火箭队基地 B4F / 银牙大楼 11F / 常青道馆），
# 取第三场 —— 那才是道馆战。
#
# 中文名全部是**任天堂官方译名**（zh_nin 字段），不是动画/漫画的代理译名。
#
# 三个容易搞错的地方：
#   ① 徽章是**颜色名**，不是英文概念的直译。
#      Boulder Badge = 灰色徽章（グレーバッジ），不是「岩石徽章」。
#      从英文回译八个全错。
#   ② 城市名跟**日文的颜色**，不是英文。
#      Saffron = 金黄市（ヤマブキ），别拿 "saffron" 去核对。
#   ③ 最终对手是**青绿**（グリーン/Blue），不是赤红。
#      赤红是 Gen 2 金银的隐藏 BOSS。广为流传的「小茂」「小智」
#      是动画代理译名，游戏内不用。
# ---------------------------------------------------------------------------

@dataclass
class Gym:
    """一个道馆。"""

    order: int                  # 第几馆
    leader: str                 # 馆主（官方简体译名）
    leader_ja: str
    city: str                   # 城市（官方简体译名）
    type_name: str              # 属性专精
    badge: str                  # 徽章（官方译名，颜色名）
    biome: str                  # 绑定的 biome —— 本项目的解锁条件
    level_cap: int              # 取得该徽章后可指挥的等级上限
    dwell_hours: int            # 该 biome 累计驻留要求（小时）
    encounters: int             # 累计遭遇要求
    seen: int                   # 已见物种要求
    team: list = field(default_factory=list)    # [(species_id, level)]


# 等级上限：**取得第 N 枚徽章后**可指挥到多少级。
#
# 我第一版把这张表错位了一格，当成「持有 N 枚徽章时的上限」——
# 于是 0 徽章上限 Lv10 而第一馆小刚有 Lv14，四个道馆数学上打不过。
# 徽章是**奖励**，给的是取得之后的上限。
#
# 而 0 徽章时原版根本没有上限（LEVEL_CAP_NONE）—— 原版这套限制
# 只对**交换来**的宝可梦生效，自己抓的一律听话。本项目没有交换，
# 所以 0 徽章不设限，但保留后续曲线让「练级」与「推进度」咬合。
LEVEL_CAP_NONE = 100            # 0 徽章：不设限
# 第一档给 22 而非 20：小霞的宝石海星是 Lv21，上限刚好 20 会让
# 玩家必须靠属性相克才打得过 —— 边界卡这么紧不是设计，是巧合。
# 留 1 级余量。其余档位对手最高等级都低于上限至少 6 级。
LEVEL_CAPS = (22, 30, 40, 50, 60, 70, 80, 100)

# biome 绑定：让馆主属性与 AP 语义呼应（docs/03-spawning.md#32）
#
# 岩石/水 → 野外（低 AP 密度、公园）
# 电      → 办公区（企业级 AP → 电系，语义直接对上）
# 草/毒   → 住宅区（居民路由器密集）
# 超能    → 交通枢纽（人流聚集 → 超能/格斗）
# 火      → 商业区（商场供电密集）
# 地面    → 野外（最终馆回到起点，形成闭环）

GYMS = [
    Gym(1, "小刚", "タケシ", "深灰市", "岩石", "灰色徽章",
        "野外", LEVEL_CAPS[0], dwell_hours=2, encounters=20, seen=8,
        team=[(74, 12), (95, 14)]),        # 小拳石、大岩蛇
    Gym(2, "小霞", "カスミ", "华蓝市", "水", "蓝色徽章",
        "野外", LEVEL_CAPS[1], dwell_hours=5, encounters=45, seen=15,
        team=[(120, 18), (121, 21)]),      # 海星星、宝石海星
    Gym(3, "马志士", "マチス", "枯叶市", "电", "橙色徽章",
        "办公区", LEVEL_CAPS[2], dwell_hours=10, encounters=75, seen=24,
        team=[(100, 21), (25, 18), (26, 24)]),   # 霹雳蛋、皮卡丘、雷丘
    Gym(4, "莉佳", "エリカ", "玉虹市", "草", "彩虹徽章",
        "住宅区", LEVEL_CAPS[3], dwell_hours=16, encounters=110, seen=34,
        team=[(71, 29), (114, 24), (45, 29)]),    # 大食花、蔓藤怪、霸王花
    Gym(5, "阿桔", "キョウ", "浅红市", "毒", "粉红徽章",
        "住宅区", LEVEL_CAPS[4], dwell_hours=24, encounters=150, seen=45,
        team=[(109, 37), (89, 39), (109, 37), (110, 43)]),
        # 瓦斯弹、臭臭泥、瓦斯弹、双弹瓦斯（原版真有两只瓦斯弹）
    Gym(6, "娜姿", "ナツメ", "金黄市", "超能", "金色徽章",
        "交通枢纽", LEVEL_CAPS[5], dwell_hours=34, encounters=200, seen=58,
        team=[(64, 38), (122, 37), (49, 38), (65, 43)]),
        # 勇基拉、魔墙人偶、摩鲁蛾、胡地
    Gym(7, "夏伯", "カツラ", "红莲镇", "火", "深红徽章",
        "商业区", LEVEL_CAPS[6], dwell_hours=46, encounters=260, seen=72,
        team=[(58, 42), (77, 40), (78, 42), (59, 47)]),
        # 卡蒂狗、小火马、烈焰马、风速狗
    Gym(8, "坂木", "サカキ", "常青市", "地面", "绿色徽章",
        "野外", LEVEL_CAPS[7], dwell_hours=60, encounters=340, seen=88,
        team=[(111, 45), (51, 42), (31, 44), (34, 45), (112, 50)]),
        # 独角犀牛、三地鼠、尼多后、尼多王、钻角犀兽（常青道馆那场）
]

# 四天王 + 最终对手
#
# 原版挑战条件是八枚徽章。本项目沿用 —— 这是唯一合理的门槛，
# 也让八个道馆真的是「一条路」而非八个独立挑战。

@dataclass
class EliteMember:
    order: int
    name: str
    name_ja: str
    type_name: str
    team: list = field(default_factory=list)


ELITE_FOUR = [
    EliteMember(1, "科拿", "カンナ", "冰",
                [(87, 54), (91, 53), (80, 54), (124, 56), (131, 56)]),
    EliteMember(2, "希巴", "シバ", "格斗",
                [(95, 53), (107, 55), (106, 55), (95, 56), (68, 58)]),
    EliteMember(3, "菊子", "キクコ", "幽灵",
                [(94, 56), (42, 56), (93, 55), (24, 58), (94, 60)]),
    EliteMember(4, "阿渡", "ワタル", "龙",
                [(130, 58), (148, 56), (148, 56), (142, 60), (149, 62)]),
]

# 最终对手：**青绿**（グリーン / Blue），不是赤红。
# 他的首发随玩家开局选择而变（原版：玩家选草→他选火，等等）。
CHAMPION_NAME = "青绿"
CHAMPION_JA = "グリーン"
CHAMPION_TEAM_BASE = [(18, 61), (65, 59), (112, 61), (103, 63)]
# 首发对应表：玩家选 → 青绿的最终形态（原版的相克关系）
CHAMPION_STARTER = {1: 6, 4: 9, 7: 3, 25: 6}     # 妙蛙→喷火、小火→水箭、杰尼→妙蛙花

# Gen 2 的赤红（白银山隐藏 BOSS）—— 本项目作为**八馆之后的额外挑战**。
# 他的队伍比四天王更强，适合当真正的终点。
RED_NAME = "赤红"
RED_JA = "レッド"
RED_TEAM = [(25, 81), (3, 77), (9, 77), (6, 77), (131, 73), (59, 77)]
# 解锁条件：打完四天王 + 图鉴收满一定比例。
# 原版 Gen 2 的条件是「全 16 枚徽章」，本项目没有第二地区，
# 改成收集度 —— 那是这个游戏真正的长线目标。
RED_UNLOCK_CAUGHT = 100         # 已捕获 100 只（151 的三分之二）


# ---------------------------------------------------------------------------
# 解锁判定
# ---------------------------------------------------------------------------

@dataclass
class GymCheck:
    """能否挑战某个道馆。"""

    can: bool
    reason: str = ""
    progress: dict = field(default_factory=dict)    # 各条件的 当前/需要


def check_gym(gym: Gym, badges: int, biome_dwell: dict,
              total_encounters: int, seen_count: int) -> GymCheck:
    """能否挑战第 N 馆。

    四个条件：
      ① 前一馆已通关（线性，与原版一致）
      ② 该 biome 累计驻留够久 —— **空间轴，主条件**
      ③ 累计遭遇够多 —— 时间轴
      ④ 已见物种够多 —— 收集轴

    ② 是主的：这个项目的立项理由是真实世界探索，
    如果只看 ③ 就等于挂时间（窝家里也涨），只看等级就退化成刷怪。
    """
    prog = {}

    # ① 线性顺序
    if badges < gym.order - 1:
        return GymCheck(False, f"要先取得第 {gym.order - 1} 枚徽章",
                        {"badges": (badges, gym.order - 1)})

    if badges >= gym.order:
        return GymCheck(False, f"已取得{gym.badge}", {})

    # ② biome 驻留（主条件）
    got_h = biome_dwell.get(gym.biome, 0) / 3600.0
    prog["dwell"] = (round(got_h, 1), gym.dwell_hours)
    # ③ 累计遭遇
    prog["encounters"] = (total_encounters, gym.encounters)
    # ④ 已见物种
    prog["seen"] = (seen_count, gym.seen)

    if got_h < gym.dwell_hours:
        return GymCheck(False,
                        f"{gym.biome}驻留不足（{got_h:.1f}/{gym.dwell_hours} 小时）",
                        prog)
    if total_encounters < gym.encounters:
        return GymCheck(False,
                        f"遭遇次数不足（{total_encounters}/{gym.encounters}）",
                        prog)
    if seen_count < gym.seen:
        return GymCheck(False, f"图鉴见闻不足（{seen_count}/{gym.seen}）", prog)

    return GymCheck(True, f"可以挑战{gym.leader}", prog)


def check_elite(badges: int, party_healthy: int) -> GymCheck:
    """能否挑战四天王 —— 八枚徽章，与原版一致。

    还要求队伍里至少 3 只能战斗：四天王是连续四场不能中途治疗
    （原版规则），带一只去必输，而那种失败不教给玩家任何东西。
    """
    if badges < 8:
        return GymCheck(False, f"需要八枚徽章（{badges}/8）",
                        {"badges": (badges, 8)})
    if party_healthy < 3:
        return GymCheck(False, f"队伍至少要 3 只能战斗（{party_healthy}/3）",
                        {"healthy": (party_healthy, 3)})
    return GymCheck(True, "可以挑战四天王", {})


def check_red(elite_done: bool, caught_count: int) -> GymCheck:
    """能否挑战赤红 —— 打完四天王 + 图鉴收集度。

    原版 Gen 2 的条件是全 16 枚徽章。本项目没有第二地区，
    改成收集度 —— 那才是这个游戏真正的长线目标。
    """
    if not elite_done:
        return GymCheck(False, "要先打完四天王", {})
    if caught_count < RED_UNLOCK_CAUGHT:
        return GymCheck(False,
                        f"图鉴收集不足（{caught_count}/{RED_UNLOCK_CAUGHT}）",
                        {"caught": (caught_count, RED_UNLOCK_CAUGHT)})
    return GymCheck(True, "白银山顶有人在等你", {})


# ---------------------------------------------------------------------------
# 徽章的机制作用
# ---------------------------------------------------------------------------

def level_cap(badges: int) -> int:
    """当前可指挥的宝可梦等级上限。

    超过上限的宝可梦**不听指挥**（原版行为：无视命令、自己乱动）。
    本项目简化成「战斗中有概率不行动」，见 S3。

    这条让练级与推进度咬合 —— 没有它，玩家可以先练一只 Lv50
    再一口气打完八馆，八个道馆就退化成一场碾压。

    注意 badges=0 时**不设限**：原版这套限制只对交换来的宝可梦生效，
    自己抓的一律听话。本项目没有交换，所以开局不该有天花板 ——
    我第一版让 0 徽章上限 Lv10，而第一馆对手就有 Lv14。
    """
    if badges <= 0:
        return LEVEL_CAP_NONE
    return LEVEL_CAPS[min(badges, len(LEVEL_CAPS)) - 1]


def obeys(level: int, badges: int) -> bool:
    return level <= level_cap(badges)


# 原版徽章还给属性加成（攻击/防御/特攻/速度各 +12.5%），
# 但那是为了补偿原版的数值曲线。本项目的 effective_stat 已经
# 按等级线性成长（见 S3），再加徽章加成会双重放大 —— 不做。
BADGE_STAT_BOOST = False


# ---------------------------------------------------------------------------
# 进度总览
# ---------------------------------------------------------------------------

def progress_summary(badges: int, elite_done: bool, red_done: bool) -> dict:
    """一句话说清「你走到哪了」—— 这是整个系统存在的理由。"""
    total = len(GYMS) + 1 + 1               # 八馆 + 四天王 + 赤红
    done = badges + (1 if elite_done else 0) + (1 if red_done else 0)
    if red_done:
        stage = "白银山之后"
    elif elite_done:
        stage = "冠军"
    elif badges >= 8:
        stage = "八枚徽章齐了"
    elif badges == 0:
        stage = "还没有徽章"
    else:
        stage = f"{GYMS[badges - 1].badge}"
    return {"badges": badges, "done": done, "total": total,
            "stage": stage, "level_cap": level_cap(badges),
            "next": (GYMS[badges].leader if badges < len(GYMS)
                     else ("四天王" if not elite_done
                           else (RED_NAME if not red_done else "—")))}


def badge_names() -> list:
    return [g.badge for g in GYMS]


def all_opponents() -> list:
    """全部对手 —— 用于验收面板展示。"""
    out = [{"kind": "gym", "order": g.order, "name": g.leader,
            "type": g.type_name, "badge": g.badge, "biome": g.biome,
            "cap": g.level_cap, "team": g.team,
            "req": {"dwell": g.dwell_hours, "enc": g.encounters,
                    "seen": g.seen}}
           for g in GYMS]
    out += [{"kind": "elite", "order": e.order, "name": e.name,
             "type": e.type_name, "team": e.team} for e in ELITE_FOUR]
    out.append({"kind": "champion", "order": 5, "name": CHAMPION_NAME,
                "type": "—", "team": CHAMPION_TEAM_BASE})
    out.append({"kind": "red", "order": 6, "name": RED_NAME,
                "type": "—", "team": RED_TEAM})
    return out
