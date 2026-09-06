#!/usr/bin/env python3
"""静态检查 play_*.c 的绘制坐标是否跨 80px 横带边界（呈现层门禁）。

用法：
    /usr/bin/python3 tools/pipeline/verify_layout.py [firmware/main 路径]

## 为什么需要它（BUG-1 的结构性根源）

十个既有门禁编译的固件源只有 9 个 .c，而 firmware/main 有 33 个 ——
**七个 play_*.c 合计近两千行，零门禁覆盖**。门禁验的是算法层，
BUG-1 发生在**呈现层**：元素跨 80px 横带边界（screen.h 的
SCREEN_BAND_H），而带式渲染只重画脏带 —— 跨带元素会被截断/撕裂。

更隐蔽的是观测盲区：`redraw_for_dump` 一次重画全部四条带，
**dump 路径没有频率差**，截图永远看不出跨带问题 ——
「经验 +%u」那行跨带跨了两轮才被发现，靠的不是观测是读码。

## 判定规则

- 解析 #define（含函数宏如 AXIS_Y(i)）、常量数组、局部 int y、for 域，
  对 render_text / draw_bar / render_sprite* 的 Y 参数求出**全部取值**
  （for 循环逐值展开），元素区间 [y, y+h) 跨带即违规
- **无法静态求值的如实报 SKIP 并计数** —— 不猜值、不静默丢
  （BUG-1 的成因正是静默丢弃，检查器自己不能重犯）。
  **退出码只由确定的违规决定**，SKIP 不算失败（否则永远红）
- **豁免必须带理由且打印**：脚本内 WHITELIST 表（行号绑定，代码一挪
  就失效，这是有意的）或源码行尾 `// band-ok: 理由`。豁免逐条打印，
  绝不静默生效；过期的白名单条目也会被点名
- 带宽从 screen.h 的 SCREEN_BAND_H 解析（单一事实源），不硬编码

退出码 0 = 无确定违规；非 0 = 有（SKIP 不影响）。
"""

from __future__ import annotations

import os
import pathlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAIN = os.path.join(REPO, "firmware", "main")

GLYPH_H = 16          # 字形高；render_text 的元素高度

# 显式豁免表：(文件名, 行号, 类别, 理由)。理由必填；行号绑定源码位置。
# 目前为空 —— play_battle.c 的三处是真违规，等 cep-coder 修，
# **不许为了绿而加豁免**（那正是这个门禁要防的恒绿）。
WHITELIST: list[tuple[str, int, str, str]] = [
    # 例：("play_xxx.c", 123, "sprite", "跨带 0/1，两带始终同频重画"),
]

RE_DEF = re.compile(r'^\s*#define\s+(\w+)\s+(\(?[\d\s+\-*/()]+\)?)\s*(?://.*)?$')
RE_DEFF = re.compile(r'^\s*#define\s+(\w+)\(\s*(\w+)\s*\)\s+(.+?)\s*(?://.*)?$')
RE_ARR = re.compile(r'(\w+)\[\w*\]\s*=\s*\{([\d,\s]+)\}')
RE_LOCY = re.compile(r'int\s+(\w+)\s*=\s*([\w\s+\-*/()]+?);')
RE_LOOP = re.compile(r'for\s*\(\s*int\s+(\w+)\s*=\s*(\d+)\s*;\s*\w+\s*<\s*(\w+)')
RE_TEXT = re.compile(r'render_text\s*\(\s*[^,]+,\s*Y\(([^;]+?)\)\s*,')
RE_BAR = re.compile(r'draw_bar\w*\s*\(\s*[^,]+,\s*Y\(([^;]+?)\)\s*,\s*[^,]+,\s*(\w+)')
RE_SPR = re.compile(r'render_sprite\w*\s*\(\s*[^,]+,\s*Y\(([^;]+?)\)\s*,.*?,\s*(\w+),\s*(\w+)')
RE_BAND_OK = re.compile(r'//\s*band-ok:\s*(.+)')


def read_band_h(main_dir: str) -> int:
    """从 screen.h 解析 SCREEN_BAND_H —— 单一事实源，不硬编码。"""
    src = (pathlib.Path(main_dir) / "screen.h").read_text(errors="replace")
    m = re.search(r'#define\s+SCREEN_BAND_H\s+(\d+)', src)
    if not m:
        print("❌ screen.h 里找不到 #define SCREEN_BAND_H", file=sys.stderr)
        sys.exit(1)
    return int(m.group(1))


def num(tok, env):
    tok = tok.strip().strip('()')
    if re.fullmatch(r'-?\d+', tok):
        return int(tok)
    return env.get(tok)


def ev(expr, env):
    """求值：字面量、常量名、四则、常量数组下标。失败返 None（不猜）。"""
    e = expr.strip()
    m = re.fullmatch(r'(\w+)\[(\w+)\]', e)
    if m and m.group(1) in env and isinstance(env[m.group(1)], list):
        return env[m.group(1)]                      # 数组 → 全部取值
    try:
        safe = re.sub(r'\b([A-Za-z_]\w*)\b',
                      lambda g: str(env[g.group(1)])
                      if isinstance(env.get(g.group(1)), int) else g.group(1), e)
        if re.fullmatch(r'[\d\s+\-*/()]+', safe):
            return [eval(safe)]                     # noqa: S307 已限定数字与运算符
    except Exception:
        pass
    return None


def scan(path: pathlib.Path, band: int):
    src = path.read_text(errors='replace').split('\n')
    env = {'SCR_W': 240, 'SCR_H': 320, 'BAND_H': band}
    fmac = {}
    for l in src:
        m = RE_DEFF.match(l)
        if m and re.fullmatch(r'[\w\s+\-*/()]+', m.group(3)):
            fmac[m.group(1)] = (m.group(2), m.group(3))
            continue
        m = RE_DEF.match(l)
        if m:
            v = ev(m.group(2), env)
            if v:
                env[m.group(1)] = v[0]
        m = RE_ARR.search(l)
        if m:
            env[m.group(1)] = [int(x) for x in
                               m.group(2).replace(' ', '').strip(',').split(',')
                               if x != '']

    fails, skips, exempt = [], [], []
    loops, locals_ = {}, {}

    def cross(y, h):
        return y // band != (y + h - 1) // band

    for ln, l in enumerate(src, 1):
        m = RE_LOOP.search(l)
        if m:
            hi = num(m.group(3), env)
            if hi:
                loops[m.group(1)] = range(int(m.group(2)), hi)
        m = RE_LOCY.search(l)
        if m:
            name, rhs = m.group(1), m.group(2)
            fm = re.fullmatch(r'(\w+)\(\s*(\w+)\s*\)', rhs.strip())
            if fm and fm.group(1) in fmac:
                par, body = fmac[fm.group(1)]
                rhs = body.replace(par, fm.group(2))
            locals_[name] = rhs

        def resolve(expr):
            e = expr
            for k, v in locals_.items():
                e = re.sub(rf'\b{k}\b', f'({v})', e)
            for k, (par, body) in fmac.items():
                e = re.sub(rf'\b{k}\(\s*(\w+)\s*\)',
                           lambda g: '(' + body.replace(par, g.group(1)) + ')', e)
            vals = []
            vs = set(re.findall(r'\b([a-z]\w*)\b', e)) & set(loops)
            if vs:
                var = next(iter(vs))
                for iv in loops[var]:
                    r = ev(re.sub(rf'\b{var}\b', str(iv), e), env)
                    if r is None:
                        return None
                    vals += r
                return vals
            return ev(e, env)

        def check(kind, yexpr, h):
            ys = resolve(yexpr)
            if ys is None or h is None:
                skips.append((ln, kind, yexpr))
                return
            for y in ys:
                if cross(y, h):
                    bo = RE_BAND_OK.search(l)
                    if bo:
                        exempt.append((ln, kind, y, h, bo.group(1).strip()))
                    else:
                        fails.append((ln, kind, y, h))

        for m in RE_TEXT.finditer(l):
            check('text', m.group(1), GLYPH_H)
        for m in RE_BAR.finditer(l):
            check('bar', m.group(1), num(m.group(2), env))
        for m in RE_SPR.finditer(l):
            check('sprite', m.group(1), num(m.group(3), env))
    return fails, skips, exempt


def main() -> int:
    main_dir = sys.argv[1] if len(sys.argv) > 1 else MAIN
    band = read_band_h(main_dir)
    files = sorted(pathlib.Path(main_dir).glob('play_*.c'))
    if not files:
        print(f"❌ {main_dir} 下没有 play_*.c", file=sys.stderr)
        return 1

    t_f = t_s = t_e = 0
    details = []
    per_file = []
    used_wl = set()
    for p in files:
        fails, skips, exempt = scan(p, band)
        # 脚本侧白名单：行号 + 类别 + 理由 必须齐备才豁免
        kept = []
        for (ln, kind, y, h) in fails:
            hit = next((w for w in WHITELIST
                        if w[0] == p.name and w[1] == ln and w[2] == kind), None)
            if hit:
                used_wl.add(hit)
                exempt.append((ln, kind, y, h, hit[3]))
            else:
                kept.append((ln, kind, y, h))
        fails = kept
        t_f += len(fails)
        t_s += len(skips)
        t_e += len(exempt)
        per_file.append((p.name, len(fails), len(skips), len(exempt)))
        for ln, kind, y, h in fails:
            details.append(f"  ✗ {p.name}:{ln} {kind} y={y}..{y + h - 1}"
                           f"（h={h}）跨带 {y // band}->{(y + h - 1) // band}")
        for ln, kind, y, h, why in exempt:
            details.append(f"  ○ {p.name}:{ln} {kind} y={y}..{y + h - 1}"
                           f" 豁免：{why}")
        for ln, kind, e in skips:
            details.append(f"  ~ {p.name}:{ln} {kind} SKIP 无法求值: {e.strip()!r}")

    print(f"  扫描           {len(files)} 个 play_*.c，带宽 "
          f"{band}px（screen.h）")
    for name, nf, ns, ne in per_file:
        print(f"  {name:20s} 违规 {nf}　豁免 {ne}　SKIP {ns}")
    for w in WHITELIST:
        if w not in used_wl:
            details.append(f"  ⚠ 白名单过期：{w[0]}:{w[1]} {w[2]} "
                           f"「{w[3]}」已无对应违规 —— 该删")
            print(f"  ⚠ 白名单过期：{w[0]}:{w[1]}（已无对应违规，该删）")

    print(f"\n  合计           确定违规 {t_f}　豁免 {t_e}　SKIP {t_s}"
          f"（SKIP 不影响退出码）")
    for d in details:
        if d.startswith('  ✗'):
            print(d)
    for d in details:
        if d.startswith('  ○') or d.startswith('  ~') or d.startswith('  ⚠'):
            print(d)

    if t_f:
        print(f"\n❌ {t_f} 处跨带违规（呈现层会被带式渲染截断）")
        return 1
    print(f"\n✅ 无确定跨带违规（豁免 {t_e} 处均已打印理由，"
          f"SKIP {t_s} 处已列明）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
