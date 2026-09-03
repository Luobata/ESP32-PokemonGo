"""S12 昵称 —— 预设候选 + 1 字节存储。

对应 docs/systems/S12-naming.md。

## 为什么不做自由取名

三键设备上从字库里逐字选，代价算出来是这样：

    字库 420 字，B 键循环切字 → 平均按 210 次选中 1 个字
    取 4 字昵称 ≈ 840 次按键

而这台设备的会话预算是 30 秒（docs/04-gameplay.md）。就算把备选砍到
32 字也要 64 次按键，仍然离谱。**自由取名在三键无触摸设备上不成立** ——
这不是妥协，是算出来的结论。

原版 GB 有十字键 + A/B + 完整假名/字母表，那是另一种输入条件。

## 方案：预设候选，B 键循环

24 个预设昵称，存 1 字节索引。平均按 12 次 B 键选中，符合会话预算。

代价是字库要多收这些名字用到的 38 个汉字（1.19 KB）—— 8MB 里的零头。

## 默认不占字节

`NICKNAME_DEFAULT = 0xFF` 表示「没起过名」，显示时回落到物种中文名
（gen1.bin 里已有）。于是**不改名的玩家一个字节都不额外花**，
而改过名的也只花 1 个字节。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 预设候选
#
# 选词取向：**像给宠物起的名**，不是像给角色起的名。
#
# 按语感分四组，B 键循环时同组相邻 —— 玩家翻的时候能感到「这一片是叠字的、
# 这一片是属性的」，而不是一串无序词。这比按拼音排更好用。
# ---------------------------------------------------------------------------

NICKNAMES = [
    # 叠字/软音 —— 最像宠物名的一组，放最前（默认停在这里）
    "小家伙", "豆豆", "果果", "乖乖", "团子", "糯米", "饭团", "肉丸",
    # 属性呼应 —— 与主宠属性对得上时格外贴切
    "闪电", "火苗", "水滴", "叶子", "石头", "毛球",
    # 单字 —— 短名在 240px 宽的状态栏里最省位置
    "风", "云", "星", "宝",
    # 称号 —— 给养到高等级的主宠用
    "大王", "队长", "老大", "阿宝", "元气", "伙计",
]

NICKNAME_DEFAULT = 0xFF     # 「没起过名」→ 显示物种中文名

# 组边界，供 UI 画分隔线（B 键循环时给玩家「翻到下一组」的感觉）
GROUP_BOUNDS = (0, 8, 14, 18, 24)
GROUP_LABELS = ("叠字", "属性", "单字", "称号")


def charset() -> set[str]:
    """这些昵称用到的全部汉字 —— 字库子集化要收进去。"""
    out: set[str] = set()
    for n in NICKNAMES:
        out |= set(n)
    return out


def display_name(nick_idx: int, species_zh: str) -> str:
    """该显示什么名字。

    没起过名（0xFF）就用物种中文名 —— 这让「不改名」是个完全合理的选择，
    而不是显示一个占位符。
    """
    if nick_idx == NICKNAME_DEFAULT or not (0 <= nick_idx < len(NICKNAMES)):
        return species_zh
    return NICKNAMES[nick_idx]


def group_of(nick_idx: int) -> str:
    """该索引属于哪一组（UI 显示用）。

    越界值与未命名同等对待 —— 与 display_name() 保持一致。
    存档损坏时会读到任意字节，两个函数对同一个坏值必须给出一致的解释，
    否则会出现「名字显示皮卡丘、组显示 ?」这种自相矛盾的界面。
    """
    if not (0 <= nick_idx < len(NICKNAMES)):
        return "未命名"
    for i in range(len(GROUP_BOUNDS) - 1):
        if GROUP_BOUNDS[i] <= nick_idx < GROUP_BOUNDS[i + 1]:
            return GROUP_LABELS[i]
    return "未命名"


# ---------------------------------------------------------------------------
# 取名交互
#
# 三键映射：B 下一个、C 上一个、A 确认。
#
# 为什么给 C 键「上一个」而不是别的功能：24 个候选里选错一步就要再转 23 次，
# 而这是个纯线性列表 —— 双向移动是这里最值钱的一个键。
# ---------------------------------------------------------------------------

MAX_PRESS_TO_ANY = len(NICKNAMES) // 2      # 双向可达时最坏一半


class NamePicker:
    """取名状态机。定长状态、无动态分配，可直接照搬进 C。"""

    __slots__ = ("cursor", "committed", "presses")

    def __init__(self, current: int = NICKNAME_DEFAULT) -> None:
        # 从当前昵称开始，而不是从 0 —— 改名时玩家想微调而非重选
        self.cursor = 0 if current == NICKNAME_DEFAULT else current
        self.committed: int = current
        self.presses = 0

    def next(self) -> int:
        """B 键。"""
        self.cursor = (self.cursor + 1) % len(NICKNAMES)
        self.presses += 1
        return self.cursor

    def prev(self) -> int:
        """C 键 —— 反向，避免转错一步要再绕一圈。"""
        self.cursor = (self.cursor - 1) % len(NICKNAMES)
        self.presses += 1
        return self.cursor

    def commit(self) -> int:
        """A 键。"""
        self.committed = self.cursor
        return self.committed

    @property
    def preview(self) -> str:
        return NICKNAMES[self.cursor]

    def distance_from(self, start: int) -> int:
        """从 start 到 cursor 最少要按几次（双向取小）。"""
        n = len(NICKNAMES)
        s = 0 if start == NICKNAME_DEFAULT else start
        fwd = (self.cursor - s) % n
        return min(fwd, n - fwd)


def worst_case_presses() -> int:
    """最坏情况按键数 —— 用来验证「符合 30 秒会话」这个断言。"""
    return MAX_PRESS_TO_ANY + 1        # +1 是 A 键确认
