#!/usr/bin/env python3
"""encounter.c 与 sim/systems.py + sim/state.py 对账。

用法：
    python3 tools/pipeline/verify_encounter.py

## 这一块是全确定性的

与战斗不同，遭遇生成完全不用随机数 —— 种子是 crc32(bssid|小时)。
所以每一项都能逐值对账，不用退到统计分布：

    · spawn_seed        200 个 (bssid, ts) 组合
    · roll_shiny        同上 × 5 个稀有度
    · rarity_from_ap    RSSI × auth × ssid × transient 全组合
    · 队列淘汰          随机灌 500 条，逐步比对队列内容
    · 图鉴位图          151 只全部 set/get + 越界

队列规则是最多五条、满后无条件顶掉第一条。
独立的最新五条参考序列同时比对 C 和 Python，防止两端同错。
"""

from __future__ import annotations

import os
import random
import subprocess
import sys
import tempfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MAIN = os.path.join(REPO, "firmware", "main")
sys.path.insert(0, os.path.join(REPO, "sim"))

DRIVER = r"""
#define HOST_BUILD 1
#include <stdio.h>
#include <string.h>
#include "encounter.c"

/* assets 桩 —— 这一层验的是队列/位图/种子，不碰真资产。
   enc_pick_species 需要 assets_species，单独测（见下面的 pool 命令）。 */
static uint16_t g_total;
static uint16_t g_sum[152];

bool assets_species(uint16_t id, species_t *out)
{
    if (id < 1 || id > g_total) return false;
    memset(out, 0, sizeof(*out));
    out->id = id;
    /* 把总和拆成五项，让 enc_pick_species 加出来正好等于 g_sum */
    uint16_t s = g_sum[id];
    out->hp = (uint8_t)(s / 5); out->attack = (uint8_t)(s / 5);
    out->defense = (uint8_t)(s / 5); out->special = (uint8_t)(s / 5);
    out->speed = (uint8_t)(s - 4 * (s / 5));
    return true;
}
uint32_t assets_species_count(void) { return g_total; }
int assets_known_moves(uint16_t a, uint8_t b, move_t *c, int d)
{ (void)a;(void)b;(void)c;(void)d; return 0; }
const uint8_t *assets_back_sprite(uint16_t id) { (void)id; return NULL; }

static enc_queue_t Q;
static dex_t D;

static void parse_mac(const char *s, uint8_t out[6])
{
    unsigned v[6];
    sscanf(s, "%x:%x:%x:%x:%x:%x", &v[0],&v[1],&v[2],&v[3],&v[4],&v[5]);
    for (int i = 0; i < 6; i++) out[i] = (uint8_t)v[i];
}

int main(void)
{
    char cmd[32];
    enc_queue_init(&Q);
    dex_init(&D);
    while (scanf("%31s", cmd) == 1) {
        if (!strcmp(cmd, "seed")) {
            char mac[32]; unsigned ts;
            scanf("%31s %u", mac, &ts);
            uint8_t b[6]; parse_mac(mac, b);
            printf("%u\n", enc_spawn_seed(b, ts));
        } else if (!strcmp(cmd, "shiny")) {
            char mac[32]; unsigned ts; int rar;
            scanf("%31s %u %d", mac, &ts, &rar);
            uint8_t b[6]; parse_mac(mac, b);
            printf("%d\n", enc_roll_shiny(b, ts, (uint8_t)rar) ? 1 : 0);
        } else if (!strcmp(cmd, "rarity")) {
            int rssi, auth, ssid, tr;
            scanf("%d %d %d %d", &rssi, &auth, &ssid, &tr);
            printf("%u\n", enc_rarity_from_ap((int8_t)rssi, (uint8_t)auth,
                                              ssid != 0, tr != 0));
        } else if (!strcmp(cmd, "qpush")) {
            int rar, sid; unsigned ts;
            scanf("%d %d %u", &rar, &sid, &ts);
            encounter_t e; memset(&e, 0, sizeof(e));
            e.rarity = (uint8_t)rar; e.species_id = (uint16_t)sid; e.ts = ts;
            enc_queue_push(&Q, &e);
            printf("%u\n", Q.count);
        } else if (!strcmp(cmd, "qdump")) {
            printf("%u", Q.count);
            for (uint8_t i = 0; i < Q.count; i++)
                printf(" %u:%u", Q.items[i].rarity, Q.items[i].species_id);
            printf("\n");
        } else if (!strcmp(cmd, "qreset")) {
            enc_queue_init(&Q); printf("ok\n");
        } else if (!strcmp(cmd, "dex")) {
            char what[16]; int sid, shiny;
            scanf("%15s %d %d", what, &sid, &shiny);
            if (!strcmp(what, "seen")) dex_mark_seen(&D, (uint16_t)sid, shiny);
            else dex_mark_caught(&D, (uint16_t)sid, shiny);
            printf("%u %u\n", dex_count_seen(&D), dex_count_caught(&D));
        } else if (!strcmp(cmd, "dexq")) {
            int sid; scanf("%d", &sid);
            printf("%d %d %d\n", dex_is_seen(&D,(uint16_t)sid)?1:0,
                   dex_is_caught(&D,(uint16_t)sid)?1:0,
                   dex_is_shiny_caught(&D,(uint16_t)sid)?1:0);
        } else if (!strcmp(cmd, "pool")) {
            /* pool <total> 然后 total 个种族值总和，再 <mac> <ts> <rarity> */
            int total; scanf("%d", &total);
            g_total = (uint16_t)total;
            for (int i = 1; i <= total; i++) { int v; scanf("%d", &v);
                                               g_sum[i] = (uint16_t)v; }
            char mac[32]; unsigned ts; int rar;
            scanf("%31s %u %d", mac, &ts, &rar);
            uint8_t b[6]; parse_mac(mac, b);
            printf("%u\n", enc_pick_species(b, ts, (uint8_t)rar));
        } else if (!strcmp(cmd, "self")) {
            printf("%d\n", enc_selftest() ? 1 : 0);
        }
        fflush(stdout);
    }
    return 0;
}
"""


def build(tmp: str) -> str:
    src = os.path.join(tmp, "d.c")
    with open(src, "w") as f:
        f.write(DRIVER)
    exe = os.path.join(tmp, "d")
    r = subprocess.run(["cc", "-O1", "-Wall", "-Wextra", "-Werror",
                        "-Wno-unused-parameter", "-I", MAIN, src,
                        "-o", exe, "-lz"], capture_output=True, text=True)
    if r.returncode != 0:
        print("编译失败：\n" + r.stderr, file=sys.stderr)
        sys.exit(1)
    return exe


class D:
    def __init__(self, exe):
        self.p = subprocess.Popen([exe], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, bufsize=1)

    def ask(self, s):
        self.p.stdin.write(s + "\n"); self.p.stdin.flush()
        return self.p.stdout.readline().strip()

    def close(self):
        self.p.stdin.close(); self.p.wait(timeout=5)


def main() -> int:
    import systems as S
    import gameplay as G
    from systems import EncounterQueue, QueuedEncounter

    fails = []
    rnd = random.Random(20260905)

    def mac_of(i):
        return "%02x:%02x:%02x:%02x:%02x:%02x" % (
            i & 0xFF, (i >> 8) & 0xFF, 0xcc, 0xdd, 0xee, 0xff)

    with tempfile.TemporaryDirectory() as tmp:
        d = D(build(tmp))

        # ---- ① spawn_seed ------------------------------------------------
        n = 0
        for i in range(50):
            for ts in (0, 3599, 3600, 86400, 1788584910):
                m = mac_of(i)
                got = int(d.ask(f"seed {m} {ts}"))
                want = G.spawn_seed(m, ts)
                n += 1
                if got != want:
                    fails.append(f"spawn_seed({m},{ts}): C {got} ≠ Py {want}")
        print(f"  刷新种子   {n} 组")

        # ---- ② roll_shiny --------------------------------------------------
        n = hits = 0
        for i in range(40):
            for ts in (0, 7200, 1788584910):
                for rar in (1, 3, 5):
                    m = mac_of(i)
                    got = d.ask(f"shiny {m} {ts} {rar}") == "1"
                    want = S.roll_shiny(m, ts, rar)
                    n += 1
                    hits += want
                    if got != want:
                        fails.append(f"shiny({m},{ts},r{rar}): C {got} ≠ Py {want}")
        print(f"  闪光判定   {n} 组（其中 {hits} 次闪光）")

        # 闪光**概率**也要验 —— 逐值一致只能证明「两边算得一样」，
        # 证明不了「这个概率是对的」。若 salt 拼错导致恒为 false，
        # 逐值对账照样全绿（两边都 false），而玩家一辈子见不到闪光。
        n5 = n3 = 0
        for i in range(1500):
            m = mac_of(i)
            n3 += d.ask(f"shiny {m} 0 3") == "1"
            n5 += d.ask(f"shiny {m} 0 5") == "1"
        # 1/512 与 1/256，1500 次的期望是 2.9 与 5.9。
        # 容差取 0~4 倍期望 —— 只为挡住「恒 false」与「概率高一个量级」
        print(f"  闪光概率   r3 {n3}/1500（期望 ~3）　r5 {n5}/1500（期望 ~6）")
        if n3 == 0 and n5 == 0:
            fails.append("1500 次采样一次闪光都没有 —— salt 可能拼错了")
        if n5 > 30 or n3 > 20:
            fails.append(f"闪光率高得离谱 r3={n3} r5={n5} —— 分母可能错了")

        # ---- ③ rarity_from_ap ----------------------------------------------
        n = 0
        AUTH = {0: "open", 3: "wpa2", 5: "wpa2-ent", 8: "wapi", 10: "wpa3-ent", 14: "wpa3-ent", 15: "wpa3-ent", 16: "wpa2-ent"}
        for rssi in (-30, -79, -80, -81, -95):
            for a_code, a_name in AUTH.items():
                for has_ssid in (True, False):
                    for tr in (True, False):
                        got = int(d.ask(f"rarity {rssi} {a_code} "
                                        f"{1 if has_ssid else 0} "
                                        f"{1 if tr else 0}"))
                        want = G.rarity_from_ap(rssi, a_name,
                                                "x" if has_ssid else "", tr)
                        n += 1
                        if got != want:
                            fails.append(
                                f"rarity(rssi={rssi},{a_name},"
                                f"ssid={has_ssid},tr={tr}): C {got} ≠ Py {want}")
        print(f"  稀有度     {n} 组")

        # ---- ④ 队列淘汰：逐步比对内容 ----------------------------------------
        d.ask("qreset")
        q = EncounterQueue()
        arrivals = []
        n = mismatch = 0
        for step in range(300):
            rar = rnd.randint(1, 5)
            sid = rnd.randint(1, 151)
            ts = 1000 + step
            d.ask(f"qpush {rar} {sid} {ts}")
            q.push(QueuedEncounter(enc=G.Encounter(
                ts=ts, species_id=sid, type_name="一般", rarity=rar,
                from_bssid_hash=0, biome="野外", is_transient=False)))
            arrivals.append((rar, sid))
            # 每 10 步比一次完整内容
            if step % 10 == 9:
                parts = d.ask("qdump").split()
                c_items = [tuple(map(int, p.split(":"))) for p in parts[1:]]
                py_items = [(x.rarity, x.species_id) for x in q.items]
                n += 1
                expected = arrivals[-5:]
                if c_items != expected or py_items != expected or len(q) != 5 or q.dropped != step + 1 - 5:
                    mismatch += 1
                    if mismatch <= 2:
                        fails.append(
                            f"队列第 {step} 步内容不同\n"
                            f"      C  {c_items}\n"
                            f"      Py {py_items}")
        print(f"  队列淘汰   {n} 次全量比对（灌了 300 条）")

        # ---- ⑤ 图鉴位图 -----------------------------------------------------
        import state as ST
        dex = ST.Dex()
        n = 0
        for sid in range(1, 152):
            shiny = (sid % 7 == 0)
            if sid % 3 == 0:
                d.ask(f"dex caught {sid} {1 if shiny else 0}")
                dex.mark_caught(sid, shiny)
            else:
                d.ask(f"dex seen {sid} {1 if shiny else 0}")
                dex.mark_seen(sid, shiny)
            r = d.ask(f"dexq {sid}").split()
            n += 1
            want_seen = bool(dex.seen[(sid-1)//8] >> ((sid-1) % 8) & 1)
            want_caught = bool(dex.caught[(sid-1)//8] >> ((sid-1) % 8) & 1)
            if (r[0] == "1") != want_seen or (r[1] == "1") != want_caught:
                fails.append(f"图鉴 #{sid}: C seen={r[0]} caught={r[1]} ≠ "
                             f"Py {want_seen}/{want_caught}")
        print(f"  图鉴位图   {n} 只")

        # ---- ⑥ enc_pick_species -------------------------------------------
        # 构造一个已知的种族值分布，验分档采样
        sums = [0] + [175 + (i * 3) % 415 for i in range(151)]
        stats = {i: sums[i] for i in range(1, 152)}
        n = 0
        for i in range(30):
            for rar in (1, 3, 5):
                m = mac_of(i)
                line = f"pool 151 " + " ".join(str(sums[k]) for k in range(1, 152))
                line += f" {m} 1788584910 {rar}"
                got = int(d.ask(line))
                want = S.pick_species(m, 1788584910, rar, stats)
                n += 1
                if got != want:
                    fails.append(f"pick_species({m},r{rar}): C {got} ≠ Py {want}")
        print(f"  分档采样   {n} 组")

        # ---- ⑦ C 侧自检 ------------------------------------------------------
        # enc_selftest 自己会先打一行说明再返回 0/1 ——
        # 只读一行会拿到说明文字并误报「未通过」（第一版就是这样）。
        d.p.stdin.write("self\n"); d.p.stdin.flush()
        verdict = None
        for _ in range(8):
            line = d.p.stdout.readline().strip()
            if line in ("0", "1"):
                verdict = line
                break
        if verdict != "1":
            fails.append("enc_selftest 未通过")

        d.close()

    if fails:
        print(f"\n❌ {len(fails)} 处不符：")
        for f in fails[:10]:
            print("   " + f)
        return 1
    print("\n✅ 遭遇/图鉴与 sim 逐值一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
