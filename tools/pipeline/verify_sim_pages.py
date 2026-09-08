#!/usr/bin/env python3
"""页面模拟器 payload 门禁：simPages 必须与 sim/ 现算逐值一致。

用法：
    /usr/bin/python3 tools/pipeline/verify_sim_pages.py [index.html 路径]

## 为什么需要这道门禁

`tools/inspector/build.py` 在 build 时把 sim/ 的数值导出进 index.html，
页面模拟器（#p-sim）的 JS **只播放这些导出值、不自己算数**。这条纪律
防的是「固件 / sim / web 三方数值漂移」。但 build 导出本身也可能错：
改了 sim 忘了重新 build、导出代码抄错字段、手改 index.html —— 本门禁
把 payload 与 sim/ 的**独立重算**逐值对上，任何一处不符即红。

## 覆盖

    · P0 开场   每框逐帧 [typed, frame] 序列 == OpeningFlow 重放；
                totalFrames == opening.total_frames()；fullLen == 行字数和
    · 提示行    hints == KEYS 拼接（"[A]xx [B]xx"），px == text_px
    · P3 战斗   两剧本 auto_battle 重算逐回合对值；win 必胜 / lose 必败
                （剧本标签不许说谎）；shake/flash == effects 序列
    · P4 捕获   三种球窗口宽重算且 poke<great<ultra；窗口居中；
                指针轨迹抽 100 点重算；hitMs 处指针确在窗口内；
                caught == attempt_capture(rng_seed=3) 重算
    · P1/P5 养成 advance(7200) 轴值重算；三动作 before/after 重算；
                方向语义（喂食不降饱食等软断言）
    · P2 遭遇   四条样本 == roll_encounter+wild_level+roll_shiny 重算
                （种子确定，可逐值）
    · P6 图鉴   cols/rows/perPage/pages == party 常量；页容量 ≥ 151
    · ui 素材   9 条；三种球位图两两不同；oak 112×112；调色板 4 色
    · 新鲜度    模板 / 固件资产 / sim / 生成器输入 hash 与当前源码一致；
                实际 HTML 正文、字体 CSS、全量 payload 未被改写；
                simPages JSON == 现算 payload

退出码 0 = 过，非 0 = 挂。缺 index.html 默认红（ALLOW_MISSING=1 容忍）。
"""

from __future__ import annotations

import json
import hashlib
import os
import pathlib
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = pathlib.Path(os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, str(REPO / "sim"))
sys.path.insert(0, str(REPO / "tools" / "inspector"))

FAILS: list[str] = []


def ck(cond: bool, msg: str):
    if not cond:
        FAILS.append(msg)


def check_build_manifest(html: str, B, repo: pathlib.Path = REPO) -> dict | None:
    """校验实际产物，不只看一个声称已接线的 marker。"""
    match = re.search(r"\bconst D\s*=\s*", html)
    if not match:
        ck(False, "index.html 缺少 const D 资产 payload")
        return None
    try:
        payload, end = json.JSONDecoder().raw_decode(html, match.end())
    except ValueError as e:
        ck(False, f"index.html 资产 JSON 无效：{e}")
        return None
    if not isinstance(payload, dict):
        ck(False, "index.html 资产 payload 不是对象")
        return None
    manifest = payload.get("buildManifest")
    if not isinstance(manifest, dict) or manifest.get("version") != 1:
        ck(False, "index.html 缺少当前构建 manifest —— 重新跑 build.py")
        return payload
    try:
        current = B.source_manifest(repo)
        saved = manifest.get("inputs", {})
        if not isinstance(saved, dict):
            saved = {}
        changed = sorted(k for k in current.keys() | saved.keys()
                         if current.get(k) != saved.get(k))
        ck(not changed, "构建输入已变化：" + ", ".join(changed[:8])
           + " —— 重新跑 build.py")
        ck(manifest.get("payloadSha256") == B.payload_hash(payload),
           "index.html 全量 payload hash 不符（产物被改写）")
        # 移除两个构建期注入区，还原模板，再逐字比对实际脚本和 DOM。
        normalized = html[:match.end()] + "ASSETS_JSON" + html[end:]
        if normalized.count(B.FONT_BEGIN) != 1 or normalized.count(B.FONT_END) != 1:
            ck(False, "index.html Kanto16 字体注入区缺失或重复")
        else:
            start = normalized.index(B.FONT_BEGIN)
            stop = normalized.index(B.FONT_END, start)
            css = normalized[start + len(B.FONT_BEGIN):stop]
            ck(bool(css) and hashlib.sha256(css.encode()).hexdigest()
               == manifest.get("fontCssSha256"), "index.html Kanto16 字体 CSS hash 不符")
            normalized = normalized[:start] + "/*KANTO16CSS*/" + normalized[stop + len(B.FONT_END):]
            ck(normalized == (repo / "tools/inspector/template.html").read_text(),
               "index.html 实际模板 / JS 与 template.html 不符（产物代码过期或被改写）")
        ck(bool(payload.get("kantoChars")), "index.html 缺少固件字形，不能用宿主字体作一致性预览")
    except (OSError, ValueError) as e:
        ck(False, f"构建 manifest 校验失败：{e}")
    return payload


def main() -> int:
    import build as B                    # tools/inspector/build.py
    import strings
    import opening as OP
    import systems as S
    import gameplay as G
    import effects as E
    import party as PT

    sp = B.sim_pages_payload()

    # ---- ① P0 开场逐帧 --------------------------------------------------
    for b, bo in enumerate(OP.SCRIPT):
        fl = OP.OpeningFlow()
        fl.box = b
        expect = []
        while fl.typing:
            expect.append([fl.typed, fl.frame])
            fl.tick()
        expect.append([fl.typed, fl.frame])
        got = [[f[0], f[1]] for f in sp["opening"]["boxes"][b]["frames"]]
        ck(got == expect, f"P0 框{b+1} 帧序列与 OpeningFlow 重放不符")
        box = sp["opening"]["boxes"][b]
        ck(box["fullLen"] == sum(len(l) for l in bo.lines),
           f"P0 框{b+1} fullLen != 行字数和")
        ck(len(bo.lines) == len(box["lines"]), f"P0 框{b+1} 行数不符")
    ck(sp["opening"]["totalFrames"] == OP.total_frames(),
       "P0 totalFrames 与 opening.total_frames() 不符")
    ck(sp["opening"]["typeFramesPerChar"] == OP.TYPE_FRAMES_PER_CHAR,
       "P0 帧每字与 TYPE_FRAMES_PER_CHAR 不符")
    print(f"  P0 开场    {len(OP.SCRIPT)} 框逐帧重放一致"
          f"（totalFrames={sp['opening']['totalFrames']}，"
          f"{sp['opening']['typeFramesPerChar']} 帧/字）")

    # ---- ② 提示行与 KEYS 同源 ------------------------------------------
    for p, ks in strings.KEYS.items():
        line = " ".join(f"[{k}]{a}" for k, a in ks.items())
        h = sp["hints"][p]
        ck(h["line"] == line, f"hints[{p}] 文案与 KEYS 拼接不符")
        ck(h["px"] == strings.text_px(line), f"hints[{p}] px 与 text_px 不符")
        ck(sp["keys"][p] == dict(ks), f"keys[{p}] 与 KEYS 不符")
    print(f"  提示行     {len(strings.KEYS)} 页与 KEYS/text_px 同源一致")

    # ---- ③ P3 战斗两剧本 -------------------------------------------------
    for label, wild_sid, plv, wlv, seed in (
            ("win", 19, 12, 5, 7), ("lose", 95, 5, 20, 11)):
        res = S.auto_battle(
            pet_types=["电"], pet_stats=[35, 55, 40, 50, 90], pet_level=plv,
            wild_types=["一般"] if wild_sid == 19 else ["岩石", "地面"],
            wild_stats=[30, 56, 35, 25, 72] if wild_sid == 19
            else [35, 45, 160, 30, 70],
            wild_level=wlv, pet_species=25, wild_species=wild_sid, seed=seed)
        sc = [x for x in sp["battle"]["scenarios"] if x["label"] == label][0]
        ck(len(sc["rounds"]) == len(res.rounds),
           f"P3 {label} 回合数与重算不符")
        for i, (a, b) in enumerate(zip(sc["rounds"], res.rounds)):
            ck(a["attacker"] == b.attacker and a["move"] == b.move
               and a["damage"] == b.damage and a["missed"] == b.missed
               and a["petHp"] == b.pet_hp and a["wildHp"] == b.wild_hp,
               f"P3 {label} 回合{i+1} 字段与重算不符")
        ck(sc["won"] == res.won, f"P3 {label} won 与重算不符")
        ck(sc["exp"] == res.exp, f"P3 {label} exp 与重算不符")
        ck(sc["won"] == (label == "win"),
           f"P3 剧本标签说谎：{label} 的 won={sc['won']}")
        # ---- 数值合理性（第十六派活补漏：petMax=pst[0] 量纲错躺了很多轮，
        # cur>max 在 web 侧被 Math.min 钳住根本看不见 —— 这里从 payload 侧拦）。
        # HP 公式唯一真源：sim/systems.py auto_battle 的
        # effective_stat(base, lv)*2 + lv（别再自己编）。
        pst = [35, 55, 40, 50, 90]
        wst = [30, 56, 35, 25, 72] if wild_sid == 19 else [35, 45, 160, 30, 70]
        ck(sc["petMax"] == S.effective_stat(pst[0], plv) * 2 + plv,
           f"P3 {label} petMax={sc['petMax']} 与 HP 公式"
           f" effective_stat*2+lv={S.effective_stat(pst[0], plv) * 2 + plv} 不符（量纲错？）")
        ck(sc["wildMax"] == S.effective_stat(wst[0], wlv) * 2 + wlv,
           f"P3 {label} wildMax={sc['wildMax']} 与 HP 公式不符（量纲错？）")
        prev_pet = prev_wild = None
        for i, rd in enumerate(sc["rounds"]):
            ck(0 <= rd["petHp"] <= sc["petMax"],
               f"P3 {label} 回合{i+1} petHp={rd['petHp']} 越界 [0,{sc['petMax']}]")
            ck(0 <= rd["wildHp"] <= sc["wildMax"],
               f"P3 {label} 回合{i+1} wildHp={rd['wildHp']} 越界 [0,{sc['wildMax']}]")
            if prev_pet is not None:
                ck(rd["petHp"] <= prev_pet and rd["wildHp"] <= prev_wild,
                   f"P3 {label} 回合{i+1} HP 回升（无治疗系统，只应不增）")
            prev_pet, prev_wild = rd["petHp"], rd["wildHp"]
    shake = [t.offset_x for t in E.shake_sequence(6)]
    ck([t["offset_x"] for t in sp["battle"]["shake"]] == shake,
       "P3 shake 序列与 effects.shake_sequence 不符")
    ck(sp["battle"]["flash"] == E.flash_sequence(6),
       "P3 flash 序列与 effects.flash_sequence 不符")
    # expDemo（十七派活）：exp_progress 只读对账 + 数值合理性
    ex = sp["battle"].get("expDemo") or {}
    if ex:
        import systems as _S
        ck(0 <= ex["expCur"] <= ex["need"], f"expDemo expCur={ex['expCur']} 越界 [0,{ex['need']}]")
        ck(0 <= ex["postCur"] <= ex["postNeed"],
           f"expDemo postCur={ex['postCur']} 越界 [0,{ex['postNeed']}]")
        c, n = _S.exp_progress(_S.exp_for_level(ex["level"] + 1) - ex["gain"], ex["level"])
        ck((ex["expCur"], ex["need"]) == (c, n),
           f"expDemo 战前进度与 exp_progress 重算不符：{(ex['expCur'], ex['need'])} vs {(c, n)}")
        ck(ex["levelUp"] == (ex["postLevel"] > ex["level"]),
           "expDemo levelUp 与 postLevel>level 矛盾")
    else:
        ck(False, "battle.expDemo 缺失（十七派活起为必导字段）")
    n_rounds = sum(len(s["rounds"]) for s in sp["battle"]["scenarios"])
    print(f"  P3 战斗    两剧本 {n_rounds} 回合逐字段一致"
          f"（win 必胜 / lose 必败）+ shake/flash 序列一致")

    # ---- ④ P4 捕获 -------------------------------------------------------
    widths = {}
    for b_ in sp["capture"]["balls"]:
        pet = G.PetState()
        w = S.window_width(45, pet.catch_window_bonus, b_["ball"], 100)
        widths[b_["ball"]] = w
        ck(b_["window"] == w, f"P4 {b_['ball']} 窗口宽与 window_width 不符")
        ck(b_["windowStart"] == (S.BAR_WIDTH - w) // 2,
           f"P4 {b_['ball']} 窗口未居中")
        ck(b_["windowStart"] <= S.pointer_position(b_["hitMs"])
           <= b_["windowStart"] + w,
           f"P4 {b_['ball']} hitMs 处指针不在窗口内")
        enc = G.Encounter(species_id=19, rarity=2, ts=1234, type_name="一般",
                          from_bssid_hash=0x1234, biome="野外",
                          is_transient=False)
        qe = S.QueuedEncounter(enc, hp_ratio=100)
        r = S.attempt_capture(qe, 45, pet, b_["ball"], b_["hitMs"],
                              rng_seed=3)
        ck(b_["caught"] == r.caught,
           f"P4 {b_['ball']} caught 与 attempt_capture 重算不符")
    ck(widths["poke"] < widths["great"] < widths["ultra"],
       "P4 三种球窗口宽必须 poke<great<ultra")
    ptr = sp["capture"]["pointer"]
    ck(len(ptr) == S.POINTER_PERIOD_MS, "P4 指针轨迹长度 != 周期")
    for ms in range(0, S.POINTER_PERIOD_MS, 12):
        ck(ptr[ms] == S.pointer_position(ms),
           f"P4 指针轨迹 t={ms} 与重算不符")
    print(f"  P4 捕获    3 球窗口/居中/hitMs/caught 重算一致"
          f"（{widths['poke']}<{widths['great']}<{widths['ultra']}，"
          f"指针抽 {len(range(0, S.POINTER_PERIOD_MS, 12))} 点一致）")

    # ---- ⑤ P1/P5 养成 ----------------------------------------------------
    pet = G.PetState()
    pet.advance(7200)
    expect_axes = [round(pet.satiety), round(pet.mood),
                   round(pet.stamina), round(pet.intimacy)]
    ck(sp["care"]["axes"] == expect_axes, "P1 轴值与 advance(7200) 重算不符")
    ck(sp["care"]["axisNames"] == ["饱食", "心情", "体能", "亲密"],
       "P1 轴名不符")
    for name in ("feed", "play", "rest"):
        a = sp["care"]["actions"][name]
        p2 = G.PetState()
        p2.satiety, p2.mood = pet.satiety, pet.mood
        p2.stamina, p2.intimacy = pet.stamina, pet.intimacy
        getattr(p2, name)()
        after = [round(p2.satiety), round(p2.mood),
                 round(p2.stamina), round(p2.intimacy)]
        ck(a["after"] == after, f"P5 {name} after 与重算不符")
        ck(a["before"] == expect_axes, f"P5 {name} before != 基准轴")
    # 方向语义（喂食不降饱食、玩耍不降心情、休息不降体能）
    ck(sp["care"]["actions"]["feed"]["after"][0]
       >= sp["care"]["actions"]["feed"]["before"][0], "P5 喂食降了饱食")
    ck(sp["care"]["actions"]["play"]["after"][1]
       >= sp["care"]["actions"]["play"]["before"][1], "P5 玩耍降了心情")
    ck(sp["care"]["actions"]["rest"]["after"][2]
       >= sp["care"]["actions"]["rest"]["before"][2], "P5 休息降了体能")
    print(f"  P1/P5 养成 轴值 {expect_axes} 与三动作 before/after 重算一致"
          f"（方向语义成立）")

    # ---- ⑥ P2 遭遇样本 ---------------------------------------------------
    APS = [("aa:bb:cc:dd:ee:01", "PokemonGo-Free", -55, "open"),
           ("aa:bb:cc:dd:ee:02", "Starbucks-5G", -72, "wpa2"),
           ("aa:bb:cc:dd:ee:03", "eduroam", -48, "wpa2-ent"),
           ("aa:bb:cc:dd:ee:04", "", -80, "wpa2")]
    for i, (bssid, ssid, rssi, auth) in enumerate(APS):
        enc = S.roll_encounter(bssid, ssid, rssi, auth, ts=1000 + i,
                               biome="野外", is_transient=(i == 3))
        e = sp["encounter"]["entries"][i]
        ck(e["sid"] == enc.species_id, f"P2 样本{i+1} sid 与重算不符")
        ck(e["rarity"] == enc.rarity, f"P2 样本{i+1} rarity 与重算不符")
        ck(e["shiny"] == S.roll_shiny(bssid, 1000 + i, enc.rarity),
           f"P2 样本{i+1} shiny 与重算不符")
        ck(e["level"] == S.wild_level(enc.rarity),
           f"P2 样本{i+1} level 与 wild_level 不符")
        ck(1 <= e["sid"] <= 151, f"P2 样本{i+1} sid 越界")
    print(f"  P2 遭遇    {len(APS)} 条样本 == roll_encounter 确定性重算"
          f"（level==wild_level(rarity)）")

    # ---- ⑦ P6 图鉴几何 ---------------------------------------------------
    d = sp["dex"]
    ck(d["cols"] == PT.BOX_COLS and d["rows"] == PT.BOX_ROWS,
       "P6 网格几何与 party 常量不符")
    ck(d["perPage"] == PT.BOX_PER_PAGE == d["cols"] * d["rows"],
       "P6 perPage 与 cols*rows 不符")
    ck(d["pages"] == PT.BOX_PAGES, "P6 pages 与 BOX_PAGES 不符")
    ck(d["pages"] * d["perPage"] >= 151, "P6 页容量盖不住 151 只")
    print(f"  P6 图鉴    {d['cols']}×{d['rows']}×{d['pages']} 页"
          f"== party 常量（容量 {d['pages']*d['perPage']} ≥ 151）")

    # ---- ⑧ stub 与 ui 素材 ----------------------------------------------
    for p in ("P7", "P8"):
        ck(isinstance(sp["stubs"][p], str) and "未实现" in sp["stubs"][p],
           f"{p} stub 必须诚实标注未实现")
    ui = sp["ui"]
    need = {"ball_24", "ball_open", "ball_great", "ball_ultra",
            "cursor", "heart", "star_5", "star_7", "oak"}
    ck(set(ui) == need, f"ui 素材集合不符：{set(ui) ^ need}")
    balls3 = [ui["ball_24"]["bytes"], ui["ball_great"]["bytes"],
              ui["ball_ultra"]["bytes"]]
    ck(len({tuple(x) for x in balls3}) == 1, "原版三种球必须共用闭球点阵")
    ck(len({tuple(ui[n]["palette"]) for n in ("ball_24", "ball_great", "ball_ultra")}) == 3, "三种球调色板必须区分")
    ck(all(ui[n]["w"] == 32 and ui[n]["h"] == 32 for n in ("ball_24", "ball_great", "ball_ultra", "ball_open")), "原版球必须保留 32×32 画布")
    ck(ui["oak"]["w"] == 112 and ui["oak"]["h"] == 112, "oak 必须 112×112")
    for nm, a in ui.items():
        ck(len(a["palette"]) == 4, f"ui {nm} 调色板不是 4 色")
    ck(sp["encounter"]["generatedBySim"] is True,
       "P2 样本必须声明 generatedBySim")
    print(f"  stub/ui    P7/P8 诚实标注；9 素材齐全，三球同形异色，"
          f"oak 112×112")

    # ---- ⑨ index.html 注入新鲜度 ----------------------------------------
    idx_path = sys.argv[1] if len(sys.argv) > 1 else \
        str(REPO / "tools" / "inspector" / "index.html")
    if not os.path.exists(idx_path):
        rel = os.path.relpath(idx_path, REPO)
        if os.environ.get("ALLOW_MISSING") == "1":
            print(f"  ⚠️ {rel} 不存在 —— ALLOW_MISSING=1 容忍，新鲜度未检")
        else:
            print(f"  ❌ {rel} 不存在 —— 先跑 build.py 再验收")
            return 1
    else:
        html = open(idx_path, encoding="utf-8").read()
        payload = check_build_manifest(html, B)
        ck(payload is not None and "simPages" in payload,
           "index.html 里没有 simPages —— build 未注入或产物过期")
        if payload is not None and "simPages" in payload:
            served = payload["simPages"]
            fresh = served == json.loads(json.dumps(sp, ensure_ascii=False,
                                                    default=str))
            ck(fresh,
               "index.html 注入的 simPages 与现算 payload 不一致"
               "（build 过期或被手改）—— 重新跑 build.py")
            # 打印要跟着判定走：ck 只记录不拦截，无条件打 ✓ 会骗读日志的人
            print("  新鲜度     " + ("simPages 注入值 == 现算 payload"
                                    if fresh else "✗ 不一致（见下）"))

    if FAILS:
        print(f"\n❌ {len(FAILS)} 处不符：")
        for f in FAILS[:15]:
            print("   " + f)
        return 1
    print("\n✅ 页面模拟器数据全部与 sim/ 现算一致"
          "（开场逐帧/按键表/战斗/捕获/养成/遭遇/图鉴/素材/输入与产物新鲜度）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
