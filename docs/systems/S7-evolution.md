# S7 进化

把「陪伴时长」与「走过多少地方」两条进度都变成进化条件，并给初代 4 只交换进化在单机场景下的替代方案。

## 输入 / 输出

| 方向 | 来源 / 目标 | 字段 |
|---|---|---|
| 入 | `sim/gameplay.py` 的 `PetState` | `can_evolve()` —— `intimacy >= 60` 且 `explore_value >= 50` |
| 入 | `assets/gen1.bin` | `evolve_trigger`(off 7)、`evolve_to`(off 8)、`evolve_level`(off 9) |
| 入 | `sim/sensing.py` 的 `PlaceMemory` | `Place.biome`、`Place.total_dwell` —— 道具进化的 14 只改用 biome 驻留时长（见 [S9 道具](S9-items.md)） |
| 出 | `PetState` | `species_id`、`type_name` 改写；`intimacy`/`explore_value` 按下方规则处理 |
| 出 | S5 图鉴 | 新形态置「已见」+「已捕」位 |
| 出 | S6 存档 | 进化是状态转换，立即提交 flash |

## 核心逻辑

两个条件必须**同时**满足：养成侧 `PetState.can_evolve()`
（`sim/gameplay.py`，默认 `need_intimacy=60.0`、`need_explore=50`），
物种侧 `gen1.bin` 的 `evolve_trigger` 且 `evolve_to != 0`。

`can_evolve()` 的意图已写在 `sim/gameplay.py` 的 docstring 里：
**两条线各自都能推进，但都推不满** —— 只在家陪着攒不满探索值，
只出门走攒不满亲密度。

### 初代三种触发的处理

实测分布（`tools/pipeline/README.md`）：**升级 52 只、道具 14 只、交换 4 只**。

| trigger | 数量 | 处理 |
|---|---|---|
| 0 = 升级 | 52 | 本项目没有等级，`evolve_level` 映射到 `explore_value` 阈值 |
| 1 = 道具 | 14 | **不做进化石**，改为 biome 驻留条件（[S9](S9-items.md#进化石怎么处理) 已决定） |
| 2 = 交换 | 4 | **需要替代方案，见下节** |
| 0xFF | 剩余 | 不进化 |

`evolve_level` 携带了「这只进化早还是晚」的原版信息，不该丢。
建议 `need_explore = evolve_level × 2`（妙蛙种子 @16 → 32，
巴大蝶 @10 → 20），**系数待调参**。

道具进化那 14 只按石头种类映射到 biome，数据取 `sim/sensing.py` 的
`Place.biome`（首次分类后冻结）与 `Place.total_dwell`：
雷之石 → 办公区驻留（呼应企业级 AP → 电系），火/水之石 → 商业区，
叶之石 → 野外，月之石 → 夜间驻留。对应关系直接取
`sim/gameplay.py` 的 `BIOME_TYPE_POOL`，不引入第二套映射。
**驻留阈值待调参。**

### 交换进化的替代方案（本项目的新设计）

初代靠交换进化的 4 只：**胡地（64→65）、怪力（67→68）、隆隆岩（75→76）、耿鬼（93→94）**。
[04-gameplay.md#44](../04-gameplay.md#44-交换与对战) 已把交换延后，
所以这 4 只在当前形态下**永远进化不了**。

| 方案 | 做法 | 评价 |
|---|---|---|
| **① 高门槛单机替代**（建议） | `trigger == 2` 视作 `trigger == 0`，门槛翻倍：`intimacy >= 90` 且 `explore_value >= evolve_level × 4` | 保留「交换进化更难得」的原版语义，零新机制，不依赖硬件 |
| ② NFC 贴手机 | 手机 App 当交换对象，贴一次算一次「交换」 | 需先确认 NFC 是 I2C 动态标签（[01-constitution.md#13](../01-constitution.md#13-已确认与待实测)未结案） |
| ③ BLE 相遇 | 两台设备相遇即触发 | 最忠于原版，但单机场景等于不可达 |

**建议 ①，因为它不引入任何新依赖** —— 「难得」这个体验靠门槛就能传达，
不必靠交换机制本身。② 可作为 NFC 型号确认后的彩蛋，两者不冲突。

### 动效

复用 `sim/effects.py` 的 `evolution_sequence(frames=12)`：调用方在
`IDENTITY` 帧画旧形态、`INVERT` 帧画新形态，由密到疏最后定格 ——
这就是初代的两 sprite 交替闪烁，零额外素材。

进化后 `intimacy` 与 `explore_value` **不清零**：进化是奖励不是重置，
清零会让连续进化线（妙蛙种子→草花→花王）第二段变成漫长的重新攒资源。
但需按新的 `evolve_level` 重算下一段门槛。

## 数据结构

**无新增持久化。** 条件全部从 `gen1.bin`、`PetState` 与 `PlaceMemory`
的现有字段读取，结果只改 `PetState.species_id` 与 `type_name_idx`
（S4 的 24 字节布局里已有）。

biome 驻留条件读 `Place.total_dwell`，它已在 S6 存档的 `place_table` 里
（8 槽 × 56 B）——**不需要新增按 biome 的累计计数器**，遍历 8 槽按
`biome` 求和即可。代价见「疑问」。

若采用 NFC 方案，需要一个 bit 记「已完成 NFC 交换」，放 S4 的
`reserved` 4 字节里即可，不必扩展存档。

## 与三键约束的关系

进化不是一个页面，而是 **P5 照料页**上的条件触发。
`can_evolve()` 为真时 P5 的 B 键循环里多出「进化」一项，A 键执行 ——
仍是三键、仍是一层菜单。

动效播完回到 **P1 待机页**，主宠 back sprite 已换新形态。这是
「打开瞬间的高光时刻」（[01-constitution.md#12](../01-constitution.md#12-由约束推导出的核心形态)）
最强的一次兑现，值得给它 12 帧。

## 待 Phase 0 验证的参数

| 参数 | 当前值 | 依赖 |
|---|---|---|
| `need_intimacy` / `need_explore` | 60 / 50 | 真实作息下 `intimacy` 涨速（`advance()` 里 `hours × 0.5`，即 120 小时满 60）与通勤下 `explore_value` 涨速 |
| `evolve_level × 2` 系数 | 2 | PC 端调参，不依赖硬件 |
| 道具进化的 biome 驻留阈值 | 未定 | **真实作息数据** —— 一天在办公区/商业区各待多久 |
| 交换进化门槛倍数 | ×4 | PC 端调参 |
| NFC 方案是否可行 | 未知 | **NFC 是静态标签还是 I2C 动态标签**（01-constitution.md 待实测项） |

## 边界情况

1. **`evolve_to` 指向 >151 的 id** —— 跨世代污染（美丽花挂在初代走走下）。`convert_gen1.py` 已过滤，但固件仍应校验 `1 <= evolve_to <= 151`，否则会读到 `gen1.bin` 之外的内存。
2. **分支进化** —— `gen1.bin` 只保留第一条，固件侧不需要选择 UI。**这是已知的信息损失**，不是 bug。
3. **biome 条件不可能满足** —— 玩家从不去办公区则雷之石系永远进化不了。对策：P5 显示条件文案（「在办公区再待 N 小时」）而非置灰。**这正是本方案相对进化石的优势** —— 条件是可行动的。
4. **承载驻留时长的地点被 LRU 淘汰** —— 见「疑问」。
5. **进化时消沉** —— 建议**允许**。消沉只打折能力，不该阻断进度，这与「不做惩罚性死亡」一致。
6. **动效播放中掉电** —— `species_id` 未提交则重启后回到旧形态，条件仍满足，可再进化。宁可重播一次动效，也不能出现「形态变了但图鉴没置位」：`species_id` 与图鉴置位必须在**同一次** S6 提交里完成。

## 疑问

**biome 驻留时长靠遍历 `place_table` 求和，会被 LRU 淘汰吞掉进度。**

`PlaceMemory` 是 8 槽 LRU，满了丢最久未访问的。于是「在办公区累计驻留
N 小时」有个反直觉的失败模式：攒了三周的驻留，出差一趟回来发现槽位
被沿途新地点挤掉，进度归零 —— 这违反了
[「不做惩罚性死亡」](../04-gameplay.md#432-状态轴与时间流逝)的精神。

两个方向，我倾向第一个：**加 5 个 u16 的 biome 驻留累计器**（10 字节，
与地点表解耦、只增不减）；或接受损失但把阈值定得足够低，
让常规通勤一两天就能满足。

采纳第一个会让 S6 总量从 813 增到 823 字节。按要求我没有改 08-systems.md。

