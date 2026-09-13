# AI Passport 社区发布

## 最新提交：2026-09-13 晚间

社区项目 234 / pokewalk，版本 624 已提交审核（pending）。本版包含体能约 1 小时回满、仓库筛选排序与快速翻页、秘境换宠结束确认。代码提交 `ec9dc53`，双语说明、五张截图、宣传片链接均已回读核对；固件 SHA-256 见 [发布回执](../../reports/evidence/stamina-one-hour-2026-09-13/community-release.json)。烧录和存档验证见同目录 `device-flash.json`。以下内容保留历史发布记录。

2026-09-13 图片补充：原版本 **607 已审核通过**；同项目新增版本 **613** 已提交审核（pending）。保留原战斗封面，追加照料、破坏光线特效、赤红登场、局内强化，共 **5 张图**；中英文介绍加入宣传片观看／下载链接。视频链接评论此前已提交审核，不重复发送。固件保持 607 的内容与摘要不变。[本次记录](../../reports/community-media-2026-09-13.md)。

2026-09-13：森林秘境与体能统一已合并 main，并上传原项目 **234 / pokewalk** 的新版本 **607**，当前 **pending（待审核）**。固件大小 3,091,152 字节，SHA-256 `d67974d037aa1cb305f5446891e57f1ada6dbbc2df48d044b47c464e07d6208d`。双语介绍、源码地址、分类 games 和固件摘要回读一致；沿用清晰战斗封面。最近三轮汇总评论此前已提交审核，本次不重复发送。[发布说明](../../reports/release-notes-2026-09-13.md) · [操作记录](../../reports/community-update-2026-09-13.md)。


2026-09-11 已提交项目234 / pokewalk的新版本404，状态pending（待审核），分类games。双语正文、分类与固件SHA-256回读一致。新版包含动画时钟修复、探索情报合并、两小时体能恢复、换宠等级和完整进化演出与叫声，并保留9月10日历史说明。回执：reports/evidence/community-update-2026-09-11/project-receipt.json。社区评论草稿已整理，但电脑锁定，尚未发布，待解锁后继续。

分类修正已完成：项目 234，新版本 401，分类 games（游戏与互动），状态 pending。此前版本 400 已审核通过；本次沿用其固件、封面及双语正文，仅修正分类。固件摘要和正文回读核对一致。回执：reports/evidence/community-update-2026-09-10/category-corrected-receipt.json。

2026-09-10 新版提交：项目 `234` / pokewalk，版本 `400`，状态 `pending`。旧版 378 已通过审核。沿用原战斗封面，中英文介绍追加今日更新说明，回读正文和固件摘要一致。官方接口把分类重置为 `developer`，等待网页登录后改回 `games`。回执见 `reports/evidence/community-update-2026-09-10/project-receipt.json`。

2026-09-09 已提交审核：项目 `234`，版本 `378`，slug `pokewalk`，分类「游戏与互动」，状态 `pending`。可在[创作者工作台](https://ai-passport.folotoy.cn/account/?project=234)查看；待审核通过后才公开展示。回执见 `reports/evidence/community-publisher-2026-09-09/submission-receipt.json`。

公开源码：https://github.com/Luobata/ESP32-PokemonGo 。发布分支为 `main`。最新双语标题与介绍以 [submission.json](submission.json) 为准，包含探索补给、12 位地图训练家、经验追赶和路线研究。社区项目地址与审核状态以官方提交回执为准。

2026-09-10 已将封面更换为清晰的原始战斗帧，项目 `234` / 版本 `378` 仍为待审核；固件、分类与双语介绍不变。

## 已备材料

- 合并固件：本地 `release/community/FoloToy-AI-Passport-full.bin`，烧录地址 `0x0`。
- 封面：`reports/evidence/community-cover-2026-09-10/cover.png`，480×640、3:4 竖版。取自游戏录屏 78.5 秒，双方精灵完整可见，无影分身遮挡。发布副本为 `release/community/pokewalk-cover.png`，来源与更新回执见同目录 `cover-update.json`。
- 历史真机证据：`release/community/device-screen.png` 及其回执属于此前版本；最新官方发布流程不要求设备截图，本次上传未将其作为新版证明。
- 宣传片：`reports/video/pokewalk-story-red-2026-09-09/pokewalk-story-v3.mp4`，约3分43秒，包含完整博士转场与赤红片段。
- 新片包含图鉴追踪、梦幻三段线索与成功捕获、队伍经验分享和强化道馆；演示存档章节在片中标注。
- 介绍草稿如下。版本限制写明，不能宣传为金银全招式复刻。

## 固件生成和验证

```sh
source tools/device/idf-env.sh
tools/device/fw.sh build
python tools/release/package_firmware.py
```

使用 ESP-IDF 5.5.3 / ESP32-C3 / 8MB。合并 bootloader、分区表和应用；不含真实设备 NVS、cardid 或 Recovery 内容。官方原样校验器检查组件一致性、分区 MD5、应用容量、恢复入口和保护区。来源及许可证见 `tools/release/README.md`。本次结果见 `reports/evidence/community-publisher-2026-09-09/release-verification.json`。

这证明产物结构通过官方检查，不等同于已经通过社区 BLE 安装/更新实测。当前工程目录与官方模板不同，因此不声称跑过官方完整 `tools/validate.sh --firmware`。合并固件的 NVS 区是空白填充，原有设备保留存档应先备份并使用仅更新应用的流程，不能直接拿完整固件覆盖旧存档。

## 实际发布步骤

按 [官方发布指南](https://github.com/FoloToy/ai-passport/blob/main/docs/development/release/publish-to-community.md)：

1. 从官方地址加载 [publisher 工作流](https://ai-passport.folotoy.cn/skills/folotoy-ai-passport-publisher.zip)，由其检查上述产物和字段。
2. 在 [AI Passport 社区](https://ai-passport.folotoy.cn) 登录，进入「发布新玩法」并展开「✦ 用 AI 辅助发布」，点击「确认连接发布助手」确认授权码；授权入口默认折叠，无需把密码交给助手。
3. 先运行 `whoami` 与 `projects` 核对授权和项目 234 / pokewalk；如已有草稿或待审版本，停止并报告冲突。最新官方流程不要求设备截图，不为发布而重置或烧录设备。
4. 选择合并固件、3:4 封面（JPEG/PNG/WebP ≤10MiB）、公开 HTTPS 源码地址及 `submission.json` 中的双语介绍，预览后上传。
5. 发布后取得社区页面，再考虑是否归档到上游 `plays/`；那是单独的双语文本 PR，不在此处上传固件或封面。

可直接发送： “按 docs/release/community.md 准备好的材料，用官方 publisher 工作流发布到 AI Passport 社区。”

## 最新发布文案

完整双语字段见 [submission.json](submission.json)。旧版宣传片仍保留在仓库中，社区介绍以本次实际功能为准。

## 发布工具兼容性

2026-09-13：最新官方脚本已支持 `--category games`，并支持不附带设备截图的上传；本次直接更新原项目成功，无需撤回修改。下文保留早期工具行为记录，不能作为覆盖当前待审版本的操作指引。

本次官方 publisher 脚本未提供分类参数，首次提交默认为「开发者实验」。已通过官网对同一项目撤回编辑，保留原封面和固件、改为「游戏与互动」后重新提交；项目和版本编号均未变化，固件 SHA-256 与校验产物一致。后续更新应使用项目 `234`，并核对分类，避免新建重复项目。

更换审核中版本的封面时，先在官网「撤回并修改」，再在编辑表单替换图片、沿用固件并提交。当前 Agent resubmit 接口即使在撤回后也可能返回「已有版本正在审核」，本次通过官网表单完成；不要因此另建项目。
