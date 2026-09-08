#!/usr/bin/env python3
"""exp.c 与 sim/systems.py 的经验曲线逐值对账。

用法：
    /usr/bin/python3 tools/pipeline/verify_exp.py [exp.c 路径]

默认对账 `firmware/main/exp.c`；传入别的路径用于反向验证 ——
把副本改坏再跑，脚本必须红，证明它真在对账而不是恒绿。

## 为什么逐值，而不是抽样统计

曲线调整为 3n³/2，比旧门槛约低 40%；硬件和 Python 必须逐值一致。抽样抓不住「一格错、整体偏一点」的缺陷：除数抄成 3、截断方向
反了，在分布上只差一两个百分点，逐值对账立刻就红。

## 覆盖

    · 常量           LEVEL_MAX / EXP_ON_CAPTURE / EXP_ON_CARE / EXP_ON_MOTION
                     与 sim 逐一相等
    · exp_for_level  n = 0..255 全量（uint8_t 全域；sim 定义域 0..100，
                     101..255 顺带验 uint8 边界不回绕）
    · exp_to_level   每级边界三点 exp_for_level(n)-1/+0/+1，n = 1..100；
                     外加 exp = 0xFFFFFFFF 钉在 cap 上（溢出邻域）
    · cap 生效       cap=20 时给足 Lv50 乃至 Lv100 的经验仍是 20；
                     cap=1 任何经验都是 1
    · exp_progress   每级「本级起点 / 起点前一级 / 中点 / 差一点升级」，
                     (got, need) 与 sim 逐值一致（含钳制语义）
    · 溢出锚点       exp_for_level(100) = 1_500_000，远小于 uint32_t 上限

退出码 0 = 过，非 0 = 挂，可当 CI 门禁。
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

DRIVER = r"""
#define HOST_BUILD 1
#include <stdio.h>
#include <stdint.h>
#include <string.h>

/* 用真的 exp.c —— 替身公式一旦与真的不同，对账全绿而固件全错。
   exp.h 按接口约定不 include 任何 ESP-IDF 头，宿主直接编。 */
#include "exp.c"

int main(void)
{
    char cmd[32];
    while (scanf("%31s", cmd) == 1) {
        if (!strcmp(cmd, "fl")) {
            unsigned n; scanf("%u", &n);
            printf("%u\n", (unsigned)exp_for_level((uint8_t)n));
        } else if (!strcmp(cmd, "tl")) {
            unsigned e, c; scanf("%u %u", &e, &c);
            printf("%u\n", (unsigned)exp_to_level((uint32_t)e, (uint8_t)c));
        } else if (!strcmp(cmd, "pr")) {
            unsigned e, l; scanf("%u %u", &e, &l);
            uint32_t got, need;
            exp_progress((uint32_t)e, (uint8_t)l, &got, &need);
            printf("%u %u\n", (unsigned)got, (unsigned)need);
        } else if (!strcmp(cmd, "cst")) {
            printf("%d %d %d %d\n", LEVEL_MAX,
                   EXP_ON_CAPTURE, EXP_ON_CARE, EXP_ON_MOTION);
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str, exp_c: str) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    # exp.c 所在目录排最前：反向验证时指向改坏的副本；
    # 副本只断曲线，exp.h 仍用 MAIN 里的真头文件。
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
           "-I", os.path.dirname(os.path.abspath(exp_c)), "-I", MAIN,
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


def main() -> int:
    exp_c = sys.argv[1] if len(sys.argv) > 1 else os.path.join(MAIN, "exp.c")
    if not os.path.exists(exp_c):
        rel = os.path.relpath(exp_c, REPO)
        print(f"❌ {rel} 不存在 —— 固件侧未交付，无从对账")
        print("   接口见 TASK.md D2（LEVEL_MAX/exp_for_level/exp_to_level/"
              "exp_progress），落地即可跑本门禁")
        return 1

    import systems as S

    fails: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        d = Driver(build(tmp, exp_c))

        # ---- ① 四个常量 ----------------------------------------------------
        names = ("LEVEL_MAX", "EXP_ON_CAPTURE", "EXP_ON_CARE", "EXP_ON_MOTION")
        got = [int(x) for x in d.ask("cst").split()]
        want = [S.LEVEL_MAX, S.EXP_ON_CAPTURE, S.EXP_ON_CARE, S.EXP_ON_MOTION]
        if got != want:
            for nm, g, w in zip(names, got, want):
                if g != w:
                    fails.append(f"{nm}: C {g} ≠ Python {w}")
        print(f"  常量           {len(names)} 个 "
              f"({' '.join(str(x) for x in want)})")

        # ---- ② exp_for_level：uint8_t 全域全量 -------------------------------
        n = 0
        for lv in range(256):
            g = int(d.ask(f"fl {lv}"))
            w = S.exp_for_level(lv)
            n += 1
            if g != w:
                fails.append(f"exp_for_level({lv}): C {g} ≠ Python {w}")
        print(f"  exp_for_level  0..255 全量 {n} 组")

        # 溢出锚点：Lv100 = 1_500_000，逐值相等已排除回绕，这里再钉死数值
        g100 = int(d.ask("fl 100"))
        if g100 != 1_500_000:
            fails.append(f"锚点 exp_for_level(100): C {g100} ≠ 1_500_000")
        print(f"  溢出锚点       exp_for_level(100) = {g100:,}，"
              f"uint32 上限 4,294,967,295（余量 ~{0xFFFFFFFF // 1_500_000}×）")

        # ---- ③ exp_to_level：每级边界三点 -----------------------------------
        # base-1 应停在上一级、base 恰好升级、base+1 停在新级 ——
        # 差一（off-by-one）只出现在这三点上，抽中间值永远测不出来。
        n = 0
        for lv in range(1, 101):
            base = S.exp_for_level(lv)
            for delta in (-1, 0, 1):
                e = base + delta
                if e < 0:          # lv=1 时 base=0，-1 在 uint32_t 里表达不了
                    continue
                g = int(d.ask(f"tl {e} {S.LEVEL_MAX}"))
                w = S.exp_to_level(e, S.LEVEL_MAX)
                n += 1
                if g != w:
                    fails.append(f"exp_to_level({e}): C {g} ≠ Python {w}")
        # 溢出邻域：最大可表达的 exp 也要钉死在 cap 上，不能回绕成低级
        g = int(d.ask(f"tl {0xFFFFFFFF} {S.LEVEL_MAX}"))
        w = S.exp_to_level(0xFFFFFFFF, S.LEVEL_MAX)
        n += 1
        if g != w:
            fails.append(f"exp_to_level(0xFFFFFFFF): C {g} ≠ Python {w}")
        print(f"  升级边界       {n} 组（每级 -1/+0/+1，含 0xFFFFFFFF）")

        # ---- ④ cap 生效 -----------------------------------------------------
        # cap 是 S17 徽章的成长上限，接口要求必须保留 —— 单独验它真的拦得住。
        n = 0
        for cap in (1, 2, 5, 20, 50, 99, 100):
            exps = {0, S.exp_for_level(cap), S.exp_for_level(50),
                    S.exp_for_level(100), 0xFFFFFFFF}
            if cap > 1:
                exps.add(S.exp_for_level(cap) - 1)
            for e in sorted(exps):
                g = int(d.ask(f"tl {e} {cap}"))
                w = S.exp_to_level(e, cap)
                n += 1
                if g != w:
                    fails.append(f"exp_to_level({e}, cap={cap}): "
                                 f"C {g} ≠ Python {w}")
        # 契约点名的场景：cap=20 给足 Lv50 的经验仍是 20
        g = int(d.ask(f"tl {S.exp_for_level(50)} 20"))
        if g != 20:
            fails.append(f"cap 生效: cap=20 + Lv50 经验 → C {g} ≠ 20")
        print(f"  cap 生效       {n} 组 + 契约点名场景（cap=20 + Lv50 经验 → 20）")

        # ---- ⑤ exp_progress：(got, need) 与 sim 一致 ------------------------
        # 语义细节：exp 落在本级起点之前时 got 钳 0（不是负数回绕），
        # need 至少 1。这两处钳制是 C 侧最容易漏抄的。
        n = 0
        for lv in (1, 2, 5, 12, 18, 29, 50, 99, 100):
            lo = S.exp_for_level(lv)
            hi = S.exp_for_level(lv + 1)
            pts = {0, lo, (lo + hi) // 2, hi - 1, S.exp_for_level(100)}
            if lo > 0:            # lv=1 的 lo=0，「起点之前」在 uint32 里不存在
                pts.add(lo - 1)
            for e in sorted(pts):
                g = tuple(int(x) for x in d.ask(f"pr {e} {lv}").split())
                w = S.exp_progress(e, lv)
                n += 1
                if g != w:
                    fails.append(f"exp_progress({e}, lv={lv}): "
                                 f"C {g} ≠ Python {w}")
        print(f"  经验进度       {n} 组（含 got 钳 0 / need ≥ 1）")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:15]:
            print("   " + f)
        if len(fails) > 15:
            print(f"   …还有 {len(fails)-15} 处")
        return 1

    print("\n✅ 经验曲线与 sim 逐值一致（常量 / 曲线 / 升级边界 / 上限 / 进度）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
