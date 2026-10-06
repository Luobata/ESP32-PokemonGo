# AI Passport 社区发布

## 2026-10-06 恢复暴鲤龙封面：REV-2158 已提交审核

REV-2139 已通过审核并公开。本次恢复用户选定的皮卡丘对战暴鲤龙原封面，沿用完全相同的固件与其余内容；REV-2158 当前 pending，尚未公开。官网及 devbox 已恢复，离线 ZIP 同步更新。无需重新烧录。AGENTS.md 已明确后续默认保留此封面。

网站源码 `6f70d56`，Pages CI 成功，22 个资源字节一致；存档发布检查及编译通过，固件仍支持 V5～V20。浏览器已确认待审第一张为暴鲤龙，视频及其余四张图片保留。[验证记录](../../reports/cover-restore-2026-10-06.md)。下文保留此前提交时的历史状态。

## 2026-10-06 轮换探索与养成：REV-2139 已提交审核

按用户明确授权，撤回后的旧草稿 REV-2070 已删除，其新地图、分路与主题秘境内容合并到本次版本。原项目 **234 / pokewalk** 的 **REV-2139** 已提交审核，当前 pending，尚未公开上线；上一公开版仍为 REV-2017。

新增轮换访客、特殊探索发现、养成正向加成、探索连携与捕获确认、补给平衡及累计时长。官网提供完整攻略，当前版和上一版数据分别固定到已验证提交。

源码 `b4ee936` 已推送 main，[固件 CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37454382488) 通过，[GitHub Release v2026.10.06-exploration](https://github.com/Luobata/ESP32-PokemonGo/releases/tag/v2026.10.06-exploration) 已公开。设备以本次保档 ZIP 更新，写前备份与写后数据核对通过；启动保留妙蛙花 38 级、图鉴 98/151、六只队伍、91 只伙伴和秘境进度，静音保持。未覆盖导入玩家唯一存档。

支持 V5～V20，旧秘境迁移及全部发布检查通过。完整安装仍需先备份再恢复；布局匹配的现有设备可使用应用更新 ZIP。新内容需更新固件；官网刷新、离线工具重新下载。Pages、devbox 和 ZIP 的 22 个资源与源码一致。

社区中英文字段与固件摘要已回读一致，五张图片随请求提交并逐张检查；待审图库内容未由 publisher 返回，不能声称服务器图片内容已核对。详情见[发布验证](../../reports/exploration-release-2026-10-06.md)、[中文更新说明](2026-10-06-exploration/changelog.zh.md)、[社区回执](../../reports/evidence/exploration-release-2026-10-06/community.json)。


## 2026-10-05 功能扩展：REV-2070 已提交审核

原项目 **234 / pokewalk** 的 **REV-2070** 已提交审核（pending），尚未公开上线。上一公开版 **REV-2017** 已通过审核，之前的待审冲突解除。本次把八张新地图、八个主题秘境、冠军远征、地区研究和稀有伙伴奖励，以及 24 条栖息地分路、地区等级和追踪图标修复一起提交。

源码 **`68ffedd`** 已合并并推送 main，[固件 CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37333984955) 全部通过。[GitHub Release v2026.10.05-expansion](https://github.com/Luobata/ESP32-PokemonGo/releases/tag/v2026.10.05-expansion) 已公开，完整安装包、保档 USB 更新包和 manifest 的服务端摘要与本地一致。社区双语介绍、使用说明、增量日志、games 分类、源码地址及完整固件摘要已回读一致。保留战斗封面、赤红，配上海岛探索、分路选择及主题通关，共五张经过查看的文件随请求上传；publisher API 未返回待审图库，未核对服务器端图片内容或数量。

世界存档 V18 支持 V5～V18，旧秘境 V3→V4 迁移和历史样本通过。11 项存档/地区/栈检查、456 项预览检查、本地编译及两层发布包校验通过，另执行发布分区保护检查。本轮使用隔离环境中的真实 ESP-IDF NVS 恢复/回滚，没有烧录、复位或覆盖玩家设备；先前构建的真机验证不算本构建验收。

新内容需升级固件。现有分区匹配设备可用保档 ZIP；社区完整安装会覆盖旧存档区域，必须先备份、安装后导入。存档工具本轮未变，在线 Pages、devbox 与离线 ZIP 已重新核对一致，无需重新部署；早期工具仍须先刷新或重新下载。

[中文增量说明](2026-10-05-expansion/changelog.zh.md) · [验证报告](../../reports/expansion-release-2026-10-05.md) · [社区回执](../../reports/evidence/expansion-release-2026-10-05/community.json) · [产物核对](../../reports/evidence/expansion-release-2026-10-05/package.json)。


## 历史准备：2026-10-05 地区扩展（当时有待审冲突，后续已提交 REV-2070）

代码 **`68d4276`** 已合并并推送 main；[固件 CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37236920109) 全部通过。[GitHub Release v2026.10.05-regions](https://github.com/Luobata/ESP32-PokemonGo/releases/tag/v2026.10.05-regions) 已公开，提供完整安装包、保档 USB 更新包和摘要。

新增八张第一世代地区地图、八个主题秘境及冠军远征，串联三方向探索、深层调查、地区研究、首通/挑战奖励与稀有伙伴保底。保持前 151 只宝可梦。各秘境共用八节点流程，专属机关与长剧情尚未加入。

世界存档升级到 V18，支持 V5～V17 迁移；旧森林秘境 V3 记录迁移到 V4。设备已使用本次发布 ZIP 完成仅应用更新，写前备份与写后数据区域核对通过；首次迁移和二次启动均正常，图鉴 91/151、队伍 6、伙伴 84、喷火龙 39 级 / 95111 经验及静音保持。**真机启动保档已验证，真机覆盖导入未执行**。当前存档网页与离线工具可处理 V18，Pages/devbox 资源与源码一致。

**社区本轮尚未提交。** 原项目 234 / pokewalk 的 REV-2017 仍在审核，公开版为 REV-1966；官方 publisher 要求先解决待审冲突。本轮固件、双语介绍/说明/增量日志和五张图片已完成本地预览，没有撤回或覆盖原提交。保留战斗封面、破坏光线和赤红图片，并加入当前海岛与主题通关预览截图。完整社区安装仍会覆盖旧存档区域，必须先备份再安装、随后导入；保档 ZIP 不能作为完整固件上传。

[增量说明](2026-10-05-regions/changelog.zh.md) · [实现与验证](../../reports/gen1-regions-2026-10-05.md) · [设备回执](../../reports/evidence/gen1-release-2026-10-05/device.json) · [社区准备](../../reports/evidence/gen1-release-2026-10-05/community.json) · [GitHub 发布回执](../../reports/evidence/gen1-release-2026-10-05/github-release.json)。

## 历史提交：2026-10-05 历史存档兼容与安全更新

原项目 **234 / pokewalk** 的 **REV-2017** 已提交审核（pending），尚未公开上线；上一公开版本为已通过审核的 REV-1966。新增 V5～V17 历史样本回归，修复早期保留字节的迁移校验，改善导入结果核对，提供只写应用的 USB 更新包。完整社区安装仍须先备份后恢复。

实现 **`0f76077`** 已合并并推送 main，[GitHub CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37232407985) 全部通过。[GitHub Release v2026.10.05](https://github.com/Luobata/ESP32-PokemonGo/releases/tag/v2026.10.05) 已公开，提供完整安装包、保留存档 USB 更新包及摘要。社区上传包与已验证本地应用一致；中英文介绍、使用说明、增量日志、源码地址和摘要已回读一致，原五张图片随新版提交。

本轮完成隔离环境中的真实 NVS 恢复验证。设备重新连接后，已使用上述发布版 `PokeWalk-update.zip` 完成仅应用更新；写入前的私有备份已回读校验，写入后受保护数据分区逐字节一致。启动版本为 `0f76077`，图鉴 90/151、队伍 6、总伙伴 83、喷火龙 39 级 / 92023 经验及静音设置保持。**真机启动保档已验证，真机覆盖导入未执行**，没有把隔离恢复当作真机导入测试。在线 Pages、devbox 资源及离线 ZIP 与当前源码一致，本轮网页无需再改动。

[增量说明](2026-10-05/changelog.zh.md) · [验证记录](../../reports/save-history-compatibility-2026-10-05.md) · [发布回执](../../reports/evidence/save-history-release-2026-10-05/community.json) · [发布包](../../reports/evidence/save-history-release-2026-10-05/package.json) · [设备状态](../../reports/evidence/save-history-release-2026-10-05/device.json)。

## 历史提交：2026-10-04 旧备份导入与牛奶回复

原项目 **234 / pokewalk** 的 **REV-1966** 已提交审核（pending），尚未公开上线；当前公开版为已通过审核的 REV-1909。本轮修复同设备跨构建旧备份导入，并将牛奶的对战回复改为至少 50 HP 或最大 HP 的一半，取较高者。

实现 `75e1f86` 已烧录当前设备并推送 main；后续测试日志宏的 GCC 兼容修复 `28d9cc2` 已通过全部 GitHub CI。发布包与设备烧录应用逐字节一致。设备图鉴 90、队伍 6、总伙伴 83、队首喷火龙 39 级 / 92023 经验保持，启动未见异常。跨版本导入的实际覆盖尚未在设备上执行，已通过生产解码、迁移、暂存边界和断电故障注入测试。

GitHub Pages、在线离线工具 ZIP 及 devbox 服务已更新，运行资源摘要与源码一致。用户需要同时更新设备固件并刷新网页或重新下载离线工具；原备份不用转换。社区双语内容和固件摘要回读一致，原五张图库随新版提交。

[发布说明](../../reports/release-notes-2026-10-04.md) · [社区回执](../../reports/evidence/save-import-milk-2026-10-04/community.json) · [设备回执](../../reports/evidence/save-import-milk-2026-10-04/device.json) · [网页部署](../../reports/evidence/save-import-milk-2026-10-04/save-manager.json) · [GitHub CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37189944977)

## 历史提交：2026-10-03 电量、闪光与秘境伙伴

原项目 **234 / pokewalk** 的 **REV-1909** 已提交审核（pending），尚未公开上线；公开版仍为已通过审核的 1074。本轮包含菜单/照料电量显示与开关、满背包成就领取修复、按获取渠道提高闪光概率、秘境通关发现可捕获伙伴。

游戏实现 `ec3d667` 与跨平台测试修复 `e80f241` 已推送 main。发布包来自干净提交 `e80f241`，GitHub CI 全部通过；官方固件结构与本项目保护分区校验通过。五张原图库图片随新版提交；双语介绍、使用说明、更新日志、固件大小与 SHA-256 已回读一致。图库图片内容未从待审接口重新下载验证。

[社区回执](../../reports/evidence/battery-inline-2026-10-03/community.json) · [GitHub CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/37134045483) · [创作者工作台](https://ai-passport.folotoy.cn/account/?project=234)。

[中文更新日志](2026-10-03/changelog.zh.md) · [使用说明](2026-10-03/instructions.zh.md) · [完整发布说明](../../reports/release-notes-2026-10-03.md)。

## 历史提交：2026-09-19 亮度、配网与备份修复

原项目 **234 / pokewalk** 新版本 **1074** 已提交审核（pending），上一版 815 已通过审核。新增可持久保存的 10%–100% 亮度设置，修复 Wi-Fi 配网「Setup is not active」误报，以及网页/离线工具拒绝当前存档版本的问题。工具支持后续沿用现有备份格式和布局的存档版本；导入仍要求同设备、相同固件构建。

实现 `d080936` 已推送 main，固件 CI 与 Pages 发布通过；网站及离线 ZIP 与源码一致。当前设备已保留进度烧录，图鉴 90、伙伴总数 83、喷火龙 39 级 / 92023 经验保持，静音开启。亮度调整、重启/唤醒恢复与真实 USB 备份验证通过。手机首次配网和 NTP 完整流程、不同亮度功耗尚未实测。

此次使用社区独立「使用说明」和「更新日志」字段，增量日志仅包含本轮变化，当前介绍保留宣传片及历史说明链接；现有五张图片完整随新版提交。双语文本、分类、固件摘要已回读核对；待审图片接口需要网页登录，未完成图片下载回读。

[中文增量说明](2026-09-19/changelog.zh.md) · [使用说明](2026-09-19/instructions.zh.md) · [社区回执](../../reports/evidence/settings-fixes-2026-09-19/community.json) · [设备与验证](../../reports/settings-fixes-2026-09-19.md) · [GitHub CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/35372401070)。

## 历史提交：2026-09-15 待机省电与稳定性

原项目 **234 / pokewalk** 新版本 **815** 已提交审核（pending），上一版 804 已通过审核。包含音频经校验休眠与停时钟、音频事件等待、熄屏静止时 30→60 秒扫描、显示/音频初始化回滚和应用区增加 256 KiB；其余数据分区地址保持。原五张图片、宣传片与历史更新要点保留；中文介绍按接口 4000 字符上限压缩，完整说明仍在仓库。

核心实现 `67baf1a`，设备/社区发布构建源码提交 `eb9a5d0`；后续仅测试断言排版修复的 `4fdaad9` 已通过 [GitHub CI](https://github.com/Luobata/ESP32-PokemonGo/actions/runs/34977293826)。两层固件校验通过，设备三段烧录核验、启动音频休眠寄存器回读和熄屏唤醒日志均通过；图鉴 56、总伙伴 52、暴鲤龙 27 级 / 31002 经验保持，静音开启。非静音听感与实际功耗未实测，不承诺具体续航增幅。

[发布说明](../../reports/release-notes-2026-09-15-power.md) · [社区回执](../../reports/evidence/power-update-2026-09-15/community.json) · [设备回执](../../reports/evidence/power-update-2026-09-15/device.json) · [CI](../../reports/evidence/power-update-2026-09-15/ci.json)。

## 历史提交：2026-09-15 徽章探索、离线体能与熄屏修复

原项目 **234 / pokewalk** 新版本 **804** 已提交审核（pending），上一版 631 已通过审核。代码 `449d6a3` 已合并并推送 main；包含八项徽章活动、随机追踪轮换、野怪等级调整、Wi-Fi 校时补回关机体能、面板休眠修复。新道具及搜寻事件增强只提交设计稿，未计入可玩功能。

双语正文、分类 games、项目标识及固件摘要已回读一致；五张原图库图片全部随新版提交，宣传片和历史版本说明保留。[发布说明](../../reports/release-notes-2026-09-15.md) · [社区回执](../../reports/evidence/release-2026-09-15/community.json)。

发布构建已再次烧录当前设备，三段写入校验通过；启动摘要匹配，图鉴 56、伙伴总数 52、队首暴鲤龙 27 级 / 31002 经验保持，静音开启。烧录前保存当前进度并备份完整 8MB，私有备份不入库。[设备回执](../../reports/evidence/release-2026-09-15/device.json) · [发布包校验](../../reports/evidence/release-2026-09-15/package.json)。手机首次配网、NTP 与关机补算的完整实机流程以及实际待机功耗仍待验收。

## 历史提交：2026-09-14 USB 存档管理

项目 234 / pokewalk，版本 **631** 已提交审核（pending）。新增设备备份与确认导入、覆盖前自动备份、文件校验及重启恢复；当前仅支持同设备、同固件构建。代码已合并 main（`80ae06d`），英文说明按社区上限压缩（`f884933`）；五张原展示图、宣传片链接及历史更新说明保留。双语正文、分类 games、固件摘要和图库回读一致。[发布说明](../../reports/release-notes-2026-09-14.md) · [回执](../../reports/evidence/usb-save-backup/community-release.json)。上一版 624 已审核通过。

GitHub Pages 在线入口已部署：https://luobata.github.io/ESP32-PokemonGo/ 。通过 HTTPS 直接在桌面 Chrome / Edge 授权目录与 USB，无需 Python、内网或本地服务。网页变更推送 main 后自动发布；存档留在用户电脑。线上资源摘要、脚本 MIME 和浏览器入口已核对。[部署回执](../../reports/evidence/usb-save-backup/github-pages.json)。

开发存档服务已部署 devbox，内网入口 http://10.37.197.13:8767/ 。普通 HTTP 入口提供本地工具 ZIP；下载并启动后，在 localhost 使用浏览器 USB 与目录授权，不需要开发机 SSH 权限。工具不上传存档。本次仅更新网页分发方式，社区固件仍为版本 631。按用户要求追加的字节内网存档工具评论已提交审核，页面回执为「提交成功，审核通过后公开」。[评论回执](../../reports/evidence/usb-save-backup/community-comment.json)。

## 历史提交：2026-09-13 晚间

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

这证明产物结构通过官方检查，不等同于已经通过社区 BLE 安装/更新实测。当前工程目录与官方模板不同，因此不声称跑过官方完整 `tools/validate.sh --firmware`。合并固件的 NVS 区是空白填充，原有设备保留存档应先备份并使用保留存档的组件更新流程（本次新增导入暂存区，需要同时更新分区表与应用），不能直接拿完整固件覆盖旧存档。

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
