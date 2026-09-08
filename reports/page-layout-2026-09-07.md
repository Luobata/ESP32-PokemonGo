# 页面布局检查与修复（2026-09-07）

最终收口：原生 P1 四条进度条已统一 x80..232；正常固件构建补齐了 U+73B0「现」，字库现有 882 glyph。默认后台页签改为固件同源预览。构建 `b3f8f2a8c1130f51830a` 的 15 帧真实 Canvas 与独立 native 输出完全一致，记录见 `browser-firmware-parity-2026-09-07.json`；320/835/1280px 窗口均保持整数缩放，无横向溢出。下文保留分阶段发现，最终 P3 使用本报告末节的真实 GSC HUD。

最终验证：848 次局部/整页重绘对照通过，删除 DMA 等待或漏画宠物横带的负向均有效；P2 B 长按丢弃已接通。`verify_web_coords.py` 已转调实际 C 渲染门禁，不再以历史 JS 参考稿保证整页同构。延迟输入探针也在最终 `firmware.js` 上重跑通过，SHA-256 为 `ca41020c17d89f0378d21982d982f283362cc9c77b12d55d1dedc83fad351ee3`。

P3 的主要问题来自仍然独立绘制的 JS 设计稿：HUD 使用不同对齐线、名字跨横带、动画覆盖 HUD、结算在上一条消息上再次绘字。本次修复这些可见问题，并把 base 明确标为 JS 参考稿。整页是否复用固件渲染，交由本轮新增的「固件同源预览」验证；不能以参考稿截图代替。

## 改动

| 页面/区域 | 发现与处理 |
|---|---|
| P3 G 主宠 HUD | 名字原 y150、16px 高，跨过 y160；改为 y164。HP / 数字 / EXP 分别位于 y186 / 202 / 226，完整落在第三条 80px 横带内，三者右缘统一为 x228。 |
| P3 G 动画与 HUD | 特效舞台裁剪到 y38..239，HUD 在其后绘制；主宠 HUD 背板让突进/屏抖经过其后方，名字和读数保持可见。技能动画算法未改。 |
| P3 G 消息 | 消息框改为 `(4,242,232,74)`；先画框，后画 y249 / 269 / 292 三行。回合、结算、经验动画互斥，不再叠印。野生前缀统一为较短的「野生」，为最坏物种名与伤害数字保留间距。 |
| P3 base 结算 | 结算与回合文字改用互斥分支，避免同一坐标先写回合再写胜败。 |
| P3 固件结算 | 「看起来虚弱了」改为右对齐。最终 GSC 消息框内边界是 x12..228，弱化提示位于 x132；实际字体下 `经验 +65535` 宽 88px，保留 32px 净空。旧 x96 的最坏净空为 0px。属于对齐/净空修复，不是宣称旧布局发生文字重叠。 |
| P3 抖动 | 预览错误读取 `shake[].ox`，而构建输出字段为 `offset_x`，导致抖动恒为零；已接到实际字段，落空仍保持不抖。 |
| P1 G/C | G 心情行移到 y160，四轴改为 y184 / 204 / 224 / 244，均容纳 16px 文字而不跨带；数据框与底部按键框重新留空。C 数据框底边也让开最后一行。 |
| P1 标签宽度 | 进度条起点按标签实际宽度加 8px 计算，防四字标签压条。当前 payload 第四轴是两字「亲密」，并没有四字标签重叠；与固件第四轴「今日行程」的语义差异仍属于 JS 参考稿的限制。 |
| P4 | `D.mons[19]` 实际是 #20，却配 `spr(19)`；改为 `D.mons[19-1]`，名字与 #19 小拉达 sprite 一致。 |
| P0/P7/P8 | 完成/占位文字按实际宽度居中；P0 完成态首行也避开 160px 横带边界。P7/P8 仍是未实现页，没有将占位当成功能。 |
| 所有 JS 参考页 | `bar()` 用整数矩形描边，修正 `strokeRect(x+.5,y+.5,w,h)` 多出一像素的右/下边；ASCII 判据改为 `<0x80`，Latin1 的推进宽度与固件相同。 |
| base 与导航 | base 从旧 GB 绿改为当前金银色；共享矩形的 RGB565 展开改为与固件串口截图相同的位复制，修正 floor 缩放造成的 1 级色差。去掉「整页逐像素等于真机」声明，指向固件同源页签；深链正则补 `d=base`，修正从 G 点击 base 链接仍停留在 G 的问题。 |

P2 当前四条样本与 P5 布局未发现必须移动的重叠；P6 G 的现有五列无框布局保留。A/B/C 是设计备选，本轮没有将它们迁移为固件布局。

写入范围：`tools/inspector/template.html` 的页面布局/参考说明、`firmware/main/play_battle.c` 的结算对齐，以及本报告和证据脚本。没有改 `render_scene.h`：本轮采用直接编译真实固件页面的预览入口后，无需再为修布局增加另一套局部配方。没有改用户起始 dirty 文件，没有刷硬件或提交。

## 验证

- `verify_layout.py` 与 `verify_web_coords.py` 通过；前者仍有 5 个明确报告的静态解析 SKIP，未据此声称全页均无跨带。
- 当前 template 的主脚本 `node --check` 通过，`git diff --check` 通过。
- [JS 布局探针](evidence/layout-2026-09-07/layout_probe.js)：最终执行当前 renderer 的 610 个 P3 帧和其他页面的 16 个状态，记录绘制命令，检查文字屏幕边界、相互叠印与 G 动态 HUD 横带边界。另覆盖五字物种名/Lv100/五字招式/65535 伤害、四字轴标签、完成页/占位页居中、抖动和物种一致性。
- 同一探针读取旧 Git HEAD 作为负向对照，确实检测到 G 名字跨带、base 结算叠字、抖动零偏移、P4 物种错配，未把永远通过的脚本当证据。
- [固件结算探针](evidence/layout-2026-09-07/battle_result_probe.py)：从实际 `play_battle.c` 提取结算绘制分支和全部 `MSG_*` 宏，用生产 `render.h` 测宽函数和 `battle.h`/`screen.h` 编译。最终 GSC 边框整合后重新遍历 uint16_t 的全部 65,536 个经验值，当前最小间距 32px，全部文字在 x12..228 内；旧 HEAD 最小 0px。至少 8px 净空的负向对照对旧版返回 2，当前返回 0。AddressSanitizer 与 UndefinedBehaviorSanitizer 通过。

复现（仓库根目录）：

```sh
python3 tools/inspector/build.py --assets assets --out /tmp/pokemon-layout-20260907/index.html
node reports/evidence/layout-2026-09-07/layout_probe.js
python3 reports/evidence/layout-2026-09-07/battle_result_probe.py
python3 tools/pipeline/verify_layout.py
python3 tools/pipeline/verify_web_coords.py
```

证据边界：JS 探针使用记录型 Canvas context，验证实际排版代码和文字推进，不验证浏览器字形栅格或 LCD。当前系统 Python 的临时 build 报 `fontTools` 缺失，Kanto16 被跳过；该临时页面没有被用作字形/像素一致性证据。实际浏览器截图及新增同源入口的整帧对账由主代理另行完成。本子任务没有执行硬件耗时、DMA 或真实刷屏同步验证。

## 同源预览交互修复复核

已复核主代理修正后的 `firmware.js`。此前延迟 tick 请求期间，`busy` 分支会丢掉按键，全部按钮禁用也让暂停暂时失效；当前 Promise 队列保持输入顺序，暂停在请求未完成时立即停止后续播放调度。

[延迟请求探针](evidence/layout-2026-09-07/firmware_input_queue_probe.js) 直接执行当前 `firmware.js`，保持一个播放 tick 的 fetch 响应未完成，期间连续输入 A/B/C、点击暂停，再依次释放响应。结果：

- 请求顺序严格为 `reset → tick → key 0 → key 1 → key 2`，3 个按键全部送出，最大并发请求数为 1。
- 每条请求使用上一条响应返回的 session；暂停按钮在 tick 未完成时可用，点击后文字立即变为「继续运行」（追加修复后的文案）。
- 释放最后一条响应后，播放定时器和请求超时定时器均已清除，没有追加 tick。
- 本次执行的 `firmware.js` SHA-256 为 `5f7b17c09bd87dc8c3893cd33cacb799ed90461ddab3c26b1ec1443514698546`。复现：`node reports/evidence/layout-2026-09-07/firmware_input_queue_probe.js`。

`serve.sh` 只读复核与 `bash -n` 通过：已移除 `/tmp/gen1/gen1.json` 存在性前置条件；保留的 `--src` 只是兼容参数。启动流程通过 `/api/firmware` 轮询确认就绪，检测子进程提前退出，失败时输出日志并返回非零；同时会选择可导入 `fontTools` 的 Python。此次没有启动/停止服务，也没有扩大审查范围。上述复现验证 JS 请求调度与脚本结构，不替代浏览器网络或硬件时序验证。

## 用户追加的 GSC 对战 HUD

用户明确要求恢复金银式血条与对战布局后，新增 `firmware/main/battle_hud.h/.c`，由主代理接入实际 P3 与固件同源预览。组件直接保存原品位平面 tile，经整数放大输出矩形像素，不再用换色矩形模拟血条。这部分组件开发没有修改 `play_battle.c`、`render_scene.h` 或模板，整页接入与布局由主代理完成。

素材来自本地 `pret/pokecrystal` 固定 commit `7a7881d0d62e0ddbd82dcf10e7116807487ac651`。每个 PNG 的 SHA-256 记录在 C 文件与验证脚本；固件已内嵌图元，运行与构建不依赖 `/tmp/pokecrystal`。

| 原品来源 | 共享组件中的用途 |
|---|---|
| `gfx/font/font_battle_extra.png` 前 12 tiles | `$60/$61` 为 HP 前缀；`$62…$6a` 为 0…8 个源像素的条；`$6b` 为野生端帽。 |
| `gfx/battle/enemy_hp_bar_border.png` 第 0 tile | 我方 `$6c` 阶梯端帽，保留原始逐行宽度。 |
| `gfx/frames/1.png` 全部 6 tiles | `home/text.asm::TextboxBorder` 使用的框 1，按原代码拼接四角、相同的上下横线 tile、左右竖线 tile。 |
| `gfx/battle/expbar.png` 前 7 tiles | `$55…$5b` 为右侧填充 1…7 源像素；经验条按 `PlaceExpBar` 从右向左回写，空/满与 HP 共用 `$62/$6a`。 |
| `gfx/battle/hp_bar.pal`、`exp_bar.pal` | 金色 HP 字样 `0xF6AF`、绿/黄/红、经验蓝；引用 `screen.h` 已有颜色宏。空条背景为白色，底部只有原品黑线；金色不是空条填色。 |

`_CGB_BattleColors` 通过 `LoadPalette_White_Col1_Col2_Black` 装载原品调色板，因此原背景是 `RGB(31,31,31)`，转换为 RGB565 是 `0xFFFF`。组件将背景作为显式参数，原品白色有独立常量，不强迫其他页面更改背景。

原版 HP 是 2 个标签 tile + 6 个条 tile + 1 个端帽，共 72×8。当前 240px 屏幕的我方 HUD 仅 120px 宽；采用原函数本已支持的可变条长 `d=4`，加整数 `scale=2`，得到 **112×16**，每个源像素固定占 2×2。没有继续旧 JS 的 1.5 倍缩放。接口也支持 `d=6, scale=1` 的原尺寸及其他整数长度/倍数。颜色判据始终保留原版 48px 归一化后的 `>=24` 绿、`>=10` 黄，缩短显示长度不改分色点；非零 HP 最少绘制 1 个源像素，HP=0 不显示填充。

共享接口及推荐整页坐标：

```c
battle_hud_draw_hp(rect, ctx, 8, 30, 4, 2, BATTLE_HUD_WILD,
                   wild_hp, wild_max, BATTLE_HUD_ORIGINAL_BACKGROUND);
battle_hud_draw_hp(rect, ctx, 120, 192, 4, 2, BATTLE_HUD_PET,
                   pet_hp, pet_max, BATTLE_HUD_ORIGINAL_BACKGROUND);
battle_hud_draw_exp(rect, ctx, 120, 224, 7, 2, exp, need,
                    BATTLE_HUD_ORIGINAL_BACKGROUND);
battle_hud_draw_message_box(rect, ctx, 0, 240, 15, 5, 2,
                            BATTLE_HUD_ORIGINAL_BACKGROUND);
```

消息区原品框的安全文字范围为 x12 至右缘228，三行 16px 文本放 y256 / 274 / 292。此前提议的 x8 / y248 会与真实框线相撞；y254 满宽首行也会碰右上角的最后一行，因此已明确更正。经验条完整 tile 行为 y224..239，实际蓝色在 y230..233、黑底线在 y236..237；若 HP 数字位于 y212，应先画经验条再写数字，避免经验条清背景擦除数字下端；数字移至 y208 则完整包围盒也不相交。

[原品像素差分探针](evidence/layout-2026-09-07/battle_hud_probe.py) 编译实际 `battle_hud.c`，并从固定 commit 的 PNG 独立拼接预期像素。通过 416 组 HP（1/4/6/16 条 tile、1/2/3/4 倍、两端帽、满/空/阈值/活体极小值）、1,088 组经验条、8 组消息框的逐像素比较；遍历全部 65,536 个 HP 比例验证三色判据；检查三个消息文本包围盒完全避开实际框像素，且负向对照确实发现旧建议坐标的相交。整屏一次绘制与四个 80px 横带分别裁剪重组完全相同，含故意跨 y80 的 HP。AddressSanitizer、UndefinedBehaviorSanitizer、既有 `verify_layout.py` 和 `git diff --check` 均通过。

复现：`python3 reports/evidence/layout-2026-09-07/battle_hud_probe.py`。组件像素图见 [battle-hud-gsc-tiles.png](evidence/layout-2026-09-07/battle-hud-gsc-tiles.png)：左列野生、右列我方，自上而下为 100/50/21/20/1/0 HP；下方蓝色是两种经验比例，再下方是原品消息框。这是实际 C 组件输出，不是整页浏览器或真实 LCD 截图；整页联调与浏览器读回另由主代理验证。

额外只读查看主代理实际 C 输出的 `.build/firmware-preview/gsc/{idle,electric,result}.png`：敌方状态左上、正面图右上、我方背面左下、状态右下的构图成立；HP 数字实际采用 y208，经验条 y224，完整包围盒已分离；三行消息在框内无碰线。初次 idle 图中「野生宝可梦出现了！」的「现」为空白，直接解析当时 `assets/font16.bin` 确认缺 U+73B0（881 字形）。已反馈主代理按项目正常 `fw.sh build` 的字库再生成流程补齐；此处未将旧图误判成完整字形渲染通过。
