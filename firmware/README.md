# 固件

跑在 **FoloToy AI Passport**（ESP32-C3）上的固件。

## 快速开始

```bash
source tools/device/idf-env.sh     # 进 ESP-IDF 环境
tools/device/fw.sh backup          # 备份设备当前 flash（首次必做）
tools/device/fw.sh build           # 构建
tools/device/fw.sh flash           # 烧写（没备份会拒绝）
python3 tools/device/monitor.py    # 看日志
```

## 哪些是上游的，哪些是我们的

这个目录是 [FoloToy/ai-passport](https://github.com/FoloToy/ai-passport)
的**衍生构建**。分清来源很重要 —— 上游更新时要能干净地同步。

| 路径 | 来源 | 改动 |
|---|---|---|
| `components/bsp/` | 上游 | **原样照抄**，不改。硬件事实的单一来源 |
| `bootloader_components/` | 上游 | 原样照抄。Recovery 手势是强制契约 |
| `main/ui_pixel*.{c,h}` | 上游 | 原样照抄。像素风 UI 组件 |
| `main/demo_{button,battery,wifi,radio}.*` | 上游 | 原样照抄。保留三个：Button 标定 ADC 分压、Battery 看电量、Wi-Fi 作扫描对照 |
| `main/demo.h` | 上游 | **删掉未编译的声明**（display/audio/ble/low_power）—— 留着会让链接错误晚到链接期才暴露 |
| `main/main.c` | 上游 | **只改 DEMOS[] 表**与启动日志。按键锁、OK 长按返回菜单等逻辑照用 |
| `partitions.csv` `sdkconfig.defaults` | 上游 | 原样照抄 |
| `main/play*.{c,h}` | **我们的** | 玩法实现 |
| `CMakeLists.txt` `main/CMakeLists.txt` | 我们的 | 基于上游，去掉 BLE 依赖 |

同步上游时：`components/` `bootloader_components/` `ui_pixel*` 可以直接覆盖，
`main.c` 与 `demo.h` 要人工合并（改动很小），`play*` 不动。

## 三条不能改的契约

上游 `AGENTS.md` 规定，小程序 BLE 安装依赖它们：

- app 分区上限 **3 MB**
- `cardid` @ `0x356000`
- `recovery` @ `0x700000` 永久保留，**上键长按 5 秒**进入

`CMakeLists.txt` 里那段 `BOOTLOADER_EXTRA_COMPONENT_DIRS` 就是保证第三条的，
删了会让 USB 开发把设备卡在小程序安装路径之外。

## 运行时规矩（上游 AGENTS.md）

- **LVGL 非线程安全** —— LVGL 任务之外访问 UI 必须持 `bsp_lvgl_lock()`。
  `main.c` 的按键回调已经统一加锁，玩法的 `key()` 里不用再加
- **按键回调不得阻塞** —— 慢活（音频、存储、网络）丢给工作任务
- **删 screen 前先停定时器** —— 否则 timer 回调会访问野指针。
  `play_collect_exit()` 就是照这条写的：先 `lv_timer_delete` 再 `lv_obj_delete`

## 当前状态

只有一个玩法：**Collect（WiFi 指纹采集器）**。

先做采集而不是游戏，因为两件事卡在缺数据上：

1. **野外 biome 是死代码**（`docs/00-handoff.md` P0-②）—— 修它需要真实户外采集，
   而我试过的两版阈值都是拿合成数据的编造分布调参
2. **口袋 RSSI 基线未标定** —— 现在用的是电脑天线数据

采集器输出的每行就是一条 NDJSON，键名与 `tools/collector` 完全一致
（`b/s/r/c/a`），可以直接喂给 `sim/` 全套工具，不需要格式转换。
这是刻意的 —— **格式一致是 F5 一致性检验的前提**。

### 真机实测（2026-09-04）

```
固件 1.22 MB → factory 3MB 分区的 41%，余量 1.78 MB
可用堆 231 KB（101+113+10+7）—— 比上游固件多 44 KB，因为砍了 BLE
电池 优特利 520mAh（文档原写 500mAh）
I2C  0x18 ES8311 音频 codec · 0x63 CW2017 电量计
```
