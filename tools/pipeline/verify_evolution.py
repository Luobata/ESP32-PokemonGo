#!/usr/bin/env python3
"""evolution.c 与 sim/systems.py 的 check_evolution 逐值对账（S7 进化）。

用法：
    /usr/bin/python3 tools/pipeline/verify_evolution.py [evolution.c 路径]

## 对账语义（基准 sim/systems.py:869 check_evolution）

    trigger==NONE(0xFF) 或 evolve_to==0 → can=false，need 字段全 0
    （sim 在赋 need 之前就返回，Early-out 的 need 是默认 0 —— C 也应零）
    默认/LEVEL/未知 trigger → need_int=60、need_exp=max(10, lv×2)
    TRADE(2)              → need_int=90、need_exp=max(20, lv×4)
    ITEM(1)               → 两条线与 LEVEL 同（60 / max(10, lv×2)）；
      biome/dwell 条件**不在 D20 接口里** —— 对账时给 sim 喂满驻留
      （biome_dwell 含全部 STONE_BIOME 值且 ≥ STONE_DWELL_SECONDS），
      对齐 C 侧可见的两线语义；dwell 归属调用方/后续阶段
    can = 亲密度 ≥ need_int **且** 探索值 ≥ need_exp（sim 用严格 <，
      恰好等于算满足 —— 边界用例必测）

## 定点说明

sim 的 need_int 是 60.0/90.0 浮点、pet.intimacy 是浮点；D20 用整数
百分比。对账按**整数**逐值比较 —— sim 侧以 float(int) 传入，
任何取整不一致都是标度问题：报 blocker，不放宽容差。

## 覆盖

    · trigger 全枚举：LEVEL/ITEM/TRADE/None + 未知值（3、0x7F 走默认分支）
    · evolve_level **0..255 全枚举** × 三种实 trigger：
      need 公式逐值（max 下限生效区 + 线性区）；
      lv×2 / lv×4 若在 uint8 域里算会回绕（128/64 以上）——
      这是 exp 门禁 pet+3 陷阱的同类，全枚举必抓
    · max 边界：LEVEL lv=3 → 10（下限生效，不是 6）；lv=16 → 32；
      TRADE lv=3 → 20（下限）；lv=16 → 64
    · can 两线判定：各线 差一/恰好/超出（只满足一条的两种情形）
    · Early-out（NONE / evolve_to=0）的 can 与 need 全零
    · cur_* 回读：结构体应回填传入值

退出码 0 = 过，非 0 = 挂。文件缺失默认红（ALLOW_MISSING=1 显式容忍）。
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
#include <stdbool.h>
#include <string.h>

/* 用真的 evolution.c —— D20 接口 + 触发码编译期钉死。 */
#include "evolution.c"

_Static_assert(EVO_TRIGGER_LEVEL == 0, "D20");
_Static_assert(EVO_TRIGGER_ITEM == 1, "D20");
_Static_assert(EVO_TRIGGER_TRADE == 2, "D20");
_Static_assert(EVO_TRIGGER_NONE == 0xFF, "D20");

int main(void)
{
    char cmd[32];
    while (scanf("%31s", cmd) == 1) {
        if (!strcmp(cmd, "chk")) {
            unsigned ip, ev, tr, to, lv;
            scanf("%u %u %u %u %u", &ip, &ev, &tr, &to, &lv);
            evo_check_t r;
            memset(&r, 0, sizeof(r));
            evo_check((uint8_t)ip, (uint16_t)ev, (uint8_t)tr,
                      (uint8_t)to, (uint8_t)lv, &r);
            printf("%d %u %u %u %u\n", r.can ? 1 : 0,
                   (unsigned)r.need_intimacy, (unsigned)r.need_explore,
                   (unsigned)r.cur_intimacy, (unsigned)r.cur_explore);
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str, evolution_c: str) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    # evolution.c 所在目录排最前：反向验证时指向改坏的副本。
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
           "-I", os.path.dirname(os.path.abspath(evolution_c)), "-I", MAIN,
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


class Pet:
    """sim 侧的 pet 替身 —— check_evolution 只读这两个字段。"""

    def __init__(self, intimacy: int, explore: int):
        self.intimacy = float(intimacy)
        self.explore_value = explore


def main() -> int:
    evolution_c = (sys.argv[1] if len(sys.argv) > 1
                   else os.path.join(MAIN, "evolution.c"))
    if not os.path.exists(evolution_c):
        rel = os.path.relpath(evolution_c, REPO)
        if os.environ.get("ALLOW_MISSING") == "1":
            print(f"⚠️ {rel} 不存在（固件侧未交付）—— ALLOW_MISSING=1 "
                  f"容忍缺失，本门禁本轮视为未运行")
            return 0
        print(f"❌ {rel} 不存在 —— 固件侧未交付，无从对账")
        print("   接口见 TASK.md D20（evolution.h + evo_check_t）；"
              "落地即可跑本门禁")
        return 1

    import systems as S

    # ITEM 的 biome/dwell 不在 D20：喂满驻留，对齐 C 侧两线语义
    DWELL_FULL = {b: S.STONE_DWELL_SECONDS for b in
                  set(S.STONE_BIOME.values()) | {"野外"}}

    def sim_check(intimacy: int, explore: int, trigger: int,
                  evolve_to: int, level: int):
        r = S.check_evolution(Pet(intimacy, explore), trigger, evolve_to,
                              level, biome_dwell=DWELL_FULL)
        return (1 if r.can else 0, int(r.need_intimacy), r.need_explore,
                intimacy, explore)

    fails: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        d = Driver(build(tmp, evolution_c))

        def cmp_case(intimacy, explore, trigger, evolve_to, level, note):
            c = tuple(int(x) for x in d.ask(
                f"chk {intimacy} {explore} {trigger} {evolve_to} {level}"
            ).split())
            w = sim_check(intimacy, explore, trigger, evolve_to, level)
            if c != w:
                fails.append(f"{note}: C {c} ≠ Python {w}")

        # ---- ① trigger 全枚举 × evolve_level 0..255 全枚举 ------------------
        # 每级两档 can（顶配必真 / 零配必假）+ need 公式逐值。
        n = 0
        for trigger in (S.TRIGGER_LEVEL_UP, S.TRIGGER_ITEM, S.TRIGGER_TRADE):
            for lv in range(256):
                for intimacy, explore in ((100, 65535), (0, 0)):
                    cmp_case(intimacy, explore, trigger, 25, lv,
                             f"枚举 trigger={trigger} lv={lv}")
                    n += 1
        print(f"  全枚举          3 trigger × lv 0..255 × 两档 can"
              f" = {n} 组（含 max 下限区与 ×2/×4 回绕陷阱区）")

        # ---- ② max 边界点名 ------------------------------------------------
        CASES = [
            (100, 65535, S.TRIGGER_LEVEL_UP, 25, 3, "LEVEL lv=3 → max(10,·) 生效"),
            (100, 65535, S.TRIGGER_LEVEL_UP, 25, 5, "LEVEL lv=5 → 10"),
            (100, 65535, S.TRIGGER_LEVEL_UP, 25, 6, "LEVEL lv=6 → 12（离开下限）"),
            (100, 65535, S.TRIGGER_LEVEL_UP, 25, 16, "LEVEL lv=16 → 32（妙蛙种子）"),
            (100, 65535, S.TRIGGER_LEVEL_UP, 25, 127, "LEVEL lv=127 → 254"),
            (100, 65535, S.TRIGGER_LEVEL_UP, 25, 128, "LEVEL lv=128 → 256（uint8 回绕陷阱）"),
            (100, 65535, S.TRIGGER_LEVEL_UP, 25, 255, "LEVEL lv=255 → 510"),
            (100, 65535, S.TRIGGER_TRADE, 25, 3, "TRADE lv=3 → max(20,·) 生效"),
            (100, 65535, S.TRIGGER_TRADE, 25, 5, "TRADE lv=5 → 20"),
            (100, 65535, S.TRIGGER_TRADE, 25, 6, "TRADE lv=6 → 24"),
            (100, 65535, S.TRIGGER_TRADE, 25, 16, "TRADE lv=16 → 64"),
            (100, 65535, S.TRIGGER_TRADE, 25, 63, "TRADE lv=63 → 252"),
            (100, 65535, S.TRIGGER_TRADE, 25, 64, "TRADE lv=64 → 256（×4 回绕陷阱）"),
            (100, 65535, S.TRIGGER_TRADE, 25, 255, "TRADE lv=255 → 1020"),
            (100, 65535, 3, 25, 16, "未知 trigger=3 → 走默认（60/32）"),
            (100, 65535, 0x7F, 25, 8, "未知 trigger=0x7F → 默认"),
        ]
        for c in CASES:
            cmp_case(*c)
        print(f"  max/回绕边界    {len(CASES)} 组点名"
              f"（下限生效区 / 线性区 / uint8 回绕点 / 未知 trigger）")

        # ---- ③ can 两线判定（含恰好等于）------------------------------------
        n = 0
        for trigger in (S.TRIGGER_LEVEL_UP, S.TRIGGER_TRADE):
            ni = 90 if trigger == S.TRIGGER_TRADE else 60
            ne = 64 if trigger == S.TRIGGER_TRADE else 32
            for di in (-1, 0, 1):
                for de in (-1, 0, 1):
                    cmp_case(ni + di, ne + de, trigger, 25, 16,
                             f"两线 trigger={trigger} int={ni+di} exp={ne+de}")
                    n += 1
        print(f"  can 两线判定    {n} 组"
              f"（各线 差一/恰好/超出 —— 只满足一条的两种情形在内）")

        # ---- ③.5 G2 断言：ITEM 本轮 = 默认门槛（biome/dwell 不实现）-------
        # 修正案 G2：固件 biome 恒为 0（classify_biome 未移植），dwell 判据
        # 实现了也是死代码。这条断言把「ITEM 走默认」钉死 —— 将来有人
        # 给 ITEM 加真实判据时这里会红，逼着连 D20 接口与 sim 一起改，
        # 而不是静默把 ITEM 当已实现。
        n_g2 = 0
        for lv in range(256):
            c_item = d.ask(f"chk 100 65535 {S.TRIGGER_ITEM} 25 {lv}").split()
            c_level = d.ask(f"chk 100 65535 {S.TRIGGER_LEVEL_UP} 25 {lv}").split()
            n_g2 += 1
            if c_item != c_level:
                fails.append(f"G2: lv={lv} ITEM {c_item} ≠ LEVEL {c_level}"
                             f"（ITEM 本轮应走默认门槛，改判据先改 D20+sim）")
        print(f"  G2 ITEM≡默认    {n_g2} 级逐一相同"
              f"（biome/dwell 不实现，静默实现会在此红）")

        # ---- ④ Early-out：NONE / evolve_to=0 -------------------------------
        n = 0
        for trigger in (S.TRIGGER_LEVEL_UP, S.TRIGGER_ITEM, S.TRIGGER_TRADE,
                        S.TRIGGER_NONE, 3):
            for to in (0, 25):
                if trigger == S.TRIGGER_NONE or to == 0:
                    cmp_case(100, 65535, trigger, to, 16,
                             f"early trigger={trigger} to={to}")
                    n += 1
        print(f"  early-out       {n} 组（NONE / evolve_to=0 → can=false "
              f"且 need 全 0）")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:15]:
            print("   " + f)
        if len(fails) > 15:
            print(f"   …还有 {len(fails)-15} 处")
        print("\n（浮点/整数不一致属标度问题：附 (trigger, lv, 两值) 报 Hub，"
              "勿自行放宽）")
        return 1

    print("\n✅ 进化条件与 sim 逐值一致"
          "（trigger/等级全枚举 / max 与回绕边界 / 两线判定 / early-out）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
