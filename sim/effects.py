"""渲染动效 —— 初代原生视觉效果的参考实现。

对应 docs/05-art-audio.md。这份实现是固件渲染层的参考：
所有动效都是**对同一张静态 sprite 做变换**，不需要额外帧素材。

为什么这么做：初代 RBY 的 sprite 是完全静态的，连待机呼吸都没有。
晃动与肢体摆动是二代（金银水晶）才引入的。要原汁原味，
就不能借二代的多帧素材 —— 但初代自己有一套动效，全部靠变换实现：

  遭遇时缩放展开、受击闪白、受击抖动、进化交替闪烁

唯一的例外是主宠待机呼吸（docs/04-gameplay.md#434）——
那是本项目自己加的，因为待机画面是每次点亮屏幕的第一眼。
它也不需要新素材，只是整体上下偏移 1~2 像素。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

# 2bpp 的四个灰阶。0 = 最暗，3 = 最亮（与 convert_sprites 的约定一致）
SHADE_COUNT = 4


class Sprite2bpp:
    """一张 2bpp 位图。

    固件侧这就是一段 flash 地址加宽高，本类只是把取像素封装起来。
    """

    __slots__ = ("data", "size", "row_bytes")

    def __init__(self, data: bytes, size: int):
        self.data = data
        self.size = size
        self.row_bytes = (size * 2 + 7) // 8

    def get(self, x: int, y: int) -> int:
        """取 (x,y) 的灰阶值 0~3。越界返回 3（最亮，即背景）。"""
        if not (0 <= x < self.size and 0 <= y < self.size):
            return SHADE_COUNT - 1
        byte = self.data[y * self.row_bytes + (x * 2) // 8]
        shift = 6 - ((x * 2) % 8)
        return (byte >> shift) & 0x3


# ---------------------------------------------------------------------------
# 灰阶映射 —— 闪白/闪黑靠改映射表，不改像素
# ---------------------------------------------------------------------------

IDENTITY = (0, 1, 2, 3)
FLASH_WHITE = (3, 3, 3, 3)      # 全白：受击瞬间
FLASH_DARK = (0, 0, 1, 3)       # 压暗：进化前的凝聚感
INVERT = (3, 2, 1, 0)           # 反相：进化闪烁的另一半


def flash_sequence(frames: int = 6) -> list[tuple[int, ...]]:
    """受击闪白序列。

    初代受击是 sprite 整体闪白几帧再恢复。这里交替而非渐变 ——
    GB 只有 4 级灰阶，渐变会看起来像脏抖动，硬切反而更接近原版观感。
    """
    return [FLASH_WHITE if i % 2 == 0 else IDENTITY for i in range(frames)]


def evolution_sequence(frames: int = 12) -> list[tuple[int, ...]]:
    """进化闪烁序列 —— 由密到疏，最后定格。

    初代进化是两个 sprite 交替闪烁并逐渐加快。这里返回映射序列，
    调用方负责在 IDENTITY 帧画旧形态、在 INVERT 帧画新形态。
    """
    out: list[tuple[int, ...]] = []
    for i in range(frames):
        # 前段慢、后段快：用递减的周期
        period = max(1, (frames - i) // 3)
        out.append(INVERT if (i // period) % 2 else IDENTITY)
    return out


# ---------------------------------------------------------------------------
# 几何变换
# ---------------------------------------------------------------------------

@dataclass
class Transform:
    """一帧的绘制参数。全部是整数 —— 固件侧不做浮点。"""

    offset_x: int = 0
    offset_y: int = 0
    scale_num: int = 1        # 缩放用整数分数 num/den 表示
    scale_den: int = 1
    shade_map: tuple[int, ...] = IDENTITY
    visible: bool = True


def zoom_in_sequence(frames: int = 8) -> list[Transform]:
    """遭遇时从中心缩放展开。

    初代遭遇是 sprite 由小到大弹出。缩放用整数分数避免浮点：
    第 i 帧的比例是 (i+1)/frames。
    """
    return [Transform(scale_num=i + 1, scale_den=frames) for i in range(frames)]


def shake_sequence(amplitude: int = 2, frames: int = 6) -> list[Transform]:
    """受击横向抖动。

    幅度 2 像素在 240×320 上刚好可见又不夸张。
    """
    return [
        Transform(offset_x=amplitude if i % 2 == 0 else -amplitude)
        for i in range(frames)
    ]


# ---------------------------------------------------------------------------
# 待机呼吸（本项目自加，docs/04-gameplay.md#434）
# ---------------------------------------------------------------------------

# back sprite 的留白实测：下方留白 137 只都是 4 行，上方差异很大
# （0 行的有 22 只，最多 15 行）。
#
# 结论：**呼吸只能向上浮动**。向下会让贴着底边的 sprite 被裁掉，
# 而向上对所有 151 只都安全 —— 因为下方那 4 行留白提供了缓冲：
# 图整体上移 1 像素时，底部空出的行由背景填充，不会露出画布外。
BREATH_MAX_RISE = 2


def breath_sequence(period_frames: int = 8, rise: int = 1) -> list[Transform]:
    """待机呼吸 —— 整体上下浮动 1~2 像素。

    只向上浮动（负 offset_y），见上方 BREATH_MAX_RISE 的说明。

    period_frames 是一个完整呼吸周期的帧数。按「每次点亮屏幕的第一眼」
    设计，实际只在用户看着屏幕的那几十秒里跑，帧率可以很低
    （2~4 fps 就够，8 帧一周期即 2~4 秒一次呼吸，接近静息呼吸节律）。

    时序上「吸气快、屏息、呼气慢」比等分三角波自然得多。
    等分三角波在 1px 幅度下会退化成「三帧不动、一帧跳一格」——
    实测目检发现的（前 3 帧完全相同）。这里改成按停留时长分配：
    最高点停留最久，模拟屏息。
    """
    rise = max(0, min(rise, BREATH_MAX_RISE))
    if rise == 0 or period_frames <= 1:
        return [Transform() for _ in range(max(1, period_frames))]

    # 每个高度停留几帧：低位少停、高位多停
    #   rise=1 → [基线, 顶点, 顶点, 基线...]
    #   rise=2 → 逐级上升，顶点停留最久
    levels: list[int] = []
    for step in range(rise + 1):
        # 顶点（step==rise）停留权重最高
        weight = 2 if step == rise else 1
        levels.extend([-step] * weight)
    # 回落：反向但不重复顶点
    levels.extend(reversed(levels[:-2] if rise > 0 else levels))

    # 拉伸/裁剪到 period_frames
    out: list[Transform] = []
    for i in range(period_frames):
        v = levels[i * len(levels) // period_frames]
        out.append(Transform(offset_y=v))
    return out


# 眨眼：已评估并放弃，理由见下。函数保留但不建议使用。
#
# 两个 Opus agent 独立标注 + 审核了全部 151 只 back sprite 的眼部坐标，
# 结论是这条路走不通：
#
#   visible    1 只（#137 porygon）
#   ambiguous 29 只
#   hidden   121 只   ← back 是背影，多数宝可梦根本看不到眼睛
#
# 而那唯一一只的眨眼**也是空操作**：它的瞳孔 4 像素已经是 0（最暗档），
# 「压暗一档」对 0 是恒等变换。所以实际能驱动的眨眼数是 0，不是 1。
#
# 审核 agent 还跑了一版「暗瞳 + 亮眼白包围」的自动签名检测扫全 151 只，
# 命中约 200 处，绝大多数是须毛/壳纹/皮毛线条/抖动噪点（#36 十处、#56 十二处）。
# **该特征在 RBY 素材上不具判别力** —— 把这些当眼睛只会造成系统性假阳性，
# 压暗错误区域会让图看起来像坏了。
#
# 结论：**待机生命感靠呼吸，不靠眨眼。** 呼吸是整体位移，对全部 151 只
# 一致有效且零风险；眨眼需要逐只标注、上限只有个位数、且容易出错。
#
# 标注数据仍归档在 assets/eye_regions.json（含审核报告），
# 若将来改用 front sprite 做待机（front 信息量是 back 的 3~5 倍，
# 实测皮卡丘 609 vs 196 个非背景像素）可以重新评估。
def blink_sequence(period_frames: int = 40, blink_frames: int = 2) -> list[bool]:
    """偶尔眨眼的时序 —— **已评估放弃，见上方说明**。

    保留此函数仅为文档价值：它给的是时序，而实际阻塞在坐标标注上。
    """
    return [i >= period_frames - blink_frames for i in range(period_frames)]


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def render(
    sprite: Sprite2bpp,
    canvas_size: int,
    tf: Transform,
    put: Callable[[int, int, int], None],
) -> None:
    """把 sprite 按 tf 渲染到画布。

    put(x, y, shade) 由调用方提供 —— 固件里它写入横带缓冲，
    PC 上它可以填一个二维数组。这样渲染逻辑与输出目标解耦。

    分块渲染是硬约束：240×320×16bit = 150KB 装不进 400KB SRAM 的三分之一，
    所以固件永远是「算一条横带、推一条横带」（docs/01-constitution.md#11）。
    本函数不假设画布是整帧。
    """
    if not tf.visible:
        return

    s = sprite.size
    # 缩放后的实际尺寸
    dw = max(1, s * tf.scale_num // tf.scale_den)
    dh = dw

    # 居中，再叠加偏移
    ox = (canvas_size - dw) // 2 + tf.offset_x
    oy = (canvas_size - dh) // 2 + tf.offset_y

    for dy in range(dh):
        # 最近邻采样。GB 风格下这是对的 —— 双线性会把硬边缘糊掉，
        # 而硬边缘正是像素风的一部分。
        sy = dy * s // dh
        for dx in range(dw):
            sx = dx * s // dw
            shade = sprite.get(sx, sy)
            if shade == SHADE_COUNT - 1:
                continue          # 最亮当透明，不画背景
            put(ox + dx, oy + dy, tf.shade_map[shade])


def to_ascii(
    sprite: Sprite2bpp,
    canvas_size: int,
    tf: Optional[Transform] = None,
) -> list[str]:
    """渲染成 ASCII，用于目检动效。

    转换器和渲染器都必须能目检 —— 光看「序列长度 8 帧」
    完全看不出动效对不对。
    """
    tf = tf or Transform()
    grid = [[SHADE_COUNT - 1] * canvas_size for _ in range(canvas_size)]

    def put(x: int, y: int, shade: int) -> None:
        if 0 <= x < canvas_size and 0 <= y < canvas_size:
            grid[y][x] = shade

    render(sprite, canvas_size, tf, put)
    shades = "Oo. "     # 3=最亮→空格
    return ["".join(shades[v] for v in row) for row in grid]
