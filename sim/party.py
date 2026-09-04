"""S14 队伍与仓库 —— 捕到的宝可梦存在哪、怎么切换。

对应 docs/systems/S14-party.md。

## 这个系统补的是一个真断层

在它之前：`attempt_capture()` 成功后只调 `dex.mark_caught()` 点亮一个
图鉴 bit，**那只宝可梦的实体就消失了**。存档里只有 `pet_*` 一只主宠，
养成、进化、战斗全都只认它。

于是「捕获」这个玩法的产出无处可去 —— 玩家抓了三十只，能玩的还是开场那只。
S1~S13 各自成立，但**捕获 → 养成**这条链是断的。

## 结构：队伍 6 只 + 仓库 30 只

原版是队伍 6 + 电脑箱无上限。这里仓库设 30 是**三键 UI 的约束**，
不是存储的约束（每只 8 B，30 只才 240 B，8MB 里是零头）：

    B 键循环浏览 30 只 → 平均按 15 次
    再多就必须做分页/跳转，而那要第四个键

满了怎么办：**不做「放生」** —— 玩家不该被逼着删自己养的东西。
改成仓库满时新捕获的**自动替换掉重复物种里等级最低的那只**；
若没有重复物种，则拒绝捕获并提示（这时玩家该去主动整理）。

## 主宠 = 队伍首位

不设独立的 `pet_*` 字段，主宠就是 `party[0]`。这样「换主宠」等于
「把某只移到队首」，一个操作解决两件事，且**不会出现主宠与队伍不一致**
这种状态（那是上一版结构必然会有的 bug 来源）。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Optional

PARTY_MAX = 6            # 与原版一致
BOX_MAX = 30             # 三键 UI 的约束，见模块 docstring
MON_BYTES = 12           # 8 → 12：加了 u32 exp，见 Mon 的 docstring


# ---------------------------------------------------------------------------
# 一只宝可梦的实体
# ---------------------------------------------------------------------------

@dataclass
class Mon:
    """一只具体的宝可梦。**12 字节**。

    与 `PetState`（S4 养成的三条轴）的分工：
      · Mon 是**持久身份** —— 物种、等级、经验、亲密度，进了仓库也不变
      · PetState 是**当前状态** —— 饱食/心情/体能，只有队首那只在跑

    为什么不给每只都存三条轴：那意味着仓库里 30 只都在衰减，
    玩家一周不上线回来发现全体消沉 —— 惩罚性的，且违反
    「Tamagotchi 只养一只」的核心体验。
    仓库里的宝可梦**状态冻结**，这是刻意的。

    ## 8 → 12 字节：为什么加 exp 而不是即时结算

    原先没有 exp 字段，等级也从不增长（见 S20 的说明）。补上时有三条路：
    不存 exp 即时判等级、复用 explore_value、加字段。选了加字段：

      · 即时结算丢掉「差一点升级」的进度感，且经验曲线只能很平缓
      · explore_value 已被 S7 进化条件占用（探索值 ≥ evolve_level×2），
        两个语义挤一个字段会互相干扰 —— 打怪也能凑进化条件

    u32 而非 u16：`5n³/2` 曲线在 Lv50 要 156250 exp，u16 上限 65535
    只够到 Lv36。u16 会让后期经验**静默溢出回绕**，那比多 2 字节糟得多。
    队伍+仓库从 290 B 涨到 434 B，在 8MB flash 里仍是零头。
    """

    species_id: int
    level: int = 5
    hp: int = 100                 # 百分比
    intimacy: int = 0
    explore_value: int = 0
    nickname_idx: int = 0xFF
    shiny: bool = False
    exp: int = 0                  # 累计经验（u32），见 systems.exp_to_level
    # 原版没有性别（Gen 2 才有），这里也不做 —— flags 留位给未来

    def to_bytes(self) -> bytes:
        flags = 1 if self.shiny else 0
        return struct.pack("<BBBBHBBI", self.species_id, self.level,
                           min(self.hp, 255), min(self.intimacy, 255),
                           min(self.explore_value, 65535),
                           self.nickname_idx & 0xFF, flags,
                           min(self.exp, 0xFFFFFFFF))

    @classmethod
    def from_bytes(cls, b: bytes) -> "Mon":
        sid, lv, hp, inti, expl, nick, flags, exp = struct.unpack(
            "<BBBBHBBI", b[:12])
        return cls(species_id=sid, level=lv, hp=hp, intimacy=inti,
                   explore_value=expl, nickname_idx=nick,
                   shiny=bool(flags & 1), exp=exp)

    @property
    def is_fainted(self) -> bool:
        return self.hp == 0


# ---------------------------------------------------------------------------
# 队伍 + 仓库
# ---------------------------------------------------------------------------

REASON_OK = ""
REASON_BOX_FULL = "仓库满了"
REASON_EMPTY = "没有可用的"
REASON_LAST_ONE = "这是最后一只"


@dataclass
class Party:
    """队伍（≤6）+ 仓库（≤30）。

    `party[0]` 就是主宠 —— 不设独立字段，见模块 docstring。
    """

    party: list = field(default_factory=list)      # list[Mon]
    box: list = field(default_factory=list)        # list[Mon]

    # -- 主宠 ---------------------------------------------------------------

    @property
    def leader(self) -> Optional[Mon]:
        return self.party[0] if self.party else None

    def set_leader(self, party_index: int) -> bool:
        """把队伍里第 index 只移到队首 —— 这就是「换主宠」。

        用 insert(0, pop(i)) 而非 swap：swap 会打乱队伍其余顺序，
        而玩家心里的队伍是有次序的（谁是二号、三号）。
        """
        if not (0 < party_index < len(self.party)):
            return False
        self.party.insert(0, self.party.pop(party_index))
        return True

    # -- 收容 ---------------------------------------------------------------

    def receive(self, mon: Mon) -> tuple[bool, str, Optional[Mon]]:
        """捕获成功后收容一只。

        返回 (成功, 说明, 被替换掉的那只)。

        优先进队伍（未满时），否则进仓库。这符合直觉：
        刚抓到的应该能立刻用，而不是要先去仓库取。
        """
        if len(self.party) < PARTY_MAX:
            self.party.append(mon)
            return True, REASON_OK, None

        if len(self.box) < BOX_MAX:
            self.box.append(mon)
            return True, REASON_OK, None

        # 仓库满 —— 找重复物种里等级最低的替换
        #
        # **不做「放生」**：玩家不该被逼着删自己养的东西。
        # 重复物种的低等级个体是唯一「明确可牺牲」的对象。
        victim_i, victim = None, None
        counts: dict[int, int] = {}
        for m in self.box + self.party:
            counts[m.species_id] = counts.get(m.species_id, 0) + 1
        for i, m in enumerate(self.box):
            if counts[m.species_id] < 2:
                continue
            if victim is None or m.level < victim.level:
                victim_i, victim = i, m

        if victim_i is None:
            # 没有重复物种 —— 拒绝，让玩家自己去整理
            #
            # ⚠️ 实测这条在长线上会变成主要的挫败源：30 天跑下来
            # **225 次成功捕获全部作废**（仓库 30 满、队伍 6 满、
            # 且新抓的都不是重复物种）。球扣了、指针也按中了，
            # 只得到一句「抓到了但收容失败」。
            #
            # 三键设备上玩家不会频繁翻仓库，所以「自己去整理」这个
            # 假设不成立 —— 等他想起来时已经白费两百次。
            #
            # 这是 S14 的设计缺口，要定策略（自动放生最低级的？
            # 满了就不再触发捕获？P1 挂持续提示？），不是一行能修的。
            # 在定下来之前至少别让玩家白扣球 —— 见 orchestrate 的
            # handle_encounter：满仓时应当在投球**之前**就拦住。
            return False, REASON_BOX_FULL, None

        self.box[victim_i] = mon
        return True, f"替换了 Lv{victim.level} 的重复个体", victim

    # -- 队伍 ↔ 仓库 --------------------------------------------------------

    def deposit(self, party_index: int) -> tuple[bool, str]:
        """队伍 → 仓库。"""
        if len(self.party) <= 1:
            return False, REASON_LAST_ONE      # 队伍不能空
        if not (0 <= party_index < len(self.party)):
            return False, REASON_EMPTY
        if len(self.box) >= BOX_MAX:
            return False, REASON_BOX_FULL
        self.box.append(self.party.pop(party_index))
        return True, REASON_OK

    def withdraw(self, box_index: int) -> tuple[bool, str]:
        """仓库 → 队伍。"""
        if len(self.party) >= PARTY_MAX:
            return False, "队伍满了"
        if not (0 <= box_index < len(self.box)):
            return False, REASON_EMPTY
        self.party.append(self.box.pop(box_index))
        return True, REASON_OK

    def swap(self, party_index: int, box_index: int) -> tuple[bool, str]:
        """队伍某只与仓库某只互换 —— 队伍满时唯一的取出方式。"""
        if not (0 <= party_index < len(self.party)):
            return False, REASON_EMPTY
        if not (0 <= box_index < len(self.box)):
            return False, REASON_EMPTY
        self.party[party_index], self.box[box_index] = \
            self.box[box_index], self.party[party_index]
        return True, REASON_OK

    # -- 查询 ---------------------------------------------------------------

    @property
    def total(self) -> int:
        return len(self.party) + len(self.box)

    def species_set(self) -> set[int]:
        return {m.species_id for m in self.party + self.box}

    def healthy(self) -> list:
        """还能战斗的（队伍里 HP > 0 的）—— 道馆挑战要用。"""
        return [m for m in self.party if not m.is_fainted]

    def strongest(self) -> Optional[Mon]:
        return max(self.party + self.box, key=lambda m: m.level, default=None)

    def duplicates(self) -> dict[int, int]:
        """重复物种统计 —— 仓库满时提示玩家哪些可以牺牲。"""
        c: dict[int, int] = {}
        for m in self.party + self.box:
            c[m.species_id] = c.get(m.species_id, 0) + 1
        return {k: v for k, v in c.items() if v > 1}

    # -- 序列化 -------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """定长布局：1 + 1 + 6×12 + 30×12 = 434 字节。

        定长而非变长：变长省不了多少（最多 432 B），
        但会让固件侧的读写变成两次遍历，且掉电时半写状态更难恢复。
        """
        out = bytearray(struct.pack("<BB", len(self.party), len(self.box)))
        for i in range(PARTY_MAX):
            out += (self.party[i].to_bytes() if i < len(self.party)
                    else bytes(MON_BYTES))
        for i in range(BOX_MAX):
            out += (self.box[i].to_bytes() if i < len(self.box)
                    else bytes(MON_BYTES))
        return bytes(out)

    def load(self, data: bytes) -> None:
        need = 2 + (PARTY_MAX + BOX_MAX) * MON_BYTES
        if len(data) < need:
            return
        np, nb = struct.unpack("<BB", data[:2])
        np, nb = min(np, PARTY_MAX), min(nb, BOX_MAX)
        o = 2
        self.party = [Mon.from_bytes(data[o + i * MON_BYTES:
                                          o + (i + 1) * MON_BYTES])
                      for i in range(np)]
        o += PARTY_MAX * MON_BYTES
        self.box = [Mon.from_bytes(data[o + i * MON_BYTES:
                                        o + (i + 1) * MON_BYTES])
                    for i in range(nb)]


SERIALIZED_BYTES = 2 + (PARTY_MAX + BOX_MAX) * MON_BYTES        # 434


# ---------------------------------------------------------------------------
# 三键浏览
#
# P9 队伍页的状态机。B 循环、C 切换队伍/仓库视图、A 打开操作菜单。
#
# 为什么 C 键给「切视图」而不是「返回」：队伍与仓库是这一页的两半，
# 在它们之间来回是最频繁的操作。返回放在操作菜单里（A → 返回）。
# ---------------------------------------------------------------------------

VIEW_PARTY, VIEW_BOX = 0, 1


@dataclass
class PartyBrowser:
    """队伍页浏览状态。定长、无动态分配。"""

    view: int = VIEW_PARTY
    cursor: int = 0

    def _len(self, p: Party) -> int:
        return len(p.party) if self.view == VIEW_PARTY else len(p.box)

    def next(self, p: Party) -> int:
        n = self._len(p)
        if n:
            self.cursor = (self.cursor + 1) % n
        return self.cursor

    def prev(self, p: Party) -> int:
        n = self._len(p)
        if n:
            self.cursor = (self.cursor - 1) % n
        return self.cursor

    def toggle_view(self, p: Party) -> int:
        self.view = VIEW_BOX if self.view == VIEW_PARTY else VIEW_PARTY
        self.cursor = min(self.cursor, max(0, self._len(p) - 1))
        return self.view

    def selected(self, p: Party) -> Optional[Mon]:
        lst = p.party if self.view == VIEW_PARTY else p.box
        return lst[self.cursor] if 0 <= self.cursor < len(lst) else None

    def actions(self, p: Party) -> list[str]:
        """当前选中项可做什么 —— 菜单项按上下文变，避免给出无效选项。"""
        if self.view == VIEW_PARTY:
            acts = []
            if self.cursor > 0:
                acts.append("设为主宠")
            if len(p.party) > 1 and len(p.box) < BOX_MAX:
                acts.append("存入仓库")
            acts += ["查看详情", "取名", "返回"]
            return acts
        acts = []
        if len(p.party) < PARTY_MAX:
            acts.append("加入队伍")
        else:
            acts.append("与队伍交换")
        acts += ["查看详情", "取名", "返回"]
        return acts


def charset() -> set:
    """S14 上屏用到的全部字符 —— 字库子集化要收进去。

    队伍页的菜单项是 `actions()` **动态**拼的（按上下文变），
    所以这里不能只收 REASON_* 常量，得把两个分支的菜单项都列上。

    这个函数原本不存在 → 「设为主宠」「存入仓库」「加入队伍」「仓库满了」
    等 9 个汉字没进字库，在真机上是空白。同 gyms 的情形
    （见 tools/pipeline/convert_font.py 的 SOURCES 登记表）。
    """
    out: set = set()
    for s in (REASON_OK, REASON_BOX_FULL, REASON_EMPTY, REASON_LAST_ONE):
        out |= set(s)
    # actions() 的全部可能菜单项（两个 view × 各分支）
    for s in ("设为主宠", "存入仓库", "加入队伍", "与队伍交换",
              "查看详情", "取名", "返回"):
        out |= set(s)
    # 视图标题（S14 文档：C 键在「队伍」与「仓库」间切换）
    out |= set("队伍") | set("仓库")
    return out
