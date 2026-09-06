#!/usr/bin/env python3
"""nurture.c 与 sim/gameplay.py 逐拍 + 逐动作对账。

用法：
    python3 tools/pipeline/verify_nurture.py

## 为什么要这个

C 侧的 nurture_selftest 只能证明「符合我写它时的预期」。
而移植的验收标准是**与 PC 侧一致** —— 那边的常量是
docs/04-gameplay.md 标定过的，差一点就是不同的游戏。

同 verify_sensing.py：宿主上编译 C，喂同一串时间序列，
逐拍比对三条轴。定点与浮点必然有微小差异，
所以比的是**取整后的百分比**（那才是上屏的东西）。

## 已知的可接受偏差（仅衰减段）

Q10 下 1 单位 = 0.001，累积一天（86400 秒）最多偏 0.1 ——
远小于 1 个百分点。若某拍差 1，那是四舍五入的边界，不是错误；
**衰减段**按「差 ≥ 2」判失败。

## C2 追加：照料动作对账（严格相等，不走衰减段的容差）

原门禁只对账衰减逐拍（nurture_tick），三个照料动作完全没有覆盖 ——
固件 nurture_play 漏了 intimacy +1 而 3201 拍一直是绿的。
动作是整数算术（+30/+5/+15/−5/+1/+6h），从整数值起始状态出发
两边都落在精确值上，**差 1 就是错**：

    feed:  satiety +30（钳 100）、mood +5（钳 100）
    play:  mood +15（钳 100）、stamina −5（**地板 0，不为负**）、
           intimacy +1（钳 100）
    rest:  stamina + 6×hours（钳 100；**无夜间翻倍** —— 那是 tick 的恢复）

钳位边界必测：饱食 90+30 → 100（不是 120）；体能 3−5 → 0（不是 −2）；
体能 60 + 48 → 100（不是 108 —— 契约点名）。

若 nurture_rest 尚未交付：驱动编译失败、退出非 0 —— **缺失即红**，
不用 #ifdef 绕（B1 原则）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAIN = os.path.join(REPO, "firmware", "main")

DRIVER = r"""
#include <stdio.h>
#include <string.h>
#include "nurture.c"
#include <stdlib.h>

// 命令式协议：每行一个命令，执行后打印四条轴的百分比。
//   t <sec> <motion> <night>   衰减推进。
//     ⚠️ sec 是**绝对时刻**不是时长：nurture_tick 内部算 dt = now_us −
//     last_us（幂等，同 now_us 调两次第二次不变化）。要「再过 2h」就传
//     上一拍时刻 + 7200，直接传 7200 是「时钟走到第 7200 秒」——
//     这个坑在混合序列里踩过一次（Hub blocker 复核确认）。
//   set <sat_q> <mood_q> <sta_q> <int_q>   直接置 Q10 起始状态
//   feed / play                照料动作
//   rest <hours>               休息（小时，整数）
static nurture_t n;

static void put_axes(void)
{
    printf("%u %u %u %u\n", nurture_pct(n.satiety), nurture_pct(n.mood),
           nurture_pct(n.stamina), nurture_pct(n.intimacy));
}

int main(void)
{
    char cmd[16];
    nurture_init(&n);
    while (scanf("%15s", cmd) == 1) {
        if (!strcmp(cmd, "t")) {
            double sec; int motion, night;
            scanf("%lf %d %d", &sec, &motion, &night);
            nurture_tick(&n, (int64_t)(sec * 1000000.0), motion, night);
            put_axes();
        } else if (!strcmp(cmd, "set")) {
            int s, m, st, i;
            scanf("%d %d %d %d", &s, &m, &st, &i);
            n.satiety = s; n.mood = m; n.stamina = st; n.intimacy = i;
            put_axes();
        } else if (!strcmp(cmd, "feed")) {
            nurture_feed(&n);
            put_axes();
        } else if (!strcmp(cmd, "play")) {
            nurture_play(&n);
            put_axes();
        } else if (!strcmp(cmd, "rest")) {
            /* 固件接口固定 8 小时（NURT_REST_STAMINA = 48q），
               与 sim 的 rest() 默认 hours=8.0 对账 —— 无 hours 旋钮。 */
            nurture_rest(&n);
            put_axes();
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str, main_dir: str = MAIN) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    # -Werror：移植代码里的隐式转换必须显式处理，
    # 那是定点运算出错的常见来源
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-I", main_dir,
           src, "-o", exe]
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


def make_schedule() -> list[tuple[float, int, bool]]:
    """时间序列。覆盖几种真实节奏，不是均匀采样。

    均匀采样测不出问题 —— 真机的 tick 会被 WiFi 扫描挤掉，
    间隔从 250ms 到几秒不等，还有关机再开机的大跳。
    """
    out: list[tuple[float, int, bool]] = []
    t = 0.0
    # ① 4fps 跑 10 分钟 —— 主循环的常态，考验余数累积
    for _ in range(2400):
        t += 0.25
        out.append((t, 0, False))
    # ② 被扫描挤掉的不规则间隔，1 小时
    for i in range(600):
        t += 3.0 + (i % 7) * 0.9
        out.append((t, 1 if i % 50 == 0 else 0, False))
    # ③ 夜间静置 8 小时，一次大跳（关机再开机）
    t += 8 * 3600
    out.append((t, 0, True))
    # ④ 白天零散活动
    for i in range(200):
        t += 30.0
        out.append((t, 2 if i % 10 == 0 else 0, False))
    return out


def main() -> int:
    sys.path.insert(0, os.path.join(REPO, "sim"))
    import gameplay as G

    fails: list[str] = []
    # argv[1] 可覆盖 nurture.c 所在目录 —— 反向验证指向改坏的副本用
    main_dir = sys.argv[1] if len(sys.argv) > 1 else MAIN

    with tempfile.TemporaryDirectory() as tmp:
        d = Driver(build(tmp, main_dir))

        # ---- ① 衰减逐拍（沿用原门禁，容差 ≤1 不变）-------------------------
        pet = G.PetState()
        sched = make_schedule()
        AXES = ("饱食", "心情", "体能", "亲密")
        worst = [0, 0, 0, 0]
        bad = 0
        for i, (ts, motion, night) in enumerate(sched):
            c = [int(v) for v in d.ask(
                f"t {ts} {motion} {1 if night else 0}").split()]
            pet.advance(ts, motion_events=motion, is_night=night)
            p = [round(pet.satiety), round(pet.mood),
                 round(pet.stamina), round(pet.intimacy)]
            for k in range(4):
                dlt = abs(c[k] - p[k])
                worst[k] = max(worst[k], dlt)
                if dlt >= 2:
                    bad += 1
                    if bad <= 5:
                        fails.append(f"衰减第 {i} 拍 {AXES[k]}: "
                                     f"C {c[k]} Python {p[k]}")
        print(f"  衰减逐拍       {len(sched)} 拍，最大偏差 "
              f"{min(worst)}~{max(worst)}（容差 ≤1，四舍五入边界）")

        def F(pet):
            return lambda: pet.feed()
        def P(pet):
            return lambda: pet.play()
        def R(pet):
            return lambda: pet.rest()          # 默认 8h，与固件固定值对账

        # ---- ② 动作 × 衰减混合（2h 步长 → 全整数增量，仍严格相等）---------
        # 紧接衰减段（同一只 pet、同一份 C 状态、时钟都在 t_end）。
        # t 的参数是**绝对时刻**：dt 由 nurture_tick 内部的 last_us 差分
        # 得出（Python 侧 _last_ts 同理），「再过 2h」= 传 t_end + 7200。
        # 曾经把 7200/14400/21600 当时长直接传 —— C 侧只推进到该绝对时刻、
        # Python fresh pet 首次 advance 又是 no-op，两边各错各的（已修，
        # Hub blocker 复核过根因）。此时状态非整数（Q10 尾数），容差 ≤1；
        # 「差 1 就是错」的严格判据由动作段（整数起始态）负责。
        t_end = sched[-1][0]
        MIXED = [
            (f"t {t_end + 7200} 0 0",
             lambda: pet.advance(t_end + 7200, motion_events=0,
                                 is_night=False)),
            ("feed", F(pet)),
            (f"t {t_end + 14400} 2 0",
             lambda: pet.advance(t_end + 14400, motion_events=2,
                                 is_night=False)),
            ("play", P(pet)),
            ("rest", R(pet)),
            (f"t {t_end + 21600} 0 1",
             lambda: pet.advance(t_end + 21600, motion_events=0,
                                 is_night=True)),
        ]
        worst_m = 0
        for cmd, py in MIXED:
            c = [int(v) for v in d.ask(cmd).split()]
            py()
            p = [round(pet.satiety), round(pet.mood),
                 round(pet.stamina), round(pet.intimacy)]
            for k in range(4):
                worst_m = max(worst_m, abs(c[k] - p[k]))
                if abs(c[k] - p[k]) >= 2:
                    fails.append(f"混合「{cmd}」{AXES[k]}: "
                                 f"C {c[k]} ≠ Python {p[k]}")
        print(f"  动作×衰减混合  {len(MIXED)} 步（容差 ≤1，最大偏差 "
              f"{worst_m}）：衰减→喂食→带移动衰减→玩耍→休息→夜间衰减")

        # ---- ③ 照料动作（严格相等：差 1 就是错）----------------------------
        # (标签, 起始百分比 (sat,mood,sta,int), 动作串)。
# 放最后：本段每 case 重置 pet 且之后无 tick，不污染任何共享时间线。
        CASES = [
            ("feed 基线",        (50, 50, 50, 50), ["feed"]),
            ("feed 饱食 90 钳位", (90, 50, 50, 50), ["feed"]),
            ("feed 心情 96 钳位", (50, 96, 50, 50), ["feed"]),
            ("feed 双钳位",      (100, 100, 50, 50), ["feed"]),
            ("feed 空腹低心情",  (0, 0, 50, 50), ["feed"]),
            ("feed×3 连喂",      (50, 50, 50, 50), ["feed", "feed", "feed"]),
            ("play 基线",        (50, 50, 50, 50), ["play"]),
            ("play 体能 3 → 0（不为负）", (50, 50, 3, 50), ["play"]),
            ("play 体能 0 地板", (50, 50, 0, 50), ["play"]),
            ("play 体能 5 → 0",  (50, 50, 5, 50), ["play"]),
            ("play 心情 95 钳位", (50, 95, 50, 50), ["play"]),
            ("play 亲密 99 → 100", (50, 50, 50, 99), ["play"]),
            ("play 亲密 100 钳位", (50, 50, 50, 100), ["play"]),
            ("play×2",           (50, 50, 50, 50), ["play", "play"]),
            ("rest 体能 60 → 100（不是 108）", (50, 50, 60, 50), ["rest"]),
            ("rest 体能 50 → 98", (50, 50, 50, 50), ["rest"]),
            ("rest 体能 52 → 100（刚好）", (50, 50, 52, 50), ["rest"]),
            ("rest 体能 51 → 99", (50, 50, 51, 50), ["rest"]),
            ("rest 体能 99 → 100", (50, 50, 99, 50), ["rest"]),
            ("rest 体能 100 不动", (50, 50, 100, 50), ["rest"]),
            ("rest 体能 0 → 48", (50, 50, 0, 50), ["rest"]),
            ("rest×2 体能 50 → 100", (50, 50, 50, 50), ["rest", "rest"]),
        ]
        n_act = 0
        for label, pre, ops in CASES:
            d.ask(f"set {pre[0] * 1024} {pre[1] * 1024} "
                  f"{pre[2] * 1024} {pre[3] * 1024}")
            pet = G.PetState()
            pet.satiety, pet.mood = float(pre[0]), float(pre[1])
            pet.stamina, pet.intimacy = float(pre[2]), float(pre[3])
            for op in ops:
                if op == "feed":
                    py = F(pet)
                elif op == "play":
                    py = P(pet)
                else:
                    py = R(pet)
                c = [int(v) for v in d.ask(op).split()]
                py()
                p = [round(pet.satiety), round(pet.mood),
                     round(pet.stamina), round(pet.intimacy)]
                n_act += 1
                if c != p:
                    fails.append(f"{label}「{op}»: C {c} ≠ Python {p}")
        print(f"  照料动作       {n_act} 步严格相等"
              f"（feed 6 / play 8 / rest 8 组，含全部钳位与地板边界；"
              f"rest 为固件固定 8h 语义）")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:15]:
            print("   " + f)
        if len(fails) > 15:
            print(f"   …还有 {len(fails)-15} 处")
        return 1

    print("\n✅ 衰减逐拍一致（≤1），照料动作严格相等"
          "（feed / play / rest 全部轴与钳位边界），混合序列一致（≤1）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
