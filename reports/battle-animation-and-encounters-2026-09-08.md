# 战斗动画与遭遇流程验收 · 2026-09-08

已按最新补充调整：直接捕获失败后，野怪仅反击一次，动画结束恢复「捕获 / 战斗 / 返回」。可再次尝试捕获；只有明确按 B 才自动战斗到结束。主宠被击倒后不能继续投球。战胜后仍只给一次实际投球机会，失败则目标逃跑；查看捕获页再取消不消耗这次机会。

新增三段共用 C 动画：720 ms 双方出场、命中后 360 ms 扣血、1,080 ms 经验增长。前摇保留旧血量，扣血结束显示真实 HP；经验跨级时同步更新显示等级与本级进度。动画与游戏结算分离，奖励只提交一次，反复重绘不会推进状态。自动战斗、强制反击及经验播放期间锁定操作，包括硬件 C 长按入口。

待处理列表最多 5 条，新条无条件淘汰最早一条。首次战斗或实际投球前，先持久化从列表移除目标，再发布独立活动会话；保存失败保留原目标且不扣球。正在处理的目标不受后台 FIFO 淘汰影响，离开这次处理流程后不回列表。仅预览、未投球或开战就返回的目标仍保留。P2 每 200 ms 检查锁内快照，按显示的 UID/时间标识选择，修复后台换队列时误选另一只的问题。

V5 存档布局不变（物理保留 16 槽，逻辑上限 5）。旧档先验证全部记录，过滤已有受伤或经验结算标记的旧目标，再保留最新 5 条。旧格式中「满血、未领经验、只发生过 miss」没有可识别的历史字段，无法据此补判。

![实际 C 渲染动画采样](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/battle-animation-2026-09-08/animation-contact-sheet.png)

可播放：[出场](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/battle-animation-2026-09-08/entry.gif)、[反击与扣血](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/battle-animation-2026-09-08/retaliation.gif)、[跨级经验](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/battle-animation-2026-09-08/experience.gif)。均来自生产 C 页面实际像素，无重绘美化。

| 验证 | 结果 |
|---|---|
| 动画纯 C 采样 | 4,738 次；5 个可编译损坏版本全部被识别 |
| 捕获 / 战斗流程 | 7 条；435 次横带 / 全屏对账；7 个损坏版本被识别 |
| 队列 / 页面生命周期 | 16 条；809 次对账；2 个 P2 刷新 / 误选损坏版本被识别 |
| 实际 world/save C | 8 场景，ASan/UBSan，含 NVS 失败、旧档迁移、UID 回绕及 pthread 并发扫描 |
| 既有存档兼容回归 | 67 场景通过，ASan/UBSan |
| 全页面同源渲染 | 8 页、969 次横带对账、65,536 种 RGB565 颜色；DMA / 横带负向控制通过 |
| 实际动画像素 | 62 帧逐一比对双方 HP 条和经验条的 RGB565 像素；68 次重绘检查 |
| 浏览器实际操作 | 16 帧 Canvas RGBA 与最终原生 C 输出全部相同，每帧 76,800 像素 |
| 出场后精灵布局 | 151 只敌方正面逐像素对照，2,355,600 像素；661,080 个缩放后非透明像素完整保留 |
| ESP32-C3 | 编译通过，应用 1,592,352 字节，未烧写设备 |

最终原生构建标识为 `196048ce3b666b6e83d9`。Inspector 产物已重新生成，现有 `http://127.0.0.1:8766/firmware.html` 已恢复实时运行。预览共用生产页面、动画与横带渲染；世界/时钟/NVS 在预览中是测试适配层，实际 world/save 已另外验证。这里没有声称完成物理 LCD 或实际按键的上板测试。原有 1 MB recovery 分区小于应用的编译告警仍存在；本次应用适配现有 3 MB 主应用分区。

完整证据：[浏览器像素一致性](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/battle-animation-2026-09-08/browser-parity.json)、[动画像素](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/battle-animation-2026-09-08/native-pixels.json)、[页面生命周期](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/encounter-lifecycle-2026-09-08/preview.json)、[实际存档验证](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/battle-animation-2026-09-08/encounter-storage.json)、[固件编译日志](/Users/bytedance/luobata/ESP32-PokemonGo/reports/evidence/battle-animation-2026-09-08/firmware-build.log)。
