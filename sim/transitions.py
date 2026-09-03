"""S15 转场与出场动画 —— 闪光星环、遭遇转场、进化闪烁。

对应 docs/systems/S15-transitions.md。

## 参数全部来自 pret 反汇编逐行阅读，不是估的

    闪光星环   pokecrystal/data/moves/animations.asm
               BattleAnim_SendOutMon.Shiny (:442)
    转场       pokered/engine/battle/battle_transitions.asm
    进化       pokered/engine/movie/evolution.asm  EvolveMon

三处我原本都会做错，抄对了才有那个味道：

**闪光不是星星向外飞散。** 8 颗星停在半径 16px 圆周的固定角度，
从正右方起顺时针每 45° 一颗、每 4 帧点亮一颗。星星**不动**
（偏移只在生成时算一次），只播自己的闪烁帧然后自删。

**转场不随机。** 3 个 bit 查表，完全确定性 —— 玩家会从转场认出
对手强弱，随机化会毁掉这个信息通道。

**进化闪烁是加速的，而且是黑色剪影。** 8 轮，每轮来回次数 1→8 递增、
轮间等待 16→2 帧递减。整段闪烁用 PAL_BLACK，两个形态都是黑影在跳，
结束才恢复新形态的正常调色板。用固定间隔或彩色对切都不对味。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# ① 闪光星环
# ---------------------------------------------------------------------------

SHINY_STAR_COUNT = 8            # param $00 $08 … $38 共 8 组
SHINY_STEP_FRAMES = 4           # anim_wait 4
SHINY_TAIL_FRAMES = 32          # 末尾 anim_wait 32
SHINY_RADIUS = 16               # d=$10，注释 "circle formation of radius $10"
SHINY_TOTAL_FRAMES = SHINY_STAR_COUNT * SHINY_STEP_FRAMES + SHINY_TAIL_FRAMES

# 单颗星的帧动画 .Frameset_Sparkle：
#   oamframe OAMSET_74, 3   ← 4 个 sprite 拼成的 16×16 大星芒
#   oamframe OAMSET_14, 3   ← 单个 8×8，tile $00
#   oamframe OAMSET_15, 3   ← 单个 8×8，tile $01
#   oamframe OAMSET_14, 3
#   oamframe OAMSET_15, 3
#   oamdelete
# duration=3 → 该帧显示 4 帧（GetBattleAnimFrame 的语义）。
# 所以：先一个大星芒，然后小星在两个 tile 间闪 4 次，共 20 帧后自删。
SHINY_STAR_FRAME_DUR = 4        # duration 3 → 显示 4 帧
SHINY_STAR_FRAMES = 5           # 帧集里 5 个 oamframe
SHINY_STAR_LIFE = SHINY_STAR_FRAMES * SHINY_STAR_FRAME_DUR      # 20

# 全屏叠加（engine/battle_anims/bg_effects.asm）
SHINY_BGP_FLASHES = 3           # FLASH_INVERTED param=$3
SHINY_BGP_FLASH_FRAMES = 4      # turn=$4，每档 4 帧
SHINY_OBP_CYCLE_FRAMES = 2      # CYCLE_OBPALS turn=$2

# 音效：每颗星一次，共 8 次
SHINY_SFX_PER_STAR = True


@dataclass
class StarSpawn:
    """一颗星的出现时刻与位置。"""

    index: int
    frame: int
    dx: int
    dy: int
    angle_deg: int
    big: bool = False


def shiny_stars(radius: int = SHINY_RADIUS) -> list[StarSpawn]:
    """8 颗星的时序与位置。

    角度照反汇编的正弦表：周期 64 = 整圈（a*pi/32），
    param 依次 $00 $08 … $38 → 每 45°。
    y 向下为正，所以从正右方开始是顺时针。

    反汇编算出的整数偏移（用于校验）：
      $00 (+16, 0)  $08 (+11,+11)  $10 (0,+16)  $18 (-11,+11)
      $20 (-16, 0)  $28 (-11,-11)  $30 (0,-16)  $38 (+11,-11)
    """
    out: list[StarSpawn] = []
    for i in range(SHINY_STAR_COUNT):
        param = i * 8
        rad = param * 2 * math.pi / 64
        dx = round(math.cos(rad) * radius)
        dy = round(math.sin(rad) * radius)
        out.append(StarSpawn(
            index=i, frame=1 + i * SHINY_STEP_FRAMES,
            dx=dx, dy=dy, angle_deg=param * 360 // 64,
            # 正交四方向用大星、对角用小星 —— 视觉上圆环更匀
            big=(dx == 0 or dy == 0),
        ))
    return out


def shiny_frame_state(frame: int) -> dict:
    """第 frame 帧的完整状态。固件与页面都调它，保证时序一致。"""
    stars = []
    for s in shiny_stars():
        age = frame - s.frame
        if 0 <= age < SHINY_STAR_LIFE:
            fi = age // SHINY_STAR_FRAME_DUR        # 第几个 oamframe
            stars.append({
                "i": s.index, "dx": s.dx, "dy": s.dy, "age": age,
                # 第 0 帧是 16×16 大星芒，之后是 8×8 小星交替
                "big": fi == 0,
                "alt": fi % 2 == 0,                 # tile $00 / $01
            })
    inverted = False
    if frame <= SHINY_BGP_FLASHES * SHINY_BGP_FLASH_FRAMES:
        inverted = ((frame - 1) // SHINY_BGP_FLASH_FRAMES) % 2 == 0
    obp_yellow = ((frame - 1) // SHINY_OBP_CYCLE_FRAMES) % 2 == 0
    sfx = any(s.frame == frame for s in shiny_stars())
    return {"frame": frame, "stars": stars, "inverted": inverted,
            "obpYellow": obp_yellow, "sfx": sfx,
            "done": frame > SHINY_TOTAL_FRAMES}


# 时序位置：**在 sprite 出现之后**，作为独立的第二次动画调用。
# 野生遭遇里插在「sprite 已就位」与「叫声」之间；普通遭遇这里什么都不插。
SHINY_PHASE = "after_sprite_before_cry"

# Gen 2 的判定条件（engine/gfx/color.asm:3）：
#   Atk DV & %0010 != 0  且  Def DV == 10  且  Spd DV == 10  且  Spc DV == 10
# 概率 = (8/16) × (1/16)³ = 1/8192。
#
# 本项目不用 DV（没有个体值系统），闪光判定见 S8 的
# crc32(bssid|hour|rarity) —— 但概率取 1/512 而非 1/8192：
# 原版 8192 是为几百小时的流程设计的，而这台设备的遭遇频率低得多。
GEN2_SHINY_DENOM = 8192


# ---------------------------------------------------------------------------
# ② 遭遇转场
#
# pokered 的选择规则（battle_transitions.asm:71），**完全确定性**：
#   bit0 训练师战
#   bit1 敌方等级 ≥ 我方首只未濒死宝可梦 +3
#   bit2 迷宫地图
#
# 本项目把 bit2「迷宫」换成 biome —— 我们没有迷宫，但有 biome，
# 而「在什么地方遇到」同样该影响观感。
# ---------------------------------------------------------------------------

TRANSITIONS = {
    "double_circle": {"frames": 102, "zh": "双圆", "kind": "circle",
                      "note": "72 帧闪屏 + 10 轮 × 3"},
    "circle": {"frames": 132, "zh": "圆形", "kind": "circle",
               "note": "72 帧闪屏 + 20 轮 × 3（两个半圆串行）"},
    "h_stripes": {"frames": 60, "zh": "横向百叶", "kind": "stripes",
                  "note": "20 轮 × 3"},
    "v_stripes": {"frames": 54, "zh": "纵向百叶", "kind": "stripes",
                  "note": "18 轮 × 3"},
    "spiral_out": {"frames": 120, "zh": "外螺旋", "kind": "spiral",
                   "note": "b=120，每轮 1 帧"},
    "spiral_in": {"frames": 153, "zh": "内螺旋", "kind": "spiral",
                  "note": "359 格，每 7 格 Delay3 → 51×3"},
    "shrink": {"frames": 64, "zh": "向心收拢", "kind": "shrink",
               "note": "9 轮 × 6 + 尾 10"},
    "split": {"frames": 64, "zh": "上下撕开", "kind": "split",
              "note": "9 轮 × 6 + 尾 10"},
}

OPEN_BIOMES = ("野外", "交通枢纽")       # 对应原版的「非迷宫」

# 转场开头的闪屏 —— 只有 Circle 系有（BattleTransition_FlashScreen_）
FLASH_KINDS = ("circle",)
FLASH_FRAMES = 72               # 12 个调色板条目 × 2 帧 × 3 次


def pick_transition(is_trainer: bool, wild_level: int, pet_level: int,
                    biome: str) -> tuple[str, int]:
    """选转场。返回 (名称, 3-bit 索引)。

    **完全确定性，不随机** —— 这是原版一个聪明的设计：
    玩家会从转场认出对手强弱，看到某种转场就知道这场不好打。
    随机化会毁掉这个信息通道。

    bit1 的判据照原版：敌方等级 ≥ 我方 + 3。
    """
    bit0 = 1 if is_trainer else 0
    bit1 = 2 if wild_level >= pet_level + 3 else 0
    bit2 = 0 if biome in OPEN_BIOMES else 4
    idx = bit0 | bit1 | bit2

    # 索引顺序照 pokered 的 BattleTransitions 表
    table = {
        0b000: "double_circle",     # 野生 / 开阔 / 同级
        0b001: "spiral_in",         # 训练师 / 开阔 / 同级
        0b010: "circle",            # 野生 / 开阔 / 强敌
        0b011: "spiral_out",        # 训练师 / 开阔 / 强敌
        0b100: "h_stripes",         # 野生 / 密闭 / 同级
        0b101: "shrink",            # 训练师 / 密闭 / 同级
        0b110: "v_stripes",         # 野生 / 密闭 / 强敌
        0b111: "split",             # 训练师 / 密闭 / 强敌
    }
    return table[idx], idx


# 屏幕的 8×8 tile 网格。240×320 → 30×40 格
TILE = 8
GRID_W, GRID_H = 240 // TILE, 320 // TILE       # 30 × 40


def transition_mask(name: str, progress: float) -> list[list[bool]]:
    """转场在进度 progress（0~1）时哪些 tile 已被黑块覆盖。

    机制照原版：**往 BG tilemap 写纯黑 tile**（pokered 里是 tile $ff，
    我确认过 gfx/overworld/battle_transition.png 全部像素为 0 即纯黑），
    不是 scanline 也不是调色板。唯一用调色板的是 Circle 系开头的闪屏。

    所以这里返回 30×40 布尔网格，固件直接照它填黑块。
    每种几何的填充顺序不同 —— 那就是转场之间的差异所在。
    """
    kind = TRANSITIONS.get(name, {}).get("kind", "shrink")
    m = [[False] * GRID_W for _ in range(GRID_H)]
    cx, cy = (GRID_W - 1) / 2.0, (GRID_H - 1) / 2.0
    p = max(0.0, min(1.0, progress))

    if kind == "circle":
        r_max = (cx * cx + cy * cy) ** 0.5
        r_now = r_max * (1.0 - p)
        for y in range(GRID_H):
            for x in range(GRID_W):
                d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                m[y][x] = d > r_now
        if name == "double_circle":
            # 双圆：中心同时长出一个小黑圆，两者相向合拢
            r_in = r_max * p * 0.45
            for y in range(GRID_H):
                for x in range(GRID_W):
                    if ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 < r_in:
                        m[y][x] = True

    elif kind == "stripes":
        # 原版是「隔行填充、逐列推进」（HorizontalStripes 每轮写一条隔行竖列）。
        # 隔一行才有「百叶」的透光感 —— 一次填满整行就只是幕布下落。
        if name == "h_stripes":
            done = int(GRID_W * p)
            for x in range(done):
                for y in range(0, GRID_H, 2):
                    m[y][x] = True
            # 后半程补上奇数行
            if p > 0.5:
                for x in range(int(GRID_W * (p - 0.5) * 2)):
                    for y in range(1, GRID_H, 2):
                        m[y][x] = True
        else:
            done = int(GRID_H * p)
            for y in range(done):
                for x in range(0, GRID_W, 2):
                    m[y][x] = True
            if p > 0.5:
                for y in range(int(GRID_H * (p - 0.5) * 2)):
                    for x in range(1, GRID_W, 2):
                        m[y][x] = True

    elif kind == "spiral":
        # 原版外螺旋从中心 (10,10) 起、撞到已填格就转向（右→上→左→下）。
        # 这里用「半径为主序 + 角度为次序」近似，效果是一圈一圈地转。
        cells = []
        for y in range(GRID_H):
            for x in range(GRID_W):
                d = ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5
                a = math.atan2(y - cy, x - cx)
                cells.append((d + a / (2 * math.pi), y, x))
        cells.sort(reverse=(name == "spiral_in"))
        for k in range(int(len(cells) * p)):
            _, y, x = cells[k]
            m[y][x] = True

    elif kind == "shrink":
        # 上下左右四边同时向内挤（原版 CopyTiles1/2 每轮挤 2 行/列）
        band_y = int(cy * p) + 1
        band_x = int(cx * p) + 1
        for y in range(GRID_H):
            for x in range(GRID_W):
                if (y < band_y or y >= GRID_H - band_y
                        or x < band_x or x >= GRID_W - band_x):
                    m[y][x] = True

    elif kind == "split":
        # 与 shrink 相反：中线裂开，画面向上下撕走（中间露黑）
        half = int(cy * p) + 1
        for y in range(GRID_H):
            if abs(y - cy) < half:
                m[y] = [True] * GRID_W

    return m


def transition_frames(name: str) -> int:
    return TRANSITIONS.get(name, {}).get("frames", 64)


def has_flash(name: str) -> bool:
    return TRANSITIONS.get(name, {}).get("kind") in FLASH_KINDS


# ---------------------------------------------------------------------------
# ③ 进化闪烁
#
# pokered/engine/movie/evolution.asm 的 EvolveMon：
#   lb bc, $1, $10        ; b=1（本轮来回次数）, c=16（轮间等待帧）
#   循环末 inc b / dec c / dec c
#
# 于是 8 轮：
#   轮次  来回次数  轮间等待
#    1       1        16
#    2       2        14
#    ...
#    8       8         2
#
# **加速曲线必须照抄** —— 固定间隔就不对味了。
# 总来回 1+…+8 = 36 次，每次来回 2 次切图 × 3 帧 = 6 帧 → 216 帧，
# 加轮间等待 72 帧 = 288 帧（≈4.8 秒）。
# ---------------------------------------------------------------------------

EVOLVE_ROUNDS = 8
EVOLVE_START_SWAPS = 1          # b 初值
EVOLVE_START_WAIT = 16          # c 初值
EVOLVE_WAIT_STEP = 2            # 每轮 dec c 两次
EVOLVE_SWAP_HOLD = 3            # 每次切图后 Delay3
EVOLVE_PRE_WAIT = 80            # 音乐起后、闪烁前的 DelayFrames 80

# **整段闪烁用 PAL_BLACK** —— 两个形态都是黑色剪影在跳，不是彩色对切。
# 结束时才恢复新形态的正常调色板（EvolutionSetWholeScreenPalette c=0）。
EVOLVE_SILHOUETTE = True


def evolution_timeline() -> list[dict]:
    """进化闪烁的完整时间线。

    每项是一次切图：frame（发生在第几帧）、show_new（显示新形态还是旧的）、
    round（第几轮）。
    """
    out: list[dict] = []
    frame = EVOLVE_PRE_WAIT
    swaps, wait = EVOLVE_START_SWAPS, EVOLVE_START_WAIT

    for rnd in range(1, EVOLVE_ROUNDS + 1):
        for k in range(swaps):
            # 一次「来回」= 切到新形态再切回旧形态
            out.append({"frame": frame, "show_new": True, "round": rnd})
            frame += EVOLVE_SWAP_HOLD
            out.append({"frame": frame, "show_new": False, "round": rnd})
            frame += EVOLVE_SWAP_HOLD
        frame += wait                       # 轮间等待
        swaps += 1
        wait -= EVOLVE_WAIT_STEP
        if wait <= 0:
            break

    # 定格在新形态
    out.append({"frame": frame, "show_new": True, "round": EVOLVE_ROUNDS + 1})
    return out


def evolution_blink_frames() -> int:
    """**只有闪烁段**的帧数 —— 与反汇编推导的 288 对齐。

    来回 36 次 × 2 次切图 × 3 帧 = 216，加轮间等待 72 = 288。
    """
    return evolution_total_frames() - EVOLVE_PRE_WAIT


def evolution_total_frames() -> int:
    """含前置等待的总帧数。

    注意与 288 的区别：288 是**纯闪烁段**，而这个数含 EVOLVE_PRE_WAIT
    的 80 帧（音乐起后的静止等待）。368 = 288 + 80，两个数都对，
    只是含义不同 —— 我第一版把它们混为一谈了。
    """
    tl = evolution_timeline()
    return tl[-1]["frame"] if tl else 0


def evolution_rounds() -> list[dict]:
    """逐轮参数 —— 用来在验收面板上展示加速曲线。"""
    out = []
    swaps, wait = EVOLVE_START_SWAPS, EVOLVE_START_WAIT
    for rnd in range(1, EVOLVE_ROUNDS + 1):
        out.append({"round": rnd, "swaps": swaps, "wait": wait,
                    "frames": swaps * 2 * EVOLVE_SWAP_HOLD + wait})
        swaps += 1
        wait -= EVOLVE_WAIT_STEP
        if wait <= 0:
            break
    return out


# 进化流程的音频时序（无逐次闪烁音效，闪烁期间只有 BGM）
EVOLVE_AUDIO = [
    ("stop_music", "停掉原音乐"),
    ("sfx_tink", "一声 tink"),
    ("cry_old", "旧形态叫声（等它播完）"),
    ("bgm", "进化 BGM（原版复用 Safari Zone 曲）"),
    ("wait_80", "静止 80 帧"),
    ("blink", "288 帧闪烁 —— 期间只有 BGM"),
    ("stop_music", "停 BGM"),
    ("cry_new", "新形态叫声（若被取消则播旧形态）"),
]


# ---------------------------------------------------------------------------
# 渲染预算
# ---------------------------------------------------------------------------

BAND_H = 16                     # 分块横带高度


def budget() -> dict:
    """转场的重绘代价。

    240×320 整帧 RGB565 = 150 KB 而 SRAM 只有 400 KB ——
    转场不能整帧重绘，必须按横带刷。
    """
    return {
        "fullFrameKB": round(240 * 320 * 2 / 1024, 1),
        "bandKB": round(240 * BAND_H * 2 / 1024, 1),
        "bandsPerFrame": 320 // BAND_H,
        "gridW": GRID_W, "gridH": GRID_H,
        "shinyFrames": SHINY_TOTAL_FRAMES,
        "shinyStarLife": SHINY_STAR_LIFE,
        "evolveBlinkFrames": evolution_blink_frames(),    # 288，对齐反汇编
        "evolveTotalFrames": evolution_total_frames(),     # 368 = 288 + 前置 80
        "evolvePreWait": EVOLVE_PRE_WAIT,
        "evolveSwaps": sum(r["swaps"] for r in evolution_rounds()),
        "transitions": {k: v["frames"] for k, v in TRANSITIONS.items()},
    }
