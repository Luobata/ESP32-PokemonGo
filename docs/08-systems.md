# 系统清单

本项目的全部系统与页面索引。每个系统单独一份文档，本页只做导航与状态。

> **命名约定**：`S*` 是系统（逻辑），`P*` 是页面（UI）。
> 依赖 Phase 0 实测数据的项标注 ⏳ —— 那些数值目前都是估算。

## 玩法系统

| # | 系统 | 状态 | 依赖实测 | 文档 |
|---|---|---|---|---|
| S1 | 遭遇累积 | **✅ 已实现** | ⏳ 遭遇频率 | [S1-encounter.md](systems/S1-encounter.md) |
| S2 | 捕获判定 | **✅ 已实现** | — | [S2-capture.md](systems/S2-capture.md) |
| S3 | 自动战斗 | **✅ 已实现** | — | [S3-battle.md](systems/S3-battle.md) |
| S4 | 养成状态机 | **✅ 已实现** | ⏳ RTC 精度 | [S4-nurture.md](systems/S4-nurture.md) |
| S5 | 图鉴 | **✅ 已实现** | — | [S5-dex.md](systems/S5-dex.md) |
| S6 | 存档 | **✅ 已实现** | — | [S6-save.md](systems/S6-save.md) |
| S7 | 进化 | **✅ 已实现** | — | [S7-evolution.md](systems/S7-evolution.md) |
| S8 | 闪光 | **✅ 已实现** | — | [S8-shiny.md](systems/S8-shiny.md) |
| S9 | 道具 | **✅ 已实现** | — | [S9-items.md](systems/S9-items.md) |
| S10 | 成绩与排行 | **✅ 已实现** | — | [S10-records.md](systems/S10-records.md) |
| S11 | 开场流程 | **✅ 已实现** | — | [S11-intro.md](systems/S11-intro.md) |
| S12 | 昵称 | **✅ 已实现** | — | [S12-naming.md](systems/S12-naming.md) |
| S13 | 音频 | **✅ 已实现** | ⏳ 音频通路 / 续航 | [S13-audio.md](systems/S13-audio.md) |
| S14 | 队伍与仓库 | **✅ 已实现** | — | [S14-party.md](systems/S14-party.md) |
| S15 | 转场动画 | **✅ 已实现** | — | [S15-transitions.md](systems/S15-transitions.md) |
| S16 | 开场剧情 | **✅ 已实现** | — | [S16-opening.md](systems/S16-opening.md) |
| S17 | 道馆与四天王 | **✅ 已实现** | — | [S17-gyms.md](systems/S17-gyms.md) |
| S18 | 自动存档 | **✅ 已实现** | — | [S18-autosave.md](systems/S18-autosave.md) |
| S19 | 全流程编排 | **✅ 已实现** | — | [S19-orchestration.md](systems/S19-orchestration.md) |

实现分布在三个模块：

| 模块 | 系统 | 说明 |
|---|---|---|
| [`sim/systems.py`](../sim/systems.py) | S1 S2 S3 S8 | 共享遭遇队列，S1 生产、S2/S3 消费 |
| [`sim/state.py`](../sim/state.py) | S5 S6 S9 S10 | 状态容器，S6 存档序列化其余三个 |
| [`sim/gameplay.py`](../sim/gameplay.py) | S4 | `PetState` 三条状态轴 |
| [`sim/systems.py`](../sim/systems.py) | S7 | `check_evolution()` / `do_evolve()` |
| [`sim/intro.py`](../sim/intro.py) | S11 | GB 启动动画 + 伙伴选择 |
| [`sim/naming.py`](../sim/naming.py) | S12 | 预设昵称 + `NamePicker` |
| [`sim/strings.py`](../sim/strings.py) | 全部 | UI 文案单一来源 + 排版审计 |
| [`sim/audio.py`](../sim/audio.py) | S13 | 四通道 APU + 11 条音效 |
| [`sim/party.py`](../sim/party.py) | S14 | 队伍 6 + 仓库 30 |
| [`sim/transitions.py`](../sim/transitions.py) | S15 | 闪光星环 / 转场 / 进化闪烁 |
| [`sim/opening.py`](../sim/opening.py) | S16 | 大木博士台词 |
| [`sim/gyms.py`](../sim/gyms.py) | S17 | 八馆 + 四天王 + 赤红 |
| [`sim/autosave.py`](../sim/autosave.py) | S18 | 分级自动存档 |
| [`sim/orchestrate.py`](../sim/orchestrate.py) | S19 | **唯一让 19 个系统同时工作的入口** |

## UI 页面

| # | 页面 | 三键分配 | 文档 |
|---|---|---|---|
| P1 | 待机（主界面） | A 照料 / B 图鉴 / C 遭遇 | [P1-idle.md](pages/P1-idle.md) |
| P2 | 遭遇列表 | A 选中 / B 返回 / C 丢弃 | [P2-encounter-list.md](pages/P2-encounter-list.md) |
| P3 | 遭遇详情 / 战斗 | A 捕获 / B 战斗 / C 逃跑 | [P3-battle.md](pages/P3-battle.md) |
| P4 | 捕获 | A 投球 / B 换球 / C 取消 | [P4-capture.md](pages/P4-capture.md) |
| P5 | 照料 | A 执行 / B 切换 / C 返回 | [P5-care.md](pages/P5-care.md) |
| P6 | 图鉴 | A 详情 / B 翻页 / C 返回 | [P6-dex.md](pages/P6-dex.md) |
| P7 | 成绩 | A 切榜 / B 翻页 / C 返回 | [P7-records.md](pages/P7-records.md) |
| P8 | 取名 | A 确认 / B 下个 / C 上个 | [P8-naming.md](pages/P8-naming.md) |

> 页面文档由 [`tools/pipeline/gen_pages.py`](../tools/pipeline/gen_pages.py)
> 从 [`sim/strings.py`](../sim/strings.py) 生成 —— 文案有**单一来源**，
> 索引见 [pages/README.md](pages/README.md)。

> **P7 的进入路径**：P1 的三个键已占满（A 照料 / B 图鉴 / C 遭遇），
> 所以成绩页挂在图鉴之后 —— `P1 ──B──→ P6 图鉴 ──B(末页)──→ P7 成绩`。
> 图鉴与成绩都属「回看类」，玩家心智模型接近，且都不是高频操作。

## 已实现的底层模块

这些不是"系统"，是系统建立在上面的地基：

| 模块 | 文件 | 提供什么 |
|---|---|---|
| 感知层 | [`sim/sensing.py`](../sim/sensing.py) | `SensingResult`（状态/移动量/瞬现 AP/地点） |
| 刷新与语义 | [`sim/gameplay.py`](../sim/gameplay.py) | `roll_encounter()` 确定性刷新、biome 分类、OUI/SSID 语义 |
| 动效 | [`sim/effects.py`](../sim/effects.py) | 缩放/闪白/抖动/进化闪烁/呼吸，全部零素材成本 |
| 素材管线 | [`tools/pipeline/`](../tools/pipeline/) | 151 只数据 + front/back sprite → 固件二进制 |
| 验收 | [`tools/inspector/`](../tools/inspector/) | 浏览器里目检 sprite 与动效 |

## 不做的（明确排除）

记在这里，避免反复讨论：

| 项 | 理由 |
|---|---|
| 招式表 / PP / 状态异常 | 战斗定为自动结算，不需要 |
| 六只队伍轮换 | 三键切换成本高，且情感投射需要唯一主宠 |
| 对战 / 交换 | 单机自用场景没有对象。BLE 协议已延后 |
| 眨眼动效 | 已评估放弃 —— back sprite 151 只里只有 1 只可见眼部，且那只的实现是空操作。详见 [`sim/effects.py`](../sim/effects.py) 的说明 |
| 步数统计 | 无 IMU，硬件层面不可能 |
| 惩罚性死亡 | 状态低下只进入消沉、能力打折，绝不清零存档 |

## 存储预算

| 项 | 大小 | 来源 |
|---|---|---|
| 主宠状态 | 9 B | S4 |
| 图鉴位图（已见/已捕/闪光已见/闪光已捕） | 76 B | S5 + S8 |
| 道具 | 4 B | S9 |
| 成绩与纪录 | 136 B | S10 |
| 地点表（RTC RAM 镜像） | 512 B | 感知层 |
| 遭遇队列 | 128 B | S1 |
| biome 驻留累计（5 × u32） | 20 B | 感知层 → S7 |
| 头部（魔数/版本/CRC） | 10 B | S6 |
| **合计** | **897 B**（实测） | |

**实测 897 字节**，与设计估值 891 只差 6 —— 差异来自成绩块（136 vs 估 132）
与日索引字段。双 buffer = **1.75 KB**，远小于 flash 页。

**养成数据与成绩是唯一不可再生的**，CRC 必须有。已验证主槽损坏能正确
回退到备份槽（[`sim/state.py`](../sim/state.py) 的 `DualBufferSave`）。

### 三个已决的取舍

| 问题 | 决定 | 理由 |
|---|---|---|
| 闪光要不要「已见」位图 | **要**（+19 B） | S8 的「捕获失败逃跑留下遗憾感」需要它，否则那句设计描述存不下。19 字节买一个完整维度，与 S8 自己的判断一致 |
| biome 驻留怎么算 | **独立累计器**（+20 B） | 遍历地点表求和会被 LRU 吞掉 —— 攒三周的办公区驻留，出差回来槽位被挤掉就归零，违反「不做惩罚性死亡」的精神 |
| 主宠昵称怎么存 | **待字库定稿**（阶段 D） | 「小家伙」UTF-8 是 9 字节，超出原估的 8 字节。改存字库索引（4 字 = 8 B）更省，但依赖字库子集先定 |

素材侧（不进存档，只读）：

| 项 | 大小 |
|---|---|
| 怪物数据 151 × 28 B + 名字池 | 5.2 KB |
| front sprite（三档原生尺寸） | 88.2 KB |
| back sprite（151 × 32×32） | 37.8 KB |
| 调色板（10 普通 + 10 闪光 + 索引） | 0.32 KB |
| **合计** | **131.5 KB**，占 8MB 的 1.6% |

## 系统依赖图

```
感知层 SensingResult
   │
   ├─→ S1 遭遇累积 ──→ S2 捕获 ──→ S5 图鉴 ──→ S10 成绩
   │        │             │           │
   │        └─→ S3 战斗 ──┘           └─→ S8 闪光（捕获时判定）
   │
   └─→ S4 养成 ──→ S7 进化
            │
            └─→ S2（心情影响捕获窗口）

S9 道具 ←── S1（遭遇掉落）
   └──→ S2（球种）、S4（喂食）

S6 存档 ←── 全部系统
```

关键的双向咬合：**S4 养成 → S2 捕获**（心情影响判定窗口），
这是「养成反哺探索」的落点，见 [04-gameplay.md#433](04-gameplay.md#433-养成如何反哺探索)。

## 实现顺序

| 阶段 | 内容 | 需要硬件 |
|---|---|---|
| A | S1/S2/S3 在 `sim/` 里实现并调参 | 否 |
| B | S8 闪光、S9 道具、S10 成绩 | 否 |
| C | 验收页面加 UI 原型预览 | 否 |
| D | 中文点阵字体子集化（209 字，16×16） | 否 |
| E | S6 存档、S4 时间基准 | **是**（RTC 实测） |
| F | 固件渲染层、分块横带、三键输入 | **是** |

**最小可玩闭环**：P1 待机 + S4 养成。它独立于感知层与捕获战斗，
且已经是完整体验 —— Tamagotchi 的空间输入是零，照样能撑几个月。
