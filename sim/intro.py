"""S11 开场流程 —— GB 启动动画 + 初始伙伴选择。

对应 docs/systems/S11-intro.md。

两段：
  ① 启动动画 —— 复刻 DMG boot ROM 的 logo 滚动
  ② 伙伴选择 —— 三个精灵球（御三家）+ 皮卡丘在外，手指光标选择

固件移植取向与其他系统一致：定长状态、整数运算、无动态分配。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# ① 启动动画
#
# 参数取自 DMG boot ROM 反汇编（drhelius/6063288）：
#
#   LD D,$64        滚动循环 100 次，每次 SCY 减 1
#   CP $62          H==98  → 播 sound #1（E=$83）
#   CP $64          H==100 → 播 sound #2（E=$c1）
#   LD D,$20        落定后 32 次的暂停循环
#
# **关键细节：音效在第 98 与 100 步响，也就是落定瞬间** —— 不是开头。
# 很多复刻版把「叮」放在动画开始，那是错的：原版是 logo 停住的同时出声，
# 两者的节奏感完全不同。
# ---------------------------------------------------------------------------

SCROLL_STEPS = 100          # 原版 D=$64
SOUND_STEP_1 = 98           # 原版 CP $62
SOUND_STEP_2 = 100          # 原版 CP $64
SETTLE_PAUSE_STEPS = 32     # 原版 D=$20

# 240×320 上的位置。GB 原生 160×144、logo 48×8 位于 Y≈64；
# 等比放大 1.5× → 72×12。
LOGO_W, LOGO_H = 72, 12
LOGO_X = (240 - LOGO_W) // 2
LOGO_Y_START = 220          # 屏幕下方偏中
LOGO_Y_END = 120            # 落定位置（略高于中线，给下方标题留空间）


@dataclass
class BootFrame:
    """启动动画的一帧。"""

    step: int
    logo_y: int
    sound: Optional[int] = None    # 1 或 2，对应原版两声
    settled: bool = False


def boot_sequence() -> list[BootFrame]:
    """完整启动序列 —— 滚动 100 步 + 落定暂停 32 步。

    按 30fps 播放约 4.4 秒，与原版观感（约 2.5 秒滚动 + 0.8 秒停顿）
    量级一致。固件侧可按实测帧率调整。
    """
    frames: list[BootFrame] = []

    for step in range(1, SCROLL_STEPS + 1):
        # 线性插值：step=1 在起点，step=100 在终点
        y = LOGO_Y_START - (LOGO_Y_START - LOGO_Y_END) * step // SCROLL_STEPS
        snd = 1 if step == SOUND_STEP_1 else (2 if step == SOUND_STEP_2 else None)
        frames.append(BootFrame(step=step, logo_y=y, sound=snd))

    # 落定暂停 —— logo 不动，给「叮」的余韵留时间
    for i in range(SETTLE_PAUSE_STEPS):
        frames.append(BootFrame(step=SCROLL_STEPS + i + 1,
                                logo_y=LOGO_Y_END, settled=True))

    return frames


# ---------------------------------------------------------------------------
# ② 伙伴选择
#
# 布局：三个精灵球一排（御三家藏在里面），皮卡丘站在球外。
#
# 为什么皮卡丘在球外：它在原版黄版里就是**跟在训练家身后**的，
# 从不进球。把它放在三球之外，一眼就能看出「这只不一样」——
# 而不需要任何文字说明。
#
# 手指光标（原版选择菜单的标志性元素）在四个位置间移动。
# 三键映射：B 键移动光标、A 键确认、C 键查看详情。
# ---------------------------------------------------------------------------

# 御三家 + 皮卡丘。id 对应 gen1.bin 的记录序号。
STARTERS = [
    {"id": 1, "slug": "bulbasaur", "zh": "妙蛙种子", "type": "草", "in_ball": True},
    {"id": 4, "slug": "charmander", "zh": "小火龙", "type": "火", "in_ball": True},
    {"id": 7, "slug": "squirtle", "zh": "杰尼龟", "type": "水", "in_ball": True},
    {"id": 25, "slug": "pikachu", "zh": "皮卡丘", "type": "电", "in_ball": False},
]

# 240×320 上的坐标。三球一排在中部，皮卡丘在下方偏右 —— 刻意不对齐，
# 强化「它不在队列里」的感觉。
BALL_Y = 150
BALL_XS = (54, 120, 186)        # 三球中心 X，间距 66
# 皮卡丘上移到 226：它的下方手指（中心 +30，形状占 -16~+6）
# 原本落在 252~274，压在 sprite（213~263）身上。上移后手指在 240~262，
# sprite 在 201~251 —— 手指尖触到它下缘，与三球一致。
PIKA_POS = (172, 226)           # 皮卡丘中心

# 手指光标的位置：目标**下方**，指向上。
#
# 原版菜单的手指在选项左侧向右指，但那是**纵向列表**。这里是三球横排，
# 240px 宽装不下「每球各配一个左侧手指」——
#   每格需 手指22 + 间隙30 + 球34 = 86px，三格 258px > 240。
# 实测算出来才发现，所以改成手指在球下方向上指：只占垂直空间，
# 三球 102px + 间隙 24px = 126px 绰绰有余。
#
# 保留「手指」这个形状而不换成箭头 —— 那是初代菜单最认得出的符号，
# 换成箭头功能一样但味道就没了。
CURSOR_OFFSET_X = 0
CURSOR_OFFSET_Y = 30            # 在目标下方 30px


@dataclass
class StarterChoice:
    """伙伴选择的状态机。"""

    cursor: int = 1              # 默认停在小火龙（中间那颗球）
    revealed: list = field(default_factory=lambda: [False] * 4)
    confirmed: Optional[int] = None

    def move(self, delta: int = 1) -> int:
        """B 键 —— 光标循环移动。"""
        self.cursor = (self.cursor + delta) % len(STARTERS)
        return self.cursor

    def peek(self) -> dict:
        """C 键 —— 开球看一眼（不确认）。

        原版是选了才知道，但那对**三键无触摸**的设备太苛刻：
        玩家看不到球里是什么，选择就是纯赌博。
        允许预览，但保留「开球」的动作感 —— 球会打开，sprite 弹出。
        """
        self.revealed[self.cursor] = True
        return STARTERS[self.cursor]

    def confirm(self) -> dict:
        """A 键 —— 确认选择。"""
        self.confirmed = self.cursor
        self.revealed[self.cursor] = True
        return STARTERS[self.cursor]

    @property
    def target(self) -> dict:
        return STARTERS[self.cursor]

    def cursor_pos(self) -> tuple[int, int]:
        """手指光标当前该画在哪 —— 目标下方，指向上。"""
        cx, cy = self.sprite_pos(self.cursor)
        return (cx + CURSOR_OFFSET_X, cy + CURSOR_OFFSET_Y)

    def sprite_pos(self, index: int) -> tuple[int, int]:
        """第 index 只的 sprite 中心位置。"""
        if index < 3:
            return (BALL_XS[index], BALL_Y)
        return PIKA_POS


# ---------------------------------------------------------------------------
# 初始状态
# ---------------------------------------------------------------------------

# 初始等级。原版御三家是 Lv5，但本项目的野怪 ★ 档是 Lv5
# （见 systems.py 的 WILD_LEVEL_BAND）—— 同级开局会让第一场战斗五五开，
# 而新手第一场应该赢。给 Lv5 但送几个球，让玩家先靠捕获起步。
STARTER_LEVEL = 5
STARTER_ITEMS = {"poke": 5, "berry": 3}


def apply_choice(choice_index: int) -> dict:
    """把选择结果转成初始存档字段。

    返回的字段名与 sim/state.py 的 SaveData 对应。
    """
    s = STARTERS[choice_index]
    return {
        "pet_species": s["id"],
        "pet_level": STARTER_LEVEL,
        "pet_type": s["type"],
        # 初始不起名 —— 显示物种中文名，玩家想改再去 P5 改
        "nickname_idx": 0xFF,
        "satiety": 80,
        "mood": 70,          # 不给满 —— 留出「照料能提升」的空间
        "stamina": 90,
        "intimacy": 0,
        "explore_value": 0,
        "items": dict(STARTER_ITEMS),
        # 初始伙伴直接入图鉴「已捕获」
        "dex_caught": [s["id"]],
    }


# ---------------------------------------------------------------------------
# 完整开场流程
# ---------------------------------------------------------------------------

PHASE_BOOT = "boot"           # GB 启动动画
PHASE_TITLE = "title"         # 标题画面（按任意键继续）
PHASE_CHOOSE = "choose"       # 伙伴选择
PHASE_DONE = "done"


@dataclass
class IntroFlow:
    """开场状态机。

    只在**首次启动**跑一次 —— 之后由 S6 存档的存在判定跳过。
    这是刻意的：GB 启动动画的仪式感来自「开机」，
    每次点亮屏幕都放一遍会变成负担（而屏幕不能常亮，点亮很频繁）。
    """

    phase: str = PHASE_BOOT
    frame: int = 0
    choice: StarterChoice = field(default_factory=StarterChoice)

    def tick(self) -> Optional[BootFrame]:
        """推进一帧。返回当前启动帧（仅 boot 阶段）。"""
        if self.phase != PHASE_BOOT:
            return None
        seq = boot_sequence()
        if self.frame >= len(seq):
            self.phase = PHASE_TITLE
            return None
        f = seq[self.frame]
        self.frame += 1
        return f

    def press(self, key: str) -> str:
        """三键输入。返回新阶段。"""
        if self.phase == PHASE_BOOT:
            # 允许跳过 —— 第 N 次刷固件时不想再看
            self.phase = PHASE_TITLE
        elif self.phase == PHASE_TITLE:
            self.phase = PHASE_CHOOSE
        elif self.phase == PHASE_CHOOSE:
            if key == "A":
                self.choice.confirm()
                self.phase = PHASE_DONE
            elif key == "B":
                self.choice.move()
            elif key == "C":
                self.choice.peek()
        return self.phase

    def result(self) -> Optional[dict]:
        if self.phase != PHASE_DONE or self.choice.confirmed is None:
            return None
        return apply_choice(self.choice.confirmed)
