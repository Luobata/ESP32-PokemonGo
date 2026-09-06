#!/usr/bin/env python3
"""party.c 与 sim/party.py 逐值对账（S14 队伍与仓库）。

用法：
    /usr/bin/python3 tools/pipeline/verify_party.py [party.c 路径]

默认对账 `firmware/main/party.c`；传入别的路径用于反向验证 ——
把副本改坏再跑，脚本必须红，证明它真在对账而不是恒绿。

## 为什么逐值、全字节

这是硬件 1:1 复刻的验收标尺。S14 最危险的缺陷形态是**错位寻址**：
布局抄错一位（漏算队伍区、格宽写错），读出来的仍是合法数值，
不报错、只是离谱 —— sim/party.py 的 docstring 就真错过一次
（把 1886 写成 1814）。所以这里不做抽样统计，全部走
**完整 1886 字节比对**：C 侧 `party_serialize` 的输出必须与
Python 镜像 `to_bytes()` 逐字节相等。

## 覆盖

    · 布局        空档全零基线 / Mon 12 字节 <BBBBHBBI 全字段边界值
                  （hp·intimacy 的 255 钳、explore_value 的 65535 钳、
                   exp 的 u32 上限、shiny 进 flags bit0 —— Python 侧的
                   钳位结果必须与 C 侧饱和值落在同一字节上）
    · better      shiny > level > exp，三个维度两两冲突 + 平局
    · receive     永不失败：先进队伍、满 6 进仓库、同种按 better 替换、
                  「不如旧的」也返回成功；队伍内同种不去重（只查仓库）
    · 200 连捕    STATUS 第 2 步点名场景 —— 固定 LCG 序列灌 200 只，
                  每步 FNV-1a 指纹 + total 对账，末尾全字节对账
    · 仓库寻址    第 i 格 = species_id i+1；全长 1886（编译期 _Static_assert）
    · set_leader  insert(0, pop(i)) 语义 —— 队伍其余次序不变；
                  0/越界返回失败且不动状态
    · deserialize 往返一致；短输入拒绝且状态不动；头部计数越界/伪造
                  两边同样钳位重算

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

/* 用真的 party.c（经 party.h）—— 接口按 TASK.md D7 钉死。
   宏值也在编译期钉死：布局改一格，这里先红，不用等对账。 */
#include "party.c"

_Static_assert(PARTY_MAX == 6, "D7: PARTY_MAX must be 6");
_Static_assert(BOX_SPECIES == 151, "D7: BOX_SPECIES must be 151");
_Static_assert(MON_BYTES == 12, "D7: MON_BYTES must be 12");
#define SER_BYTES (2 + (PARTY_MAX + BOX_SPECIES) * MON_BYTES)
_Static_assert(SER_BYTES == 1886, "serialized length must be 1886");

static party_t g_party;
static mon_t g_mon[8];

int main(void)
{
    static uint8_t buf[SER_BYTES];
    static char hex[SER_BYTES * 2 + 8];
    char cmd[32];
    while (scanf("%31s", cmd) == 1) {
        if (!strcmp(cmd, "new")) {
            party_init(&g_party);
            printf("ok\n");
        } else if (!strcmp(cmd, "setmon")) {
            /* setmon <i> <sid> <lv> <hp> <inti> <expl> <nick> <shiny> <exp> */
            unsigned i, sid, lv, hp, ii, ev, nick, sh, ex;
            scanf("%u %u %u %u %u %u %u %u %u",
                  &i, &sid, &lv, &hp, &ii, &ev, &nick, &sh, &ex);
            if (i < 8) {
                g_mon[i].species_id = (uint8_t)sid;
                g_mon[i].level = (uint8_t)lv;
                g_mon[i].hp = (uint8_t)hp;
                g_mon[i].intimacy = (uint8_t)ii;
                g_mon[i].explore_value = (uint16_t)ev;
                g_mon[i].nickname_idx = (uint8_t)nick;
                g_mon[i].flags = (uint8_t)(sh ? 1 : 0);
                g_mon[i].exp = (uint32_t)ex;
            }
            printf("ok\n");
        } else if (!strcmp(cmd, "recv")) {
            unsigned i; scanf("%u", &i);
            printf("%d\n", party_receive(&g_party, &g_mon[i]) ? 1 : 0);
        } else if (!strcmp(cmd, "better")) {
            unsigned i, j; scanf("%u %u", &i, &j);
            printf("%d\n", party_better(&g_mon[i], &g_mon[j]) ? 1 : 0);
        } else if (!strcmp(cmd, "setleader")) {
            unsigned i; scanf("%u", &i);
            printf("%d\n", party_set_leader(&g_party, (uint8_t)i) ? 1 : 0);
        } else if (!strcmp(cmd, "leader")) {
            const mon_t *m = party_leader(&g_party);
            if (!m) printf("none\n");
            else printf("%u %u %u %u %u %u %u %u\n",
                        m->species_id, m->level, m->hp, m->intimacy,
                        m->explore_value, m->nickname_idx, m->flags, m->exp);
        } else if (!strcmp(cmd, "total")) {
            printf("%u\n", (unsigned)party_total(&g_party));
        } else if (!strcmp(cmd, "pcount")) {
            printf("%u\n", (unsigned)g_party.party_count);
        } else if (!strcmp(cmd, "ser")) {
            party_serialize(&g_party, buf);
            for (int i = 0; i < SER_BYTES; i++) printf("%02x", buf[i]);
            printf("\n");
        } else if (!strcmp(cmd, "fnv")) {
            party_serialize(&g_party, buf);
            uint32_t h = 2166136261u;
            for (int i = 0; i < SER_BYTES; i++) { h ^= buf[i]; h *= 16777619u; }
            printf("%08x\n", h);
        } else if (!strcmp(cmd, "deser")) {
            scanf("%3779s", hex);
            int n = (int)(strlen(hex) / 2);
            for (int i = 0; i < n && i < (int)sizeof(buf); i++) {
                unsigned v;
                sscanf(hex + i * 2, "%2x", &v);
                buf[i] = (uint8_t)v;
            }
            printf("%d\n", party_deserialize(&g_party, buf, (uint16_t)n) ? 1 : 0);
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str, party_c: str) -> str:
    src = os.path.join(tmp, "driver.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "driver")
    # party.c 所在目录排最前：反向验证时指向改坏的副本；
    # 副本的 #include "party.h" 若本地没有，仍落回 MAIN 的真头文件。
    cmd = ["cc", "-O1", "-Wall", "-Wextra", "-Werror", "-Wno-unused-parameter",
           "-I", os.path.dirname(os.path.abspath(party_c)), "-I", MAIN,
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


def fnv1a(b: bytes) -> str:
    h = 0x811C9DC5
    for x in b:
        h = ((h ^ x) * 0x01000193) & 0xFFFFFFFF
    return f"{h:08x}"


def setmon_line(i: int, f: tuple) -> str:
    sid, lv, hp, inti, expl, nick, shiny, exp = f
    return f"setmon {i} {sid} {lv} {hp} {inti} {expl} {nick} {1 if shiny else 0} {exp}"


def main() -> int:
    party_c = sys.argv[1] if len(sys.argv) > 1 else os.path.join(MAIN, "party.c")
    if not os.path.exists(party_c):
        rel = os.path.relpath(party_c, REPO)
        print(f"❌ {rel} 不存在 —— 固件侧未交付，无从对账")
        print("   接口见 TASK.md D7（party.h 九个函数 + 三个布局宏），"
              "落地即可跑本门禁")
        return 1

    import systems  # noqa: F401  # 确认 sim 可导入（与其它门禁同环境）
    import party as S

    fails: list[str] = []
    ser_len = 2 + (S.PARTY_MAX + S.BOX_SPECIES) * S.MON_BYTES

    with tempfile.TemporaryDirectory() as tmp:
        d = Driver(build(tmp, party_c))

        # ---- ① 空档基线：全长 1886、全零 ----------------------------------
        d.ask("new")
        got = d.ask("ser")
        n = len(got) // 2
        want = S.Party().to_bytes()
        if n != ser_len or n != len(want):
            fails.append(f"全长: C {n} ≠ {ser_len}")
        if bytes.fromhex(got) != want:
            fails.append("空档基线: C 序列化 ≠ Python 全零 1886 字节")
        print(f"  空档基线       全长 {n} = 1886，全零一致")

        # ---- ② Mon 12 字节布局：全字段边界值 ------------------------------
        # 用 deserialize 注入、serialize+leader 读回 —— 字节由 Python（基准）
        # 生成，C 必须按同一布局解出同样的字段、再原样写回。
        # （不用 receive 注入：C 侧对 sid ∉ [1,151] 有防御性拒绝，那是输入域
        #  校验，不是布局语义 —— receive 的「永不失败」在 ④ 的域内用例里验。）
        D = S.MON_BYTES
        CASES = [
            ("基线（sim 默认值）", dict(species_id=25)),
            ("sid=1",        dict(species_id=1)),
            ("sid=151",      dict(species_id=151)),
            ("sid=255",      dict(species_id=255)),
            ("level=0",      dict(species_id=7, level=0)),
            ("level=100",    dict(species_id=7, level=100)),
            ("level=255",    dict(species_id=7, level=255)),
            ("hp=0（濒死）", dict(species_id=7, hp=0)),
            ("hp=255",       dict(species_id=7, hp=255)),
            ("hp 钳位 300→255", dict(species_id=7, hp=300)),
            ("intimacy=255", dict(species_id=7, intimacy=255)),
            ("intimacy 钳位 999→255", dict(species_id=7, intimacy=999)),
            ("explore=65535", dict(species_id=7, explore_value=65535)),
            ("explore 钳位 70000→65535", dict(species_id=7, explore_value=70000)),
            ("nickname=0",   dict(species_id=7, nickname_idx=0)),
            ("shiny → flags bit0", dict(species_id=7, shiny=True)),
            ("exp=2500000（Lv100）", dict(species_id=7, exp=2500000)),
            ("exp=0xFFFFFFFF", dict(species_id=7, exp=0xFFFFFFFF)),
            ("exp 钳位 2^32→u32 上限", dict(species_id=7, exp=2 ** 32)),
            ("全极值组合", dict(species_id=255, level=255, hp=255, intimacy=255,
                                explore_value=65535, nickname_idx=255,
                                shiny=True, exp=0xFFFFFFFF)),
        ]
        for label, kw in CASES:
            m = S.Mon(**kw)
            pm_ = S.Party()
            pm_.receive(m)                    # 空队伍 → 落 party[0]
            blob = pm_.to_bytes()
            d.ask("new")
            r = d.ask(f"deser {blob.hex()}")
            got = bytes.fromhex(d.ask("ser"))
            canon = S.Mon.from_bytes(m.to_bytes())   # 钳位后的规范值
            want_f = [canon.species_id, canon.level, canon.hp,
                      canon.intimacy, canon.explore_value, canon.nickname_idx,
                      1 if canon.shiny else 0, canon.exp]
            ld = [int(x) for x in d.ask("leader").split()]
            if r != "1":
                fails.append(f"{label}: deserialize 返回 {r} ≠ 1")
            if got[2:2 + D] != m.to_bytes():
                fails.append(f"{label}: Mon 12 字节往返 "
                             f"C {got[2:2+D].hex()} ≠ Python {m.to_bytes().hex()}")
            if got != blob:
                fails.append(f"{label}: 整体序列化 ≠ Python 镜像")
            if ld != want_f:
                fails.append(f"{label}: leader 字段 {ld} ≠ Python {want_f}")
        print(f"  Mon 布局       {len(CASES)} 组"
              f"（deser→ser 往返 + 字段读回，含钳位 / shiny bit0 / 全极值）")

        # ---- ③ better：shiny > level > exp，两两冲突 + 平局 ----------------
        BET = [
            ("闪光压等级：shiny Lv5 > 普通 Lv40",
             (1, 5, 0, 0, 0, 0xFF, 1, 0), (2, 40, 0, 0, 0, 0xFF, 0, 0), True),
            ("反向：普通 Lv40 不如 shiny Lv5",
             (2, 40, 0, 0, 0, 0xFF, 0, 0), (1, 5, 0, 0, 0, 0xFF, 1, 0), False),
            ("闪光压经验：shiny exp0 > 普通 exp 满",
             (1, 1, 0, 0, 0, 0xFF, 1, 0), (2, 1, 0, 0, 0, 0xFF, 0, 0xFFFFFFFF), True),
            ("同为闪光 → 比等级",
             (1, 10, 0, 0, 0, 0xFF, 1, 0), (2, 20, 0, 0, 0, 0xFF, 1, 0), False),
            ("同为普通 → 比等级（等级压经验）",
             (1, 10, 0, 0, 0, 0xFF, 0, 999999), (2, 9, 0, 0, 0, 0xFF, 0, 0), True),
            ("同级 → 比经验",
             (1, 5, 0, 0, 0, 0xFF, 0, 100), (2, 5, 0, 0, 0, 0xFF, 0, 99), True),
            ("同级同经验 → False",
             (1, 5, 0, 0, 0, 0xFF, 0, 100), (2, 5, 0, 0, 0, 0xFF, 0, 100), False),
            ("完全相同 → False",
             (3, 7, 50, 9, 123, 4, 0, 456), (3, 7, 50, 9, 123, 4, 0, 456), False),
            ("等级边界 255 vs 254",
             (1, 255, 0, 0, 0, 0xFF, 0, 0), (2, 254, 0, 0, 0, 0xFF, 0, 0xFFFFFFFF), True),
            ("经验边界 0xFFFFFFFF vs 0xFFFFFFFE",
             (1, 5, 0, 0, 0, 0xFF, 0, 0xFFFFFFFF),
             (2, 5, 0, 0, 0, 0xFF, 0, 0xFFFFFFFE), True),
        ]
        pm = S.Party()
        for label, fa, fb, want in BET:
            d.ask(setmon_line(0, fa))
            d.ask(setmon_line(1, fb))
            ma = S.Mon(*fa[:1], level=fa[1], hp=fa[2], intimacy=fa[3],
                       explore_value=fa[4], nickname_idx=fa[5],
                       shiny=bool(fa[6]), exp=fa[7])
            mb = S.Mon(*fb[:1], level=fb[1], hp=fb[2], intimacy=fb[3],
                       explore_value=fb[4], nickname_idx=fb[5],
                       shiny=bool(fb[6]), exp=fb[7])
            got = d.ask("better 0 1") == "1"
            if got != want:
                fails.append(f"better「{label}」: C {got} ≠ Python {want}")
            # 反方向不自己发明「互补」不变量 —— species/hp 等不参与比较，
            # 只差这些维度的两只双向都 False 是**正确**语义。以 sim 为准。
            rev = d.ask("better 1 0") == "1"
            if rev != pm.better(mb, ma):
                fails.append(f"better 反向「{label}」: C {rev} ≠ "
                             f"Python {pm.better(mb, ma)}")
        print(f"  better 顺序    {len(BET)} 组 ×正反两向（均对 sim）")

        # ---- ④ receive 语义：永不失败 + 仓库按物种寻址 --------------------
        d.ask("new")
        mirror = S.Party()
        for sid in range(10, 16):                     # 6 只不同种 → 填满队伍
            f = (sid, sid - 8, 90, 1, sid * 3, 0xFF, 0, sid * 1000)
            d.ask(setmon_line(0, f))
            m = S.Mon(species_id=f[0], level=f[1], hp=f[2], intimacy=f[3],
                      explore_value=f[4], nickname_idx=f[5], shiny=bool(f[6]),
                      exp=f[7])
            if d.ask("recv 0") != "1" or mirror.receive(m)[0] is not True:
                ok = False
        if d.ask("pcount") != "6" or len(mirror.party) != 6:
            fails.append("receive: 6 只后队伍长度 ≠ 6")
        if d.ask("total") != str(mirror.total):
            fails.append(f"total: 与 Python 镜像不等（{mirror.total}）")
        n_case = 0

        def recv_check(label, f, kw):
            """收一只 → 比对返回值（永不失败）+ 整体序列化字节。"""
            nonlocal n_case
            d.ask(setmon_line(0, f))
            r = d.ask("recv 0")
            mirror.receive(S.Mon(**kw))
            g = bytes.fromhex(d.ask("ser"))
            n_case += 1
            if r != "1":
                fails.append(f"receive「{label}」: 返回 {r} —— 永不失败被打破")
            if g != mirror.to_bytes():
                fails.append(f"receive「{label}」: 序列化 ≠ Python 镜像")

        recv_check("满 6 后新种进仓库 sid=25",
                   (25, 12, 80, 0, 0, 0xFF, 0, 500),
                   dict(species_id=25, level=12, hp=80, exp=500))
        box_base = 2 + S.PARTY_MAX * D
        slot = bytes.fromhex(d.ask("ser"))[box_base + 24 * D: box_base + 25 * D]
        want_slot = S.Mon(species_id=25, level=12, hp=80, exp=500).to_bytes()
        if slot != want_slot:
            fails.append("仓库寻址: 第 24 格（sid=25）字节不符 —— 不是 sid-1 下标")
        recv_check("同种更强（lv 更高）→ 替换",
                   (25, 20, 60, 0, 0, 0xFF, 0, 900),
                   dict(species_id=25, level=20, hp=60, exp=900))
        recv_check("同种更弱（lv 低）→ 放走但仍成功",
                   (25, 3, 30, 0, 0, 0xFF, 0, 10),
                   dict(species_id=25, level=3, hp=30, exp=10))
        recv_check("同种闪光低级 → 闪光留下",
                   (25, 2, 20, 0, 0, 0xFF, 1, 5),
                   dict(species_id=25, level=2, hp=20, shiny=True, exp=5))
        recv_check("sid=151 落最后一格 / sid=1 落第一格",
                   (151, 9, 70, 0, 0, 0xFF, 0, 100),
                   dict(species_id=151, level=9, hp=70, exp=100))
        recv_check("sid=1",
                   (1, 9, 70, 0, 0, 0xFF, 0, 100),
                   dict(species_id=1, level=9, hp=70, exp=100))
        # 队伍内同种不去重 —— receive 只查仓库，队伍有位就直接进队伍
        d.ask("new")
        mirror = S.Party()
        for sid in (30, 30, 31):
            f = (sid, 5, 90, 0, 0, 0xFF, 0, 100)
            d.ask(setmon_line(0, f))
            mirror.receive(S.Mon(species_id=sid, hp=90, exp=100))
            d.ask("recv 0")
        n_case += 1
        if d.ask("pcount") != "3" or len(mirror.party) != 3:
            fails.append("receive: 队伍内同种应当不去重（3 只都在队伍）")
        g = bytes.fromhex(d.ask("ser"))
        if g != mirror.to_bytes():
            fails.append("receive: 队伍内同种场景序列化不符")
        print(f"  receive 语义   {n_case} 组（永不失败 / 替换 / 寻址 / 不去重）")

        # ---- ⑤ 200 连捕：逐步指纹 + 末尾全字节 ----------------------------
        # 固定 LCG，两边喂同一序列；物种取模 40 强制高频同种相遇，
        # shiny 概率抬高到 1/8 —— 压的是状态机分支，不是掉率仿真。
        x = 12345

        def rng():
            nonlocal x
            x = (1103515245 * x + 12345) % (1 << 31)
            return x

        d.ask("new")
        mirror = S.Party()
        step_fail = None
        for step in range(200):
            sid = 1 + rng() % 40
            lv = 1 + rng() % 100
            hp = rng() % 256
            inti = rng() % 256
            expl = rng() % 65536
            nick = 0xFF if rng() % 2 else 0
            sh = 1 if rng() % 8 == 0 else 0
            ex = rng() % 3000000
            f = (sid, lv, hp, inti, expl, nick, sh, ex)
            d.ask(setmon_line(0, f))
            r = d.ask("recv 0")
            m = S.Mon(species_id=sid, level=lv, hp=hp, intimacy=inti,
                      explore_value=expl, nickname_idx=nick,
                      shiny=bool(sh), exp=ex)
            mirror.receive(m)
            g_fnv = d.ask("fnv")
            g_tot = d.ask("total")
            if (r != "1" or g_fnv != fnv1a(mirror.to_bytes())
                    or g_tot != str(mirror.total)):
                step_fail = (step, sid, r, g_fnv, fnv1a(mirror.to_bytes()))
                break
        if step_fail:
            step, sid, r, gf, wf = step_fail
            fails.append(f"200 连捕第 {step} 步（sid={sid}）漂移："
                         f"recv={r} fnv C {gf} ≠ Py {wf}")
        g = bytes.fromhex(d.ask("ser"))
        if g != mirror.to_bytes():
            fails.append("200 连捕: 末态整体序列化 ≠ Python 镜像")
        print(f"  200 连捕       {'200 步全比对' if not step_fail else f'第 {step_fail[0]} 步起漂移'}"
              f"（逐步 FNV + 末尾全字节；末态 total={mirror.total}）")

        # ---- ⑥ set_leader：insert(0, pop(i)) 语义 -------------------------
        d.ask("new")
        mirror = S.Party()
        for sid in (10, 11, 12, 13):
            f = (sid, 5, 90, 0, 0, 0xFF, 0, 0)
            d.ask(setmon_line(0, f))
            mirror.receive(S.Mon(species_id=sid, hp=90))
            d.ask("recv 0")
        LEADER_OPS = [
            ("中段 i=2 → [C,A,B,D]", 2, True),
            ("末位 i=3 → [D,C,A,B]", 3, True),
            ("i=0 → 失败且不动", 0, False),
            ("越界 i=4 → 失败且不动", 4, False),
            ("i=1 → [C,D,A,B]", 1, True),
        ]
        for label, idx, want in LEADER_OPS:
            got = d.ask(f"setleader {idx}") == "1"
            w = mirror.set_leader(idx)
            g = bytes.fromhex(d.ask("ser"))
            if got != want or w != want:
                fails.append(f"set_leader「{label}」: C {got} ≠ Python {w}（期望 {want}）")
            if g != mirror.to_bytes():
                fails.append(f"set_leader「{label}」: 队伍次序 ≠ insert(0,pop(i)) 语义")
        # 单只队伍：i=0 也必须失败
        d.ask("new")
        mirror1 = S.Party()
        d.ask(setmon_line(0, (42, 5, 90, 0, 0, 0xFF, 0, 0)))
        mirror1.receive(S.Mon(species_id=42, hp=90))
        d.ask("recv 0")
        if d.ask("setleader 0") == "1" or mirror1.set_leader(0):
            fails.append("set_leader: 单只队伍 i=0 应失败")
        # leader / total 查询
        d.ask("new")
        if d.ask("leader") != "none":
            fails.append("leader: 空队伍应返回 NULL")
        d.ask(setmon_line(0, (42, 5, 90, 0, 0, 0xFF, 0, 0)))
        d.ask("recv 0")
        d.ask(setmon_line(1, (99, 8, 70, 0, 0, 0xFF, 0, 0)))
        d.ask("recv 1")
        ld = d.ask("leader").split()
        if ld[0] != "42":
            fails.append(f"leader: 应是队首 sid=42，得到 {ld[0]}")
        print(f"  set_leader     {len(LEADER_OPS) + 2} 组（次序保持 / 边界拒绝 / leader·total）")

        # ---- ⑦ deserialize：往返、短输入、伪造头部 ------------------------
        blob = mirror1.to_bytes()
        if d.ask(f"deser {blob.hex()}") != "1":
            fails.append("deserialize: 合法 1886 字节应返回成功")
        g = bytes.fromhex(d.ask("ser"))
        if g != blob:
            fails.append("deserialize→serialize 往返不恒等")
        n7 = 1

        before = d.ask("ser")
        if d.ask(f"deser {blob[:1885].hex()}") == "1":
            fails.append("deserialize: 1885 字节应被拒绝")
        if d.ask("ser") != before:
            fails.append("deserialize: 短输入不应改动状态")
        n7 += 1

        for k, note in ((0, "队伍计数越界 255 → 钳到 6"), (1, "仓库计数伪造 99 → 重数")):
            bad = bytearray(blob)
            bad[k] = 255 if k == 0 else 99
            re_p = S.Party()
            re_p.load(bytes(bad))                     # Python 侧行为基准
            d.ask(f"deser {bytes(bad).hex()}")
            g = bytes.fromhex(d.ask("ser"))
            n7 += 1
            if g != re_p.to_bytes():
                fails.append(f"deserialize「{note}」: C 与 Python 的钳位/重数不一致")
        print(f"  deserialize    {n7} 组（往返 / 短输入 / 伪造头部）")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:15]:
            print("   " + f)
        if len(fails) > 15:
            print(f"   …还有 {len(fails)-15} 处")
        return 1

    print("\n✅ 队伍与仓库与 sim 逐值一致"
          "（布局 / better / receive / 200 连捕 / set_leader / 序列化）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
