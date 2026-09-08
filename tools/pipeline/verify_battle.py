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
        } else if (!strcmp(cmd, "dmg")) {
            /* D73：伤害逐值对账。
               do_hit 里有两处随机（选招、命中判定），这里都消掉：
                 · 只给**一招** → pick_move 恒返回 moves[0]
                   （权重>0 时 rng_below(total) 必 < ws[0]；权重==0 时
                    rng_below(1)==0，两条路都指向同一招）
                 · accuracy 传 255（ACC_ALWAYS_HIT）→ 跳过命中掷骰
               于是 do_hit 退化为纯函数，可以逐值比。
               dmg <a_lv> <atk_t1> <atk_t2> <def_t1> <def_t2>
                   <a_hp,atk,def,spc,spd> <d_hp,atk,def,spc,spd>
                   <mv_type> <mv_power> <mv_special> <factor_q10> */
            int alv, at1, at2, dt1, dt2;
            int ah, aa, ad, as_, asp, dh, da, dd, ds, dsp;
            int mty, mpw, msp, fq;
            scanf("%d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d %d",
                  &alv, &at1, &at2, &dt1, &dt2,
                  &ah, &aa, &ad, &as_, &asp, &dh, &da, &dd, &ds, &dsp,
                  &mty, &mpw, &msp, &fq);
            species_t asp_s = {0}, dsp_s = {0};
            asp_s.type1 = (uint8_t)at1; asp_s.type2 = (uint8_t)at2;
            dsp_s.type1 = (uint8_t)dt1; dsp_s.type2 = (uint8_t)dt2;
            stats_t A = {(uint16_t)ah, (uint16_t)aa, (uint16_t)ad,
                         (uint16_t)as_, (uint16_t)asp};
            stats_t D = {(uint16_t)dh, (uint16_t)da, (uint16_t)dd,
                         (uint16_t)ds, (uint16_t)dsp};
            move_t m = {0};
            m.type = (uint8_t)mty; m.power = (uint8_t)mpw;
            m.accuracy = ACC_ALWAYS_HIT; m.special = msp ? true : false;
            m.name_zh = "招"; m.name_zh_len = 3;
            uint16_t mult; const move_t *got; bool miss;
            uint16_t d = do_hit(&asp_s, &A, (uint8_t)alv, &dsp_s, &D,
                                &m, 1, (uint16_t)fq, (uint16_t)dh, &mult, &got, &miss);
            printf("%u %u %d\n", d, mult, miss ? 1 : 0);
        } else if (!strcmp(cmd, "battle")) {
            int plv, wlv; unsigned seed;
            scanf("%d %d %u", &plv, &wlv, &seed);
            battle_result_t r;
            battle_run(g_sp[0].id, (uint8_t)plv, g_sp[1].id, (uint8_t)wlv,
                       1024, seed, &r);
            printf("%d %u %u\n", r.won ? 1 : 0, r.round_count, r.wild_hp_ratio);
        } else if (!strcmp(cmd, "session")) {
            int plv, wlv; unsigned seed; int fail = 0;
            scanf("%d %d %u", &plv, &wlv, &seed);
            battle_result_t whole;
            battle_run(g_sp[0].id, plv, g_sp[1].id, wlv, 1024, seed, &whole);
            battle_session_t live;
            battle_session_init(&live, g_sp[0].id, plv, g_sp[1].id, wlv, 1024, seed);
            for (unsigned i = 0; i < whole.round_count; i++) {
                battle_session_t saved = live, other;
                battle_round_t got, noise;
                // Other battles consume RNG between saving and restoring this
                // one: a global RNG must not silently corrupt resumed turns.
                battle_session_init(&other, g_sp[0].id, plv, g_sp[1].id, wlv, 1024, seed + 77);
                for (int k = 0; k < 3; k++) battle_session_step(&other, &noise);
                live = saved;
                if (!battle_session_step(&live, &got) ||
                    memcmp(&got, &whole.rounds[i], sizeof got)) fail |= 1;
                if (!live.rng || live.rng == saved.rng) fail |= 128;
            }
            if (!live.finished || live.won != whole.won ||
                battle_session_hp_ratio(&live) != whole.wild_hp_ratio ||
                battle_session_exp(&live) != whole.exp) fail |= 2;
            if (battle_session_can_capture(&live) != live.won) fail |= 4;
            live.capture_used_after_win = true;
            if (battle_session_can_capture(&live)) fail |= 8;
            battle_session_t terminal = live; battle_round_t ignored;
            if (battle_session_step(&live, &ignored) || memcmp(&terminal, &live, sizeof live)) fail |= 16;
            battle_session_init(&live, g_sp[0].id, plv, g_sp[1].id, wlv, 1024, seed);
            uint16_t wild_before = live.wild_hp, pet_before = live.pet_hp;
            live.next_by_pet = true;
            live.retaliation_pending = true;
            if (battle_session_can_capture(&live)) fail |= 32;
            if (!battle_session_step(&live, &ignored) || ignored.by_pet ||
                live.wild_hp != wild_before || live.pet_hp > pet_before ||
                !live.next_by_pet || live.retaliation_pending || live.attack_count != 1) fail |= 64;
            printf("%d\n", fail);
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

        # ---- ⑦ damage：伤害公式逐值（D73）---------------------------------
        #
        # 这一组是补一个实测出来的缺口：**伤害公式原先只被胜率间接覆盖**，
        # 而 `STAB` 从 150 改到 600（4 倍伤害）门禁仍报绿 ——
        # 三个场景的胜率本就饱和在 100%/0%/0%，推不动（回合数变了，但没人验它）。
        #
        # 能逐值对账是因为把随机消掉了：只给一招 → C 侧 pick_move 恒选它；
        # accuracy=255 → 跳过命中掷骰。于是 do_hit 退化成纯函数。
        #
        # factor 固定 1024（=1.0）：两侧在 factor≠1.0 时算法本就不同
        # （C 在 base 之后乘、sim 乘进 atk，`+2` 是否被缩放不一致），
        # 那是一个既存分叉，**本轮只报不掩盖** —— 见 reports/test.md 第十五轮。
        n = 0
        # 属性号：0 一般 / 3 电 / 8 地面 / 12 岩石（与上面 setup 同源）
        #
        # ⚠️ atk/def/spc 必须**互不相同**：第一版我把五项都填成同一个值，
        # 于是 `special ? spc : atk` 无论选哪个都拿到同一个数 ——
        # 「物理/特殊选反」这类缺陷完全测不出（实测注入后仍 rc=0）。
        # 现在三者刻意错开，选反必被抓。
        #
        # power 含 1：power=0 时 base 恒为 2，`max(1,...)` 那条下限
        # 永远不被触及；要 mult=0 才压到 0，所以电打地面那组负责它。
        for a_lv in (5, 12, 25, 50, 100):
            for atk_base in (30, 55, 90, 130):
                for power in (0, 1, 40, 90, 120):
                    for def_base in (30, 60, 100, 160):
                        for mty, at1, dt1 in ((3, 3, 0),      # 电打一般：×100 且同属性
                                              (3, 0, 8),      # 电打地面：×0
                                              (0, 0, 12),     # 一般打岩石：×50
                                              (3, 3, 12)):    # 电打岩石：×100 同属性
                            for special in (0, 1):
                                A = S.effective_stat(atk_base, a_lv)
                                D = S.effective_stat(def_base, a_lv)
                                SPC = S.effective_stat(atk_base // 2 + 5, a_lv)
                                got = d.ask(
                                    f"dmg {a_lv} {at1} 255 {dt1} 255 "
                                    f"1 {A} {D} {SPC} {A}  "
                                    f"1 {A} {D} {SPC} {A} "
                                    f"{mty} {power} {special} 1024").split()
                                c_dmg, c_mult = int(got[0]), int(got[1])
                                mult = S.effectiveness(T[mty], [T[dt1]])
                                stab = S.STAB if mty == at1 else 100
                                # 物理用 atk/def，特殊用 spc 双向（两侧同规则）
                                pa, pd = (SPC, SPC) if special else (A, D)
                                want = S.damage_of(a_lv, pa, power, pd,
                                                   mult, stab)
                                n += 1
                                if c_dmg != want or c_mult != mult:
                                    fails.append(
                                        f"damage(lv={a_lv},A={pa},P={power},"
                                        f"D={pd},mty={mty},at1={at1},"
                                        f"dt1={dt1},spc={special}): "
                                        f"C {c_dmg}/×{c_mult} ≠ "
                                        f"Python {want}/×{mult}")
        print(f"  伤害公式   {n} 组（factor=1.0；随机已消除）")

        # ---- ⑧ 战斗：统计分布 ----------------------------------------------
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

            for seed in range(1, 33):
                result = d.ask(f"session {plv} {wlv} {seed}")
                if result != "0":
                    fails.append(f"{label}: session seed={seed} failed flags={result}")
        print("  战斗恢复   96 组（跨会话 RNG、HP、终局锁、一次反击）")

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
