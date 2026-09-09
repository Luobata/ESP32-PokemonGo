# S25 · 原作执行轨迹接入

本轮将全部191招的正常命中／蓄力主动画换为金银原作执行生成的显示轨迹。此前的通用属性图元、手写直线和冲浪直条色带不再用于这些主动画。失败、免疫和跳过回合仍走旧的反馈路径；没有把这些分支标成原作还原。

## 来源与生成

使用 `pret/pokegold@656583c939d30f920a316177311a502dd222b57c`，RGBDS 1.0.3 从源码构建。ROM SHA-1 与仓库校验表一致：`d8b8a3600a465308c9953dfa04f0081c05bdcb94`。PyBoy 2.7.0 只在离线生成时执行原作的动画指令、对象回调、帧集和背景回调；固件不包含ROM，也不运行Game Boy模拟器。

离线执行用同步拷贝代替VBlank分批传输，用显式逻辑帧推进代替等待VBlank，禁用音频输出调用；帧序列、对象函数和背景函数使用原机器码。OAM循环处的观察钩子保留各对象原点，防止将一个多图块对象逐块映射到竖屏而破坏拼接。变身、替身恢复身体时使用符号引用，由运行时当前宝可梦提供身体图块。

生成覆盖191招 × 双侧 × 参数0/1 = 764个执行案例，导出476个8×8图块、9143个去重显示状态、395条去重轨迹。来源、哈希和逐案例帧数在 `assets/gold_fx_sources.json`。

```sh
# 固定源码检出及RGBDS构建见该仓库INSTALL.md；不得换用未知ROM。
python3 -m venv /tmp/pokewalk-original-animation-env
/tmp/pokewalk-original-animation-env/bin/pip install -r tools/pipeline/requirements-gold-animation.txt
/tmp/pokewalk-original-animation-env/bin/python tools/pipeline/extract_gold_animation_tracks.py --source /tmp/pokewalk-gold-review
python3 tools/pipeline/compile_gold_animation_tracks.py
python3 tools/pipeline/compile_gold_animation_tracks.py --check
```

生成的 `gold_fx_data.h` 是只读索引池，包括图块、OAM、精灵图块映射、扫描线状态和调色板；不分配全屏帧缓存。原始提取中间文件默认在 `/tmp/pokewalk-gold-tracks`。

## 渲染与节奏

- 原作逻辑约59.7275Hz执行，设备以45ms采样轨迹，不把原作每个wait都拉长到45ms。
- 多图块特效保留原对象内部的2×像素间距、翻转及OAM先后顺序；对象原点映射到竖屏战斗区域。
- 前／背面身体图块使用当前宝可梦素材及其调色板，按原作7×7／6×6布局重建遮罩和背景位移；复制到OAM的头部／脚部按同一身体坐标系绘制。
- 保留原作效果调色板，精灵调色变化映射到当前物种的颜色。场景整体闪色对HUD也生效；消息框仍不覆盖。
- 野战、训练家战、后台使用同一C实现。出场、经验和回合间停顿仍按原90ms节奏推进，主动画刷新改为45ms；HP变化在主动画结束后的受击阶段开始。
- 保留项目的双侧三次受击闪烁，每次隐藏／显示90ms。原作敌方闪烁、我方震屏的差异仍未逐项还原。
- 后台按实际总帧数播放，支持超过63帧的招式。选择和拖帧增加响应版本校验，旧请求不能把新选项或新帧覆盖回去。

## 验证与边界

通过764个原作执行案例、78536帧边界／清屏／状态不变检查、6112次真实P3的脏矩形与完整重绘比对、118项训练家换宠出场回归。单独验证双方闪烁、冲浪波峰跨越两侧HUD、消息窗稳定、末尾恢复。固件构建和社区包保护布局检查通过，本轮未烧录。

这次完成的是全招式主动画的原作轨迹接入和美术表现替换，**不是整个Game Boy画面逐像素等价认证**。竖屏原点映射、绘制采样、HUD闪色合成仍是适配；源端参数2及以上、未命中／免疫、战斗多次调用同一动画和原作完整声音事件仍需要进一步对照。离线执行为显示数据提取环境，不是从原作完整战斗流程录屏；不能用本轮自身像素回归声称原作最终画面完全相同。

验收与代表性动图见 `reports/evidence/gold-animation-tracks-2026-09-09`。
