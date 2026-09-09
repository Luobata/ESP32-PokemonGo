# PokeWalk · ESP32-PokemonGo

在 FoloToy AI Passport 上运行的宝可梦像素同人游戏：探索路线、捕获与养成前 151 只宝可梦，组建队伍，挑战道馆、四天王和赤红。设备为 ESP32-C3、8MB Flash、240×320 屏幕、三键操作。

[宣传片（2分09秒）](reports/video/pokewalk-promo-2026-09-09/pokewalk-promo.mp4) · [玩法与架构文档](docs/) · [金银学习表核查](docs/systems/S21-auto-learning.md) · [社区发布准备](docs/release/community.md)

## 已实现

- 四条探索路线：Wi-Fi 环境变化积累探索机会；体力随设备运行时间恢复。不是 GPS 定位，也不是实际计步。
- 最多保留 5 个待处理遭遇；直接捕捉失败，敌方反击一次后可再次选择；主动开战后自动交锋。
- 六人队伍和按物种存储的仓库；捕获、进化和闪光记录进入图鉴与成就。
- 战胜、战败、捕获均有经验；饱食、心情、亲密度影响经验、战斗和稀有遭遇。
- 招式随等级自动学习、保留进化前技能，不设四招上限和 PP。兼容的机器/遗传招式自动加入成长库，详见 S21。
- 道馆、四天王连战、冠军与赤红；解锁进度扩展稀有探索目标与道具获取。
- 音乐、技能音效、捕获成功短曲；静音和音量设置；60秒无操作熄屏、长按 C 熄屏。
- Web 原生预览编译相同的 C 页面/渲染代码，复用固件素材；Wi-Fi、NVS 和按键用隔离夹具，预览不会修改真实设备存档。

**招式范围如实说明：** 当前引擎支持 191 招（初代 165 招及 26 招二代招式）。金银前 151 只宝可梦在升级、TM/HM、遗传和进化前形态中涉及 238 种招式，仍有 48 种二代招式机制未实现；未实现项不会作为无效技能加入自动出招。机器学习资格按原物种表限制，普通皮卡丘不会凭空获得活动限定的冲浪。

招式逐项验收：启动预览服务后打开 [moves.html](http://127.0.0.1:8766/moves.html)，支持搜索、双侧出招、命中/未命中展示、实际结算和蓄力释放。详见 [本批招式与验收说明](docs/systems/S22-move-acceptance.md) 与 [原版动画数据对齐核查](docs/systems/S23-animation-source-alignment.md)。

## 三键操作

| 场景 | A | B / 长按 B | C |
|---|---|---|---|
| 列表/菜单 | 确认 | 下一项 / 上一项 | 返回 |
| 野生遭遇 | 捕捉 | 开始自动战斗 | 尝试逃跑 |
| 队伍列表 | 查看详情；详情再次 A 设队首 | 选择成员 | 返回 |
| 队伍列表长按 A | 为当前位置打开仓库换入 | 仓库中选择 | 返回 |
| 训练家对战 | 回合结束后进入战术 | — | 认输确认 |

队伍详情长按 A 查看已学技能。战斗过程的换宠投球动画只作用于换宠的一方。长按 C 熄屏，唤醒按键不会同时触发游戏动作。

## 本地构建和预览

所需：ESP-IDF 5.5.3、C 编译器、Python 3；字库/素材管线另需 Pillow。运行所需的 7 个二进制素材和生成头文件随源码提供。

```sh
# 根据本机安装位置配置 ESP-IDF；脚本也支持已有 IDF_PATH。
source tools/device/idf-env.sh
tools/device/fw.sh build

# 同源网页预览
python3 tools/inspector/server.py --port 8766
# 打开 http://127.0.0.1:8766/firmware.html
```

```sh
python3 tools/pipeline/verify_gs_learning.py
python3 tools/pipeline/verify_trainer_sendout.py
python3 tools/pipeline/verify_combat_system.py
python3 tools/pipeline/verify_trainer_campaign.py
python3 tools/pipeline/verify_system_links.py
```

固件应用在 `firmware/build/PokeWalk.bin`，应用地址 `0x10000`。现有设备增量更新前备份 NVS，不能把应用文件当成从 `0x0` 烧写的合并固件。存档版本 V11，3664字节；真实设备备份、扫描原始数据与凭证不进入 Git。

社区上架需要另行验证的 `0x0` 合并固件、封面、源码地址和双语介绍，见发布说明。本仓库 push 不代表已经发布到社区。

## 来源与验证边界

宝可梦名称、角色、原作像素画及音乐素材各自来源见 `assets/*_sources.json` 和 `docs/05-art-audio.md`；不将原作素材声称为本项目原创或统一 MIT 授权。金银招式事实表来自固定提交的 [pret/pokegold](https://github.com/pret/pokegold/tree/656583c939d30f920a316177311a502dd222b57c)，本项目的自动学习等级、养成与探索规则属于适配设计。

宣传片从全新存档初始化开始，后续“成长后的旅程”使用隔离的演示存档展示功能，音轨来自逐帧游戏混音器。没有用真实玩家存档录制或注入测试进度。

构建、主机回归、真机启动及存档读回分别记录在 `reports/`。长期续航、真实步行环境下的遇敌速度、关机期间的时间恢复仍需后续验证；完全关机目前不补体力。
