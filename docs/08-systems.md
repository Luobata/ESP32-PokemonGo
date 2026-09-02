# 系统清单

本项目的全部系统与页面索引。每个系统单独一份文档，本页只做导航与状态。

> **命名约定**：`S*` 是系统（逻辑），`P*` 是页面（UI）。
> 依赖 Phase 0 实测数据的项标注 ⏳ —— 那些数值目前都是估算。

## 玩法系统

| # | 系统 | 状态 | 依赖实测 | 文档 |
|---|---|---|---|---|
| S1 | 遭遇累积 | 设计完成 | ⏳ 遭遇频率 | [S1-encounter.md](systems/S1-encounter.md) |
| S2 | 捕获判定 | 设计完成 | — | [S2-capture.md](systems/S2-capture.md) |
| S3 | 自动战斗 | 设计完成 | — | [S3-battle.md](systems/S3-battle.md) |
| S4 | 养成状态机 | 部分实现 | ⏳ RTC 精度 | [S4-nurture.md](systems/S4-nurture.md) |
| S5 | 图鉴 | 设计完成 | — | [S5-dex.md](systems/S5-dex.md) |
| S6 | 存档 | 设计完成 | ⏳ flash 磨损 | [S6-save.md](systems/S6-save.md) |
| S7 | 进化 | 设计完成 | — | [S7-evolution.md](systems/S7-evolution.md) |
| S8 | 闪光 | 设计完成 | — | [S8-shiny.md](systems/S8-shiny.md) |
| S9 | 道具 | 设计完成 | — | [S9-items.md](systems/S9-items.md) |
| S10 | 成绩与排行 | 设计完成 | — | [S10-records.md](systems/S10-records.md) |

## UI 页面

| # | 页面 | 三键分配 | 文档 |
|---|---|---|---|
| P1 | 待机（主界面） | A 照料 / B 图鉴 / C 遭遇 | [P1-idle.md](pages/P1-idle.md) |
| P2 | 遭遇列表 | A 选中 / B 返回 / C 丢弃 | [P2-encounter-list.md](pages/P2-encounter-list.md) |
| P3 | 遭遇详情 / 战斗 | A 捕获 / B 战斗 / C 逃跑 | [P3-battle.md](pages/P3-battle.md) |
| P4 | 捕获 | A 投球 / B 换球 / C 取消 | [P4-capture.md](pages/P4-capture.md) |
| P5 | 照料 | A 执行 / B 切换 / C 返回 | [P5-care.md](pages/P5-care.md) |
| P6 | 图鉴 | A 详情 / B 翻页 / C 返回 | [P6-dex.md](pages/P6-dex.md) |
| P7 | 成绩 | A 切换榜单 / B 翻页 / C 返回 | [P7-records.md](pages/P7-records.md) |

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
