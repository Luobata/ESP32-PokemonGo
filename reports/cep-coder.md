# cep-coder 报告：A 组四件接线

Contract: pokemon-cep-coder · 2026-09-06

---

## 0. 前置判断：该不该等素材定稿？

**判断：可以先接，不等。** 三个理由，按重要性排：

### 0.1 接线与素材在三条轴上解耦

| 轴 | 机制 | 换素材要不要改调用方 |
|---|---|---|
| 位图 | `assets_ui(name, &out)` 按名查表，ui.bin 只存 2bpp 色号 | **不要**。重跑 `convert_ui.py` 重新生成 ui.bin 即可，调用方零改动 |
| 颜色 | 调色板由**调用侧** PAL 数组供给，素材不内嵌颜色 | **不要**。pixelart.py 的「自带彩色」是设计时意图，不是烧进素材的 |
| 尺寸 | 渲染用运行时 `art.w`/`art.h`，不写死 | x 方向自适应；y 居中是按当前尺寸算的常量，换尺寸改一行 |

**唯一的半耦合是 y 居中常量**：heart 的 `Y(9)` 是按 7×6 在心 16px 字行里居中算的；
若原品 heart 是 16×16（见 §0.2），y 要改成 `Y(4)`。这是一行机械改动，不是重接线。

### 0.2 契约更正后的新算式

Hub 更正 2 说原品「现在就能取」（test 已 clone pokered 到 /tmp/pokered）。
这**加强**而不是推翻「先接」的结论：

- 原品替换是**纯素材替换**（test 建议原话），前提是接线已就位。
  我现在接好，test/web-coder 换位图时才是真正的「换图不换码」。
- 我**没有** `sim/pixelart.py` 或 `tools/**` 的写权限（Do not touch），
  原品替换本身不归我做 —— 我的职责是把当前 ui.bin 里的素材接上屏。
- 尺寸注意：原品 heart 是 16×16（tiles $08,$09,$18,$19），
  当前手绘 heart 是 7×6；原品 star 是 24×24（tiles $2c,$2d,$3c,$3d），
  当前手绘 star_7/star_5 是 7×7/5×5。**换原品时 y 居中常量和 star 的 x 起点
  要跟着调**（24×24 双星从 x=200 起会溢出 240px 宽）。这一行我在代码注释里
  已经标了尺寸依据，换素材的人能看到。

### 0.3 ball 尺寸（24→32）我的判断

契约更正 2 把「24→32 要不要改调用方」明确划给我判断。

**判断：保持 24×24，不改 32×32。**

- 我的渲染用 `ball.w`/`ball.h`（运行时），24 或 32 都能画，**调用方不用改**。
- 24×24 在 BALL_Y=176 行里与球名文字（y=180）、判定条（BAR_Y=208）间距合适；
  32×32 会下探到 y=208 贴判定条，视觉上压。
- 原品 ball_open 来自 `balls.png`（32×8 = 4 帧 8×8），**8×3=24 整数倍可取 24**；
  原品 ball_24 来自 `poke_ball.png`（16×16），整数倍取不到 24 —— 但那是
  test 换素材时的缩放选择，不是我接线的阻塞。
- 结论：接线保持尺寸无关，24 是当前素材的正确尺寸，换原品时 test 自行决定缩放。

---

## 1. heart → P1 亲密度

**文件**：`firmware/main/play_idle.c`

原来的占位是文字 `亲%u`（注释自己写着「♥ 不在字库，等 HEART 点阵接进来再换」）。
换成 heart 点阵 + 数字：

```c
snprintf(buf, sizeof(buf), "%u", nurture_pct(s_w.pet.intimacy));
int w = render_text_width(buf);
render_text(SCR_W - 8 - w, Y(4), buf, ink);
ui_art_t heart;
if (assets_ui("heart", &heart)) {
    static const uint16_t HEART_PAL[4] = {
        RGB_HEX(0x0f380f), RGB_HEX(0xe04858), RGB_HEX(0xf8a0a8), 0,
    };
    render_sprite_2bpp_wh(SCR_W - 8 - w - 2 - heart.w, Y(9),
                          heart.data, heart.w, heart.h, 1, HEART_PAL);
}
```

- 颜色走调用侧 `HEART_PAL`（粉 `#e04858` + 亮粉 `#f8a0a8`），与 pixelart.py 的
  设计意图一致，但不烧进素材。
- y=9 是按 7×6 在 16px 字行居中：`4 + (16-6)/2 = 9`。
- **真机截图**：`cep-coder-r6-p1-heart.png` —— 「雷丘 Lv1 ♥60」，
  粉色心形 + 数字 60，不是「亲60」。✓

## 2. star_7 + star_5 → P2 闪光标记

**文件**：`firmware/main/play_enc.c`

原来的闪光标记是文字 `闪`（一个汉字）。换成 star_7 + star_5 一大一小两颗星：

```c
if (e->is_shiny) {
    static const uint16_t STAR_PAL[4] = {
        RGB_HEX(0x0f380f), RGB_HEX(0xfff0a0), RGB_HEX(0xffffff), 0,
    };
    ui_art_t s7, s5;
    if (assets_ui("star_7", &s7)) {
        render_sprite_2bpp_wh(200, Y(y + (ROW_H - s7.h) / 2),
                              s7.data, s7.w, s7.h, 1, STAR_PAL);
        if (assets_ui("star_5", &s5)) {
            render_sprite_2bpp_wh(200 + s7.w + 2,
                                  Y(y + (ROW_H - s5.h) / 2),
                                  s5.data, s5.w, s5.h, 1, STAR_PAL);
        }
    }
}
```

- 金色 `#fff0a0` + 白高光，与 pixelart.py 设计意图一致。
- x=200：稀有度星（★☆ 文字）右对齐到 x=112..192，星星从 200 起不撞。
- y 居中用 `(ROW_H - s.h)/2`，**尺寸自适应**（换原品 24×24 时 y 自动跟着走，
  但 x=200 起点要调 —— 24+2+24=50px 会溢出 240 宽，换原品时注意）。
- **真机截图**：见 §5 闪光触发。

## 3. ball_open → P4 捕获成功反馈

**文件**：`firmware/main/play_capture.c`

捕获成功时把球种点阵换成 `ball_open`（盖子上移那一帧）：

```c
ui_art_t ball;
const char *ball_name = s_caught ? "ball_open" : BALL_ART[s_ball];
if (assets_ui(ball_name, &ball)) {
    ...
    render_sprite_2bpp_wh(8, Y(BALL_Y), ball.data, ball.w, ball.h, 1, PAL);
}
```

- 两态同名族素材，换位图不改调用方（`ball_name` 三元选名）。
- 捕获成功的 throw handler 里 `draw_all()` 同步重画，ball_open 立即上屏。
- **真机截图**：`cep-coder-r6-p4-ball-open.png` —— 波波 front sprite +
  张开的球（盖子上移）+ 「已捕获 图鉴 +1」，无底部按键提示（hold 态）。✓

## 4. P4 野怪换 front sprite

**文件**：`firmware/main/play_capture.c`

```c
uint8_t sprite_size = 0;
const uint8_t *spr = assets_front_sprite(c->enc.species_id, &sprite_size);
if (!spr) {
    spr = assets_back_sprite(c->enc.species_id);
    sprite_size = spr ? 32 : 0;
}
```

- front 按物种分三档（40/48/56），在 64px 盒子里居中。
- 资产损坏退回 back，不让一张图搞崩页面。
- **代码核对（契约第 5 条）**：

```
$ grep -n "assets_front_sprite\|assets_back_sprite" firmware/main/play_capture.c
168:    const uint8_t *spr = assets_front_sprite(c->enc.species_id, &sprite_size);
170:        spr = assets_back_sprite(c->enc.species_id);
```

  调的是 `assets_front_sprite`，back 只是 fallback。**不是只看截图** ——
  契约记的坑（Gen1 back 低分辨率看着也像正面）在这里用 grep 证伪。
- **真机截图**：`cep-coder-r6-p4-front.png` —— 波波正面（脸朝玩家）。✓

---

## 5. 闪光怎么触发的（不靠碰运气）

**办法：确定性 CRC 触发，不碰概率常数。**

`enc_roll_shiny(bssid, ts, rarity) = crc32("mac|hour|shiny") % denom == 0`，
hour = floor(uptime_s / 3600)。设备每 30s 扫一次 AP 并打 NDJSON。

脚本 `/tmp/shiny_spawn.py`：
1. 解析 NDJSON 扫描行，拿当前 AP 表和 uptime ts。
2. 离线算当前小时哪些 AP 下标会出闪光（zlib.crc32 逐 AP 算）。
3. debug spawn（'e'）用 `ts % n` 挑 AP —— 在 `t % n == 闪光下标` 那一秒发 'e'，
   入队的就是闪光。
4. 等设备日志 `闪光!` 确认。

**不改 SHINY_DENOM（512/256），不改 TIME_BUCKET（3600），不碰数值层。**

### 本轮结果

设备 uptime ~340s，hour=0（要 uptime ≥3600s 才进 hour=1）。
hour=0 的闪光 AP 集合是固定的，本轮扫描到的 6~8 个 AP 里**没有一个**
crc32("mac|0|shiny")%512==0。脚本跑满 600s 窗口未触发。

**这不是办法失败，是当前小时的 AP 集合里没有闪光种子。** 三条出路：
- 等 hour=1（uptime ≥3600s，约 54 分钟后）—— 换一组 AP 闪光集合。
- 换物理环境（不同 WiFi 集合）—— 不可控。
- 接受本轮无闪光截图，用以下证据替代：

### 闪光接线的替代证据

1. **sim 侧门禁**：`verify_encounter.py` 有「闪光判定 360 组」全过
   （含 0 次闪光的负例 + r3 2/1500、r5 6/1500 的概率分布）。
2. **代码接线**：`play_enc.c:176-190` 的 `if (e->is_shiny)` 分支，
   star_7/star_5 都在 `assets_ui` 登记（assets.c:418-419）。
3. **素材存在**：ui.bin 9 条目含 star_5/star_7，`verify_ui.py` 逐像素对账过。
4. **P2 列表截图**：`cep-coder-r6-p2-encounters.png` —— 8 条遭遇，
   稀有度星（★☆ 文字）正常，无闪光（队列里确实没有闪光遭遇）。

**接线是对的，素材在，sim 侧 360 组判定全过 —— 只差一次真机闪光遭遇来截图。**
等 hour=1 或换环境后重跑 `/tmp/shiny_spawn.py` 即可补上这张图。

---

## 6. 验证汇总

| 项 | 结果 | 证据 |
|---|---|---|
| 十三门禁 | ✅ 全绿 | `inventory_assets` + 12 个 `verify_*.py` 全过（verify_sensing 已知红，未碰） |
| `fw.sh build` | ✅ 通过 | `PokeWalk.bin` 生成（recovery 分区溢出警告是历史遗留，与本次无关） |
| P1 ♥N | ✅ | `cep-coder-r6-p1-heart.png`（雷丘 Lv1 ♥60） |
| P4 ball_open | ✅ | `cep-coder-r6-p4-ball-open.png`（已捕获 + 张开的球） |
| P4 front sprite | ✅ | `cep-coder-r6-p4-front.png` + grep 证明调 `assets_front_sprite` |
| P2 闪光星 | ⏳ 无截图 | 确定性触发办法已备好（§5），hour=0 无闪光 AP；sim 360 组 + 代码接线 + 素材登记替代 |

### 截图踩的坑（记给后人）

ball_open 那张图第一轮花了：捕获成功只停留 1.0s（HOLD_TICKS=25×40ms），
截图 dump ~0.5s。**在 throw 后 0.8s 才发 's'，dump 会跨过 hold 到期点，
LVGL tick 在 dump 中途 nav_go(P2)，四条带混了两个页面的状态**
（「已捕获」和底部按键提示同屏 —— 不可能在一个一致帧里）。
修法：throw 后 0.12s 抓日志、0.22s 发 's'，dump 在 ~0.6s 完成，远在 1s 内。

---

## 7. Caveats

1. **闪光截图未取到**（§5）。办法是确定性的、不碰概率常数，但 hour=0 的 AP 集合
   里没有闪光种子。等 hour=1 或换环境重跑 `/tmp/shiny_spawn.py` 可补。
2. **换原品素材时要调两处常量**（§0.2）：heart 的 `Y(9)`（若原品 16×16）、
   star 的 `x=200`（若原品 24×24 双星会溢出）。代码注释里标了尺寸依据。
3. **verify_layout 的 SKIP**：play_capture.c:198 的 ball sprite 被 SKIP
   （`BALL_Y` 非常量无法求值）。手工核对过：ball 在 y=176..199（带 2），
   不跨带。这是门禁的既有盲区（多行 render 调用不解析），不是本次引入。
4. **球数是静态的** `{12,3,1}`（play_capture.c:80，TODO S9 接道具系统）。
   截图里「高级球 ×0」是 throw 后 1→0，不是 bug。
