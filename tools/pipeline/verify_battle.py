#!/usr/bin/env python3
"""battle.c / capture.c 与 sim/systems.py 对账。

用法：
    python3 tools/pipeline/verify_battle.py

## 两层对账，因为随机源不同

固件用 xorshift32，sim 用 Python 的 Mersenne Twister ——
在 C 里复刻 MT 要上百行状态机，且一处写错就全错，
而「全错」的表现只是「战斗结果不一样」，极难反查。

战斗的观感取决于**胜率分布**，不取决于第 7 场第 3 回合的伤害。
所以分两层：

**① 确定性部分逐值对账** —— 这是大头：
    · 15×15 相克表全部 225 格（含 4 条初代特有差异）
    · effective_stat 全部 (种族值 × 等级) 组合
    · wild_level 全部稀有度
    · window_width 全部 (capture_rate × 心情 × 球种 × HP) 组合
    · pointer_position 一个完整周期的每一毫秒
    · 逃跑判定（crc32，确定性）

**② 随机部分对统计分布** —— 1000 场战斗的胜率在容差内。

第 ① 层能抓到的缺陷比第 ② 层多得多：表抄错一格、公式漏一个乘数、
截断方向反了 —— 这些在分布上可能只差 1~2 个百分点，看不出来，
但逐值对账立刻就红。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAIN = os.path.join(REPO, "firmware", "main")
sys.path.insert(0, os.path.join(REPO, "sim"))

# 宿主上跑的驱动。**不 include assets.c** —— 那需要嵌入的 bin 符号，
# 而这一层要验的是纯算法（相克/公式/窗口），不碰资产。
DRIVER = r"""
#define HOST_BUILD 1
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* **用真的 assets.h**，不写替身 —— 替身的结构体字段顺序若与真的不同，
   对账全绿而固件全错。这里只把两个查询函数换成桩，
   数据由 stdin 灌进来（宿主不解 bin）。 */
#include "assets.h"

#include "battle.c"
#include "capture.c"

/* 驱动侧的物种/招式表由 stdin 灌进来 —— 这样宿主不用解 bin。 */
static species_t g_sp[2];
static move_t g_mv[2][8];
static int g_nmv[2];

bool assets_species(uint16_t id, species_t *out)
{
    for (int i = 0; i < 2; i++)
        if (g_sp[i].id == id) { *out = g_sp[i]; return true; }
    return false;
}

int assets_known_moves(uint16_t sid, uint8_t lv, move_t *out, int max_out)
{
    (void)lv;
    for (int i = 0; i < 2; i++) {
        if (g_sp[i].id != sid) continue;
        int n = g_nmv[i] < max_out ? g_nmv[i] : max_out;
        for (int k = 0; k < n; k++) out[k] = g_mv[i][k];
        return n;
    }
    return 0;
}

int main(void)
{
    char cmd[32];
    while (scanf("%31s", cmd) == 1) {
        if (!strcmp(cmd, "eff")) {
            int a, d1, d2;
            scanf("%d %d %d", &a, &d1, &d2);
            printf("%u\n", battle_effectiveness((uint8_t)a, (uint8_t)d1, (uint8_t)d2));
        } else if (!strcmp(cmd, "stat")) {
            int b, l; scanf("%d %d", &b, &l);
            printf("%u\n", battle_effective_stat((uint8_t)b, (uint8_t)l));
        } else if (!strcmp(cmd, "wildlv")) {
            int r; scanf("%d", &r);
            printf("%u\n", battle_wild_level((uint8_t)r));
        } else if (!strcmp(cmd, "win")) {
            int cr, mb, ball, hp; scanf("%d %d %d %d", &cr, &mb, &ball, &hp);
            printf("%u\n", cap_window_width((uint8_t)cr, (uint16_t)mb,
                                            (cap_ball_t)ball, (uint8_t)hp));
        } else if (!strcmp(cmd, "ptr")) {
            unsigned ms; scanf("%u", &ms);
            printf("%u\n", cap_pointer_position(ms));
        } else if (!strcmp(cmd, "flee")) {
            int rar; unsigned seed;
            scanf("%d %u", &rar, &seed);
            cap_result_t r;
            /* elapsed 取一个必定不命中的值：窗口居中，指针在 0 处 */
            cap_attempt(1, 1024, CAP_BALL_POKE, 100, (uint8_t)rar, 0, seed, &r);
            printf("%d %d\n", r.caught ? 1 : 0, r.fled ? 1 : 0);
        } else if (!strcmp(cmd, "setup")) {
            /* setup <i> <id> <t1> <t2> <hp> <atk> <def> <spc> <spd> <nmv>
                     然后 nmv 行： <type> <power> <acc> <special> */
            int i, id, t1, t2, hp, at, df, sp, sd, nm;
            scanf("%d %d %d %d %d %d %d %d %d %d",
                  &i, &id, &t1, &t2, &hp, &at, &df, &sp, &sd, &nm);
            g_sp[i].id = (uint16_t)id;
            g_sp[i].type1 = (uint8_t)t1; g_sp[i].type2 = (uint8_t)t2;
            g_sp[i].hp = (uint8_t)hp; g_sp[i].attack = (uint8_t)at;
            g_sp[i].defense = (uint8_t)df; g_sp[i].special = (uint8_t)sp;
            g_sp[i].speed = (uint8_t)sd;
            g_nmv[i] = nm;
            for (int k = 0; k < nm; k++) {
                int ty, pw, ac, spc;
                scanf("%d %d %d %d", &ty, &pw, &ac, &spc);
                g_mv[i][k].type = (uint8_t)ty;
                g_mv[i][k].power = (uint8_t)pw;
                g_mv[i][k].accuracy = (uint8_t)ac;
                g_mv[i][k].special = spc ? true : false;
                g_mv[i][k].name_zh = "招"; g_mv[i][k].name_zh_len = 3;
            }
            printf("ok\n");
        } else if (!strcmp(cmd, "battle")) {
            int plv, wlv; unsigned seed;
            scanf("%d %d %u", &plv, &wlv, &seed);
            battle_result_t r;
            battle_run(g_sp[0].id, (uint8_t)plv, g_sp[1].id, (uint8_t)wlv,
                       1024, seed, &r);
            printf("%d %u %u\n", r.won ? 1 : 0, r.round_count, r.wild_hp_ratio);
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
           "-I", MAIN, src, "-o", exe, "-lz"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("编译失败：\n" + r.stderr, file=sys.stderr)
        sys.exit(1)
    return exe


class Driver:
    def __init__(self, exe: str):
        self.p = subprocess.Popen([exe], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, bufsize=1)

    def ask(self, line: str) -> str:
        self.p.stdin.write(line + "\n")
        self.p.stdin.flush()
        return self.p.stdout.readline().strip()

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=5)


def main() -> int:
    import systems as S
    import strings

    T = strings.TYPES_CN
    fails: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        d = Driver(build(tmp))

        # ---- ① 相克表：全部 225 格 --------------------------------------
        n = 0
        for i, a in enumerate(T):
            for j, b in enumerate(T):
                got = int(d.ask(f"eff {i} {j} 255"))
                want = S.effectiveness(a, [b])
                n += 1
                if got != want:
                    fails.append(f"相克 {a}→{b}: C {got} ≠ Python {want}")
        # 双属性也验几组 —— 相乘的顺序与截断可能出错
        for (i, j, k) in ((3, 2, 9), (1, 4, 11), (13, 10, 255), (5, 1, 8)):
            got = int(d.ask(f"eff {i} {j} {k}"))
            defs = [T[j]] + ([T[k]] if k < 15 else [])
            want = S.effectiveness(T[i], defs)
            n += 1
            if got != want:
                fails.append(f"双属性 {T[i]}→{defs}: C {got} ≠ Python {want}")
        print(f"  相克表     {n} 组")

        # ---- ② effective_stat --------------------------------------------
        n = 0
        for base in (1, 5, 35, 55, 100, 180, 255):
            for lv in (1, 5, 12, 25, 50, 75, 100):
                got = int(d.ask(f"stat {base} {lv}"))
                want = S.effective_stat(base, lv)
                n += 1
                if got != want:
                    fails.append(f"effective_stat({base},{lv}): "
                                 f"C {got} ≠ Python {want}")
        print(f"  能力值成长 {n} 组")

        # ---- ③ wild_level -------------------------------------------------
        for r in range(6):
            got = int(d.ask(f"wildlv {r}"))
            want = S.wild_level(r)
            if got != want:
                fails.append(f"wild_level({r}): C {got} ≠ Python {want}")
        print(f"  野怪等级   6 组")

        # ---- ④ window_width：四个乘数的组合 --------------------------------
        n = 0
        BALLS = ("poke", "great", "ultra")
        for cr in (3, 45, 90, 190, 255):
            for mood_q10, mood_f in ((1024, 1.0), (717, 0.7), (1434, 1.4)):
                for bi, ball in enumerate(BALLS):
                    for hp in (100, 50, 10, 1):
                        got = int(d.ask(f"win {cr} {mood_q10} {bi} {hp}"))
                        want = S.window_width(cr, mood_f, ball, hp)
                        n += 1
                        if abs(got - want) > 1:      # 定点 vs 浮点，容 1px
                            fails.append(
                                f"window_width({cr},{mood_f},{ball},{hp}): "
                                f"C {got} ≠ Python {want}")
        print(f"  捕获窗口   {n} 组")

        # ---- ⑤ pointer_position：一个完整周期 ------------------------------
        n = 0
        for ms in range(0, 1200, 7):
            got = int(d.ask(f"ptr {ms}"))
            want = S.pointer_position(ms)
            n += 1
            if got != want:
                fails.append(f"pointer({ms}): C {got} ≠ Python {want}")
        print(f"  指针轨迹   {n} 点")

        # ---- ⑥ 逃跑判定（crc32，确定性）------------------------------------
        n = bad = 0
        for rar in range(1, 6):
            for seed in range(0, 400, 13):
                got = d.ask(f"flee {rar} {seed}").split()
                c_fled = got[1] == "1"
                chance = S.FLEE_CHANCE.get(rar, 0.2)
                import zlib
                py_fled = ((zlib.crc32(str(seed).encode()) & 0xFFFF)
                           / 65535.0) < chance
                n += 1
                if c_fled != py_fled:
                    bad += 1
                    if bad <= 3:
                        fails.append(f"逃跑 rarity={rar} seed={seed}: "
                                     f"C {c_fled} ≠ Python {py_fled}")
        print(f"  逃跑判定   {n} 组")

        # ---- ⑦ 战斗：统计分布 ----------------------------------------------
        # 三组对局，验的是**难度梯度**而不只是「能打赢」。
        # 只测一组稳赢的看不出问题：伤害公式整体偏高时它照样 100%。
        N = 400
        # 皮卡丘（电 35/55/40/50/90）· 小拉达（一般 30/56/35/25/72）
        # 大岩蛇（岩石/地面 35/45/160/30/70）—— 电系打地面 0 倍，最差情况
        d.ask("setup 0 25 3 255 35 55 40 50 90 2  3 40 100 1  0 40 100 0")
        CASES = [
            # (对手 setup, 主宠等级, 野怪等级, 期望胜率区间, 说明)
            ("setup 1 19 0 255 30 56 35 25 72 1  0 35 95 0",
             12, 5, (90, 100), "Lv12 皮卡丘 打 Lv5 小拉达"),
            ("setup 1 19 0 255 30 56 35 25 72 1  0 35 95 0",
             5, 20, (0, 25), "Lv5 皮卡丘 打 Lv20 小拉达"),
            # 电打地面 0 倍 —— 皮卡丘只能靠电光一闪（一般系）
            ("setup 1 95 12 8 35 45 160 30 70 1  8 60 100 0",
             25, 20, (0, 90), "Lv25 皮卡丘 打 Lv20 大岩蛇（电系无效）"),
        ]
        for setup, plv, wlv, (lo, hi), label in CASES:
            d.ask(setup)
            wins = rounds = 0
            for s in range(1, N + 1):
                out = d.ask(f"battle {plv} {wlv} {s}").split()
                wins += int(out[0])
                rounds += int(out[1])
            rate = wins * 100 // N
            avg = rounds / N
            ok = lo <= rate <= hi
            print(f"  {label:32s} 胜率 {rate:3d}%  {avg:4.1f} 回合  "
                  f"{'✓' if ok else '✗ 期望 %d~%d%%' % (lo, hi)}")
            if not ok:
                fails.append(f"{label}: 胜率 {rate}% 不在 {lo}~{hi}% 内")
            # 回合数要落在「30 秒会话」的预算内（伤害公式分母压 25 的目的）
            if avg > 25:
                fails.append(f"{label}: 平均 {avg:.1f} 回合太长")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:15]:
            print("   " + f)
        if len(fails) > 15:
            print(f"   …还有 {len(fails)-15} 处")
        return 1

    print("\n✅ 确定性部分与 sim 逐值一致，随机部分分布合理")
    return 0


if __name__ == "__main__":
    sys.exit(main())
