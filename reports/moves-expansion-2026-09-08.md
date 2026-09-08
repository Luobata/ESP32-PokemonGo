# 技能与动画扩展验收 · 2026-09-08

本批已将招式表从 **99 招扩至 104 招**，补入 **22 条红蓝版升级学习记录**。新增的五招有真实伤害机制，且均已通过实际 P3 的正常学习表、自动选招和 C 渲染出现。新增八种动画轨迹；没有通过强制写入招式或伪造回合来取得页面证据。

| 招式 | 实际规则 | P3 证据（对手 #74、稀有度 5，初始 HP 197） |
|---|---|---|
| #49 音爆 | 命中后固定 20，命中率 90 | #81 Lv21、seed 2，197 → 177 |
| #69 地球上投 | 伤害等于使用者等级 | #56 Lv33、seed 1，197 → 164 |
| #82 龙之怒 | 命中后固定 40 | #130 Lv25、seed 5，197 → 157 |
| #101 黑夜魔影 | 伤害等于使用者等级 | #92 Lv25、seed 3，197 → 172 |
| #162 愤怒门牙 | 目标当前 HP 除 2 向下取整，最少 1，命中率 90 | #19 Lv34、seed 2，197 → 99 |

上述招式遵守当前项目的属性免疫；其余抗性、克制倍率、STAB、攻防和养成能力倍率不改变固定伤害。来源为固定 [pret/pokecrystal 提交 7a7881d](https://github.com/pret/pokecrystal/tree/7a7881d0d62e0ddbd82dcf10e7116807487ac651) 的 `data/moves/moves.asm`、`BattleCommand_ConstantDamage` 和 `BattleCommand_ResetTypeMatchup`。这是选定 Crystal 机制与现有 15 属性系统的结合，保留当前幽灵对超能免疫等初代相克表，不宣称完整复刻某一代战斗。

`verify_move_effects.py` 直接读取固定上游源码与原始 PokeAPI `pokemon_<id>.json` 的 `red-blue + level-up` 记录作独立 oracle；它没有用转换器输出再验证转换器自己。检查上游工作文件与固定 Git tree 逐字节一致。源文件、招式缓存和最终数据的 SHA 见 `assets/move_effect_sources.json` 及 `reports/evidence/moves-expansion-2026-09-08/mechanics.json`。

## 数据与选招

- MOVE v1 与 12 字节记录格式保持，效果通过稳定 `move_id` 派发。`moves.bin` 3856 → 4011 B；学习记录 607 → 629；`gen1.bin` 与存档结构没有因技能扩展更改。
- 物理/特殊修正为初代按属性划分，受影响的既有 16 招 ID 为 `7,8,9,13,16,22,51,63,75,123,124,127,128,129,152,161`。其余既有招式的威力、命中、PP、属性、名称与既有来源一致。
- 固定伤害招按实际伤害计算选招权重，避免原版参数 `power=1` 让它们几乎永远选不到；免疫招权重为零，维持全部免疫时仍能出招的既有逻辑。
- C 与 Python 均保留最近学会的 8 条记录，固定内存容量不变；新记录顶掉最老记录，保留此前重复学习记录的语义。修复了 #136 Lv54 火焰旋涡被前八条永久遮挡的问题，并在实际 P3 用 seed 42 选到该招。
- 上述物特修正会改变相关物种的伤害与部分胜负，尤其藤鞭/飞叶快刀、水系招和破坏光线。验收以新规则为准。既有 #139 Lv100 对 #137 seed 3 的胜后一次捕获 fixture 仍有效。

## 动画与资源

当前为 **39 种 C 样式、55 个定向 move_id 映射、15 种属性回退、104 招可见覆盖**。55 个映射不代表 55 套独立动画；自爆和大爆炸等有意共享样式。以前的 35 指 OAM 图元数量，不是 35 套独立动画；历史 Inspector 的 26 个 JS 动画也不能当作硬件覆盖数量。

新增五招分别使用目标声波、球体抛落、龙焰波、暗色滚动条带、重复牙齿闭合。另将水炮、破坏光线、自爆/大爆炸从普通属性表现中分出。图元来自同一固定 Crystal 的 PNG、framesets 和 OAM，新增 10 个组合图元，图元像素数据 **3372 → 4908 B（+1536 B）**。黑夜魔影原作属于背景/配色震荡，本项目使用目标区域内的短时条带表达，没有虚构所谓原版专属精灵图。

仍为整数运算、横带绘制，无新增帧缓冲或动态分配；每招最多 18 × 60 ms。保护敌名字、HP、稀有度、闪光标记、主宠右侧 HUD 和底部消息。最后两帧清理位移与图元；未命中不画伤害 overlay，免疫目标不受击抖动。轨迹、压缩节奏和效果调色板是项目改编，原版图元保真不等于完整 GSC 动画逐帧 1:1。

![八种新增轨迹的实际 P3 帧](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/moves-expansion-2026-09-08/actual-p3-contact-sheet.png)

## 验证层次

| 检查 | 结果 |
|---|---|
| 固定源与数据 | 104 招、629 学习记录、16 物特修正逐项通过 |
| 实际 `assets.c + battle.c`，ASan/UBSan | 12,000 固定伤害矩阵、715 全物种关键等级查询、1,536 会话恢复用例通过；含双方出手、强制单次反击、精确 HP、跨会话 RNG |
| 机制/学习负向 | 删除效果派发、错误半血取整、重复 STAB、去掉免疫、保留最老八条，5 项均被拒绝 |
| 实际 `battle_fx.c` | 51,494 相位案例；104 招双方与多尺寸 bbox 有可见像素；15 属性回退互异；新增 8 轨迹与彼此及原属性回退不同 |
| FX 负向 | 未命中、恢复、敌 HP/稀有度/闪光保护、位移边界、actor/overlay 对齐、顶部裁剪、新招误回退，9 项均被拒绝 |
| 真实 P3 | 9 个正常可学招式 fixture、3,139 次 dirty/full RGB565 一致；新招伤害与渐变 HP 一致，实际帧随动画变化；详见 `native.json` |
| 捕获契约 | 7 流程、568 dirty/full 通过；7 个语义负向通过。等待完整入场/原版正面动作；自动战斗仅检查 A/B 锁，C 逃跑由根任务独立测试；战败 A 可进照料 |
| 既有算法门禁 | `verify_battle.py` 通过，含 3200 普通伤害逐值、96 战斗恢复及相克/捕获公式等 |

P3 证据构建指纹为 `68ff02e5d313e457b575`，所有 PNG 来自实际 C 的 RGB565 屏幕帧。它证明桌面原生执行路径与页面接线，不替代物理 ESP32 的速度测量；根任务统一运行最终固件构建与浏览器验收。

可复现命令：

```sh
python3 tools/pipeline/convert_moves.py --src /tmp/gen1c --out assets
python3 tools/pipeline/convert_battle_fx.py --src /tmp/pokecrystal --check
python3 tools/pipeline/verify_move_effects.py --negative
python3 tools/pipeline/verify_battle_fx.py --negative-checks
python3 tools/pipeline/verify_move_preview.py
python3 tools/pipeline/verify_capture_flow.py --negative
python3 tools/pipeline/verify_battle.py
```

104 招表示本项目支持其已有伤害与可见表现，不表示每招全部原作附加机制齐全。PP 消耗、状态、吸血回血、多次命中、自爆自伤/自灭、破坏光线休息等未在本批新增；这些动画不应被描述为已有完整机制。接下来的扩展应继续按“原始规则 → 数值实现 → 可学/可选 → 同源页面实际效果”逐批闭环。
