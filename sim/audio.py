"""S13 音频 —— GB 风格四通道 APU + 音序数据。

对应 docs/systems/S13-audio.md。

## 为什么是实时合成而不是采样播放

ESP32-C3 **无内置 DAC**（区别于经典 ESP32），播不了采样音频
（[01-constitution.md](../docs/01-constitution.md) 硬约束）。
出路是 PWM 或外接 I2S，两者都要 CPU 现算波形。

而这恰好是好事：实时合成**几乎不占 flash**，且与像素美术天然统一。

## CPU 预算：不是瓶颈

    ESP32-C3 @160MHz，22050Hz 采样率 → 每样本 7256 周期
    4 通道方波 + 混音 ≈ 120 周期/样本
    → 占 CPU 1.65%

算清这个之后才敢照 GB APU 的真实结构做**四个通道**，
而不是砍成一两个。瓶颈从来不在合成，在中断延迟与 DMA 缓冲。

## 通道配置照 GB DMG

| 通道 | GB 原型 | 本项目用途 |
|---|---|---|
| CH1 | 方波 + 扫频 | 主旋律；扫频用于捕获音、进化音 |
| CH2 | 方波 | 和声 / 副旋律 |
| CH3 | 波表（32×4bit） | 低音线；波表让它音色区别于方波 |
| CH4 | 噪声（LFSR） | 打击、爆炸、失败音 |

方波占空比 12.5/25/50/75% 四档 —— 这是 GB 音色最标志性的来源，
同一个音高换占空比听起来像换了乐器。

零第三方依赖（wave 是标准库），Python 3.9+。
"""

from __future__ import annotations

import math
import struct
import wave
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# 全局参数
# ---------------------------------------------------------------------------

SAMPLE_RATE = 22050        # 固件侧同值。44100 也跑得动，但 22050 省一半 DMA
CHANNELS = 4
MASTER_VOL = 0.22          # 四通道叠加后防削波

# GB 的占空比四档。同音高换占空比 ≈ 换乐器，这是 GB 音色的核心。
DUTIES = (0.125, 0.25, 0.50, 0.75)

# 十二平均律。A4=440，用半音数寻址。
A4_HZ = 440.0
A4_MIDI = 69


def midi_hz(note: int) -> float:
    return A4_HZ * (2.0 ** ((note - A4_MIDI) / 12.0))


# 音名 → MIDI，方便手写音序
NOTE_BASE = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
             "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11}


def n(name: str) -> int:
    """音名转 MIDI 号，如 n("C4")=60、n("A#3")=58。"""
    i = 1 if len(name) > 1 and name[1] == "#" else 0
    return (int(name[1 + i:]) + 1) * 12 + NOTE_BASE[name[:1 + i]]


REST = -1        # 休止符


# ---------------------------------------------------------------------------
# 包络
#
# GB 的硬件包络只有「线性升/降 + 步长」，没有 ADSR。
# 这里照做 —— 不是偷懒，是**音色的一部分**：
# GB 音效那种「啪」的干脆感来自没有 attack 斜坡。
# ---------------------------------------------------------------------------

@dataclass
class Envelope:
    start: float = 1.0        # 初始音量 0~1
    step: float = 0.0         # 每步变化量（负=衰减）
    step_ms: int = 16         # 每步时长（GB 是 1/64 秒 ≈ 15.6ms）

    def at(self, t_ms: float) -> float:
        if self.step == 0.0:
            return self.start
        steps = int(t_ms / self.step_ms)
        return max(0.0, min(1.0, self.start + self.step * steps))


# 常用包络
ENV_FLAT = Envelope(1.0, 0.0)
ENV_PLUCK = Envelope(1.0, -0.10)      # 拨弦感，快衰减
ENV_FADE = Envelope(1.0, -0.03)       # 慢衰减，长音
ENV_HIT = Envelope(1.0, -0.25)        # 打击，极快


# ---------------------------------------------------------------------------
# 波形发生器
# ---------------------------------------------------------------------------

def square(phase: float, duty: float) -> float:
    """方波。phase 在 0~1。返回值**已去直流并归一化**到 ±1。

    ## 为什么必须去直流

    朴素方波（高=+1 / 低=-1）在占空比 ≠ 50% 时带直流分量：

        占空比 0.125 → 直流 -0.750
        占空比 0.250 → 直流 -0.500
        占空比 0.750 → 直流 +0.500

    实测 shiny 音效（全用 12.5%）直流偏移到 -0.1365。直流的后果是
    扬声器持续偏压、发热、并白吃掉动态余量。

    真机上通常有耦合电容把直流滤掉 —— 但**不能假设那个电容存在**，
    这台设备的音频通路（PWM 还是 I2S）还没确认。在合成侧解决更稳。

    去直流后峰值会涨（12.5% 时高电平变 +1.75），所以同时按峰值归一化，
    保持 ±1 的动态范围不变。
    """
    dc = 2.0 * duty - 1.0                       # 该占空比的直流分量
    hi, lo = 1.0 - dc, -1.0 - dc                # 中心化后的两个电平
    peak = max(abs(hi), abs(lo))                # 归一化因子
    return (hi if (phase % 1.0) < duty else lo) / peak


# CH3 波表：32 个 4bit 值。这里给一个三角波表 ——
# GB 游戏里 CH3 最常用来做低音线，三角比方波更"圆"，不抢主旋律。
WAVE_TRIANGLE = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0,
]


def wavetable(phase: float, table: list[int]) -> float:
    idx = int((phase % 1.0) * len(table))
    return table[idx] / 7.5 - 1.0        # 0~15 映射到 -1~1


class Noise:
    """LFSR 噪声 —— GB 的 CH4。

    15 位线性反馈移位寄存器，与 GB 硬件同构。
    7 位模式（short=True）音色更"金属"，GB 用它做某些打击音。
    """

    def __init__(self, short: bool = False) -> None:
        self.reg = 0x7FFF
        self.short = short

    def step(self) -> float:
        bit = (self.reg ^ (self.reg >> 1)) & 1
        self.reg >>= 1
        self.reg |= bit << 14
        if self.short:
            self.reg = (self.reg & ~(1 << 6)) | (bit << 6)
        return -1.0 if (self.reg & 1) else 1.0


# ---------------------------------------------------------------------------
# 音符与音轨
# ---------------------------------------------------------------------------

@dataclass
class Note:
    """一个音。

    固件侧每个音 4 字节：midi(1) + 时长(1) + 音量/包络索引(1) + 标志(1)。
    这里用 dataclass 表达，但字段刻意保持在能压进 4 字节的范围。
    """

    midi: int
    dur_ms: int
    duty: int = 2                       # DUTIES 下标
    env: Envelope = field(default_factory=lambda: ENV_FLAT)
    sweep: float = 0.0                  # 每毫秒的半音变化（扫频）
    vol: float = 1.0


@dataclass
class Track:
    """一个通道的音符序列。"""

    kind: str = "square"                # square / wave / noise
    notes: list = field(default_factory=list)
    noise_short: bool = False


def render(tracks: list[Track], sr: int = SAMPLE_RATE) -> list[float]:
    """把多轨渲染成 float 采样序列（-1~1）。

    这个函数是**PC 侧的参考实现**。固件侧的定点版本要产出听起来一样的结果，
    但用整数相位累加器（Q16.16）而非浮点。
    """
    # 总长取最长轨
    total_ms = max((sum(x.dur_ms for x in t.notes) for t in tracks), default=0)
    total = int(total_ms * sr / 1000) + 1
    buf = [0.0] * total

    for tr in tracks:
        phase = 0.0
        cursor = 0
        noise = Noise(tr.noise_short)
        for note in tr.notes:
            ns = int(note.dur_ms * sr / 1000)
            if note.midi == REST:
                cursor += ns
                continue
            for i in range(ns):
                if cursor + i >= total:
                    break
                t_ms = i * 1000.0 / sr
                # 扫频：GB CH1 的标志性效果，用于捕获音与进化音
                semi = note.sweep * t_ms
                hz = midi_hz(note.midi) * (2.0 ** (semi / 12.0))
                amp = note.env.at(t_ms) * note.vol

                if tr.kind == "noise":
                    s = noise.step()
                elif tr.kind == "wave":
                    s = wavetable(phase, WAVE_TRIANGLE)
                else:
                    s = square(phase, DUTIES[note.duty])

                buf[cursor + i] += s * amp
                phase += hz / sr
            cursor += ns

    # 混音：只在超出预算时才归一化，**保留音效之间的相对音量**。
    #
    # 两个陷阱都踩过：
    #
    # ① 只在最后 clamp 是硬削波 —— 产生刺耳高次谐波，小扬声器上尤其难听。
    #    实测 escaped 峰值 0.330、evolve 0.374 都越过了 MASTER_VOL 预算。
    #
    # ② 无条件按峰值归一化会**抹掉音效之间的音量差**。menu 峰值刻意压到
    #    0.077（它会被按几万次），归一化会把它拉到和 caught 一样响 ——
    #    那就毁掉了「常触发的音效要轻」这个设计。
    #
    # 所以只在越界时缩，不在未越界时放。
    peak = max((abs(v) for v in buf), default=0.0)
    limit = 1.0 / MASTER_VOL          # 混音域里的上限
    g = MASTER_VOL * (min(1.0, limit / peak) if peak > limit else 1.0)
    return [v * g for v in buf]


def write_wav(path: str, samples: list[float], sr: int = SAMPLE_RATE) -> int:
    """写 16bit 单声道 WAV —— 用来在**没有硬件时也能听**。

    这是音频这一项能在硬件到手前推进的关键：设计好不好听，
    耳朵能判断，不需要等设备。
    """
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, s)) * 32767))
            for s in samples))
    import os
    return os.path.getsize(path)


# ---------------------------------------------------------------------------
# 音效库
#
# 每条都对应一个具体的游戏事件。设计取向：**短**。
# 会话是 30 秒量级，一个 800ms 的音效会占掉 2.7%，且重复听几百次。
# GB 的音效大多在 100~400ms。
# ---------------------------------------------------------------------------

def sfx_boot_1() -> list[Track]:
    """S11 开场第一声（第 98 步）。原版是个短促的高音。"""
    return [Track("square", [Note(n("C6"), 90, duty=2, env=ENV_PLUCK)])]


def sfx_boot_2() -> list[Track]:
    """S11 开场第二声（第 100 步）—— 比第一声低、更长，形成「叮-咚」。

    原版两声的关系是这个动画的灵魂：第一声吊起来，第二声落下去。
    """
    return [Track("square", [Note(n("G5"), 420, duty=2, env=ENV_FADE)])]


def sfx_encounter() -> list[Track]:
    """遭遇提示 —— 三连上行，制造「有东西出现」。"""
    return [Track("square", [
        Note(n("E5"), 60, duty=1, env=ENV_PLUCK),
        Note(n("G5"), 60, duty=1, env=ENV_PLUCK),
        Note(n("C6"), 120, duty=1, env=ENV_FADE),
    ])]


def sfx_ball_throw() -> list[Track]:
    """投球 —— 扫频下行（球飞出去的感觉）+ 噪声（撞击）。"""
    return [
        Track("square", [Note(n("A5"), 160, duty=0, env=ENV_PLUCK,
                              sweep=-0.06)]),
        Track("noise", [Note(REST, 140), Note(n("C4"), 50, env=ENV_HIT)]),
    ]


def sfx_caught() -> list[Track]:
    """捕获成功 —— 上行大三和弦分解。短促但完整，给一个「成了」。"""
    return [Track("square", [
        Note(n("C5"), 70, duty=2, env=ENV_PLUCK),
        Note(n("E5"), 70, duty=2, env=ENV_PLUCK),
        Note(n("G5"), 70, duty=2, env=ENV_PLUCK),
        Note(n("C6"), 220, duty=2, env=ENV_FADE),
    ])]


def sfx_escaped() -> list[Track]:
    """跑掉了 —— 下行两音 + 噪声尾。**不刺耳**：失败音听几百次会烦。"""
    return [
        Track("square", [
            Note(n("G4"), 100, duty=1, env=ENV_PLUCK),
            Note(n("D4"), 200, duty=1, env=ENV_FADE),
        ]),
        Track("noise", [Note(REST, 90), Note(n("C3"), 60, env=ENV_HIT,
                                             vol=0.5)]),
    ]


def sfx_shiny() -> list[Track]:
    """闪光 —— 高频闪烁音。

    这是全游戏最该被记住的 400ms。用快速交替的两个高音（tremolo 感），
    与其他音效完全不同的音区，一听就知道是它。
    """
    # vol 给到 1.0 而不是 0.8：12.5% 占空比归一化后 RMS 只有 0.378
    # （尖锐音色的固有性质 —— 峰值满但大部分时间在低电平），
    # 实测这条 RMS 0.069 比「照料」的 0.121 还轻 ——
    # 全游戏最该被记住的音效反而最不响。
    #
    # 修法是提 vol，不是改占空比：改占空比就换了音色，
    # 那份「一听就知道是它」的辨识度就没了。
    tr = []
    for i in range(8):
        tr.append(Note(n("E6") if i % 2 == 0 else n("B6"), 34,
                       duty=0, env=ENV_FLAT, vol=1.0))
    tr.append(Note(n("E7"), 160, duty=0, env=ENV_FADE, vol=1.0))
    return [Track("square", tr)]


def sfx_evolve() -> list[Track]:
    """进化 —— 长扫频上行。

    GB 进化动画那种「越来越紧张」的感觉全在扫频上：
    音高持续爬升，玩家会本能地等它到顶。
    """
    return [
        Track("square", [Note(n("C4"), 900, duty=2, env=ENV_FLAT,
                              sweep=0.028)]),
        Track("wave", [Note(n("C3"), 900, env=ENV_FADE, vol=0.7)]),
    ]


def sfx_level_up() -> list[Track]:
    """升级 —— 短上行四音。比捕获音更轻，因为它出现得更频繁。"""
    return [Track("square", [
        Note(n("G5"), 55, duty=3, env=ENV_PLUCK),
        Note(n("A5"), 55, duty=3, env=ENV_PLUCK),
        Note(n("B5"), 55, duty=3, env=ENV_PLUCK),
        Note(n("D6"), 160, duty=3, env=ENV_FADE),
    ])]


def sfx_care() -> list[Track]:
    """照料（喂食/玩耍）—— 两个软音。**最常触发的音效，必须不烦**。

    一天三次 × 几个月 = 几百次。所以用 50% 占空比（最"圆"）、
    音量压低、时长最短。
    """
    return [Track("square", [
        Note(n("E5"), 50, duty=2, env=ENV_PLUCK, vol=0.6),
        Note(n("A5"), 90, duty=2, env=ENV_FADE, vol=0.6),
    ])]


def sfx_menu() -> list[Track]:
    """光标移动 —— 极短的一声。三键设备上这个音会被按几万次。"""
    # vol 0.55 而非 0.35：24ms × 12.5% 占空比，实测 RMS 只有 0.027，
    # 在小扬声器上很可能根本听不见。要「轻」靠时长短，不靠音量小到消失。
    return [Track("square", [Note(n("C6"), 24, duty=0, env=ENV_HIT,
                                  vol=0.55)])]


SFX = {
    "boot_1": sfx_boot_1, "boot_2": sfx_boot_2,
    "encounter": sfx_encounter, "ball_throw": sfx_ball_throw,
    "caught": sfx_caught, "escaped": sfx_escaped,
    "shiny": sfx_shiny, "evolve": sfx_evolve,
    "level_up": sfx_level_up, "care": sfx_care, "menu": sfx_menu,
}


# ---------------------------------------------------------------------------
# 存储预算
# ---------------------------------------------------------------------------

BYTES_PER_NOTE = 4       # midi(1) + dur(1) + vol/env(1) + flags(1)


def sfx_bytes(name: str) -> int:
    """一条音效的固件字节数。"""
    tracks = SFX[name]()
    return sum(len(t.notes) for t in tracks) * BYTES_PER_NOTE + len(tracks) * 2


def total_bytes() -> int:
    return sum(sfx_bytes(k) for k in SFX)


def budget() -> dict:
    """全部音效的存储账 —— 用来验证「几乎不占 flash」这个断言。"""
    per = {k: sfx_bytes(k) for k in SFX}
    durs = {k: max((sum(x.dur_ms for x in t.notes) for t in SFX[k]()),
                   default=0) for k in SFX}
    return {
        "per_sfx": per,
        "durations_ms": durs,
        "total_bytes": sum(per.values()),
        "longest_ms": max(durs.values()),
        "sample_rate": SAMPLE_RATE,
        # 对照：同样的音效若存 16bit PCM 要多少
        "as_pcm_bytes": int(sum(durs.values()) / 1000 * SAMPLE_RATE * 2),
    }
