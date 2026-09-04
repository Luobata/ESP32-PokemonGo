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

一条 `monitor.py --info` 拿到的（2026-09-04，设备当时跑的是社区的离线图鉴玩法）：

```
芯片       v1.1
ESP-IDF    v5.5.3
flash      8MB
CPU        160000000 Hz
可用堆      187 KiB（57 + 113 + 10 + 7）
I2C 设备    0x18(ES8311 音频 codec)  0x63(CW2017 电量计)
```

### ⚠️ 可用堆只有 187 KB，不是 400 KB

这是最重要的一条修正。400KB 是 SRAM 物理总量，扣掉固件静态占用后
**实际可动态分配 187 KB**，而且那还是在 LVGL + WiFi 栈已初始化之后。

全屏 16bit 帧缓冲 150 KB = 可用堆的 **80%**。
「必须分块渲染」这条结论比原先估的更硬，详见
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

## 五、社区已有一个宝可梦玩法

`docs/reference/sunny0826/offline-pokedex/` —— 全国图鉴 1025 只 + 像素精灵 +
叫声全部内嵌固件。它证明了几件对我们有用的事：

- **1025 只精灵 + 叫声能塞进 8MB**（我们只做初代 151 只，宽裕得多）
- 数据源同样是 PokeAPI
- 三键靠**双击/长按**扩展：单击 ±1、双击 ±10、长按跳世代

最后一条值得借鉴 —— 我们 S12 取名算过「24 个候选双向循环最坏 13 次」，
如果用上双击跳段，那个数还能再降。
