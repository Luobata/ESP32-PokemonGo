# 2026-10-24：城都的来信发布记录

本次合并自上一公开版本 REV-2661（2026-10-12，V23 / 453 格仓库）以来的城都开发工作，发布源码、固件和配套攻略。代码已合入 main，官网与在线/离线工具已部署。GitHub 固件版本已公开，社区 REV-3636 已提交审核、尚未公开。devbox 公司登录过期；在说明项目同步要求后，用户明确选择先完成 GitHub 和社区发布，因此该部署单独留待登录恢复。

## 交付内容

251 只图鉴与 753 格仓库；城都八条路线、每条三条分支和独立等级区间；八座道馆及赤红后自动开启的冠军重赛；空木最终对战、固定闪光红色暴鲤龙剧情。包含波克比神秘蛋、捕虫调查、未知图腾、图图犬、救助委托、漩涡远征、传说追踪、五件进化研究道具与共 43 项成就。

城都从四枚关都徽章开始衔接，旧玩家按既有进度取得资格，新活动和奖励不会被误标为完成。NPC 对话、调查册和 17 处伙伴协作现场串联后续进程；游戏提示只写环境和能力，攻略的具体解法默认折叠。

动画采用按实际时间推进的舒缓动作，显示刷新与播放速度分离；音频切换和显示传输修复见对应性能报告。USB 备份输出增加跨任务整行互斥，防止 Wi-Fi 日志打断协议；严格拒绝残缺设备截图，避免工具填黑造成误判。

完整玩家说明见 [中文更新](../docs/release/2026-10-24-johto/changelog.zh.md)、[操作说明](../docs/release/2026-10-24-johto/instructions.zh.md) 和 [官网攻略](https://luobata.github.io/ESP32-PokemonGo/guide/)。保留用户选定的皮卡丘对战暴鲤龙封面。

## 兼容性与升级路径

- 当前逻辑 V31，39,944 B；扩展分区位置和大小不变；格式 4 的 72 KiB 备份，继续接受容器 1～4、逻辑 V5～V31。历史结构固定样本未改写，来源校验已通过。
- 同设备升级保留队伍/仓库、等级经验、闪光、图鉴、背包、挑战/秘境和设置。已有开发版城都进度由对应版本迁移；新增叙事默认状态不替玩家领取奖励。拒绝不支持的新格式倒灌旧固件、错误设备、损坏数据和不匹配布局。
- 使用 USB 保档更新包前仍须导出备份。社区完整安装包从 0x0 写入，空白填充会覆盖 NVS，不能当保档更新；完整安装前备份、安装后通过新版网页导入。
- 新功能需要升级固件，备份网站需刷新，旧离线工具需重新下载。CLI 的同设备/同构建和扩展仓库恢复限制保持，不宣称与网页同样支持跨版本。

## 验证范围与发现

[发布门禁](evidence/johto-release-2026-10-24/checks.json) 完成 44 项检查；官网目录/549 个页面变体、在线离线分发、目标构建另行核对。新增城都、保存、动画和串口门禁已加入 GitHub CI。

补跑原有 CI 的 30 项检查时，8 项旧测试初次失败：[原记录](evidence/johto-release-2026-10-24/extra-checks.json)。涉及写死的 453 格容量、旧背包布局、旧音频时钟桩、尚未出招就截取招式名称，以及原关都成就和新研究奖励的领取口径。已更新测试夹具与明确断言；未改生产逻辑绕过测试。最终捕获覆盖 251 物种 × 胜负两种状态及两项边界，共 504 场景；新增 648、752 仓位与稳定个体属性断言。[修复复测](evidence/johto-release-2026-10-24/repair-checks.json)。历史证据图片恢复原字节，本轮生成的旧目录输出另留本地，不覆盖旧验收结论。

[真机烧录与覆盖验收](johto-story-hardware-2026-10-24.md) 使用最终 `bd7eb3b4…` 固件，真实 V30→V31 和 V31→V31 两轮均经过正常亮度 100→89 修改、预备份回读 ACK、576 块上传、匹配重启回执与恢复 100 后重新导出核对；各伴随三次 Wi-Fi 扫描。实测最小堆 9,956 B、最大连续块 9,728 B。使用生产网页 Receiver 配合串口驱动，不冒称浏览器 WebSerial/离线网页点击端到端。历史 V5～V31 通过宿主与隔离真实 NVS，不等于每个历史玩家备份都已实机验证。

真机剧情、照料、队伍与暂停继续的性能及完整重绘成本已记录；未用完整重绘倒数冒称动画 FPS。后段 17 处现场未由当前一枚城都徽章存档逐个解锁，依据生产事务/UI 检查，不能写成真机全剧情通关；本轮也没有重新实听所有音乐或测完所有战斗场景。旧构建偶发导出缺块尚未定位，不能宣称所有历史备份问题都已根治。

## 构建与源码对应

功能源码提交 `7950282aae6b1b53999990d729a374c6446e7205`，官网目录从该不可变提交及上版 `0c768bc` 导出。发布应用使用已验证的 `bd7eb3b4b2be3df9a3e89fdca705fa5f8c27171738096cbdc3761bbb7eb3ac56` 原文件；本次再次目标编译通过，二进制 89 个差异字节全部限于 app descriptor 的版本字符串、构建时间、ELF 校验及末尾图像校验，程序/资源数据逐字节相同。[差异断言](evidence/johto-release-2026-10-24/rebuild-identity.json)。不替换真机记录的应用摘要，也不把新时间戳构建冒称重新上机测试。

打包器增加 `--build-dir`，明确使用已验收的构建快照，不覆盖当前 IDF build 目录。普通系统 Python 缺少 esptool 的第一次打包未完成；改用项目 ESP-IDF Python 后，官方检查器、项目分区保护检查及七项篡改拒绝检查通过。恢复区 1 MiB 小于主应用是既有布局，安装/更新仅写 factory 主应用，不尝试把游戏写入 recovery；主应用余量 205,664 B。

[包与摘要](evidence/johto-release-2026-10-24/package.json) 同时记录完整安装和保档更新 ZIP；最终回归结果见 [检查汇总](evidence/johto-release-2026-10-24/final-checks.json)。


Linux CI 补充验证中发现宿主编译器与依赖顺序差异：两处有符号/无符号比较显式化后，目标程序和资源仍逐字节一致；严格 C11 的 USB 测试补上 POSIX 声明与不可恢复 UBSan；五项事务测试加上明确循环括号，显示所有权检查改在真实 LVGL 依赖安装后运行，按平台链接且保留负向对照。未通过关闭告警或删除断言绕过。首次运行记录和修复对应见 [CI 差异](evidence/johto-release-2026-10-24/ci-repairs.json) 与 [六项本地复测](evidence/johto-release-2026-10-24/portable-checks.json)。

最终固件源代码位于 `8209fc69433ca0d01f8c640a6ce3dc4720f5340e`（后续提交仅测试/文档），官网目录已重新从该提交导出；其重新构建与验收应用的程序和资源一致，见 [最终代码对照](evidence/johto-release-2026-10-24/portable-build-identity.json)。

## 提交、部署与当前发布状态

- [PR #3](https://github.com/Luobata/ESP32-PokemonGo/pull/3) 已合并，合并提交 `023d3b80fbc9fc792fcdfe39094b11e1a6d8346a`。官网最终页面提交 `58f990ca79242fe8bd734d9e1eeb584aa59cde85`；发布前又纠正两处旧中文说明中的 V23 当前版本措辞，并同步完整社区 payload，GitHub 发布标签对应 `590aaa794c3408b6da09931412cbe2b12a8aaf9a`。这些后续提交未改变固件程序和资源。
- [PR 固件 CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/40101647091) 与 [main 固件 CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/40102746582) 均通过，包含宿主回归、ESP-IDF 构建、真实 NVS、目标栈、LVGL 实际引擎及分区保护。此前失败保留在 ci-repairs.json；[main 回执](evidence/johto-release-2026-10-24/ci-main.json)。
- [Pages CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/40102797227) 成功。[生产资源核对](evidence/johto-release-2026-10-24/pages-deployment.json) 对在线 11 项资源及离线 ZIP 共 12 项逐字节检查，全部与本次源码一致；离线 ZIP 是确定性打包，未包含私有文件。[官网截图](evidence/johto-release-2026-10-24/website-updates.png)。
- [GitHub v2026.10.24-johto](https://github.com/Luobata/ESP32-PokemonGo/releases/tag/v2026.10.24-johto) 已于 2026-10-24 15:34:40 UTC 公开，并标记为 Latest。完整安装、保档更新、离线存档工具和 manifest 四个附件已从公开版本重新下载，大小、SHA-256 及原文件字节均匹配：[发布回读](evidence/johto-release-2026-10-24/github-published.json)。首次公开请求使用短提交号被 GitHub 422 拒绝；检查草稿仍未变后，改用已推送的完整 SHA 成功，未新建重复版本。
- 社区项目 234 / pokewalk 新版本 **REV-3636** 为 **pending（待审核，尚未公开）**，上一公开版仍为 REV-2661 approved。双语标题、介绍、操作说明、更新日志八个字段、源码地址、固件长度与摘要均回读一致：[社区回执](evidence/johto-release-2026-10-24/community-submitted.json)。沿用原封面与四张附图，逐张检查了实际上传文件；API 只确认 hasImage，不返回待审图库字节，不能宣称服务器图片内容已回读。没有额外发送评论。
- devbox 的现有别名为 `devbox-online`，SSH 因公司 Kerberos 凭据过期拒绝 GSSAPI。先前发布草稿保留是为满足 AGENTS.md 的同步要求；用户随后明确回复 **“先完成 GitHub 和社区发布”**，授权本次暂缓 devbox 后先发布。该例外与未完成状态已记入 [部署记录](evidence/johto-release-2026-10-24/deployment-devbox.json)。当前应使用 GitHub Pages 或 Release 离线 ZIP，旧 devbox 尚不能作为新版备份入口；登录恢复后补部署并做 12 项资源比对。

发布应用仍为真机验收的 `bd7eb3b4…` 原文件。本轮仅执行代码、网页与发布操作，没有再次烧录、重置或改动用户设备进度；私人存档、原始 NVS 与 Flash 备份没有提交仓库或社区。已发布附件中的 manifest 是打包时的验证快照，`community_upload_performed: false` 表示打包时尚未上传，当前提交状态以上述独立社区回执为准。
