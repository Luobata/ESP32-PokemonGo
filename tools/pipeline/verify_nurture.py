#!/usr/bin/env python3
"""nurture.c 与 sim/gameplay.py 逐拍对账。

用法：
    python3 tools/pipeline/verify_nurture.py

## 为什么要这个

C 侧的 nurture_selftest 只能证明「符合我写它时的预期」。
而移植的验收标准是**与 PC 侧一致** —— 那边的常量是
docs/04-gameplay.md 标定过的，差一点就是不同的游戏。

同 verify_sensing.py：宿主上编译 C，喂同一串时间序列，
逐拍比对三条轴。定点与浮点必然有微小差异，
所以比的是**取整后的百分比**（那才是上屏的东西）。

## 已知的可接受偏差

Q10 下 1 单位 = 0.001，累积一天（86400 秒）最多偏 0.1 ——
远小于 1 个百分点。若某拍差 1，那是四舍五入的边界，不是错误；
脚本按「差 ≥ 2」判失败。
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
#include "nurture.c"
#include <stdlib.h>

// 从 stdin 读 "秒 移动事件数 是否夜间"，每行输出三条轴的百分比。
int main(void)
{
    nurture_t n;
    nurture_init(&n);
    double sec; int motion, night;
    while (scanf("%lf %d %d", &sec, &motion, &night) == 3) {
        nurture_tick(&n, (int64_t)(sec * 1000000.0), motion, night);
        printf("%u %u %u %u\n",
               nurture_pct(n.satiety), nurture_pct(n.mood),
               nurture_pct(n.stamina), nurture_pct(n.intimacy));
    }
    return 0;
}
"""


def build(tmp: str) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    # -Werror：移植代码里的隐式转换必须显式处理，
    # 那是定点运算出错的常见来源
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-I", MAIN, src, "-o", exe]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("编译失败：\n" + r.stderr, file=sys.stderr)
        sys.exit(1)
    return exe


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


def run_python(sched) -> list[tuple[int, int, int, int]]:
    sys.path.insert(0, os.path.join(REPO, "sim"))
    import gameplay

    pet = gameplay.PetState()
    rows = []
    for ts, motion, night in sched:
        pet.advance(ts, motion_events=motion, is_night=night)
        rows.append((round(pet.satiety), round(pet.mood),
                     round(pet.stamina), round(pet.intimacy)))
    return rows


def main() -> int:
    sched = make_schedule()

    with tempfile.TemporaryDirectory() as tmp:
        exe = build(tmp)
        stdin = "".join(f"{t} {m} {1 if n else 0}\n" for t, m, n in sched)
        r = subprocess.run([exe], input=stdin, capture_output=True, text=True)
        if r.returncode != 0:
            print("C 侧运行失败：\n" + r.stderr, file=sys.stderr)
            return 1
        c_rows = [tuple(int(v) for v in line.split())
                  for line in r.stdout.strip().splitlines()]

    py_rows = run_python(sched)

    if len(c_rows) != len(py_rows):
        print(f"行数不同：C {len(c_rows)}  Python {len(py_rows)}")
        return 1

    AXES = ("饱食", "心情", "体能", "亲密")
    worst = [0, 0, 0, 0]
    bad = []
    for i, (c, p) in enumerate(zip(c_rows, py_rows)):
        for k in range(4):
            d = abs(c[k] - p[k])
            worst[k] = max(worst[k], d)
            if d >= 2:
                bad.append((i, AXES[k], c[k], p[k]))

    print(f"{len(sched)} 拍对账")
    for k in range(4):
        print(f"  {AXES[k]}  最大偏差 {worst[k]}")

    if bad:
        print(f"\n❌ {len(bad)} 处偏差 ≥ 2：")
        for i, ax, c, p in bad[:10]:
            print(f"   第 {i} 拍 {ax}: C {c}  Python {p}")
        return 1

    print("\n✅ 定点与浮点逐拍一致（偏差 ≤ 1，四舍五入边界）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
