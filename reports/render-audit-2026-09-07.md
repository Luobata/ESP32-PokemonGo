# Web / ESP32 渲染一致性审计

审计日期：2026-09-07。基线为 `8e94a743b0560ec808f10cce90fb3815fdd08965` 的现有实现；本文记录本轮修复前的发现。主任务正在并行修改 inspector / host 渲染路径，本文不是那些后续改动的验收结果。本次没有修改业务文件、`.gsb-local` 或 `docs/00-handoff.md`，没有启动浏览器、烧写或操作硬件。

**结论：共享 C 配方的方向合理，局部已工作；正式预览尚不能实现整页 1:1。** 当前成功迁移的是 P3 主宠 HP 的求值与矩形消费，以及主宠名牌的文案/测宽/位置求值。主宠 back sprite 只接了固件。其余页面仍各有 C / JS 布局和绘制逻辑。已有绿灯主要证明状态数据、部分坐标、资产字节正确，不能证明浏览器实际画对了，更不能证明设备时序。

## 当前真实调用链

| 层 | 实际实现 | 同源程度 |
|---|---|---|
| 数据 / 素材 | 固件 `CMakeLists.txt:42` 嵌入仓库 `assets/`；web `build.py:1237` 默认读 `/tmp/_inspect_assets`，可显式传 `--assets` | 可使用同一资产，但默认根目录不同，不能只凭注释认定一致 |
| 演示状态 | `build.py:1079` 构建两个固定战斗剧本，`verify_sim_pages.py:100` 对账 sim 重算 | 固定状态有数据证据；不是任意输入运行同一游戏状态机 |
| HP 配方 | `render_scene.h:55` → 固件 `render_scene_screen.h:32`；构建期 `scene_cli.c:87/96` → `sceneP3PetHp` → `scenePetHp()` | 正式 base 路径两端求值同源；只覆盖已导出剧本回合 |
| 主宠名牌 | `render_scene.h:29` / `render.h:38` → 固件文本回调；CLI `scene_cli.c:72` → `scenePetName()` | 文案、回退与位置同源，字形光栅化仍不同 |
| 主宠 back | `render_scene.h:74` 解码 / 缩放 / 透明色 → 固件 `play_battle.c:226` | web 仍 `spr(25,'back',8+pdx,140,3)`，CLI 无 back 导出分支 |
| 其余元素 / 页面 | `play_*.c` 对应 `template.html` 的 `R1/R3/R6/PAGES` 等 | 布局、文案、primitive、动画时序大多双写 |
| 推屏 | `screen.c:38` 240×80 缓冲，`:115` 字节交换 / DMA 同步；web 一次整屏 Canvas | 后端职责分离合理，Canvas 无法证明 DMA / 横带时序 |

`docs/11-render-engine.md` 开头是 D64 历史状态，不能把它当当前实现总表。文档后部已经记录 D78 sprite、D85/D90/D92 文本进展；真实代码也已比“只实现一根 HP 条”更前进。但“固件已有配方”不等于“正式 web 接上了配方”，也不等于“整页已经由配方生成”。

目前 `scenePetHp()` / `scenePetName()` 的正式调用仅在 `R3.base`。G 方向由 `PAGES.P3.render()` 调用独立的 `p3G()`；A/B/C 与 alternate 也是各自实现。G 不能继承 base 的配方验收结论。

## 已确认的问题

### 1. 标为真机的 base 已经不是固件当前画面

`template.html:3539` 的 `DIRS.base` 使用旧 DEVG 绿底 / 绿字，默认 `DIR='base'`（`:3605`）。固件 `screen.h:52-60` 已使用金银配色：底 `0xFFF0`、主字 `0x0000`、次字 `0x7240` 等。共享 HP / 名牌又独立使用新颜色，base 实际混用了两套配色。

`template.html:4868` 仍注释“base 方向……与固件逐像素一致”，`DIRS.G.note` 也称 base 才与固件一致；这些声明与代码不符。G 的版式确实是设计稿，但 base 也不能继续当作已验收真机参照。

优先修法：从 `screen.h` 导出固件 palette，正式硬件预览用这份数据；其它设计方向保留清楚的设计稿含义。色表不要再手抄一份。

### 2. P3 受击抖动的正式消费读错字段，现状恒为 0

`build.py:1131` 用 `dataclasses.asdict()` 导出 `offset_x`；`template.html:3697-3702` 的 `p3Shake()` 读取 `s.ox`。本次提取真实 `p3Shake()`，交给 Node 执行，使用当前 `index.html` 内嵌 payload：

```text
payload offset_x = [6, -6, 6, -6, 6, -6]
p3Shake(pet hit, ph=0..5)  = 六次 [0, 0]
p3Shake(wild hit, ph=0..5) = 六次 [0, 0]
```

即使改对字段，仍不能称动画 1:1：固件 `play_battle.c:104-105` 是 4 帧、3px，`:299` 之后使用 60ms tick 与约 600ms 回合；web 使用 6 帧、6px 的 sim 序列与 `MOVE_FX.dur` 的 100ms 播放。它们需要共同的状态/时间快照，或者明确以哪种模式展示。

优先修法：修消费字段，并为实际消费函数补小范围行为验证；生产预览最终直接消费 C 的帧输出即可消除这处双写。

### 3. 字宽规则与字形后端仍会漂移

固件 `render.h:38` 判 `cp < 0x80` 为半宽；web `text()` / `textW()` / `hintAt()`（`template.html:3478/3496/3644`）判 `charCodeAt(0) > 0xFF` 才为全宽，因此 Latin-1 区间不一致。Node 执行当前 `textW()`，C 编译真实 `render_text_width_sized()` 的结果：

| 文本 | web 宽度 | 固件宽度 |
|---|---:|---:|
| 高级球 ×99 | 80 | 88 |
| ÷ / ° / é（逐字） | 8 | 16 |
| 三合一磁怪 Lv100 | 128 | 128 |

不是纯假设输入：`play_capture.c:195` 实际绘制 `%s ×%u`。

字体资产同源也不等于字形像素同源。固件 `render.c:114-146` 逐位写 1bpp；web `make_font.py:87` 将位图转换为 TTF，再由浏览器光栅化。`build.py:1290` 缺 fontTools 时允许退回宿主字体，`template.html:3487` 在字体未加载或缺字时也退回宿主字体，而固件缺字会跳过墨迹。现有门禁并不检查这个差异。

优先修法：正式预览复用 C 的位图输出；至少先统一 ASCII 判据、禁用正式一致性模式的宿主字体静默回退，并实测 Canvas readback。名牌“文本 + 坐标”配方不能单独替代字体像素验收。

### 4. 相同坐标下，HP 原语仍不是相同像素

固件 `play_battle.c:116` 的野怪 `draw_bar()` 只绘制 `w×h`，整数 `w*cur/max`，填充被边框覆盖后相当于 `filled-1`。web `template.html:3522` 的 `bar()` 使用 `strokeRect(x+.5,y+.5,w,h)`，再按 `round((w-2)*pct)` 填充。名义宽高相同，stroke 右/下边仍多占一个像素，比例量化也不是同一公式；web 野怪条颜色取 `t.dim`，固件按三段 HP 色值。

本次真实 JS 原语调用记录（50%、112×10）为：

```text
strokeRect(120.5, 28.5, 112, 10)
fillRect(121, 29, 110, 8)  // track
fillRect(121, 29, 55, 8)   // fill
```

此处是源码及命令消费证据；本轮没有启动 Canvas，不将它包装成浏览器像素测试。

优先修法：让野怪 HP 也复用 C 配方，或直接复用整个 `draw_band()`。仅把 x/y/w/h 抽到同一张表不能解决原语语义差异。

### 5. RGB565 展开有三种口径，PNG 不能逐值对齐

`template.html:3781` 的 `rgb565hex()` 用比例向下取整，`build.py:189` 的资产 palette 只左移补零，`tools/device/screenshot.py:54` 则位复制补低位：

| RGB565 | 共享配方 Canvas 色 | 设备截图色 | 资产 palette 色 |
|---|---|---|---|
| 0xFFF0 | #ffff83 | #ffff84 | #f8fc80 |
| 0x7240 | #734800 | #734900 | #704800 |
| 0xF6AF | #f6d67b | #f7d77b | #f0d478 |
| 0x247F | #208dff | #218eff | #208cf8 |

差异不代表 RGB565 逻辑帧一定错误，但会直接破坏 PNG / Canvas RGB888 逐值对账。应统一扩展函数，以同一 RGB565 逻辑帧为主证据，再比较统一扩展后的 RGBA。

### 6. 调试覆盖层和演示状态没有隔离出正式帧

`template.html:4863` 无条件在 240×320 离屏 Canvas 调用 `bands()`，半透明红虚线直接进入被显示/截图的帧。它不是固件内容。应把辅助线放到独立显示覆盖层，或在像素验收模式下关闭。

P2 进入 P3（`:4700` 附近）只按所选条目的 level 选择 win/lose 剧本，没有把选中物种和完整状态交给 C。它证明固定剧本可重放，不能证明任意页面操作都与硬件状态同构。固定快照预览可以满足布局检查；任意交互需要同一 C 执行入口（host 服务、WASM 或设备状态/帧输出）。

## 门禁复跑与反向验证

| 验证 | 本轮结果 | 能证明的范围 |
|---|---|---|
| `verify_sim_pages.py` | exit 0；两剧本 17 回合等数据一致 | payload 与 sim 重算 / payload 新鲜度 |
| `verify_web_coords.py` | exit 0；15 元素、17 项比较，5 项跳过、13 条固件独有声明 | 部分静态坐标与源码 marker |
| `verify_layout.py` | exit 0；0 确定违规，5 项 SKIP | 部分固件元素不跨带；不是整页 overlap / alignment 验证 |
| `verify_ui.py` | exit 0；8 条点阵全等，oak 专项通过 | ui.bin 资产格式 / 点阵；不是页面落图 |
| `gen_layout_budget.py --check` | exit 0 | 生成预算头与 VAR_ELEMENTS 一致 |
| D64 持久探针 | 125 组、9,600,000 RGB565 像素一致；x+1 反例被发现 | 当前主宠 HP 配方、实际横带 adapter 与独立 JS RGB565 矩形后端 |

本次额外反向验证只改了 `/tmp` 副本：保留当前 payload、函数定义与调用，删除 `scenePetHp()` 中真正画条的 `sceneRects(fr.rects)`。结果：

```text
verify_sim_pages(copy.index.html) -> exit 0
verify_web_coords(WEB=copy.template.html) -> exit 0
```

因此“共享配方 marker 存在 → 自动跳过”的判据不能保证实际消费有效。空白 HP 条也能通过。这不是否定数据/坐标门禁，而是明确它们不能替代消费端验证。

`verify_sim_pages.py:273-305` 的“新鲜度”仅比较 `simPages` JSON，没有比较模板、字库、整套素材或实际 Canvas。审计时 `/tmp/_inspect_assets` 中的三个 gen1 主资产恰好与仓库 hash 一致，但 cached palettes/font/ui 并不存在；当前 index 包含 palette 和 881 字形，说明当前产物不等于默认构建路径的保证。统一默认素材根并对产物记录源码 / 资产 hash，可以避免下一次重建退回旧资产或无调色板 fallback。

本轮临时证据：

```text
/tmp/pokemon-render-audit-20260907/d64.py
/tmp/pokemon-render-audit-20260907/d64/result.json
/tmp/pokemon-render-audit-20260907/consumer_probe.py
/tmp/pokemon-render-audit-20260907/consumer-result.json
/tmp/pokemon-render-audit-20260907/negative_sim_pages.log
/tmp/pokemon-render-audit-20260907/negative_web_coords.log
```

D64 探针已持久保存在 `docs/11-render-engine.md` 的 `D64_PROBE_BEGIN` 区块，本次原样恢复执行，只更改临时输出目录。consumer probe 提取真实 HTML 函数并用 Node 运行，C 部分直接 include 当前 `render.h`；没有重写受测逻辑，没有模拟浏览器 Canvas。

## 最优先的落地顺序

1. **建立正式硬件预览入口，直接执行相同 C 页面渲染和相同 assets。** 当前 host 工具链已能编译 C 配方，扩大到现有 `play_*.c` / `render.c`，用最小平台 adapter 将四个横带拼成 RGB565 帧，比继续搬一张 JS 布局表更接近用户所需的整页同构。设计方向可继续单独保留。
2. **修 P3 和公共原语实错，验收消费端。** 基线配色、shake 字段、Latin-1、HP 框边界、RGB888 展开、辅助线均有明确落点。名牌长输入、回合消息、两侧 HP 与 sprite 边界至少各留一个同状态快照。
3. **先证明同状态整页帧，再扩大技能效果。** host 原生四带帧 vs 正式预览消费 readback，报告首差异坐标/颜色；有意移 1px、漏一条命令、改一种色值应变红。独立的字体和资产基准用于防止“同一条错误链路自比”。
4. **设备链路单独验收。** `screen_dump()` 输出交换后的发送字节且会重新绘制全页（`screen.c:130/186`），可以查传输字节序，不能证明真实 LCD 颜色，也可能掩盖平时只重画一半带的时序问题。动画应另测脏带调度 / 真机连续帧。当前共享配方保留单条 37.5KB 横带缓冲是合理边界，不应为预览引入固件整屏缓存。

验收口径应分别写为“固定快照逻辑 RGB565 一致”“正式 Canvas readback 一致”“设备实际显示/刷新已验证”。只完成其中一项时，不再使用“整个预览与硬件逐像素一致”的笼统声明。

## 审计后已实施的工具修复

按主任务新分工，本角色随后只修改 `tools/inspector/build.py` 与 `tools/pipeline/verify_sim_pages.py`；页面、固件布局和 native 预览由其它角色负责。

- 默认构建输入改为固件的 `assets/`，检查全部 7 个嵌入资产；`--assets` 仍可指定相同内容副本，内容不同会明确拒绝，避免主 sprite 与 sim / UI / font 混用两套资产。不再从临时缓存隐式生成缺失素材。
- 缺 palette / font / UI / sprite 或 fontTools 时失败，不输出静默回退的正式产物；校验 palette 长度/索引、UI 必需条目与位图区。
- `load_data()` 保留完整 uint8 palette 索引；`load_palettes()` 统一使用 `rgb565_hex()` 位复制展开，并校验两份物种索引一致。
- 新增 `buildManifest`，包含模板、资产、sim、pipeline、固件/host 等生成输入的内容 hash，以及全量 payload / 字体 CSS hash。构建前后检测到输入变化会拒绝输出。CLI 临时路径按进程隔离，允许构建与门禁并行。
- 新鲜度检查读取真实 JSON，剥离构建期 JSON / 字体注入区后，将 HTML 正文逐字比回当前模板；因此“payload 没变，实际绘制代码被删”也会报红。此检查证明产物未过期/被改写，仍不代替 Canvas 像素验收。

验证结果：冻结本轮源码到 `/tmp/pokemon-render-audit-20260907/frozen` 后，完整构建与新 `verify_sim_pages.py` 均 exit 0。使用副本修改模板、front 资产 1bit、sim 生成输入、产物 `draw()`、字体 CSS、全量 payload，六类负向变更全部被发现。分别移走 palettes/font/UI 时均拒绝；索引 17 在 gen1/palette 两个 loader 中完整保留；65536 个 RGB565 值与 `screenshot.py` 真实 helper 比较，零差异。

PATH 的 `python3` 实为 pyenv 3.12，缺 fontTools；本次已证实新构建明确失败。`/usr/bin/python3` 具有 fontTools 4.60.2，无需安装依赖。建议使用：

```sh
/usr/bin/python3 tools/inspector/build.py
/usr/bin/python3 tools/pipeline/verify_sim_pages.py
```

其它角色仍在并行编辑时，manifest 会按设计报告过期。最终 `index.html` 应在所有生成输入稳定后统一重建；本角色未覆盖工作区的默认 `index.html`。

完整专项结果在 `/tmp/pokemon-render-audit-20260907/build-input-results.json`，执行脚本为同目录的 `verify_build_inputs.py`。其中最关键的模板/资产负向验证可在当前仓库复现（先运行上面两条构建/验证命令）：

```sh
/usr/bin/python3 - <<'PY'
from pathlib import Path
import shutil, sys, tempfile
root = Path.cwd()
sys.path[:0] = [str(root/'tools/inspector'), str(root/'tools/pipeline')]
import build as B
import verify_sim_pages as V
html = (root/'tools/inspector/index.html').read_text()
payload = V.check_build_manifest(html, B)
assert not V.FAILS, V.FAILS
with tempfile.TemporaryDirectory() as directory:
    copy = Path(directory)
    for relative in payload['buildManifest']['inputs']:
        target = copy/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root/relative, target)
    for relative in ('tools/inspector/template.html', 'assets/gen1_front.bin'):
        target = copy/relative
        original = target.read_bytes()
        target.write_bytes(original[:-1] + bytes([original[-1] ^ 1]))
        V.FAILS.clear()
        V.check_build_manifest(html, B, copy)
        assert any(relative in failure for failure in V.FAILS), V.FAILS
        print('detected:', relative)
        target.write_bytes(original)
PY
```
