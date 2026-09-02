# S4 养成状态机

三条状态轴随时间推进，状态低下只进入消沉、能力打折，绝不清零 —— 这是全项目唯一不可再生的数据。

## 输入 / 输出

| 方向 | 来源 / 目标 | 字段 |
|---|---|---|
| 入 | 时间 | `ts`（只需要「过了多久」） |
| 入 | `sim/sensing.py` 的 `SensingResult` | `motion_events`（增量）、`is_new_place` |
| 入 | 绝对时间 | `is_night`（唯一需要真实时钟的输入） |
| 入 | S9 道具 | 喂食消耗品 |
| 出 | S2 捕获 | `catch_window_bonus` 直接乘判定窗口宽度 |
| 出 | S3 战斗 | `ability_factor`（消沉 0.6） |
| 出 | S7 进化 | `intimacy`、`explore_value` |
| 出 | S6 存档 | 整个 `PetState` |

## 核心逻辑

**已实现**，在 `sim/gameplay.py` 的 `PetState`。S4 不需要新算法，只需要固件移植：

| 行为 | 函数（均在 `sim/gameplay.py`） |
|---|---|
| 时间推进 | `PetState.advance(ts, motion_events, is_night)` |
| 喂食 | `PetState.feed(amount=30.0)` |
| 玩耍 | `PetState.play()` |
| 休息 | `PetState.rest(hours=8.0)` |
| 到新地方 | `PetState.on_new_place()` |
| 久别重逢 | `PetState.on_reunion(days_away)` |
| 移动量事件 | `PetState.on_motion_event()` |
| 派生状态 | `is_despondent` / `ability_factor` / `catch_window_bonus` / `mood_label` |

衰减常量已在 `sim/gameplay.py` 定稿：

| 常量 | 值 |
|---|---|
| `SATIETY_DECAY_PER_HOUR` | 4.0 |
| `MOOD_DECAY_PER_HOUR` | 3.0 |
| `STAMINA_RECOVER_PER_HOUR` | 6.0（夜间 ×2） |
| `STAMINA_COST_PER_MOTION_EVENT` | 2.0 |
| `LOW_THRESHOLD` | 25.0 |
| `DESPONDENT_PENALTY` | 0.6 |

**不做惩罚性死亡。** 任一轴低于 25 进入 `is_despondent`，
能力打折到 0.6，恢复照料即复原。`advance()` 里三条轴全部 `max(0.0, ...)`
—— 下界是 0 而不是「归零后清档」。惩罚的是体验密度，不是存档。

**RTC 漂移影响很小。** `advance()` 只用 `(ts - _last_ts) / 3600.0`，
即「过了多久」。漂移会让流逝时长有偏差，但不会让状态机错乱。
只有 `is_night` 需要绝对时间；若对时方案都不理想，砍掉夜间加速即可
（[02-sensing.md#25](../02-sensing.md#25-无连接带来的时间问题)）。

**原型跑出的一条结论**：一天照料一次抵不过衰减，三次（每 8 小时一个窗口）
才打得平 —— 见 `sim/prototype.py` 的 `care_slot` 逻辑。这不是拍的，是跑出来的。

## 数据结构

`PetState` 的持久化布局，**24 字节**：

```
pet_state 24 B
   off  size  field
   0    1     species_id      1~151
   1    1     type_name_idx   TYPES 下标 0~14
   2    1     satiety         定点：0~200（值 = 浮点 × 2），0.5 精度
   3    1     mood            同上
   4    1     stamina         同上
   5    1     intimacy        同上
   6    2     explore_value   u16，够存 65535 次移动量事件
   8    4     last_ts         对应 _last_ts
   12   8     nickname        UTF-8 截断（"小家伙" = 9 B → 需 12 B，见「疑问」）
   20   4     reserved        预留：进化次数、累计照料次数
```

浮点转定点 ×2 是有意的：三条轴的衰减最小步长远大于 0.5，
而定点让固件完全避开浮点（C3 无 FPU，软浮点开销大）。

## 与三键约束的关系

对应 **P5 照料页**：**A 执行 / B 切换 / C 返回**。

B 键在「喂食 / 玩耍 / 休息」三项间循环，A 执行当前项 ——
恰好三个动作对三条轴，线性菜单一层就够，**不需要子菜单**。
这是「少而重」（[04-gameplay.md#43](../04-gameplay.md#43-培育)）的直接体现。

主宠常驻 **P1 待机页**，用 back sprite（32×32）+ `sim/effects.py` 的
`breath_sequence()` 呼吸。消沉时可切 `FLASH_DARK` 灰阶映射表压暗姿态，
零额外素材。

## 待 Phase 0 验证的参数

| 参数 | 依赖 |
|---|---|
| 全部六个衰减常量 | **RTC 走时精度** —— 若只能做到「天」级，小时级衰减率没有意义，三条轴要重新按天标定 |
| `is_night` 能否保留 | 外置 32.768kHz 晶振是否存在；无对时方案则砍掉夜间加速 |
| 一天几次照料才打平 | 已用合成数据跑出「三次」，需真实作息数据复核 |

08-systems.md 把 S4 标为「部分实现 / ⏳ RTC 精度」，与此一致。

## 边界情况

1. **`_last_ts` 为 `None`**（首次运行或存档新建）—— `advance()` 已处理：只记录 ts 直接返回，不推进。
2. **`ts` 回跳**（对时修正把时间调早）—— `advance()` 已处理：`hours <= 0` 直接返回。状态不会因对时倒退。
3. **长时间离线**（出差两周）—— `hours` 很大，三条轴会全部触底到 0 并进入消沉，但**不清零存档**。`on_reunion(days_away)` 给心情 +8 作为重逢补偿，奖励真实生活节律。
4. **`explore_value` 溢出** —— u16 上限 65535；按每天几十次事件算够几年，但仍需 clamp 而非回绕（回绕会让 S7 的进化条件突然失效）。
5. **定点精度下的衰减吞没** —— 若单次 `advance()` 的时长极短（几秒），衰减量小于 0.5 会被定点截断成 0，长期空转会让状态永不下降。对策：累加余量，或只在 ≥1 分钟间隔时推进。

## 疑问

`nickname` 的字节预算需要确认。`PetState.nickname` 默认值 `"小家伙"`
UTF-8 是 9 字节，上表给 8 字节存不下。三个方向：

- 扩到 12 字节（4 个汉字），`pet_state` 变 28 字节
- 存中文点阵字库的字索引而非 UTF-8（每字 2 字节，4 字仅 8 字节）——
  与「中文点阵字体子集化」（08-systems.md 实现顺序阶段 D）天然配套
- 昵称不可改则不存，编译期常量

倾向第二种，但它依赖 D 阶段的字库子集先定稿。这条不影响 S4 的逻辑，
只影响 S6 的总字节数（08-systems.md 估的约 710 字节需按此微调）。
