"""S16 开场剧情 —— 大木博士的话。

对应 docs/systems/S16-opening.md。

## 中文文本的来源与处理

**Gen 1 从未官方中文化**，所以不存在官方中文原文 ——
网上流传的版本（包括百科上看着像官方的那段）都是爱好者翻译。
用户确认「可以用爱好者翻译，然后审核修改」。

所以这里的做法是：
  ① 英文原文从 pret/pokered 一手取得（data/text/text_2.asm:1697
     的 _OakSpeechText1 / 2A / 2B / 3）
  ② 中文取常见爱好者译法为底
  ③ 逐句审核改写，理由记在每句的注释里

每句都标了英文原文，方便核对我改了什么、为什么。

## 三处对原版的必要偏离

**删掉「这是我孙子，你的对手」那一段**（_IntroduceRivalText）。
本项目是单机、没有对手角色，也没有任何地方会再提到他 ——
留着会开一个永不回收的伏笔。

**删掉名字输入**（_IntroducePlayerText「First, what is your name?」）。
三键设备上输入名字要按几百次（S12 算过：420 字的字库取 4 字名要 840 次），
自由取名在这台设备上不成立。

**「让它们互相切磋」而非「用它们战斗」**。
英文原文是 "Others use them for fights"。直译「用来打斗」在中文里
指向斗兽，与整个项目的养成取向相悖 —— 而原版接下来就要你去捕获和对战，
它并不认为那是残忍的事。「切磋」保留了对战的意思而不带那层暗示。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 排版约束（与 sim/strings.py 一致）
# ---------------------------------------------------------------------------

SCREEN_W = 240
GLYPH = 16
MARGIN = 4
USABLE_W = SCREEN_W - MARGIN * 2         # 232px
LINES_PER_BOX = 4                        # 原版 GB 文本框也是 4 行

# 打字机效果：每字间隔帧数。
# 原版是每帧一个字符（英文），但汉字信息密度高得多 ——
# 每帧一个汉字会快到读不了。取 3 帧一字。
TYPE_FRAMES_PER_CHAR = 3
BOX_APPEAR_FRAMES = 6                    # 文本框弹出


def text_px(s: str) -> int:
    """字串宽度（像素）。汉字 16、ASCII 8。"""
    return sum(GLYPH if c > "ÿ" else GLYPH // 2 for c in s)


# ---------------------------------------------------------------------------
# 台词
#
# 每个 Box 是一个文本框（按 A 键翻到下一个）。
# `en` 字段是 pokered 的英文原文，`note` 记我改了什么。
# ---------------------------------------------------------------------------

@dataclass
class Box:
    """一个文本框。"""

    lines: list                          # 每行一个字串，≤4 行
    en: str = ""                         # 英文原文（对照用）
    note: str = ""                       # 审核改动说明
    show_oak: bool = True                # 是否显示博士立绘
    show_mon: int = 0                    # 显示某只宝可梦（species_id，0=不显示）
    pause_after: int = 0                 # 该框结束后额外停顿帧数


SCRIPT = [
    Box(
        lines=["你好！", "欢迎来到", "宝可梦的世界！"],
        en='Hello there! / Welcome to the / world of #MON!',
        note="直译即可。原文 3 行，中文拆 3 行以内。",
    ),
    Box(
        lines=["我叫大木", "人们都叫我", "宝可梦博士"],
        en='My name is OAK! / People call me / the #MON PROF!',
        note="「大木」是官方译名（オーキド博士 → 大木博士），"
             "不是爱好者常用的「欧金博士」。",
    ),
    Box(
        lines=["这个世界里", "生活着一种", "被称为宝可梦的生物"],
        en='This world is / inhabited by / creatures called / #MON!',
        note="英文 inhabited by 是「栖息」的中性说法。"
             "爱好者译常作「充满了」，那偏向数量多；"
             "改「生活着」贴近原意，也为下一句的「有人当伙伴」留出语气。",
        show_mon=25,          # 说到宝可梦时把皮卡丘放出来
    ),
    Box(
        lines=["有人把它们当作伙伴", "也有人", "让它们互相切磋"],
        en='For some people, / #MON are / pets. Others use / them for fights.',
        note="两处改动：pets 译「伙伴」而非「宠物」——"
             "后者在中文里有从属意味，而这游戏的核心是并肩；"
             "fights 译「互相切磋」而非「用来打斗」——"
             "直译在中文里指向斗兽，与养成取向相悖，"
             "而原版并不认为对战是残忍的事。",
        show_mon=25,
    ),
    Box(
        lines=["而我", "把研究宝可梦", "当作毕生的事业"],
        en='Myself... / I study #MON / as a profession.',
        note="原文 Myself... 单独一框（一个停顿）。"
             "这里并进同一框但单独一行，保留那个停顿的节奏。",
        pause_after=20,       # 「而我」之后的停顿是原版的语气所在
    ),
    Box(
        lines=["你的宝可梦传奇", "就要开始了！"],
        en='<PLAYER>! / Your very own / #MON legend is / about to unfold!',
        note="原文以玩家名开头（<PLAYER>!）。本项目不做名字输入"
             "（S12 算过三键取名要按 840 次），所以去掉称呼直接说事。",
    ),
    Box(
        lines=["一个充满", "梦想与冒险的世界", "正在等着你", "出发吧！"],
        en='A world of dreams / and adventures / with #MON / awaits! Let\'s go!',
        note="四行正好是原版文本框的容量上限。"
             "「出发吧」对应 Let's go —— 这句是原版开场的收束，保留感叹。",
        show_oak=False,       # 最后一框博士退场，画面留给玩家
    ),
]

# 被删掉的两段，记录在此以便查证「为什么没有」
OMITTED = [
    {
        "en": 'First, what is / your name?',
        "name": "_IntroducePlayerText",
        "why": "三键设备上输入名字要按几百次（S12：420 字字库取 4 字名 840 次）。"
               "自由取名在这台设备上不成立。",
    },
    {
        "en": "This is my grand- / son. He's been / your rival since / "
              "you were a baby. / ...Erm, what is / his name again?",
        "name": "_IntroduceRivalText",
        "why": "本项目单机、没有对手角色，也没有任何地方会再提到他 —— "
               "留着会开一个永不回收的伏笔。",
    },
]


# ---------------------------------------------------------------------------
# 校验
# ---------------------------------------------------------------------------

def audit() -> dict:
    """排版审计 —— 每行放得下吗、每框行数超了吗。"""
    bad_w, bad_n = [], []
    for i, b in enumerate(SCRIPT):
        if len(b.lines) > LINES_PER_BOX:
            bad_n.append(f"第{i+1}框 {len(b.lines)} 行 > {LINES_PER_BOX}")
        for ln in b.lines:
            px = text_px(ln)
            if px > USABLE_W:
                bad_w.append(f"第{i+1}框「{ln}」{px}px > {USABLE_W}px")
    return {
        "boxes": len(SCRIPT),
        "lines": sum(len(b.lines) for b in SCRIPT),
        "chars": sum(len(ln) for b in SCRIPT for ln in b.lines),
        "widest": max((text_px(ln) for b in SCRIPT for ln in b.lines),
                      default=0),
        "usable": USABLE_W,
        "width_violations": bad_w,
        "line_violations": bad_n,
        "ok": not bad_w and not bad_n,
    }


def charset() -> set:
    """台词用到的全部字符 —— 字库子集化要收进去。"""
    out: set = set()
    for b in SCRIPT:
        for ln in b.lines:
            out |= set(ln)
    return out


def total_frames() -> int:
    """整段开场的帧数（打字机 + 停顿），不含玩家按键等待。

    这个数用来回答「开场要多久」：太长玩家第二次就想跳过了。
    """
    f = 0
    for b in SCRIPT:
        f += BOX_APPEAR_FRAMES
        f += sum(len(ln) for ln in b.lines) * TYPE_FRAMES_PER_CHAR
        f += b.pause_after
    return f


# ---------------------------------------------------------------------------
# 播放状态机
#
# 三键：A 推进（打字中则立即显示整框）、B 无（避免误触跳过）、C 跳过全部。
#
# 为什么 B 键空着：开场只跑一次，而「上一句」在这里没有意义
# （玩家还没有任何信息需要回看）。空着比塞一个功能好 ——
# 三键设备上每个键都该有明确的期待。
# ---------------------------------------------------------------------------

@dataclass
class OpeningFlow:
    """开场剧情状态机。定长状态、无动态分配。"""

    box: int = 0                # 当前第几框
    typed: int = 0              # 当前框已打出几个字
    frame: int = 0
    skipped: bool = False
    done: bool = False

    @property
    def current(self) -> Optional[Box]:
        return SCRIPT[self.box] if 0 <= self.box < len(SCRIPT) else None

    @property
    def full_len(self) -> int:
        b = self.current
        return sum(len(ln) for ln in b.lines) if b else 0

    @property
    def typing(self) -> bool:
        return self.typed < self.full_len

    def tick(self) -> None:
        """推进一帧。"""
        if self.done:
            return
        self.frame += 1
        if self.typing and self.frame % TYPE_FRAMES_PER_CHAR == 0:
            self.typed += 1

    def visible_lines(self) -> list:
        """当前该显示的文本（含打字机效果的部分行）。"""
        b = self.current
        if not b:
            return []
        out, left = [], self.typed
        for ln in b.lines:
            if left <= 0:
                break
            out.append(ln[:left])
            left -= len(ln)
        return out

    def press(self, key: str) -> str:
        """三键输入。返回发生了什么。"""
        if self.done:
            return "已结束"
        if key == "C":
            self.skipped = True
            self.done = True
            return "跳过全部"
        if key == "A":
            if self.typing:
                # 打字中按 A 立即显示整框 —— 不是跳到下一框。
                # 这是原版行为，也是唯一合理的：玩家想快看完这句，
                # 而不是错过它。
                self.typed = self.full_len
                return "立即显示整框"
            self.box += 1
            self.typed = 0
            self.frame = 0
            if self.box >= len(SCRIPT):
                self.done = True
                return "剧情结束"
            return f"第 {self.box + 1} 框"
        return "无效"        # B 键刻意不响应
