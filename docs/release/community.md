# AI Passport 社区发布准备

本次只准备发布素材并提交源码，尚未上传社区。公开源码：https://github.com/Luobata/ESP32-PokemonGo ，本轮分支 `render-engine-and-gates`。

## 已备材料

- 合并固件：本地 `release/community/FoloToy-AI-Passport-full.bin`，烧录地址 `0x0`。
- 封面：`reports/video/pokewalk-promo-2026-09-09/pokewalk-cover.jpg`。
- 宣传片：同目录 `pokewalk-promo.mp4`，2分09秒、720×1280、游戏原生音轨；另有无外框版本 `pokewalk-gameplay-clean.mp4`。
- 介绍草稿如下。版本限制写明，不能宣传为金银全招式复刻。

## 固件生成和验证

```sh
source tools/device/idf-env.sh
tools/device/fw.sh build
python tools/release/package_firmware.py
```

使用 ESP-IDF 5.5.3 / ESP32-C3 / 8MB。合并 bootloader、分区表和应用；不含真实设备 NVS、cardid 或 Recovery 内容。官方原样校验器检查组件一致性、分区 MD5、应用容量、恢复入口和保护区。来源及许可证见 `tools/release/README.md`。结果见 `reports/evidence/selected-moves-2026-09-09/community-artifact.json`。

这证明产物结构通过官方检查，不等同于已经通过社区 BLE 安装/更新实测。当前工程目录与官方模板不同，因此不声称跑过官方完整 `tools/validate.sh --firmware`。合并固件的 NVS 区是空白填充，原有设备保留存档应先备份并使用仅更新应用的流程，不能直接拿完整固件覆盖旧存档。

## 实际发布步骤

按 [官方发布指南](https://github.com/FoloToy/ai-passport/blob/main/docs/development/release/publish-to-community.md)：

1. 从官方地址加载 [publisher 工作流](https://ai-passport.folotoy.cn/skills/folotoy-ai-passport-publisher.zip)，由其检查上述产物和字段。
2. 在 [AI Passport 社区](https://ai-passport.folotoy.cn) 登录，通过官方网页确认显示的授权码；无需把密码交给助手。
3. 选择合并固件、封面（JPEG/PNG/WebP ≤10MiB）、公开 HTTPS 源码地址及双语标题和介绍，预览后确认上传。
4. 发布后取得社区页面，再考虑是否归档到上游 `plays/`；那是单独的双语文本 PR，不在此处上传固件或封面。

可直接发送： “按 docs/release/community.md 准备好的材料，用官方 publisher 工作流发布到 AI Passport 社区。”

## 标题与介绍草稿

**中文标题：** PokeWalk · 随身宝可梦探索

**中文介绍：** 在 AI Passport 上开启一段三键像素冒险。从大木博士介绍和选择伙伴开始，探索路线、捕获前151只宝可梦、培养六人队伍，挑战道馆、四天王和赤红。养成、图鉴、成就与探索奖励相互联动；招式随成长自动学习，无需管理 PP 或遗忘技能。配有像素动画、场景音乐、技能音效和可调音量。探索使用 Wi-Fi 环境变化，不是 GPS 或真实计步。本版本支持191种招式，仍有48种金银招式待补充。非官方同人项目；素材来源见源码文档。

**English title:** PokeWalk · A Pocket Pokémon Adventure

**English description:** Start with Professor Oak and choose your partner in this three-button pixel adventure for AI Passport. Explore routes, catch the first 151 Pokémon, raise a six-member party, and challenge Gym Leaders, the Elite Four and Red. Care, Pokédex progress, achievements and exploration rewards work together. Compatible moves unlock as Pokémon grow, without PP management or forced forgetting. Includes pixel animations, scene music, battle effects and adjustable volume. Exploration uses changes in the Wi-Fi environment, not GPS or step counting. This build supports 191 moves; 48 Gold/Silver moves remain unimplemented. An unofficial fan project; asset sources are documented in the repository.
