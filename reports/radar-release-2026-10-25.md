# 雷达与地图漫游发布记录 · 2026-10-25

本批交付 Wi-Fi 遭遇雷达、三张金银风格小地图、地图观察与活动接续，以及来源独立的闪光概率和官网攻略。原皮卡丘对战暴鲤龙封面保持不变，新玩法使用真机回读画面作附图。完整玩家说明见 [更新日志](../docs/release/2026-10-25-radar-maps/changelog.zh.md) 与 [操作说明](../docs/release/2026-10-25-radar-maps/instructions.zh.md)。

## 源码、固件与容量

功能提交 `8ed15058ce193159b918ad3ca81b21a7c8ac004e`；攻略从该不可变来源与上版 `v2026.10.24-johto` 导出。文档提交 `f975c06878b487d90b3e5d2eabf040cd6a587cc4`。程序与资源在这两个提交之间没有改动。

使用上轮已烧录验收的原应用：3,227,920 B，SHA-256 `d15fff85e99fa079302fd55f448aa6f0e78a759dc5930861501a397d020d3a9a`。再次 IDF 构建成功，其 91 个差异字节限于 app descriptor 的版本/时间/ELF 哈希和图像校验，程序与资源相同；没有把新构建冒称重新真机验收。[构建对照](evidence/radar-release-2026-10-25/rebuild-identity.json)。

完整安装包 3,293,456 B，SHA-256 `93dd1a3468c4195c012072ce2fc2f71b12f59dbf7f158c3d1809b3d14a596f5d`。factory 余 179,952 B，8 MiB 布局与现有保护区不变。官方结构校验、项目保护校验及篡改拒绝检查通过。完整包应用部分、USB 更新 ZIP 内应用和真机已验收文件逐字节相同。[包与摘要](evidence/radar-release-2026-10-25/package.json)。

## 存档与验证边界

V32 在冻结的 V31 后追加 32 B，世界记录 39,976 B；继续使用格式 4 / 72 KiB 容器、现有分区和 RTC codec。支持同设备 V5～V32，旧字段与固定样本保持；新增观察和冷却初始化为零。旧格式迁移、错误拒绝、保存故障、满仓、共享 NVS 垃圾回收与 USB 协议均包含在 [48 项发布检查](evidence/radar-release-2026-10-25/checks.json)。官网检查覆盖两版共 664 个页面变体、源码目录比对与分发包，见 [附加检查](evidence/radar-release-2026-10-25/documentation-checks.json)。

[真机报告](radar-fieldmaps-hardware-2026-10-25.md) 已完成 V31→V32 及 V32→V32 两次真实覆盖：正常改变亮度、匹配预备份 ACK、完整 576 块传输、重启回执及再次导出比对；原有 123 个伙伴与进度保留，测试遭遇已移除。Wi-Fi 扫描运行中完成导入。首次导出有一块缺失被严格拒绝，完整重试后才烧录；该次传输失败的根因未定位。

新公园行走/发现、雷达/冷却和四个原页面性能完成真机对照，未达到 15% 退化阈值；不把静态绘制耗时或包含停顿的观察窗换算成恒定 FPS。759 个体、未解锁两图和完整活动接续属于宿主覆盖；本轮未重新做全战斗/捕获/进化真机遍历，音频统计不等于扬声器实听。当前发布动作未再次烧录或改动设备进度。

更新前先备份；已有 PokeWalk 优先使用 USB 保档更新 ZIP。社区完整安装从 0x0 写入，空白填充覆盖 NVS，需备份后安装、再恢复。新玩法需更新固件；网页刷新可获得新版攻略，旧离线工具请更新到本次 ZIP。新备份不倒灌不支持它的旧固件，开发 CLI 的扩展仓库恢复限制不变。

## 发布与部署状态

- [PR #4](https://github.com/Luobata/ESP32-PokemonGo/pull/4) 已合并至 main，合并提交 `612e17e32b7af2a4b06ca1417a942dc953483e25`。[PR CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/40179276556) 全部通过，包含完整宿主回归、ESP-IDF 构建、真实 NVS、栈预算和发布包校验。合并树与检查过的分支提交逐字节一致。main 自动触发同一套重复 CI，本记录快照时仍运行；不把尚未结束的重复运行写作通过。[PR 回执](evidence/radar-release-2026-10-25/ci-pr.json) · [main 状态快照](evidence/radar-release-2026-10-25/ci-main.json)。
- [GitHub v2026.10.25-radar-maps](https://github.com/Luobata/ESP32-PokemonGo/releases/tag/v2026.10.25-radar-maps) 已公开并设为 Latest，标签指向上述 main 合并提交。完整安装、USB 更新、manifest、离线工具四个附件再次从公开链接下载，字节与已验收本地文件全部一致。[公开下载核对](evidence/radar-release-2026-10-25/github-published.json)。
- [Pages CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/40180254468) 成功，在线 13 个资源及确定性离线 ZIP 共 14 项与本次源码一致。实际浏览器验收了玩法、候选池、解锁、等级、概率与版本说明。[线上校验](evidence/radar-release-2026-10-25/pages-deployment.json) · [官网截图](evidence/radar-release-2026-10-25/website-field.png)。
- 社区原项目 **234 / pokewalk** 新修订 **REV-3696** 已提交，当前 **pending（待审核）**，上一公开版 REV-3636 为 approved。八个双语文本字段、源码 URL、固件长度和 SHA-256 回读一致，分类 games。沿用原暴鲤龙封面，四张附图为雷达、地图漫游、赤红与养成加成；上传前已逐张查看准确文件。待审 API 未提供图库字节，不声称已回读服务器图片。[社区回执](evidence/radar-release-2026-10-25/community-submitted.json)。没有另发评论。
- devbox 仍按用户此前“先完成 GitHub 和社区发布”的明确指示暂缓，本轮使用 GitHub Pages 与 Release 离线 ZIP；不宣称旧 devbox 已同步。[部署边界](evidence/radar-release-2026-10-25/deployment-devbox.json)。

发布包 manifest 的 `community_upload_performed: false` 表示打包时尚未上传；当前状态以上述独立回执为准。未提交私人备份、原始 NVS、Wi-Fi 记录或完整设备 Flash。
