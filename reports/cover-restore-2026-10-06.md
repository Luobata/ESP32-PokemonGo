# 2026-10-06 宣传封面恢复

上次发布误将用户选择的皮卡丘对战暴鲤龙封面换成小拳石截图。本次恢复原图，社区和攻略首页共用原文件；AGENTS.md 增加默认保留用户选定封面的约定。

- 网站源码：`6f70d568a9bc07e4ce504bc858699310476468bf`，已推送 main。[Pages CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37481438699) 成功。
- GitHub Pages、devbox 及两处离线 ZIP 共 22 个资源与本次源码逐字节一致，详见 `evidence/cover-restore-2026-10-06/site.json`。官网刷新可见；离线用户重新下载 ZIP 可看到恢复后的封面。
- 社区项目 234：此前 REV-2139 已批准公开；本次仅恢复封面的 REV-2158 已提交审核（pending），尚未公开。API 回读介绍、标题、使用说明及固件摘要均未变。浏览器确认待审图库为 1 段视频、5 张图片，第一张为暴鲤龙。
- 沿用 `b4ee936992c60bc90bd934693be6f92f0b65a913` 已验证固件，未打包或上传本轮验证编译产物。完整固件 SHA-256：`14ab4de700228fc5984efacccd876cd9caac7197c44816a80e996193af5098b3`；应用 SHA-256：`53708aa98e74f2c987b6f673362b1aee6c8aefd547a90b2947598905e3801233`。固件 CI、真机启动保档和包检查见 [原发布报告](exploration-release-2026-10-06.md)。
- 本次无固件、存档布局或协议变更，支持来源仍为 V5～V20，旧秘境 V3→V4 迁移保持。全部 11 项存档/地区/栈发布检查及编译通过，另通过探索、养成、时长、可获取性、攻略和分区检查。均为本机自动化/隔离 NVS 验证；本轮未烧录、未进行真机覆盖导入。无需升级固件。
- 既有完整社区安装仍会覆盖存档区域，更新需先备份再恢复；相同布局可使用既有保档更新 ZIP。本次封面恢复无需执行这些安装步骤。

证据：[社区结果](evidence/cover-restore-2026-10-06/community.json)、[检查结果](evidence/cover-restore-2026-10-06/checks/results.json)、[官网截图](evidence/cover-restore-2026-10-06/guide-cover.png)、[待审封面截图](evidence/cover-restore-2026-10-06/community-cover.png)。
