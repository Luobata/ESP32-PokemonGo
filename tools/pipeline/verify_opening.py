#!/usr/bin/env python3
"""opening.c 与 sim/opening.py 的 OpeningFlow 状态机逐帧对账（S16 开场）。

用法：
    /usr/bin/python3 tools/pipeline/verify_opening.py [opening.c 路径]

默认对账 `firmware/main/opening.c`；传入别的路径用于反向验证 ——
把副本改坏再跑，脚本必须红，证明它真在对账而不是恒绿。

## 为什么逐帧

开场是**帧级时序状态机**（打字机 3 帧/字），这类逻辑最容易
「看起来对但差一帧」—— 差一帧在真机上肉眼分辨不出，录屏都难对证。
所以核心不是「最终到了哪」，而是**每一帧的五元组都一致**：

    (box, typed, frame, typing, done) —— 逐帧与 sim 的 OpeningFlow 相等

## sim 侧语义要点（对账基准，逐条来自 sim/opening.py 源码）

    · tick：done 时不动；否则 frame+1，且 typing 且 frame%3==0 时 typed+1。
      **没有 BOX_APPEAR 门控** —— 第 3 帧就打出第 1 个字；
      BOX_APPEAR_FRAMES 只进 total_frames 的预算，不进状态机
    · **pause_after 同理** —— 20 帧只计入 total_frames()=407，
      状态机里没有暂停：打完字后 frame 继续涨，等玩家按 A
    · press('A') 打字中 → typed=full_len，**框不变、frame 不变**（立即显示
      整框，不是跳框）；打字完 → box+1、typed/frame 归零，
      第 7 框打完再按 → done，box 停在 7（越界一格）
    · press('C') → skipped 且 done；此后 tick/press 全部无操作
    · press('B') → 无操作（三键设计里 B 刻意空着）
    · 播完后 full_len=0、show_mon=0；结束后 press 同状态同键返回码确定

## 对账返回码吗？

D15 没钉返回码的取值（sim 侧是中文字符串，C 侧必是 cep-coder 自选的
枚举）。本门禁比对**状态效果**（严格逐帧），返回码只验一条：
同状态同键必须同码（纯函数确定性）。

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
#include <stdbool.h>
#include <string.h>

/* 用真的 opening.c —— 接口按 TASK.md D15 钉死，宏值编译期就钉住。 */
#include "opening.c"

_Static_assert(OPENING_BOXES == 7, "D15: OPENING_BOXES must be 7");
_Static_assert(OPENING_TYPE_FRAMES_PER_CHAR == 3, "D15: 3 frames per char");
_Static_assert(OPENING_BOX_APPEAR_FRAMES == 6, "D15: box appear 6 frames");
_Static_assert(OPENING_LINES_PER_BOX == 4, "D15: 4 lines per box");

static opening_t g_o;

static void put_state(void)
{
    printf("%u %u %u %d %d %d\n", (unsigned)g_o.box, (unsigned)g_o.typed,
           (unsigned)g_o.frame, opening_typing(&g_o) ? 1 : 0,
           g_o.done ? 1 : 0, g_o.skipped ? 1 : 0);
}

int main(void)
{
    char cmd[32], key[8];
    while (scanf("%31s", cmd) == 1) {
        if (!strcmp(cmd, "init")) {
            opening_init(&g_o);
            put_state();
        } else if (!strcmp(cmd, "tick")) {
            opening_tick(&g_o);
            put_state();
        } else if (!strcmp(cmd, "press")) {
            scanf("%7s", key);
            unsigned code = opening_press(&g_o, key[0]);
            printf("%u ", code);
            put_state();
        } else if (!strcmp(cmd, "flen")) {
            printf("%u\n", (unsigned)opening_full_len(&g_o));
        } else if (!strcmp(cmd, "tframes")) {
            printf("%u\n", (unsigned)opening_total_frames());
        } else if (!strcmp(cmd, "smon")) {
            printf("%u\n", (unsigned)opening_show_mon(&g_o));
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str, opening_c: str) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    # opening.c 所在目录排最前：反向验证时指向改坏的副本。
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
           "-I", os.path.dirname(os.path.abspath(opening_c)), "-I", MAIN,
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


def m_state(m) -> tuple:
    return (m.box, m.typed, m.frame, 1 if m.typing else 0,
            1 if m.done else 0, 1 if m.skipped else 0)


def c_state(line: str) -> tuple:
    return tuple(int(x) for x in line.split())


def main() -> int:
    opening_c = (sys.argv[1] if len(sys.argv) > 1
                 else os.path.join(MAIN, "opening.c"))
    if not os.path.exists(opening_c):
        rel = os.path.relpath(opening_c, REPO)
        # 缺失默认红 ——「还没做」不等于「做对了」，这条产线不合格。
        # ALLOW_MISSING=1 是给阶段 B 开工前的显式容忍开关（B1），
        # 用它的人必须在报告/命令里写明，不许当默认。
        if os.environ.get("ALLOW_MISSING") == "1":
            print(f"⚠️ {rel} 不存在（固件侧未交付）—— ALLOW_MISSING=1 "
                  f"容忍缺失，本门禁本轮视为未运行")
            return 0
        print(f"❌ {rel} 不存在 —— 固件侧未交付，无从对账")
        print("   接口见 TASK.md D15（opening.h 九个符号 + 四个时序宏）；"
              "开工前可用 ALLOW_MISSING=1 显式容忍")
        return 1

    import systems  # noqa: F401  # 与其它门禁同环境
    import opening as S

    fails: list[str] = []
    N_BOX = len(S.SCRIPT)

    with tempfile.TemporaryDirectory() as tmp:
        d = Driver(build(tmp, opening_c))

        def cmp_state(got: tuple, m, where: str):
            if got != m_state(m):
                fails.append(f"{where}: C {got} ≠ Python {m_state(m)}")

        def press(m, key: str):
            """两边同按键；返回 (C 返回码, C 状态)。"""
            m.press(key)
            parts = d.ask(f"press {key}").split()
            return int(parts[0]), tuple(int(x) for x in parts[1:])

        # ---- ① 总帧数 ------------------------------------------------------
        g = int(d.ask("tframes"))
        w = S.total_frames()
        if g != w or w != 407:
            fails.append(f"total_frames: C {g} ≠ Python {w}（且应 = 407）")
        print(f"  总帧数         C {g} = Python {w} = 407")

        # ---- ② 核心逐帧：自然播放 ------------------------------------------
        # 每框打完字后刻意再滚 25 帧：sim 状态机里 pause_after 不存在
        # （20 帧只进总预算），打完后 frame 继续涨、不翻框、等 A ——
        # C 若把暂停编进 tick（锁 20 帧或自动翻框）立刻在此现形。
        m = S.OpeningFlow()
        cmp_state(c_state(d.ask("init")), m, "初始状态")
        n_frames = 0
        for b in range(N_BOX):
            if int(d.ask("flen")) != m.full_len:
                fails.append(f"full_len 第{b+1}框: C ≠ Python {m.full_len}")
            w_mon = m.current.show_mon if m.current else 0
            if int(d.ask("smon")) != w_mon:
                fails.append(f"show_mon 第{b+1}框: C ≠ Python {w_mon}")
            while m.typing:
                m.tick()
                cmp_state(c_state(d.ask("tick")), m, f"自然播放 第{b+1}框")
                n_frames += 1
            for _ in range(25):
                m.tick()
                cmp_state(c_state(d.ask("tick")), m, f"打完后滚动 第{b+1}框")
                n_frames += 1
            _, st = press(m, "A")
            cmp_state(st, m, f"按A推进 第{b+1}框")
            n_frames += 1
        # 末态：box=7、done、flen=0、smon=0；结束后不崩不回绕
        if int(d.ask("flen")) != m.full_len:
            fails.append(f"播完后 full_len: C ≠ Python {m.full_len}")
        if int(d.ask("smon")) != 0:
            fails.append("播完后 show_mon 应为 0")
        for _ in range(3):
            m.tick()
            cmp_state(c_state(d.ask("tick")), m, "结束后tick")
        c1, s1 = press(m, "A")
        cmp_state(s1, m, "结束后pressA")
        c2, s2 = press(m, "A")
        cmp_state(s2, m, "结束后pressA第二次")
        if c1 != c2:
            fails.append(f"结束后 press 返回码不确定: {c1} vs {c2}")
        _, s3 = press(m, "C")
        cmp_state(s3, m, "结束后pressC")
        print(f"  自然播放逐帧   {n_frames} 帧全比对"
              f"（含每框打完后 25 帧滚动 + 结束后无操作）")

        # ---- ③ 打字中按 A：两种语义 × 三个深度 × 全部 7 框 ------------------
        # 深度 1/4/10 都在最短打字时长（13 字 × 3 帧 = 39 帧）之内，
        # 保证按 A 时必在打字中 → 第一按应「整框显示」（框不变、frame 不变），
        # 第二按才推进。深度 1 顺带覆盖「第 1 帧就按 A」的急躁玩家。
        n_press = 0
        for depth in (1, 4, 10):
            m = S.OpeningFlow()
            d.ask("init")
            for b in range(N_BOX):
                for _ in range(depth):
                    m.tick()
                    cmp_state(c_state(d.ask("tick")), m,
                              f"深度{depth} 第{b+1}框")
                pre = m_state(m)
                flen_b = m.full_len
                _, st = press(m, "A")
                cmp_state(st, m, f"打字中A 深度{depth} 第{b+1}框")
                if (st[0], st[1], st[2]) != (pre[0], flen_b, pre[2]):
                    fails.append(f"打字中A 深度{depth} 第{b+1}框: "
                                 f"应整框显示(box={pre[0]},typed={flen_b},"
                                 f"frame={pre[2]})，得到 {st[:3]}")
                n_press += 1
                for _ in range(3):
                    m.tick()
                    cmp_state(c_state(d.ask("tick")), m,
                              f"整框后滚动 深度{depth} 第{b+1}框")
                _, st = press(m, "A")
                cmp_state(st, m, f"再按A推进 深度{depth} 第{b+1}框")
                n_press += 1
            if not m.done:
                fails.append(f"深度{depth}: 走完 7 框后应 done")
        # B 键：刻意无操作
        m = S.OpeningFlow()
        d.ask("init")
        for _ in range(2):
            m.tick()
            d.ask("tick")
        pre = m_state(m)
        m.press("B")
        parts = d.ask("press B").split()
        if tuple(int(x) for x in parts[1:]) != pre:
            fails.append("press B: 应无操作（三键设计里 B 空着）")
        n_press += 1
        print(f"  打字中按A      {n_press} 次"
              f"（3 深度 × 7 框 × 两段语义 + B 键无操作）")

        # ---- ④ C 跳过 ------------------------------------------------------
        m = S.OpeningFlow()
        d.ask("init")
        for _ in range(7):
            m.tick()
            d.ask("tick")
        _, st = press(m, "C")
        cmp_state(st, m, "按C跳过")
        if st[4] != 1 or st[5] != 1:
            fails.append(f"按C: 应 skipped 且 done，得到 done={st[4]} "
                         f"skipped={st[5]}")
        for _ in range(5):
            m.tick()
            cmp_state(c_state(d.ask("tick")), m, "跳过后tick")
        _, st = press(m, "A")
        cmp_state(st, m, "跳过后pressA")
        _, st = press(m, "C")
        cmp_state(st, m, "跳过后pressC")
        if m.frame != 7:
            fails.append(f"跳过后 frame 应冻结在 7，C 侧为 {st[2]}")
        print("  C 跳过         打字中跳过 → skipped+done，"
              "此后 tick/press 无操作、frame 冻结")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:15]:
            print("   " + f)
        if len(fails) > 15:
            print(f"   …还有 {len(fails)-15} 处")
        return 1

    print("\n✅ 开场状态机与 sim 逐帧一致"
          "（总帧数 / 逐帧五元组 / A 两语义 / B 空键 / C 跳过 / 结束边界）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
