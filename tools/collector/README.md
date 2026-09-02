# wifi-collect — macOS WiFi 环境采集器

用笔记本电脑采集真实 WiFi 环境，输出 NDJSON 供 `sim/` 回放。

**这是硬件到手前价值最高的工作** —— 它让匹配算法能在真实数据上调通，
且能提前回答两个 Phase 0 问题（真实 AP 密度、三态判别可分性）。

## 构建与使用

```bash
./build.sh                                    # 编译（需 Xcode CLT）
./wifi-collect --count 1                      # 试跑一次
./wifi-collect -i 30 -o ../../data/raw/day1.ndjson   # 正式采集
```

| 参数 | 说明 |
|---|---|
| `-i, --interval N` | 扫描间隔秒数（默认 30） |
| `-o, --out FILE` | 输出文件（默认 stdout）。**追加模式**，不会覆盖已有采集 |
| `-n, --count N` | 扫 N 次后退出（默认 0 = 无限，Ctrl-C 停止） |
| `-q, --quiet` | 不向 stderr 打印进度 |
| `--allow-degraded` | 无定位授权时也继续（见下） |

## 定位授权

**macOS 12+ 对 BSSID 有权限门禁。** 没有定位授权时 `bssid` 和 `ssid` 全返回 `nil`，
只剩 RSSI 和 channel —— 而[指纹方案的核心正是 BSSID](../../docs/02-sensing.md#21-五条感知通道)。

程序启动时会**实扫一次自我检测**（比查 `authorizationStatus()` 可靠，
因为最终能否读到 BSSID 由系统综合判定）。检测到无授权会给出指引并退出。

### 关键：必须打包成 .app

**TCC（隐私授权）按 bundle identifier 判定权限，而裸可执行文件没有身份。**
后果是两条看起来显然的路都走不通（本机已实测）：

| 尝试 | 结果 |
|---|---|
| 在「定位服务」列表里给 iTerm 授权 | ✗ **列表里根本没有 iTerm** |
| `sudo ./wifi-collect` | ✗ **同样拿不到 BSSID** —— root 不等于有 TCC 授权 |
| `system_profiler SPAirPortDataType` | ✗ 能列出网络但不给 BSSID |

所以正解是给它一个身份：

```bash
./make-app.sh        # 打包 + ad-hoc 签名（不需要开发者账号）
```

然后**在你自己的终端里**跑一次触发授权弹窗：

```bash
./WiFiCollect.app/Contents/MacOS/wifi-collect --count 1
```

弹窗出现就点「允许」。没弹窗则去 **系统设置 → 隐私与安全性 → 定位服务**，
找到 **WiFiCollect** 打开开关 —— 打包后它才会出现在列表里。

> 弹窗需要图形会话触发。从非交互环境（比如 AI agent 的 shell）跑不出弹窗，
> 必须你亲自在终端里执行。

验证：

```bash
./check-auth.sh --app
```

成功会打印 `✓ BSSID 可读`，并报告扫到多少 AP、其中 2.4GHz 几个。

### 降级模式（仅验证管线）

```bash
./wifi-collect --count 2 --allow-degraded
```

无 BSSID 时用 `channel + RSSI 分桶` 合成稳定的伪 BSSID：

```
bucket = (rssi / 6) * 6                       # 6dB 分桶
hash   = channel * 7919 + bucket * 104729 + index
```

分桶宽度 6dB 是个折中 —— 太窄会因 RSSI 抖动裂成多个假 AP，太宽会把不同 AP 合并。
实测相邻两次扫描的伪 BSSID 完全一致，因此**能当弱指纹用，可以把管线跑通**。

> ⚠️ **但判别质量明显下降，不能用于最终标定。**
> 输出行会带 `"degraded":true` 标记，`sim/` 侧会识别并警告。
>
> 不过有一点是真的：**channel 和 RSSI 不受权限限制**，
> 所以「这个地方能扫到几个 2.4GHz AP」这个数即使在降级模式下也是准的 ——
> 而它正好决定[降级阶梯](../../docs/02-sensing.md#23-降级阶梯)要降到哪一级。

## 输出格式

每行一次扫描（格式契约见 [docs/06-engineering.md](../../docs/06-engineering.md#数据格式)）：

```json
{"ts":1788350200,"aps":[{"b":"aa:bb:cc:dd:ee:ff","s":"MyWiFi","r":-45,"c":6,"a":"wpa2"}]}
```

字段名压到一个字母 —— 将来固件侧若落盘同格式，每字节都要算（8MB flash）。

| 字段 | 含义 |
|---|---|
| `ts` | Unix 时间戳（秒） |
| `b` | BSSID（降级模式下为 `syn:` 前缀的伪值） |
| `s` | SSID（隐藏 SSID 是空串，不是错误） |
| `r` | RSSI（dBm） |
| `c` | channel（`<= 14` 为 2.4GHz） |
| `a` | authmode：`open` / `wep` / `wpa` / `wpa2` / `wpa2-ent` / `wpa3` / `wpa3-ent` / `unknown` |

行级可选字段：`"degraded":true`（降级模式）、`"err":"scan_failed"`（该次扫描失败，
`aps` 为空数组 —— 扫描失败不终止长跑采集）。

## 采集建议

要回答「家/公司/通勤能否区分」，至少需要覆盖这三个场景各一段：

```bash
# 在家开一个（睡前到起床）
./wifi-collect -i 30 -o ../../data/raw/home.ndjson

# 通勤路上开一个（间隔调短，捕捉快速变化的 AP）
./wifi-collect -i 10 -o ../../data/raw/commute.ndjson

# 公司开一个
./wifi-collect -i 30 -o ../../data/raw/office.ndjson
```

采集完用回放器看结果：

```bash
python3 ../../sim/replay.py ../../data/raw/home.ndjson
```

## 与目标硬件的差异（重要）

电脑采集的数据**不能直接用于阈值标定**，有三个系统性差异：

| 差异 | 影响 |
|---|---|
| **电脑能看 5GHz，ESP32-C3 只有 2.4GHz** | 电脑看到的 AP 数会显著偏多。实测本机 61 个 AP 里只有 17 个是 2.4G |
| **电脑天线远好于设备**，且不在口袋里 | RSSI 系统性偏高。见 [2.6 口袋标定](../../docs/02-sensing.md#26-口袋标定一个会坑人的实测陷阱) |
| 扫描实现与时序不同 | 单次扫描的完整度不同 |

因此这批数据的正确用途是**验证算法逻辑与获得定性结论**
（「家和公司能不能分开」），而非确定最终阈值。

分析时若要模拟设备视角，可以只保留 `c <= 14` 的 AP —— `sim/replay.py --only-24g` 会这么做。

**数据不入库**：`data/raw/` 已在 `.gitignore` 中。
BSSID 属位置关联数据，[本地存储风险低但不该上传](../../docs/02-sensing.md#28-隐私与合规)。
