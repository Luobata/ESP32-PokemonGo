# 设备调试

目标机 **FoloToy AI Passport**（ESP32-C3，<https://github.com/FoloToy/ai-passport>）。
这份文档记录怎么连上它、怎么看它在说什么、怎么把我们的玩法刷进去。

## 一、看设备在说什么（零门槛，不用装 ESP-IDF）

```bash
python3 tools/device/monitor.py --info      # 复位并解析硬件事实
python3 tools/device/monitor.py             # 同上 + 完整日志
python3 tools/device/monitor.py --follow    # 持续跟随，不复位
```

只依赖 `pyserial`（`pip3 install pyserial`）。**读日志不需要 ESP-IDF** ——
那几 GB 的工具链只在真要编译烧写时才需要。

### 两个串口，别选错

设备会枚举出两个 Espressif 口：

| VID:PID | 名字 | 用途 |
|---|---|---|
| `303A:1001` | USB JTAG/serial debug unit | **芯片原生调试口，ESP-IDF 日志在这** |
| `303A:4005` | ColoPlay | 固件自己注册的 CDC |

我第一次读了后者，收到的是乱码 —— **那不是波特率问题**，是那个口根本不输出
ESP-IDF 日志。`monitor.py` 默认选 PID `0x1001`。

## 二、真机实测到的硬件事实

一条 `monitor.py --info` 拿到的（2026-09-04）：

```
芯片       v1.1          ESP-IDF   v5.5.3
flash      8MB           CPU       160 MHz
电池       优特利 520mAh（CW2017 profile；文档原估 500）
I2C 设备    0x18(ES8311 音频 codec)  0x63(CW2017 电量计)

可用堆      上游固件 187 KiB（57+113+10+7）
           我们的   231 KiB（101+113+10+7）
```

### ⚠️ 可用堆不是 400 KB

这是最重要的一条修正。400KB 是 SRAM 物理总量，扣掉固件静态占用后
上游完整固件（含 BLE 栈 + 七个 demo）只剩 **187 KB**。

我们砍掉 BLE 和四个用不上的 demo 后回到 **231 KB** ——
**换回 44 KB，在 C3 上是很大一笔**。

全屏 16bit 帧缓冲 150 KB 仍占可用堆的 65%，
「必须分块渲染」这条结论不变，详见
[01-constitution.md](01-constitution.md#11-硬约束清单)。

### 分区表跟着玩法走

设备当时的分区（社区图鉴玩法刷进去的）：

```
factory      1.06 MB      pkdata_a  2.21 MB
recovery     1.00 MB      pkdata_b  3.65 MB
```

上游默认是 `factory 3MB + recovery 1MB`。刷我们的固件时会换成我们自己的表。
我们全部资产 **158.8 KB**，用上游默认的 3MB app 分区绰绰有余，
**不需要额外数据分区**。

### 三条不能改的契约

上游 `AGENTS.md` 规定（小程序 BLE 安装依赖它们）：

- app 分区上限 **3 MB**
- `cardid` @ `0x356000`
- `recovery` @ `0x700000` 永久保留，上键长按 5 秒进入

## 三、要编译烧写时

需要 ESP-IDF 5.5.3。上游提供了门禁脚本：

```bash
./tools/validate.sh --static      # 仓库检查 + host tests
./tools/validate.sh --firmware    # ESP-IDF 构建 + 合并镜像验证
./tools/validate.sh               # 完整门禁
```

**编译成功不等于硬件验证成功。** 上游要求交付时分别报告：

```text
Build:        PASS / FAIL / NOT RUN
Host tests:   PASS / FAIL / NOT RUN
Device tests: PASS / FAIL / NOT RUN
Unverified:   仍需板卡、仪器或用户确认的事项
```

这条对我们同样适用 —— 本项目已经栽过「node --check 通过不代表画对了」。

## 四、这台设备解掉的几个未知项

[01-constitution.md](01-constitution.md#13-已确认与待实测) 的待实测表里，
下面几项因为有了真机而变得可测或已结案：

| 原待办 | 现状 |
|---|---|
| 音频通路 PWM 还是 I2S | **结案**：ES8311 codec + I2S 全双工，还能录音 |
| 续航天数怎么测 | **不用外接电流表** —— `bsp_battery_soc()` 直接读百分比 |
| 屏幕型号 | **结案**：ST7789P3，SPI 40MHz，出厂需反色 |
| 按键电路 | **结案**：三键共用一个 ADC 引脚靠分压区分 |
| 三键够不够用 | BSP 提供 PRESS/CLICK/DOUBLE/LONG **四种事件** → 12 种输入 |
| 口袋 RSSI 基线 | 有设备了，装兜里跑一轮采集即可 |
| NFC 型号 | BSP 引脚表里**没有 NFC** → 加强「静态标签」判断 |

## 五、采集数据（已验证跑通）

```bash
# 设备上：菜单选 Collect → OK 进入 → OK 开始采集
python3 tools/device/collect.py --seconds 300 --out data/raw/park.ndjson
python3 tools/device/collect.py --replay data/raw/park.ndjson   # 只回放
```

抓完立刻喂给 `sim/` 对账 —— 采完就知道这份数据有没有用，
而不是回来发现全是 UNKNOWN。

### 真机首次验证（2026-09-04）

设备输出的每行就是一条 NDJSON，键名与 `tools/collector` 完全一致：

```json
{"ts":6906,"aps":[{"b":"aa:bb:cc:dd:ee:ff","s":"ExampleWiFi","r":-32,"c":6,"a":"open"},…],"bat":100}
```

**零转换直接喂给 sim/ 跑通了**：

```
2.4G AP=6   unknown  biome=住宅区  family_ratio=0.17  ← 新地点
2.4G AP=6   staying  biome=住宅区  family_ratio=0.33
2.4G AP=8   staying  biome=住宅区  family_ratio=0.25
完整流程：遭遇 1 捕获 1 图鉴 2 日志 10 条
```

19 个系统在真机数据上完整走了一遍：判出住宅区 → 遭遇海星星 →
战斗（用「电击」，S20 招式系统在工作）→ 捕获 → 存档 2144 B。

两个顺带验证的数字：

- **扫描间隔实测 32~33 秒**（设定 30），多出的是扫描本身耗时
- **family_ratio 0.17~0.33** 与 `data/raw/home.ndjson` 的 0.22 吻合 ——
  印证了合成数据那次把邻居 SSID 调到 0.17 的方向是对的

### 采户外数据时看什么

野外 biome 是死代码（[00-handoff.md](00-handoff.md) P0-②），修它需要
**真实户外的 AP 数分布**。采的时候盯 `--replay` 输出的两列：

| 列 | 看什么 |
|---|---|
| `2.4G AP=N` | 户外应明显低于室内（室内实测 6~65） |
| `biome=` | 现在一定判不出野外（死代码），但要看它判成什么、AP 数在什么区间 |

采够公园/街道各半小时，就能定出「空旷」的判据。

## 六、社区已有一个宝可梦玩法

`docs/reference/sunny0826/offline-pokedex/` —— 全国图鉴 1025 只 + 像素精灵 +
叫声全部内嵌固件。它证明了几件对我们有用的事：

- **1025 只精灵 + 叫声能塞进 8MB**（我们只做初代 151 只，宽裕得多）
- 数据源同样是 PokeAPI
- 三键靠**双击/长按**扩展：单击 ±1、双击 ±10、长按跳世代

最后一条值得借鉴 —— 我们 S12 取名算过「24 个候选双向循环最坏 13 次」，
如果用上双击跳段，那个数还能再降。
