# 地图漫游：金银素材与人物行走

开发分支 `codex/radar-field-maps`。本轮只调整 P22 的图块、人物、镜头、碰撞路径和对话框；不修改已经实现的遭遇概率、观察记录、消耗、冷却或剧情资格。本文初次记录时未烧录、未发布；同日用户追加烧录要求后的结果见 [真机验收记录](radar-fieldmaps-hardware-2026-10-25.md)。

## 素材及交互

- 原始素材固定为 [pret/pokegold 656583c](https://github.com/pret/pokegold/tree/656583c939d30f920a316177311a502dd222b57c/gfx/tilesets)：Johto、Park、Tower 的 8×8 图块，原 metatile 组合、日间颜色与碰撞表。主角 Chris、研究员、捕虫少年采用原始 16×16 站立/步行帧，左右翻转和上下交替脚遵循 `data/sprites/facings.asm`。
- 使用整数 2 倍像素；地图视口 224×184，摄像机跟随主角。三个 16×14 行走格场景是 PokeWalk 的紧凑布局，不是对金银完整地图或全部地图规则的移植。
- 遗迹呈现树丛、岩壁、洞口和告示；公园呈现大树、围栏、花丛、长草和池塘；烧焦塔呈现木地板、石柱、塌落区域和楼梯。调查地点、说明及操作提示使用现有 Gold frame-1 对话框，仍可接续已有活动。
- A/B 选地点，C 行走、到达后 C 互动，长按 B 返回。目标位置是对象旁的可通行格；预计算路径绕开树、水、墙和 NPC。所有目标互通，最长 12 格约 1.92 秒。摄像机和身体运动只按经过时间采样，步态四姿势按每四个 GBC VBlank 选择；保持原 50 ms UI 采样周期。
- `compile_field_maps.py` 从原始素材可重现生成 `field_map_assets.h`；源文件 SHA、配置 SHA、产物 SHA 全部登记。无源码缓存的 CI 校验提交产物与配置摘要，有源码时额外重新转换对比所有字节和碰撞路线。

## 验证

- 桌面构建：`96a2130af6bebc864b21`。
- `compile_field_maps.py --check`：已使用固定 Gold 源码重新生成比较，三图所有目的地与出生点互相可达，无路径穿越 NPC/水域/墙壁。
- `verify_field_map_art.py`：412 帧生产 C 条带输出与独立的整张场景像素参考逐像素相等，覆盖 16 个方向/步态组合、四方向镜头移动、边缘裁切、精灵透明和遮挡。
- `verify_field_adventure_ui.py`：518 次生产页面像素检查，覆盖三图观察/搜寻/失败重试/活动接续、熄屏与延迟回调；第一段绕告示的行走在 40/80/160 ms 回调下同为 640 ms。
- 其余 20 页、80 帧与上一版 `5f07db342c1afe6de3cb` 像素相等，包括雷达、战斗、捕获、剧情和活动；新增字库文字未改变既有字形。
- `verify_field_adventure.py` 和 `verify_save_import_compatibility.py` 再次通过。本轮继续使用 V32 的 39,976 字节记录、V5～V32 历史迁移、原分区和格式 4 的 72 KiB USB 容器，没有新增持久化字节。上轮存储/USB/NVS 全套验证仍见雷达地图开发记录，本轮没有把它们重新标为新的真机测试。
- `fw.sh build` 通过：应用 3,227,920 B，较上一版增加 12,576 B；factory 仍余 179,952 B，分区保持 8 MiB 布局。应用 SHA-256：`d15fff85e99fa079302fd55f448aa6f0e78a759dc5930861501a397d020d3a9a`。构建日志关于独立 recovery 分区放不下游戏应用的提示不涉及实际 factory 写入，本轮未打包也未写入 recovery。
- `verify_save_stack.py` 通过：地图页面最大单函数栈 176 B，核心 160 B；无新增动态分配或全屏缓冲。图块/路线/调色板均为只读 Flash 数据；RTC codec 仍为 7,792 B，RTC 总余量 328 B，IRAM 79,360 B。

证据：[三图预览](evidence/gold-field-ui-2026-10-25/maps-overview.png)、[像素参考检查](evidence/gold-field-ui-2026-10-25/art-check.json)、[交互检查](evidence/gold-field-ui-2026-10-25/ui.json)、[其他页面对照](evidence/gold-field-ui-2026-10-25/unrelated-pages.json)、[栈预算](evidence/gold-field-ui-2026-10-25/stack.txt)。

本文初次记录时尚未做真机 LCD 帧间隔、Wi-Fi 后堆余量、音频、导入覆盖验收。后续已完成的范围、实测结果与未测部分均单独记录在上述真机验收报告；静态构建与桌面像素相等不能证明这些项目通过。
