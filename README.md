# ESP32-PokemonGo

在一台**没有 GPS**的 ESP32-C3 掌机上实现「现实世界探索 + 初代宝可梦收集 + 电子宠物养成」。

用 WiFi/BLE/声学的**环境指纹**代替 GPS 定位。设备揣在兜里后台低频扫描、静默累积事件；
玩家偶尔掏出来，30 秒内处理完一批。形态上接近 Tamagotchi 与宝可梦步行者，而不是掌机。

> **项目范围：自用、不分发。** CC 系列许可与 GPL 的义务触发条件都是「分发」，
> 私人使用不触发，因此素材可按实用性而非许可宽松度来挑。相关约束见
> [docs/05-art-audio.md](docs/05-art-audio.md#54-如果将来想分发)。

## 当前状态

**PC 侧基本完成，固件阻塞于硬件。**

| 项 | 状态 |
|---|---|
| **三态判别** | ✅ 真实数据验证成立 —— 家 0% 移动 / 通勤 52% / 办公 5%，家与公司指纹相似度 **0.0000** |
| **感知层算法** | ✅ 四轮实测修正（每轮都是真数据推翻纸上设计） |
| **10 个系统** | ✅ 9 个已实现（S7 只有条件判定） |
| **素材管线** | ✅ 151 只 + 彩色配色 + 中文名 + 点阵字库 = 144.9 KB |
| **验收平台** | ✅ 六个调试面板 |
| 固件 | ⛔ 硬件未到 |

仍需实测的：**续航天数、RTC 走时精度、口袋 RSSI 基线、flash 磨损**。
详见 [07-roadmap.md](docs/07-roadmap.md)。

## 硬件

`ESP32-C3FH8X` · 240×320 TFT · 3 键 · WiFi/BLE · 被动 NFC · 麦克风 + 扬声器 · 500mAh · 60×95×8.5mm / 50g

型号可直接读出两个事实：**FH8 = 8MB 片内 flash**，**X = 单核 RISC-V**。
C3 不支持外接 PSRAM，因此约 400KB SRAM 就是全部内存 —— 240×320×16bit 的全屏帧缓冲
需 150KB，占 SRAM 三分之一以上，**必须分块渲染**。

官方器件清单穷举了全部硬件，其中**不含任何传感器**：**确认无 IMU，步数统计不可实现**。

## 快速开始

```bash
# 1. 采集真实 WiFi 环境（macOS，需定位授权，见下方说明）
tools/collector/build.sh && tools/collector/make-app.sh
tools/collector/collect.sh -i 30 -o data/raw/$(date +%Y%m%d).ndjson

# 2. 用采集数据回放感知层算法
python3 sim/replay.py data/raw/20260902.ndjson

# 3. 跑玩法原型（养成状态机 + 遭遇判定）
python3 sim/prototype.py data/raw/20260902.ndjson --days 7
```

Python 部分**零第三方依赖**，用系统 python3 即可（已在 3.9 上验证）。

### macOS 定位授权（重要）

macOS 12+ 对 BSSID 做了权限门禁：**没有定位授权时 `bssid` 和 `ssid` 全返回 nil**，
只剩 RSSI 和 channel。而指纹方案的核心正是 BSSID。

**已实测通过的唯一路径是「打包成 .app + 用 `open` 启动」**，也就是 `collect.sh` 做的事。
以下都试过且无效：给 iTerm 授权（列表里根本没有它）、`sudo`（root 不等于有 TCC 授权）、
直接 exec .app 里的二进制（系统认的是调用方 shell）。
完整对照表见 [tools/collector/README.md](tools/collector/README.md#定位授权)。

采集器支持**降级模式**：无授权时用 `channel + RSSI 分桶`合成伪 BSSID，
可以先把管线跑通、验证算法逻辑，但**指纹判别质量会明显下降**，不能用于最终标定。
不过 channel 与 RSSI 不受权限限制，所以「这里能扫到几个 2.4GHz AP」这个数即使降级也准。

## 文档

| 文档 | 内容 |
|---|---|
| [01-constitution.md](docs/01-constitution.md) | 设计宪法 —— 硬约束清单与由此推导的核心形态。**先读这个** |
| [02-sensing.md](docs/02-sensing.md) | 感知层 —— 环境指纹、降级阶梯、匹配算法、无连接对时 |
| [03-spawning.md](docs/03-spawning.md) | 地点属性与刷新机制 —— OUI 语义、biome、一致性规则 |
| [04-gameplay.md](docs/04-gameplay.md) | 玩法 —— 遇敌/捕获/培育/交换/图鉴，含电子宠物养成 |
| [05-art-audio.md](docs/05-art-audio.md) | 美术与音频 —— GB 像素风、chiptune、素材来源 |
| [06-engineering.md](docs/06-engineering.md) | 工程 —— 仿真器、内容管线、存档、调度 |
| [07-roadmap.md](docs/07-roadmap.md) | 推进节奏 —— 当前可做什么、Phase 0 要测什么 |
| **[08-systems.md](docs/08-systems.md)** | **系统索引** —— 10 个系统 + 7 个页面的导航与状态。各系统详见 `docs/systems/` |

## 目录结构

```
docs/                 设计文档
tools/pipeline/       素材管线：初代 151 只数据+sprite→二进制、flash 预算
tools/collector/      macOS WiFi 采集器（Swift + CoreWLAN）
  collect.sh          采集入口 —— 必须用这个启动（见定位授权）
sim/                  PC 端仿真与系统实现
  sensing.py          感知层：滑动窗口指纹、AP 新鲜度、8槽 LRU、移动量
  gameplay.py         S4 养成、S7 进化条件、biome 分类、确定性刷新
  systems.py          S1 遭遇累积、S2 捕获判定、S3 自动战斗、S8 闪光
  state.py            S5 图鉴、S6 存档（双 buffer+CRC）、S9 道具、S10 成绩
  effects.py          动效：缩放/闪白/抖动/进化/呼吸（零素材成本）
  replay.py           回放采集数据，输出感知层判定
  prototype.py        玩法原型，输出模拟游玩日志
  preview_effects.py  逐帧 ASCII 目检动效
assets/               素材产物 + 眼部标注归档
data/raw/             采集的原始数据（.gitignore，不入库）
firmware/             ESP32 固件（硬件到手后）
```

## 设计要点速览

**WiFi 是上下文开关，不是内容生产者。** 初版把探索值挂在「新见 BSSID 数」上是错的
—— 它会衰减到零：第一周发现完所有东西，第五周设备变砖。真实情况是**空间稀缺、时间充裕**
（三个地点 × 24 小时 × 7 天），所以让**时间生产内容，空间调制内容**。

**猎场与基地。** 通勤时会短暂经过大量 AP，每个只出现一次然后消失 —— 这对定位是噪声，
但对「遭遇」是完美映射：**一个转瞬即逝的 AP 天然就是一只出现又跑掉的野生怪**。
移动中 = 猎场（遭遇密集、窗口窄），驻留 = 基地（适合照料孵化）。只需三个地点就成立。

**移动量而非步数。** 无 IMU 所以步数做不了，改用相邻扫描的加权 Jaccard 距离累积。
这不是退而求其次：步数奖励原地踏步也能刷的动作，移动量奖励**空间位移**，
而且**摇不出来** —— 计步器能绑电风扇上，但没人能在家里摇出一片新的射频环境。

**不做惩罚性死亡。** 原版 Tamagotchi 的宠物会饿死，那是 1996 年的设计语境。
在一个「揣兜里跑一周」的设备上，一次出差清零进度只会让人把它扔进抽屉。
改为状态低下时进入消沉，**能力打折但不清零** —— 惩罚体验密度，不惩罚存档。
