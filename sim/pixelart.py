"""开场画面的像素素材 —— 精灵球、手指光标、星光。

## 为什么单独一个模块

验收时截图暴露的问题：**画风打架**。
精灵球是 canvas 矢量画的平滑圆、皮卡丘顶着白方块、标题用拉丁点阵字 ——
跟 151 只 2bpp sprite 的像素画风完全不是一回事。

矢量圆在像素画里格外突兀：它没有台阶感，而周围一切都有。

所以这些元素也按点阵生成，与 sprite 同一套渲染路径（2bpp + 调色板）。

## 为什么算法生成而非手画点阵

精灵球是规则几何体。我先手画了一版 16×16，不对称、白格没对齐 ——
算法生成能保证左右严格对称，且换尺寸不用重画。

关键是**先量化到像素网格再判断**，圆边才有台阶感；
若先算连续圆再采样会得到反锯齿的软边，那就又变回矢量观感了。

零第三方依赖，Python 3.9+。
"""

from __future__ import annotations

# 2bpp 色号约定（与 sprite 一致：低号深、高号浅，3 号当透明）
INK = 0          # 描边
MID = 1          # 主色（精灵球上半的红）
LIGHT = 2        # 亮色（下半的白、按钮）
CLEAR = 3        # 透明

# 精灵球调色板（RGB565 源色，与 assets/palettes.bin 同格式）
BALL_PALETTE = ["#101010", "#c83c30", "#f0f0f0", "#182838"]
# 开球后的空球（灰）—— 用于「已经开过的球」
BALL_OPEN_PALETTE = ["#101010", "#707070", "#c0c0c0", "#182838"]


def poke_ball(size: int = 24, open_top: bool = False) -> list[list[int]]:
    """生成精灵球点阵。

    open_top=True 时上半盖打开（画成两片分离），用于「开球」瞬间。

    参数是**比例**而非绝对像素，所以任何尺寸都成立：
      描边 1.6px、中央带 size/10、按钮半径 size×0.16
    这几个比例是照 GB 原版精灵球图标的观感调的。
    """
    c = (size - 1) / 2.0
    r_out = size / 2.0
    band = max(2.0, size / 10.0)          # 中央黑带厚度
    btn = size * 0.16                     # 按钮半径

    g = [[CLEAR] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            dx, dy = x - c, y - c
            d = (dx * dx + dy * dy) ** 0.5
            if d > r_out - 0.5:
                continue                              # 圆外
            if d > r_out - 1.6:
                g[y][x] = INK                         # 外描边
            elif abs(dy) < band / 2:
                g[y][x] = INK                         # 中央带
            elif btn - 0.2 <= d < btn + 1.3:
                g[y][x] = INK                         # 按钮描边
            elif d < btn:
                g[y][x] = LIGHT                       # 按钮
            elif dy < 0:
                g[y][x] = MID                         # 上半（红）
            else:
                g[y][x] = LIGHT                       # 下半（白）

    if open_top:
        # 上半盖上移 3px 并留出缝隙 —— 「打开」的最小表达
        top = [row[:] for row in g[:size // 2]]
        for y in range(size // 2):
            g[y] = [CLEAR] * size
        for y in range(size // 2):
            ty = y - 3
            if 0 <= ty < size // 2:
                g[ty] = top[y]

    return g


# ---------------------------------------------------------------------------
# 手指光标
#
# 原版菜单最认得出的符号。上一版用 canvas 路径画（贝塞尔平滑边），
# 在像素画里同样突兀 —— 改成手绘点阵。
#
# 朝上指（三球横排的约束，见 sim/intro.py 的 CURSOR_OFFSET_Y）：
# 竖起的食指 + 握起的拳。12×11。
#
# 不对称是**应该的** —— 手本来不对称，所以不对它做对称检查。
# ---------------------------------------------------------------------------

_C = """
.....00.....
....0220....
....0220....
....0220....
....0220....
.00002200000
.0220222 220
.02202222220
.02222222220
.00222222220
...000000000
""".strip().split("\n")

CURSOR = [[CLEAR if ch == "." else (INK if ch == "0" else LIGHT) for ch in row]
          for row in _C]
CURSOR_W, CURSOR_H = len(CURSOR[0]), len(CURSOR)
CURSOR_PALETTE = ["#101010", "#f8f8f8", "#f8f8f8", "#182838"]


# ---------------------------------------------------------------------------
# 星光 —— 闪光出场用（S8）
#
# 四角星，三档尺寸。GB 的闪光星星就是这种简单十字星，
# 不是多角星也不是光晕。
# ---------------------------------------------------------------------------

def star(size: int = 7) -> list[list[int]]:
    """四角星点阵 —— 十字主芒 + 对角短芒。size 应为奇数。

    GB 的闪光星星就是这种简单十字星，不是多角星也不是光晕。

    我第一版用「双循环镜像」写（g[c+i][c+j] 与 g[c+j][c+i] 同时赋值），
    长出了斜向杂散点 —— 镜像赋值把主芒也镜像成了对角线。
    改成显式画十字 + 中心菱形，形状才干净。
    """
    if size % 2 == 0:
        size += 1
    c = size // 2
    g = [[CLEAR] * size for _ in range(size)]

    # 十字主芒（贯穿全宽/全高）
    for i in range(size):
        g[c][i] = LIGHT
        g[i][c] = LIGHT

    # 中心加粗成菱形，让它看起来"亮"
    if size >= 5:
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            g[c + dy][c + dx] = LIGHT
        g[c - 1][c - 1] = g[c - 1][c + 1] = LIGHT
        g[c + 1][c - 1] = g[c + 1][c + 1] = LIGHT

    return g


# 两档就够：小星做散射、大星做中心爆点。
# 原本设了 5/7/9 三档，9×9 加对角芒时间隔太稀、看着是散点不是光芒 ——
# 十字星在这个尺寸区间本来就只有「小」和「大」两种有意义的形态。
STAR_SIZES = (5, 7)
STAR_PALETTE = ["#101010", "#fff0a0", "#ffffff", "#182838"]


# ---------------------------------------------------------------------------
# 导出为 2bpp 字节流 —— 与 gen1_front.bin 同格式，固件同一套解码
# ---------------------------------------------------------------------------

def to_2bpp(grid: list[list[int]]) -> bytes:
    """点阵转 2bpp。每字节 4 像素，高位在左（与 convert_sprites.py 一致）。"""
    h, w = len(grid), len(grid[0])
    out = bytearray()
    for y in range(h):
        for x0 in range(0, w, 4):
            b = 0
            for k in range(4):
                v = grid[y][x0 + k] if x0 + k < w else CLEAR
                b |= (v & 3) << (6 - k * 2)
            out.append(b)
    return bytes(out)


def budget() -> dict:
    """这些素材的 flash 占用 —— 验证「零素材成本」这个说法还成立。"""
    items = {
        "ball_24": to_2bpp(poke_ball(24)),
        "ball_24_open": to_2bpp(poke_ball(24, open_top=True)),
        "cursor": to_2bpp(CURSOR),
    }
    for s in STAR_SIZES:
        items[f"star_{s}"] = to_2bpp(star(s))
    return {
        "per": {k: len(v) for k, v in items.items()},
        "total": sum(len(v) for v in items.values()),
    }


def ascii_preview(grid: list[list[int]]) -> str:
    """终端预览 —— 点阵对不对，只有看出来才知道。"""
    m = {INK: "██", MID: "▒▒", LIGHT: "░░", CLEAR: "  "}
    return "\n".join("".join(m[v] for v in row) for row in grid)


def is_symmetric(grid: list[list[int]]) -> bool:
    """左右对称检查 —— 精灵球与星星都必须对称。"""
    return all(row == row[::-1] for row in grid)
