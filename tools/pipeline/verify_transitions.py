#!/usr/bin/env python3
"""transition.c 与 sim/transitions.py 逐值对账（S15 遭遇转场）。

用法：
    /usr/bin/python3 tools/pipeline/verify_transitions.py [transition.c 路径]

默认对账 `firmware/main/transition.c`；传入别的路径用于反向验证 ——
把副本改坏再跑，脚本必须红，证明它真在对账而不是恒绿。

## 对账的三块

    · trans_pick        全枚举 8 种 bit 组合 × 等级边界（含 uint8 溢出陷阱
                        pet=253/wild=255：+3 会到 256，uint8 里回绕成 0）
    · trans_frames      8 个帧数逐个对
    · trans_has_flash   只有 circle 系（double_circle / circle）为真
    · trans_tile_covered  本门禁核心：8 种转场 × 14 个进度点 ×
                        **全部 30×40 = 1200 格**，与 transition_mask 逐格一致

## 定点 vs 浮点

sim 用 float progress，C 用千分比（q10）。对账时把 q 换算成
`q / 1000.0` 传给 sim。**若某个进度点因舍入两边不一致，本脚本如实报红
并给出 (转场, 进度, gx, gy) —— 标度/容差的决策在 Hub，不在门禁**，
不许自己放宽容差把它糊过去。

退出码 0 = 过，非 0 = 挂，可当 CI 门禁。文件缺失默认红
（ALLOW_MISSING=1 可显式容忍，见 B1）。
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

# D16 枚举顺序 = pokered 表 = sim pick_transition 的 3-bit 索引
ENUM2NAME = ["double_circle", "spiral_in", "circle", "spiral_out",
             "h_stripes", "shrink", "v_stripes", "split"]

DRIVER = r"""
#define HOST_BUILD 1
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* 用真的 transition.c —— D16 接口 + 枚举顺序编译期钉死。 */
#include "transition.c"

_Static_assert(TRANS_TILE == 8, "D16: tile 8");
_Static_assert(TRANS_GRID_W == 30, "D16: grid 30x40");
_Static_assert(TRANS_GRID_H == 40, "D16: grid 30x40");
_Static_assert(TRANS_FLASH_FRAMES == 72, "D16: flash 72");
_Static_assert(TRANS_WAVE == 8 && TRANS_SPECKLE == 9 && TRANS_COUNT == 10, "original eight IDs plus Crystal-inspired extensions");
_Static_assert(TRANS_DOUBLE_CIRCLE == 0, "enum = pokered 表");
_Static_assert(TRANS_SPIRAL_IN == 1, "enum = pokered 表");
_Static_assert(TRANS_CIRCLE == 2, "enum = pokered 表");
_Static_assert(TRANS_SPIRAL_OUT == 3, "enum = pokered 表");
_Static_assert(TRANS_H_STRIPES == 4, "enum = pokered 表");
_Static_assert(TRANS_SHRINK == 5, "enum = pokered 表");
_Static_assert(TRANS_V_STRIPES == 6, "enum = pokered 表");
_Static_assert(TRANS_SPLIT == 7, "enum = pokered 表");

#define GRID_CELLS (TRANS_GRID_W * TRANS_GRID_H)   /* 1200 */
#define GRID_BYTES ((GRID_CELLS + 7) / 8)          /* 150 */

int main(void)
{
    char cmd[32];
    static uint8_t bits[GRID_BYTES];
    while (scanf("%31s", cmd) == 1) {
        if (!strcmp(cmd, "pick")) {
            unsigned t, w, p, o;
            scanf("%u %u %u %u", &t, &w, &p, &o);
            uint8_t idx = 0xFF;
            trans_id_t id = trans_pick(t != 0, (uint8_t)w, (uint8_t)p,
                                       o != 0, &idx);
            printf("%d %u\n", (int)id, (unsigned)idx);
        } else if (!strcmp(cmd, "frames")) {
            unsigned i; scanf("%u", &i);
            printf("%u\n", (unsigned)trans_frames((trans_id_t)i));
        } else if (!strcmp(cmd, "flash")) {
            unsigned i; scanf("%u", &i);
            printf("%d\n", trans_has_flash((trans_id_t)i) ? 1 : 0);
        } else if (!strcmp(cmd, "grid")) {
            unsigned i, q; scanf("%u %u", &i, &q);
            memset(bits, 0, sizeof(bits));
            for (int y = 0; y < TRANS_GRID_H; y++)
                for (int x = 0; x < TRANS_GRID_W; x++)
                    if (trans_tile_covered((trans_id_t)i, (uint16_t)q,
                                           (uint8_t)x, (uint8_t)y))
                        bits[(y * TRANS_GRID_W + x) / 8] |=
                            (uint8_t)(0x80u >> ((y * TRANS_GRID_W + x) % 8));
            for (int k = 0; k < GRID_BYTES; k++) printf("%02x", bits[k]);
            printf("\n");
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str, transition_c: str) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    # transition.c 所在目录排最前：反向验证时指向改坏的副本。
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
           "-I", os.path.dirname(os.path.abspath(transition_c)), "-I", MAIN,
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
    transition_c = (sys.argv[1] if len(sys.argv) > 1
                    else os.path.join(MAIN, "transition.c"))
    if not os.path.exists(transition_c):
        rel = os.path.relpath(transition_c, REPO)
        if os.environ.get("ALLOW_MISSING") == "1":
            print(f"⚠️ {rel} 不存在（固件侧未交付）—— ALLOW_MISSING=1 "
                  f"容忍缺失，本门禁本轮视为未运行")
            return 0
        print(f"❌ {rel} 不存在 —— 固件侧未交付，无从对账")
        print("   接口见 TASK.md D16（transition.h + 枚举顺序照 pokered 表）；"
              "开工前可用 ALLOW_MISSING=1 显式容忍")
        return 1

    import systems  # noqa: F401  # 与其它门禁同环境
    import transitions as S

    fails: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        d = Driver(build(tmp, transition_c))

        # ---- ① trans_pick 全枚举 ------------------------------------------
        # 等级对含三类边界：+2（不算强敌）与 +3（算）的分界、
        # pet=253/wild=255 的 uint8 溢出陷阱（253+3=256，截回 uint8 变 0）、
        # 同级与碾压（都不算强敌）。
        LV_PAIRS = [(10, 12), (10, 13), (0, 2), (0, 3),
                    (253, 255), (10, 10), (10, 5), (50, 53)]
        n = 0
        for trainer in (0, 1):
            for open_b in (0, 1):
                for pet, wild in LV_PAIRS:
                    biome = "野外" if open_b else "洞穴"
                    w_name, w_idx = S.pick_transition(
                        bool(trainer), wild, pet, biome)
                    out = d.ask(f"pick {trainer} {wild} {pet} {open_b}").split()
                    c_id, c_idx = int(out[0]), int(out[1])
                    n += 1
                    if c_idx != w_idx:
                        fails.append(f"pick(tr={trainer},open={open_b},"
                                     f"pet={pet},wild={wild}): idx "
                                     f"C {c_idx} ≠ Python {w_idx}")
                    if c_id != w_idx:
                        fails.append(f"pick(...): 返回 id C {c_id} 与 idx "
                                     f"{w_idx} 不一致（枚举≠pokered 表）")
                    if ENUM2NAME[c_id] != w_name:
                        fails.append(f"pick(...): id {c_id} 是 "
                                     f"{ENUM2NAME[c_id]}，Python 选 {w_name}")
        print(f"  trans_pick      {n} 组（8 bit 组合 × 等级边界，"
              f"含 +2/+3 分界与 uint8 溢出陷阱）")

        # ---- ② 帧数与闪屏 --------------------------------------------------
        n = 0
        for tid, name in enumerate(ENUM2NAME):
            g = int(d.ask(f"frames {tid}"))
            w = S.transition_frames(name)
            if g != w:
                fails.append(f"trans_frames({name}): C {g} ≠ Python {w}")
            gf = int(d.ask(f"flash {tid}"))
            wf = 1 if S.has_flash(name) else 0
            if gf != wf:
                fails.append(f"trans_has_flash({name}): C {gf} ≠ Python {wf}")
            n += 1
        print(f"  frames/flash    {n} 种（帧数逐个对；闪屏只有 "
              f"{'/'.join(k for k in ENUM2NAME if S.has_flash(k))}）")

        # ---- ③ 核心：逐格比对 ----------------------------------------------
        # 进度点刻意压在舍入与分支边界上：0.5 两侧（499/500/501）、
        # 起止（0/1/999/1000）与越界钳位（1200 → sim 内部钳到 1.0）。
        QPOINTS = (0, 1, 100, 250, 333, 499, 500, 501, 667, 750, 900,
                   999, 1000, 1200)
        n_cells = 0
        grid_fails = 0
        for tid, name in enumerate(ENUM2NAME):
            for q in QPOINTS:
                want = S.transition_mask(name, q / 1000.0)
                got = bytes.fromhex(d.ask(f"grid {tid} {q}"))
                for y in range(S.GRID_H):
                    row = want[y]
                    base = y * S.GRID_W
                    for x in range(S.GRID_W):
                        i = base + x
                        g = (got[i >> 3] >> (7 - (i & 7))) & 1
                        n_cells += 1
                        if bool(g) != bool(row[x]):
                            grid_fails += 1
                            if grid_fails <= 10:
                                fails.append(
                                    f"tile({name}, q={q}, gx={x}, gy={y}): "
                                    f"C {g} ≠ Python {int(bool(row[x]))}")
        print(f"  tile 逐格       {len(ENUM2NAME)} 种 × {len(QPOINTS)} 进度 "
              f"× {S.GRID_W}×{S.GRID_H} = {n_cells:,} 格"
              f"（含 0.5 两侧与钳位 1200）")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:15]:
            print("   " + f)
        if len(fails) > 15:
            print(f"   …还有 {len(fails)-15} 处")
        print("\n（定点/浮点边界不一致属标度问题：报 Hub 定，勿自行放宽容差）")
        return 1

    print("\n✅ 转场与 sim 逐值一致"
          "（pick 全枚举 / 帧数 / 闪屏 / 1200 格逐格几何）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
