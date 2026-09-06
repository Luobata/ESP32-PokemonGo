#!/usr/bin/env python3
"""audio.c 与 sim/audio.py 逐样本对账（S13 chiptune 合成）。

用法：
    /usr/bin/python3 tools/pipeline/verify_audio.py [audio.c 路径]

默认对账 `firmware/main/audio.c`；传入别的路径用于反向验证 ——
把副本改坏再跑，脚本必须红。

## 为什么逐样本

音频是**最难用观测验的**：截图看不见，「人耳听大概对」不构成判据。
而它是纯数值合成 —— 频率、占空比、包络、混音增益**每一步都可对账**。
尤其**分段渲染一致性**：真机按 DMA 分块喂数据，一次性渲染与分块
渲染若不一致，就是断续与爆音 —— 而那正是耳朵抓不到的东西。

## 换算与容差（显式声明，超差即红、报 Hub 定标度，不自行放宽）

    · 频率   C 是 Q8 定点（hz·256），sim 是 float。
             容差 ±1 LSB（舍入方向差异 ≤1；超过说明标度或公式错）。
    · 样本   sim 输出 float（±1 域），C 输出 int16。换算基准取 sim
             write_wav 的语义：int(clamp(s,-1,1) · 32767)（截断）。
             容差 ±2 LSB：截断 vs 四舍五入 ≤1，Q15 混音低比特漂移 ≤1。
             超差附 (音效, 样本号, 两边值) —— 若成片出现在方波沿上，
             可能是相位累加器精度问题，标度决策在 Hub。
    · 分段   C 与 C 自己比（一次性 vs 分块拼接），**逐位相等，零容差**。

## 混音钳位（四通道满幅）的说明

D17 接口只有 11 条固定音效（最多双轨），无法经接口注入「四通道同时
满幅」的自定义用例。以两点覆盖：① MASTER_VOL=0.22，四通道满幅叠加
0.88 < 1.0，数学上不越界；② 11 条音效全样本对账已含 sim 的
「只在越界时缩」归一化语义 —— C 侧增益或钳位行为不同会直接红。

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

# D17 枚举顺序 = sim SFX 字典序
SFX_NAMES = ["boot_1", "boot_2", "encounter", "ball_throw", "caught",
             "escaped", "shiny", "evolve", "level_up", "care", "menu"]

DRIVER = r"""
#define HOST_BUILD 1
#include <stdio.h>
#include <stdint.h>
#include <stdbool.h>
#include <string.h>

/* 用真的 audio.c —— D17 接口。 */
#include "audio.c"

_Static_assert(AUDIO_SAMPLE_RATE == 22050, "D17: 22050");
_Static_assert(AUDIO_CHANNELS == 4, "D17: 4 channels");
_Static_assert(SFX_COUNT == 11, "D17: 11 sfx");

static int16_t g_out[80000];     /* 最长 evolve ≈ 19846 样本，给足 */

static void put_seg(unsigned id, unsigned from, unsigned count)
{
    if (count > (unsigned)(sizeof(g_out) / sizeof(g_out[0])))
        count = (unsigned)(sizeof(g_out) / sizeof(g_out[0]));
    uint32_t w = audio_render((sfx_id_t)id, from, count, g_out);
    printf("%u ", (unsigned)w);
    for (uint32_t i = 0; i < w; i++)
        printf("%04x", (unsigned)((uint16_t)g_out[i] & 0xFFFFu));
    printf("\n");
}

int main(void)
{
    char cmd[32];
    while (scanf("%31s", cmd) == 1) {
        if (!strcmp(cmd, "hz")) {
            unsigned m; scanf("%u", &m);
            printf("%u\n", (unsigned)audio_note_hz_q8((uint8_t)m));
        } else if (!strcmp(cmd, "len")) {
            unsigned i; scanf("%u", &i);
            printf("%u\n", (unsigned)audio_sfx_samples((sfx_id_t)i));
        } else if (!strcmp(cmd, "seg")) {
            unsigned id, from, count;
            scanf("%u %u %u", &id, &from, &count);
            put_seg(id, from, count);
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str, audio_c: str) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    # audio.c 所在目录排最前：反向验证时指向改坏的副本。
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
           "-I", os.path.dirname(os.path.abspath(audio_c)), "-I", MAIN,
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


def decode_seg(line: str) -> tuple[int, list[int]]:
    """'written hex...' → (写入数, int16 列表)。"""
    parts = line.split()
    written = int(parts[0])
    hexs = parts[1] if len(parts) > 1 else ""
    out = []
    for k in range(written):
        v = int(hexs[k * 4:k * 4 + 4], 16)
        out.append(v - 0x10000 if v >= 0x8000 else v)
    return written, out


def sim_int16(s: float) -> int:
    """sim → int16 的换算基准：照 write_wav（截断 + 钳位）。"""
    return int(max(-1.0, min(1.0, s)) * 32767)


def main() -> int:
    audio_c = (sys.argv[1] if len(sys.argv) > 1
               else os.path.join(MAIN, "audio.c"))
    if not os.path.exists(audio_c):
        rel = os.path.relpath(audio_c, REPO)
        if os.environ.get("ALLOW_MISSING") == "1":
            print(f"⚠️ {rel} 不存在（固件侧未交付）—— ALLOW_MISSING=1 "
                  f"容忍缺失，本门禁本轮视为未运行")
            return 0
        print(f"❌ {rel} 不存在 —— 固件侧未交付，无从对账")
        print("   接口见 TASK.md D17（audio.h 三函数 + sfx_id_t 枚举）；"
              "开工前可用 ALLOW_MISSING=1 显式容忍")
        return 1

    import systems  # noqa: F401  # 与其它门禁同环境
    import audio as S

    fails: list[str] = []
    SR = S.SAMPLE_RATE

    with tempfile.TemporaryDirectory() as tmp:
        d = Driver(build(tmp, audio_c))

        # ---- ① 频率表：midi 0..127 全枚举（Q8 vs float，±1 LSB）---------
        n_bad = 0
        for m in range(128):
            got = int(d.ask(f"hz {m}"))
            want = round(S.midi_hz(m) * 256)
            if abs(got - want) > 1:
                n_bad += 1
                if n_bad <= 5:
                    fails.append(f"note_hz(midi={m}): C {got} ≠ "
                                 f"{want}±1（{S.midi_hz(m):.3f} Hz）")
        print(f"  频率表         midi 0..127 全枚举，容差 ±1 LSB"
              f"（{'全过' if not n_bad else f'{n_bad} 个超差'}）")

        # ---- ② 逐样本对账：11 条全部 ---------------------------------------
        bud = S.budget()
        TOL = 2          # int16 LSB；见文件头「换算与容差」
        renders: dict[int, list[float]] = {}
        n_smp = 0
        worst = 0
        for tid, name in enumerate(SFX_NAMES):
            tracks = S.SFX[name]()
            fl = S.render(tracks)
            renders[tid] = fl
            # 总长：与 budget 的 durations_ms 换算一致
            want_len = int(bud["durations_ms"][name] * SR / 1000) + 1
            if len(fl) != want_len:
                fails.append(f"{name}: render 长度 {len(fl)} ≠ "
                             f"durations_ms 换算 {want_len}（sim 内部矛盾）")
            got_len = int(d.ask(f"len {tid}"))
            if got_len != want_len:
                fails.append(f"{name}: audio_sfx_samples {got_len} ≠ "
                             f"{want_len}")
            written, c = decode_seg(d.ask(f"seg {tid} 0 {want_len}"))
            if written != want_len:
                fails.append(f"{name}: 一次性渲染 written {written} ≠ "
                             f"{want_len}")
                continue
            bad_here = 0
            for i in range(want_len):
                w = sim_int16(fl[i])
                dlt = abs(c[i] - w)
                worst = max(worst, dlt)
                n_smp += 1
                if dlt > TOL:
                    bad_here += 1
                    if bad_here <= 3:
                        fails.append(f"{name}[{i}]: C {c[i]} ≠ sim {w}"
                                     f"（Δ{dlt}）")
        print(f"  逐样本         {len(SFX_NAMES)} 条 / {n_smp:,} 样本，"
              f"容差 ±{TOL} LSB，最大偏差 {worst}")

        # ---- ③ 分段渲染一致性（零容差，本门禁核心）-------------------------
        n_seg = 0
        for tid, name in enumerate(SFX_NAMES):
            full_len = int(d.ask(f"len {tid}"))
            _, full = decode_seg(d.ask(f"seg {tid} 0 {full_len}"))
            # 两种切法：规则 64 一段；不规则 7/113/64 循环（不对齐压力）
            for label, chunks in (("64 规则段", [64] * ((full_len + 63) // 64)),
                                  ("7/113/64 不规则", None)):
                if chunks is None:
                    chunks, rest = [], full_len
                    for step in (7, 113, 64, 7, 113, 64):
                        if rest <= 0:
                            break
                        take = min(step, rest)
                        chunks.append(take)
                        rest -= take
                    while rest > 0:
                        take = min(64, rest)
                        chunks.append(take)
                        rest -= take
                at = 0
                ok = True
                for c_count in chunks:
                    if at >= full_len:
                        break
                    take = min(c_count, full_len - at)
                    w, part = decode_seg(d.ask(f"seg {tid} {at} {take}"))
                    if w != take or part != full[at:at + take]:
                        ok = False
                        fails.append(f"{name} {label} @ {at}: 分段结果与"
                                     f"一次性渲染不同（DMA 断续根源）")
                        break
                    at += take
                    n_seg += 1
                if not ok:
                    continue
            # 尾部与越界语义：from=len → 0；from=len-10,count=100 → 10 个
            w, _ = decode_seg(d.ask(f"seg {tid} {full_len} 100"))
            if w != 0:
                fails.append(f"{name}: from=len 应写入 0，得到 {w}")
            w, tail = decode_seg(d.ask(f"seg {tid} {max(0, full_len - 10)} 100"))
            if w != min(10, full_len) or tail != full[max(0, full_len - 10):]:
                fails.append(f"{name}: 尾部区间 (from=len-10, count=100) "
                             f"应写入末尾 {min(10, full_len)} 个一致样本")
            n_seg += 2
        print(f"  分段一致性     {n_seg} 段零容差"
              f"（64 规则 + 7/113/64 不规则 + 越界/尾部语义）")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:15]:
            print("   " + f)
        if len(fails) > 15:
            print(f"   …还有 {len(fails)-15} 处")
        print("\n（定点/浮点超容差属标度问题：附 (音效,样本,两值) 报 Hub，"
              "勿自行放宽）")
        return 1

    print("\n✅ 音频合成与 sim 逐样本一致"
          "（频率表 / 11 条全样本 / 分段渲染零容差）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
