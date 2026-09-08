# 队伍换入、经验与养成联动验收（2026-09-08）

已完成代码、同源原生预览、ESP32-C3 固件构建及真机烧录。设备重新连接为 `/dev/cu.usbmodem1101`，烧录前备份 NVS 和旧应用，写入校验通过。静音原设置为关闭，本次仅将 mute 改为 1，音量保留 80；游戏存档 blob 未修改。

## 玩法

- 菜单 → 队伍：B 选择、长 B 上一位；A 详情后 A 设为队首。列表长 A 打开仓库，B 选择、A 交换、C 返回。伙伴属性随个体保留；同物种仓库占位时拒绝覆盖，活动对战期间禁止换队。
- 野生基础经验为等级×8+20；获胜 100%、失败 30%、捕获成功 60%，战胜后捕获另加捕获经验，逃跑不奖励。训练家按既有参战分配规则发放，失败也有 30%。
- 饱食、心情、亲密将经验倍率调至 80–130%。稀有加成最高提高三星以上累计概率 5 个百分点、四星以上 2 个百分点、五星 0.5 个百分点，不能越过剧情门槛，不改变闪光判定。
- 成功探索扣 5 点体力；不足或保存失败不扣。白天每小时恢复 12 点，熄屏仍有效，完全关机不补算。休息按钮改为恢复说明，道具不再即时恢复养成体力，对战 HP 恢复保持独立。
- 经验、换队和探索扣体力通过候选存档提交后发布，错误重试不重复发奖。存档仍为 V11、3664 字节。

## 验证

| 检查 | 结果 |
|---|---|
| verify_growth_links.py | 28 个核心场景、3000 组配对稀有度序列，ASan/UBSan |
| verify_growth_preview.py | 33 项、逐帧重绘差异为零；最终 native b5ae4ded089f07b2020c |
| verify_nurture.py | 3201 次时间对账、40 次动作 |
| verify_items.py | 102 场景、19 道具、V11 兼容；原作进化表 oracle 通过 |
| verify_world_party.py | 28 场景 |
| verify_trainer_campaign.py | 1299 动作、20 次替换、4 场景 |
| verify_capture_animation.py | 1635 帧、4 流程 |
| verify_capture_timing.py | 306 判定，162 命中、144 未命中，重试无重复 |
| verify_exploration_preview.py | 460 项 |
| tools/device/fw.sh build | 通过，应用分区可容纳；恢复分区容量警告不适用于主应用烧录 |

固件大小：1841808 字节。SHA256：`763ed3597f4574a53f3410030d20f1d0d3d335e3ce514163e1e97072cf252452`。

证据：[核心规则](evidence/growth-links-2026-09-08/world.json)、[预览](evidence/growth-links-2026-09-08/preview.json)、[页面拼图](evidence/growth-links-2026-09-08/contact.png)。

真机启动通过：Display/Button/Audio/Battery/World 均就绪，mute=1；读档图鉴 10/151、队伍 6、总伙伴 11。烧录后 NVS 读回确认队伍、仓库、队列、图鉴、道具、挑战、成就、探索与队首经验全部保留；队首鲤鱼王 Lv8、EXP1088。未通过注入游戏动作改动真实进度。见 [设备读回证据](evidence/growth-links-2026-09-08/device.json)。

备份位于 `.device-backup/nvs-before-growth-links-20260908.bin`、`app-before-growth-links-20260908.bin`；烧录后读回为 `nvs-after-growth-links-20260908.bin`。
