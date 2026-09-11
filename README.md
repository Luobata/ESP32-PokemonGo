# PokeWalk · ESP32-PokemonGo

在 FoloToy AI Passport 上运行的宝可梦像素同人游戏：探索路线、捕获与养成前 151 只宝可梦，组建队伍，挑战道馆、四天王和赤红。设备为 ESP32-C3、8MB Flash、240×320 屏幕、三键操作。

[宣传片（约3分43秒，含赤红彩蛋）](reports/video/pokewalk-story-red-2026-09-09/pokewalk-story-v3.mp4) · [玩法与架构文档](docs/) · [金银学习表核查](docs/systems/S21-auto-learning.md) · [社区发布说明](docs/release/community.md)

[完整流程故事版 V3（约3分43秒，含赤红彩蛋）](reports/video/pokewalk-story-red-2026-09-09/pokewalk-story-v3.mp4) · [赤红片段](reports/video/pokewalk-story-red-2026-09-09/red-epilogue.mp4) · [博士转场预览（10秒）](reports/video/pokewalk-story-transition-2026-09-09/oak-to-starter-preview.mp4) · [故事版试剪（1分59秒）](reports/video/pokewalk-story-2026-09-09/pokewalk-story.mp4) · 以皮卡丘和尼多娜的冒险串联捕获、成长、道馆与探索解锁。

## 已实现

- 四条探索路线：Wi-Fi 环境变化积累探索机会；体力随设备运行时间恢复。不是 GPS 定位，也不是实际计步。
- 探索补给条满格获得一次机会，最多24次；12位地图训练家每场消耗5点全局体能，低等级队员有经验追赶，路线研究与首次发现/捕获也能获得经验。
- 最多保留 5 个待处理遭遇；直接捕捉失败，敌方反击一次后可再次选择；主动开战后自动交锋。
- 六人队伍和 151 格仓库（换宠保留同类个体）；捕获、进化和闪光记录进入图鉴与成就。
- 战胜、战败、捕获均有经验；饱食、心情、亲密度影响经验、战斗和稀有遭遇。
- 招式随等级自动学习、保留进化前技能，不设四招上限和 PP。兼容的机器/遗传招式自动加入成长库，详见 S21。
- 道馆、四天王连战、冠军与赤红；解锁进度扩展稀有探索目标与道具获取。
- 音乐、技能音效、捕获成功短曲；静音和音量设置；60秒无操作熄屏、长按确认键熄屏。
- Web 原生预览编译相同的 C 页面/渲染代码，复用固件素材；Wi-Fi、NVS 和按键用隔离夹具，预览不会修改真实设备存档。

**招式范围如实说明：** 当前引擎支持 191 招（初代 165 招及 26 招二代招式）。金银前 151 只宝可梦在升级、TM/HM、遗传和进化前形态中涉及 238 种招式，仍有 48 种二代招式机制未实现；未实现项不会作为无效技能加入自动出招。机器学习资格按原物种表限制，普通皮卡丘不会凭空获得活动限定的冲浪。

招式逐项验收：启动预览服务后打开 [moves.html](http://127.0.0.1:8766/moves.html)，支持搜索、双侧出招、命中/未命中展示、实际结算和蓄力释放。详见 [本批招式与验收说明](docs/systems/S22-move-acceptance.md) 与 [原版动画数据对齐核查](docs/systems/S23-animation-source-alignment.md)。全招式还原目标见 [S24](docs/systems/S24-original-animation-restoration.md)，191招原作轨迹接入和当前边界见 [S25](docs/systems/S25-gold-animation-tracks.md)。

新增 [图鉴追踪、队伍经验分享与通关道馆重赛](docs/systems/S26-collection-and-rematches.md)：图鉴详情可追踪目标，匹配属性的队员助力探索，冠军通关后开放六只队伍的强化道馆。

## 三键操作

| 功能键 | 短按 | 长按 |
|---|---|---|
| A | 光标上一项 | — |
| B | 光标下一项 | 0.6 秒返回 |
| C | 确认所选操作 | 1.5 秒熄屏 |

所有页面统一使用光标选择，包括只有 1–3 个选项的页面。主页选择照料、菜单或遭遇后按 C；菜单进入图鉴、队伍、道具、探索等页面。长按 B 返回不会额外触发一次短按。

捕获页面 A/B 选择球，按下 C 立即投球，长按 B 返回。战斗中长按 B 打开逃跑/认输确认，再用 A/B 选择、C 确认；训练家战斗中 C 打开战术菜单。60 秒无操作自动熄屏，唤醒按键不会同时操作游戏。

主页同时显示当前等级的经验进度和探索补给。升级后显示等级变化与新学会的招式；分享经验升级的队员也会提示，招式仍自动学习、永不遗忘。提示等战斗/捕获动画结束后出现，C 继续、长按 B 关闭，多页可用 A/B 翻阅。

训练家与道馆战斗同样显示出场伙伴的经验条，换宠后同步切换。战斗结束先展示经验条增长、当前伙伴与队伍获得的经验，再进入人物对话、道具奖励和升级学招提示；保存失败可按 C 重试，不重复发放经验。详见[训练家经验反馈修复](reports/trainer-exp-2026-09-10.md)。

照料中的玩耍每次消耗 5 点体能，不足 5 点时禁止玩耍；喂食只消耗树果，体能为 0 时也可以喂食。

挑战消耗全局体能：路线切磋 5 点，道馆/赤红 10 点，四天王与冠军整轮 20 点（后续关卡不重复扣）。探索保持 5 点体能＋1 次机会；已发现野怪的战斗/捕捉不额外收费。入场保存成功后才扣，认输不退；训练家战败仅额外扣 5 点心情。低体能不再降低战斗能力，饱食和心情仍影响养成。体能上限 100，开机/熄屏待机每小时恢复 12 点，真正关机暂不恢复。详见[挑战体能与节奏验证](reports/challenge-stamina-2026-09-10.md)。

Web 预览支持 A / B / C，↑ / ↓ / Enter 分别映射到同样的三个按键。当前实现与验证见 [经验条、统一按键和升级提示](reports/controls-growth-2026-09-10.md)。

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

固件应用在 `firmware/build/PokeWalk.bin`，应用地址 `0x10000`。现有设备增量更新前备份 NVS，不能把应用文件当成从 `0x0` 烧写的合并固件。存档版本 V14，3664字节；真实设备备份、扫描原始数据与凭证不进入 Git。

已向 AI Passport 社区提交项目 `234`（PokeWalk），当前待审核，见[创作者工作台](https://ai-passport.folotoy.cn/account/?project=234)与[发布回执](reports/evidence/community-publisher-2026-09-09/submission-receipt.json)。社区上传使用通过官方校验的 `0x0` 合并固件、3:4 封面和双语介绍；审核通过后才公开展示。

## 来源与验证边界

宝可梦名称、角色、原作像素画及音乐素材各自来源见 `assets/*_sources.json` 和 `docs/05-art-audio.md`；不将原作素材声称为本项目原创或统一 MIT 授权。金银招式事实表来自固定提交的 [pret/pokegold](https://github.com/pret/pokegold/tree/656583c939d30f920a316177311a502dd222b57c)，本项目的自动学习等级、养成与探索规则属于适配设计。

宣传片从全新存档初始化开始，后续“成长后的旅程”使用隔离的演示存档展示功能，音轨来自逐帧游戏混音器。没有用真实玩家存档录制或注入测试进度。

构建、主机回归、真机启动及存档读回分别记录在 `reports/`。长期续航、真实步行环境下的遇敌速度、关机期间的时间恢复仍需后续验证；完全关机目前不补体力。

等级进化：达到物种所需等级后，将伙伴设为队首，在「菜单 → 照料」选择「进化」，按 C 确认。无需额外亲密度或探索值；升级后会提示，旧存档已达等级同样可用。[修复与验证](reports/level-evolution-2026-09-10.md)。

探索仅消耗5点体能；原探索次数改为可选情报加成，零情报也可探索。体能约2小时回满，训练家换宠列表显示等级和HP。[本次改动](reports/exploration-intel-2026-09-11.md)。

进化演出：等级、进化石与机器共用约8.5秒的原版八轮切换节奏和光球效果；成功后C继续，提交前长按B可取消。[实现与边界](reports/evolution-scene-2026-09-11.md)。
