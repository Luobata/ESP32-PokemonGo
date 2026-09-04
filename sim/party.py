"""S14 队伍与仓库 —— 捕到的宝可梦存在哪、怎么切换。

对应 docs/systems/S14-party.md。

## 这个系统补的是一个真断层

在它之前：`attempt_capture()` 成功后只调 `dex.mark_caught()` 点亮一个
图鉴 bit，**那只宝可梦的实体就消失了**。存档里只有 `pet_*` 一只主宠，
养成、进化、战斗全都只认它。

于是「捕获」这个玩法的产出无处可去 —— 玩家抓了三十只，能玩的还是开场那只。
S1~S13 各自成立，但**捕获 → 养成**这条链是断的。

## 结构：队伍 6 只 + 仓库 151 格

原版是队伍 6 + 电脑箱无上限。这里仓库是 **151 格，按物种号索引** ——
第 i 格就是 `species_id = i+1`，每个物种至多存一只。

初版仓库设 30 个线性槽位，理由是三键 UI 约束（B 键循环 30 只平均 15 次，
再多就得分页而分页要第四个键）。**实测那个设计会塌**：
30 天跑下来 225 次成功捕获全部作废 —— 仓库满、队伍满、新抓的又不是
重复物种，于是球扣了、指针也按中了，只得到一句「收容失败」。
「让玩家自己去整理」这个假设在三键设备上不成立，玩家不会频繁翻仓库。

改成按物种号索引，三件事同时解决：

  · **满仓问题从根上消失** —— 位置由 species_id 决定，永远有位置
  · **仓库与图鉴变成同一个东西** —— P6 已经是 151 格 4×5 网格 8 页，
    导航现成，不需要第四个键。实测定位平均 14 次，与旧的 30 只
    线性列表（15 次）持平，而容量翻了 5 倍
  · **「再抓一只同种」有了意义** —— 刷更高等级、刷闪光；
    旧结构下那纯粹是浪费球

代价是同物种只留一只，由 `Party.better()` 判定（闪光 > 等级 > 经验）。
存储 151 × 12 = 1812 B，8MB flash 里是 0.02%。

满了怎么办：**这个问题不再存在**。同物种相遇时自动留更好的那只，
不需要玩家做删除决策 —— 而「不该逼玩家删自己养的东西」正是初版的取向。

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
# 仓库 = 151 格，**按物种号索引**（第 i 格就是 species_id = i+1）。
#
# 旧结构是 30 个槽位的线性列表，那个 30 不是存储约束而是 UI 约束
# （S14 文档：「B 键循环浏览 30 只平均要按 15 次，再多就得分页，
# 而分页要第四个键」）。但实测它导致 30 天里 225 次成功捕获全部作废。
#
# 按物种号索引同时解决两件事：
#   · 永远有位置 —— 满仓问题从根上消失
#   · **仓库与图鉴变成同一个东西** —— P6 已经是 151 格 4×5 网格 8 页，
#     导航现成，不需要第四个键。实测按键代价 14 次/次定位，
#     与旧的 30 只线性列表（15 次）持平，而容量翻了 5 倍
BOX_SPECIES = 151
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
    # 仓库：{species_id: Mon}，每个物种至多一只（见 receive 的说明）。
    # 不用 151 长的 list —— 稀疏 dict 让「有没有这只」是一次查表，
    # 而序列化时才展开成定长 151 格（见 to_bytes）。
    box: dict = field(default_factory=dict)        # {species_id: Mon}

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

    def better(self, a: Mon, b: Mon) -> bool:
        """a 是否比 b「更好」—— 决定同物种保留哪只。

        ## 闪光优先于等级，这是有意的

        闪光 Lv5 与普通 Lv40 之间，留闪光。理由：
          · 等级是**可再生的** —— 带出门练几天就回来了
          · 闪光是**不可再生的** —— 1/512 的遭遇概率，丢了就是丢了
          · S8 专门用了一整个位图（19 B）记录闪光已捕，
            自动丢掉闪光会让那个位图的语义变成「曾经抓到过」

        同为闪光或同为普通时才比等级。等级相同再比经验 ——
        「差一点升级」的那只更值得留（也让 exp 字段不白存）。
        """
        if a.shiny != b.shiny:
            return a.shiny
        if a.level != b.level:
            return a.level > b.level
        return a.exp > b.exp

    def receive(self, mon: Mon) -> tuple[bool, str, Optional[Mon]]:
        """捕获成功后收容一只。

        返回 (成功, 说明, 被替换掉的那只)。

        优先进队伍（未满时），否则进仓库。这符合直觉：
        刚抓到的应该能立刻用，而不是要先去仓库取。

        ## 仓库按物种号索引，因此**永远不会满**

        旧结构是「30 个槽位的线性列表」，实测 30 天跑下来
        **225 次成功捕获全部作废** —— 仓库满、队伍满、新抓的又不是
        重复物种，于是球扣了、指针也按中了，只得到「收容失败」。

        改成 151 格（每个物种一格）之后这个问题从根上消失：
        位置由 species_id 决定，永远有位置。代价是同物种只留一只，
        由 better() 判定 —— 而那反过来让「再抓一只同种」有了意义
        （刷更高等级、刷闪光），旧结构下那纯粹是浪费球。

        存储 151 × 12 = 1812 B，在 8MB flash 里仍是零头。
        UI 上它与 P6 图鉴共用同一个 4×5 网格 8 页的布局 ——
        **仓库和图鉴本来就是同一个东西**，合并后少一套导航。
        """
        if len(self.party) < PARTY_MAX:
            self.party.append(mon)
            return True, REASON_OK, None

        old = self.box.get(mon.species_id)
        if old is None:
            self.box[mon.species_id] = mon
            return True, REASON_OK, None

        if self.better(mon, old):
            self.box[mon.species_id] = mon
            why = ("更强的一只" if not mon.shiny or old.shiny
                   else "闪光个体")
            return True, f"替换了 Lv{old.level} 的同种（{why}）", old

        # 新的不如旧的 —— 收下了但没留住。**不算失败**：
        # 球该扣的已经扣了，图鉴该点亮的已经点亮，只是没换。
        return True, f"已有更好的 Lv{old.level}，放走了", mon

    # -- 队伍 ↔ 仓库 --------------------------------------------------------

    def deposit(self, party_index: int) -> tuple[bool, str]:
        """队伍 → 仓库。

        仓库永远有位置（按物种号索引），但那一格可能已有同种 ——
        此时按 better() 决定谁留下，与 receive 同一套规则。
        """
        if len(self.party) <= 1:
            return False, REASON_LAST_ONE      # 队伍不能空
        if not (0 <= party_index < len(self.party)):
            return False, REASON_EMPTY
        mon = self.party[party_index]
        old = self.box.get(mon.species_id)
        if old is not None and not self.better(mon, old):
            return False, f"仓库里的 Lv{old.level} 更好"
        self.party.pop(party_index)
        self.box[mon.species_id] = mon
        return True, REASON_OK

    def withdraw(self, species_id: int) -> tuple[bool, str]:
        """仓库 → 队伍。按物种号取，不是下标。"""
        if len(self.party) >= PARTY_MAX:
            return False, "队伍满了"
        mon = self.box.pop(species_id, None)
        if mon is None:
            return False, REASON_EMPTY
        self.party.append(mon)
        return True, REASON_OK

    def swap(self, party_index: int, species_id: int) -> tuple[bool, str]:
        """队伍某只与仓库某只互换 —— 队伍满时唯一的取出方式。

        仓库按物种号寻址，所以第二个参数是 species_id 而非下标。
        换进去的那只落回它自己的格子（可能与换出来的不是同一格）。
        """
        if not (0 <= party_index < len(self.party)):
            return False, REASON_EMPTY
        taking = self.box.get(species_id)
        if taking is None:
            return False, REASON_EMPTY
        giving = self.party[party_index]
        self.party[party_index] = taking
        del self.box[species_id]
        # 换出来的那只回到**它自己的**格子。若那格已有更好的，
        # better() 决定谁留下 —— 与 receive 同一套规则，避免两处判定漂移。
        old = self.box.get(giving.species_id)
        if old is None or self.better(giving, old):
            self.box[giving.species_id] = giving
        return True, REASON_OK

    # -- 查询 ---------------------------------------------------------------

    @property
    def total(self) -> int:
        return len(self.party) + len(self.box)

    def species_set(self) -> set[int]:
        return {m.species_id for m in self.party} | set(self.box)

    def healthy(self) -> list:
        """还能战斗的（队伍里 HP > 0 的）—— 道馆挑战要用。"""
        return [m for m in self.party if not m.is_fainted]

    def all_mons(self) -> list:
        """队伍 + 仓库的全部个体。仓库按物种号升序 —— 与 P6 网格顺序一致。"""
        return self.party + [self.box[k] for k in sorted(self.box)]

    def strongest(self) -> Optional[Mon]:
        return max(self.all_mons(), key=lambda m: m.level, default=None)

    def duplicates(self) -> dict[int, int]:
        """队伍与仓库之间的重复物种。

        仓库自身**不可能有重复**（按物种号索引），所以这里数的是
        「队伍里带着、仓库里也存着」的那些。留着它是因为 S14 文档
        与验收平台都在读，且它现在的语义更清楚了。
        """
        c: dict[int, int] = {}
        for m in self.all_mons():
            c[m.species_id] = c.get(m.species_id, 0) + 1
        return {k: v for k, v in c.items() if v > 1}

    # -- 序列化 -------------------------------------------------------------

    def to_bytes(self) -> bytes:
        """定长布局：1 + 1 + 6×12 + 151×12 = 1814 字节。

        仓库那 151 格**按物种号定位**：第 i 格就是 species_id = i+1，
        空格全零。定长而非「只存已拥有的」：
          · 固件侧读写是 (base + (sid-1)*12) 一次寻址，无需遍历
          · 掉电时半写状态更容易恢复（每格独立，不依赖前面的格子）
          · 省下的字节没有意义 —— 满编 1814 B 在 8MB 里是 0.02%
        """
        out = bytearray(struct.pack("<BB", len(self.party), len(self.box)))
        for i in range(PARTY_MAX):
            out += (self.party[i].to_bytes() if i < len(self.party)
                    else bytes(MON_BYTES))
        for sid in range(1, BOX_SPECIES + 1):
            m = self.box.get(sid)
            out += m.to_bytes() if m else bytes(MON_BYTES)
        return bytes(out)

    def load(self, data: bytes) -> None:
        need = 2 + (PARTY_MAX + BOX_SPECIES) * MON_BYTES
        if len(data) < need:
            return
        np, _nb = struct.unpack("<BB", data[:2])
        np = min(np, PARTY_MAX)
        o = 2
        self.party = [Mon.from_bytes(data[o + i * MON_BYTES:
                                          o + (i + 1) * MON_BYTES])
                      for i in range(np)]
        o += PARTY_MAX * MON_BYTES
        # 空格是全零 —— species_id == 0 即「这格没有」。
        # 不依赖头部的计数，格子自己说明自己是否存在。
        self.box = {}
        for i in range(BOX_SPECIES):
            m = Mon.from_bytes(data[o + i * MON_BYTES:
                                    o + (i + 1) * MON_BYTES])
            if m.species_id:
                self.box[m.species_id] = m


SERIALIZED_BYTES = 2 + (PARTY_MAX + BOX_SPECIES) * MON_BYTES    # 1886


# ---------------------------------------------------------------------------
# 三键浏览
#
# 队伍视图与仓库视图的导航模型**不一样**，这是仓库改成 151 格后的直接后果：
#
#   队伍  ≤6 只的线性列表 —— B 循环即可，最坏 5 次
#   仓库  151 格的网格   —— 线性循环平均要 75 次，不可接受。
#                          改用 P6 图鉴同一套：4×5 网格 8 页，
#                          B 翻页 + A 进页内选。平均 14 次定位，
#                          与旧的 30 只线性列表（15 次）持平
#
# 为什么 C 键给「切视图」而不是「返回」：队伍与仓库是这一页的两半，
# 在它们之间来回是最频繁的操作。返回放在操作菜单里（A → 返回）。
# ---------------------------------------------------------------------------

VIEW_PARTY, VIEW_BOX = 0, 1

# 仓库网格 —— 与 P6 图鉴完全一致（docs/systems/S5-dex.md：每页 20 只、8 页）。
# 共用同一套布局不只是省代码：**仓库和图鉴本来就是同一个东西**，
# 玩家在两处看到不同的排列反而要重新建立空间记忆。
BOX_COLS, BOX_ROWS = 5, 4
BOX_PER_PAGE = BOX_COLS * BOX_ROWS          # 20
BOX_PAGES = (BOX_SPECIES + BOX_PER_PAGE - 1) // BOX_PER_PAGE   # 8


@dataclass
class PartyBrowser:
    """队伍页浏览状态。定长、无动态分配。

    仓库视图下 `cursor` 是**页内格位**（0~19），`page` 是页号（0~7）。
    对应的 species_id = page × 20 + cursor + 1。
    """

    view: int = VIEW_PARTY
    cursor: int = 0
    page: int = 0

    # -- 队伍视图 -----------------------------------------------------------

    def _len(self, p: Party) -> int:
        return len(p.party) if self.view == VIEW_PARTY else BOX_PER_PAGE

    def next(self, p: Party) -> int:
        """B 键。队伍视图 = 下一只；仓库视图 = 下一格（跨页环绕）。"""
        if self.view == VIEW_PARTY:
            n = len(p.party)
            if n:
                self.cursor = (self.cursor + 1) % n
            return self.cursor
        self.cursor += 1
        if self.cursor >= BOX_PER_PAGE:
            self.cursor = 0
            self.page = (self.page + 1) % BOX_PAGES
        return self.cursor

    def prev(self, p: Party) -> int:
        if self.view == VIEW_PARTY:
            n = len(p.party)
            if n:
                self.cursor = (self.cursor - 1) % n
            return self.cursor
        self.cursor -= 1
        if self.cursor < 0:
            self.cursor = BOX_PER_PAGE - 1
            self.page = (self.page - 1) % BOX_PAGES
        return self.cursor

    def next_page(self) -> int:
        """仓库视图专用 —— 直接翻页，这是 151 格能用三键的关键。

        没有它，从 #001 走到 #150 要按 149 次；有了它只要 7 次翻页
        再加页内最多 19 次。
        """
        self.page = (self.page + 1) % BOX_PAGES
        return self.page

    def species_at(self) -> int:
        """仓库视图下当前格对应的 species_id（1~151）。超出 151 返回 0。"""
        sid = self.page * BOX_PER_PAGE + self.cursor + 1
        return sid if sid <= BOX_SPECIES else 0

    def toggle_view(self, p: Party) -> int:
        self.view = VIEW_BOX if self.view == VIEW_PARTY else VIEW_PARTY
        self.cursor = 0 if self.view == VIEW_BOX else min(
            self.cursor, max(0, len(p.party) - 1))
        return self.view

    def selected(self, p: Party) -> Optional[Mon]:
        if self.view == VIEW_PARTY:
            return (p.party[self.cursor]
                    if 0 <= self.cursor < len(p.party) else None)
        sid = self.species_at()
        return p.box.get(sid) if sid else None

    def actions(self, p: Party) -> list[str]:
        """当前选中项可做什么 —— 菜单项按上下文变，避免给出无效选项。"""
        if self.view == VIEW_PARTY:
            acts = []
            if self.cursor > 0:
                acts.append("设为主宠")
            # 仓库永远有位置（按物种号索引），所以只看队伍能不能少一只
            if len(p.party) > 1:
                acts.append("存入仓库")
            acts += ["查看详情", "取名", "返回"]
            return acts
        # 仓库视图：空格子只能返回 —— 别给出对空气的操作
        if self.selected(p) is None:
            return ["返回"]
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
              "查看详情", "取名", "返回",
              # receive/deposit 在同物种相遇时的提示（仓库 151 格后新增）
              "替换了的同种", "更强的一只", "闪光个体",
              "已有更好的", "放走了", "仓库里的更好", "队伍满了"):
        out |= set(s)
    # 视图标题（S14 文档：C 键在「队伍」与「仓库」间切换）
    out |= set("队伍") | set("仓库")
    return out
