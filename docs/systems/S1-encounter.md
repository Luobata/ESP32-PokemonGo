# S1 遭遇累积

设备在兜里持续扫描，把遭遇静默写入环形队列；玩家掏出来时看到的是一份「刚才路上遇到了什么」的清单。

## 输入 / 输出

| 方向 | 来源 / 目标 | 字段 |
|---|---|---|
| 入 | `sim/sensing.py` 的 `SensingResult` | `state`（moving/staying）、`transient_aps`、`ts`、`is_new_place` |
| 入 | 当次扫描的 `AP` 列表 | `bssid` / `ssid` / `rssi` / `auth` |
| 入 | `sim/gameplay.py` 的 `PetState` | `type_name` —— 主宠属性加权刷新表 |
| 出 | 遭遇环形队列（容量 16） | 追加 `Encounter` |
| 出 | S6 存档 | 队列在 RTC slow memory，按 S6 的提交时机落盘 |

不改 `PetState`，也不改地点表 —— S1 是纯生产者。

## 核心逻辑

两个触发源，对应[4.1.1 猎场与基地](../04-gameplay.md#411-猎场与基地)：

| 场景 | 触发条件 | 参考实现 |
|---|---|---|
| **猎场**（移动中） | `state == MOVING` 且 `transient_aps > 0` | `sim/prototype.py` 第 185 行 |
| **基地**（驻留） | `ts // BASE_SPAWN_INTERVAL` 跨桶（`BASE_SPAWN_INTERVAL = 4 * 3600`，定义在 `sim/prototype.py`） | 同上第 186 行 |

选中一个 AP 后，直接调用 `sim/gameplay.py` 的 `roll_encounter()`，传入
`bssid/ssid/rssi/auth/ts/biome/is_transient/pet_type`。biome 由
`sim/gameplay.py` 的 `classify_biome(aps)` 得出；稀有度由
`rarity_from_ap()` 在 `roll_encounter()` 内部算好，S1 不重复计算。

**基地必须按时间而非移动量驱动。** 否则窝在家里一整天毫无产出，
而「设备永远不会没东西可看」正是这个设计要保证的事 ——
时间生产内容，空间调制内容（[02-sensing.md#20](../02-sensing.md)）。

**队列满时的淘汰规则**：容量 16，满了丢**最旧的低稀有度**那一条 ——
先在队列里找 `rarity` 最小值，同稀有度取 `ts` 最小者。不能简单丢队首：
那会让一次通勤的 ★★★★★ 被后续一串 ★☆☆☆☆ 挤掉。

## 数据结构

环形队列每项 8 字节，定长，无动态分配：

```
遭遇记录 8 B × 16 = 128 B（RTC slow memory）
   off  size  field
   0    4     ts              Unix 秒
   4    1     species_id      1~151
   5    1     packed          bit0-3=type_index(0~14)
                              bit4-6=rarity(1~5)
                              bit7  =is_transient
   6    2     bssid_hash16    from_bssid_hash 的低 16 位（只为去重与展示）
队列头部 4 B:  head | count | biome_of_last | reserved
```

`from_bssid_hash` 截断到 16 位是有意的：只用于「同一个 AP 别连刷」的去重，
不需要反查。原始 BSSID 从不落盘（[02-sensing.md#28](../02-sensing.md)）。

## 与三键约束的关系

S1 本身**无 UI**，是后台系统。产出物由 P2 遭遇列表消费
（A 选中 / B 返回 / C 丢弃），队列容量 16 正好是 P2 一屏两页的量。
P1 待机页只需显示一个「未处理 N 条」的角标。

## 待 Phase 0 验证的参数

| 参数 | 当前值 | 依赖什么实测 |
|---|---|---|
| `BASE_SPAWN_INTERVAL` | 4 小时 | 续航实测决定扫描占空比，进而决定基地遭遇密度是否够撑起「掏出来就有东西」 |
| 队列容量 | 16 | 真实通勤的猎场遭遇率。若一趟通勤就溢出，容量或淘汰规则要改 |
| 猎场触发是否需要节流 | 无节流 | 三态判别误报率。若 MOVING 误报高，静坐时会被刷满队列 |
| `transient_aps` 的有效阈值 | `> 0` | 口袋 RSSI 基线；口袋衰减会让瞬现计数虚高 |

以上四项**全部待 Phase 0 验证**。08-systems.md 已把 S1 标为 ⏳ 遭遇频率。

## 边界情况

1. **`aps` 为空**（扫描失败 / 全 5GHz 环境）—— 不产生遭遇，直接返回，不能拿空列表取模。
2. **队列满且全为同一稀有度** —— 退化为丢最旧，行为仍确定。
3. **同一 AP 在同一时间桶内被反复选中** —— `spawn_seed()` 会给出同一只怪；用 `bssid_hash16` 去重，同桶同 AP 只入队一次。
4. **`ts` 回跳**（RTC 对时或漂移修正）—— `ts // BASE_SPAWN_INTERVAL` 可能跨回旧桶造成连刷；`last_base_bucket` 需允许「桶号变化」而非「桶号增大」，但要对单次会话内的入队数设上限（建议 ≤2）。
5. **`state` 在迟滞窗口内抖动** —— 移动/驻留反复切换时两个触发源都可能命中；以猎场优先，同一次 `feed()` 只产出一条遭遇。
