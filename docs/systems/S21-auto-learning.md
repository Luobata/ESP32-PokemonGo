# S21 · 金银学习表核查与自动学习

核查日期：2026-09-09。结论：**尚未覆盖全部金银招式**。普通获得路线涉及 238 种招式；本轮从缺失 74 种减少为 73 种，引擎支持初代 165 招和新增潮旋。现有初代招式沿用本项目战斗规则，不能把“支持”理解为逐条完全复刻金银机制。

## 范围和数据来源

来源为 [pret/pokegold 固定提交](https://github.com/pret/pokegold/tree/656583c939d30f920a316177311a502dd222b57c)。解析 `evos_attacks.asm`、`base_stats`、`egg_moves.asm` 和招式常量，覆盖前 151 只及其进化前形态（含二代宝宝）。包含升级、TM/HM、遗传；不包含跨代传回、活动限定招式和水晶教学招式。

238 种中，按途径分别有升级 203、TM/HM 57、遗传 94 种（彼此重叠，不能相加）。事实快照保存在 `data/pokemon_moves/gold_silver.json`；核查脚本为 `tools/pipeline/audit_gold_silver_moves.py`。基线报告 `reports/evidence/gold-silver-2026-09-09/audit.json` 保留修改前 74 种缺失，下面是本轮之后的 73 种。

## 简化学习规则（本项目设计）

- 符合原作物种学习资格时自动解锁；不使用机器道具、不做四选一、不设 PP。
- 保留既有学习规则、金银升级招式和进化前招式；同一招式取最早获得等级，避免更新后遗忘。
- HM：居合斩 15、飞翔 25、冲浪 25、怪力 20、闪光 10、潮旋 20、攀瀑 35。
- 其他 TM：变化招式 20 级；威力 ≤60 为 15 级，≤90 为 25 级，更高为 40 级。
- 遗传招式 30 级自动解锁，无需繁殖。如果自然升级或原规则更早获得，按更早等级。
- 普通皮卡丘不符合冲浪资格；不把活动限定能力普发给所有物种。
- 自动战斗从完整已学集合中按效果、属性、状态和随机性选招。
- 尚未实现的二代招式不加入技能库，避免显示已学却没有效果。

新增潮旋采用金银的水属性、威力 15、命中 70，造成伤害并施加束缚，使用水色束缚动画。存档仍是 V11 / 3664 字节，不要求重开。

## 回归

`verify_gs_learning.py` 检查 151 × 100 个物种等级组合、升级不遗忘、HM 资格与潮旋伤害/束缚；`verify_combat_fx.py` 检查全部 166 招、双侧与不同体型、29504 帧；`verify_trainer_sendout.py` 检查初始双方、主动换宠、倒下换宠和敌方替换，共 118 次画面一致性检查。

## 覆盖策略建议

不把全招式覆盖作为当前发布门槛。优先保证经典招式辨识度、各属性进攻选择、不同伙伴的战斗特色，以及动画与效果一致。

建议先补影子球、铁尾、咬碎、逆鳞、终极吸取等代表招式，再考虑守住、天气和亲密度关联等机制。针对 PP 的招式与当前无 PP 规则不匹配，可以明确排除或另行设计；依赖持有物、复杂换宠链的技能在对应系统完善后再评估。以下缺失表是原作差异清单，不代表每项都必须实现。此处仅记录建议，未修改这些招式的实现。

## 待实现的二代招式

以下为原作常量名，便于与源码逐项核对。后续应按机制分组实现并验收：天气与场地、守住/反制、持有物、条件威力、延迟攻击、状态/能力联动。不能统一映射为普通伤害来虚报覆盖率。

| ID | 原作名称 | 原作效果 |
|---|---|---|
| 168 | THIEF | EFFECT_THIEF |
| 170 | MIND_READER | EFFECT_LOCK_ON |
| 171 | NIGHTMARE | EFFECT_NIGHTMARE |
| 172 | FLAME_WHEEL | EFFECT_FLAME_WHEEL |
| 173 | SNORE | EFFECT_SNORE |
| 174 | CURSE | EFFECT_CURSE |
| 175 | FLAIL | EFFECT_REVERSAL |
| 176 | CONVERSION2 | EFFECT_CONVERSION2 |
| 179 | REVERSAL | EFFECT_REVERSAL |
| 180 | SPITE | EFFECT_SPITE |
| 181 | POWDER_SNOW | EFFECT_FREEZE_HIT |
| 182 | PROTECT | EFFECT_PROTECT |
| 183 | MACH_PUNCH | EFFECT_PRIORITY_HIT |
| 184 | SCARY_FACE | EFFECT_SPEED_DOWN_2 |
| 185 | FAINT_ATTACK | EFFECT_ALWAYS_HIT |
| 186 | SWEET_KISS | EFFECT_CONFUSE |
| 187 | BELLY_DRUM | EFFECT_BELLY_DRUM |
| 188 | SLUDGE_BOMB | EFFECT_POISON_HIT |
| 189 | MUD_SLAP | EFFECT_ACCURACY_DOWN_HIT |
| 190 | OCTAZOOKA | EFFECT_ACCURACY_DOWN_HIT |
| 192 | ZAP_CANNON | EFFECT_PARALYZE_HIT |
| 193 | FORESIGHT | EFFECT_FORESIGHT |
| 194 | DESTINY_BOND | EFFECT_DESTINY_BOND |
| 195 | PERISH_SONG | EFFECT_PERISH_SONG |
| 196 | ICY_WIND | EFFECT_SPEED_DOWN_HIT |
| 197 | DETECT | EFFECT_PROTECT |
| 198 | BONE_RUSH | EFFECT_MULTI_HIT |
| 199 | LOCK_ON | EFFECT_LOCK_ON |
| 200 | OUTRAGE | EFFECT_RAMPAGE |
| 201 | SANDSTORM | EFFECT_SANDSTORM |
| 202 | GIGA_DRAIN | EFFECT_LEECH_HIT |
| 203 | ENDURE | EFFECT_ENDURE |
| 204 | CHARM | EFFECT_ATTACK_DOWN_2 |
| 205 | ROLLOUT | EFFECT_ROLLOUT |
| 206 | FALSE_SWIPE | EFFECT_FALSE_SWIPE |
| 207 | SWAGGER | EFFECT_SWAGGER |
| 210 | FURY_CUTTER | EFFECT_FURY_CUTTER |
| 211 | STEEL_WING | EFFECT_DEFENSE_UP_HIT |
| 212 | MEAN_LOOK | EFFECT_MEAN_LOOK |
| 213 | ATTRACT | EFFECT_ATTRACT |
| 214 | SLEEP_TALK | EFFECT_SLEEP_TALK |
| 215 | HEAL_BELL | EFFECT_HEAL_BELL |
| 216 | RETURN | EFFECT_RETURN |
| 217 | PRESENT | EFFECT_PRESENT |
| 218 | FRUSTRATION | EFFECT_FRUSTRATION |
| 219 | SAFEGUARD | EFFECT_SAFEGUARD |
| 220 | PAIN_SPLIT | EFFECT_PAIN_SPLIT |
| 222 | MAGNITUDE | EFFECT_MAGNITUDE |
| 223 | DYNAMICPUNCH | EFFECT_CONFUSE_HIT |
| 225 | DRAGONBREATH | EFFECT_PARALYZE_HIT |
| 226 | BATON_PASS | EFFECT_BATON_PASS |
| 227 | ENCORE | EFFECT_ENCORE |
| 228 | PURSUIT | EFFECT_PURSUIT |
| 229 | RAPID_SPIN | EFFECT_RAPID_SPIN |
| 230 | SWEET_SCENT | EFFECT_EVASION_DOWN |
| 231 | IRON_TAIL | EFFECT_DEFENSE_DOWN_HIT |
| 233 | VITAL_THROW | EFFECT_ALWAYS_HIT |
| 235 | SYNTHESIS | EFFECT_SYNTHESIS |
| 236 | MOONLIGHT | EFFECT_MOONLIGHT |
| 237 | HIDDEN_POWER | EFFECT_HIDDEN_POWER |
| 238 | CROSS_CHOP | EFFECT_NORMAL_HIT |
| 239 | TWISTER | EFFECT_TWISTER |
| 240 | RAIN_DANCE | EFFECT_RAIN_DANCE |
| 241 | SUNNY_DAY | EFFECT_SUNNY_DAY |
| 242 | CRUNCH | EFFECT_SP_DEF_DOWN_HIT |
| 243 | MIRROR_COAT | EFFECT_MIRROR_COAT |
| 244 | PSYCH_UP | EFFECT_PSYCH_UP |
| 245 | EXTREMESPEED | EFFECT_PRIORITY_HIT |
| 246 | ANCIENTPOWER | EFFECT_ALL_UP_HIT |
| 247 | SHADOW_BALL | EFFECT_SP_DEF_DOWN_HIT |
| 248 | FUTURE_SIGHT | EFFECT_FUTURE_SIGHT |
| 249 | ROCK_SMASH | EFFECT_DEFENSE_DOWN_HIT |
| 251 | BEAT_UP | EFFECT_BEAT_UP |
