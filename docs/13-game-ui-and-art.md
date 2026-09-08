# 统一金银界面与宝可梦素材

## 页面风格

P0–P6、P9 的实际固件页面统一使用白底、黑色像素字、灰色辅助文字、原版框 1 和黑色光标。`game_ui.c` 负责标题、底部三键框、状态量表；对战继续使用 `battle_hud.c` 的原版 HP、EXP 与消息框。两者复用同一套边框 tiles。八页继续通过真实 `play_*.c` → `render.c` → `screen.c` 渲染，浏览器只显示收到的 RGB565 像素。

标题左右边界为 x12 / x228，基线区域 y8–24。普通页面底部操作框位于 y280–320；对战保留 y240–320 的三行消息区。开场对白单独使用 y160–272 的四行消息框。列表和图鉴以留白和对齐区分条目，不给每个条目叠加外框。

照料和图鉴使用正面图。照料按整数 2 倍显示完整素材，图鉴为保持每页 20 只，将正面图最近邻取样为 32px 缩略图，因此缩略图不能声称逐源像素保留。待机和对战主宠使用完整背图，并从资产头读取真实尺寸，32px 对应 3 倍、48px 对应 2 倍，均为 96px。

## 验收范围

素材还原需核对固定上游的原图、原调色板、转换产物和实际 C 渲染。只对比浏览器与本地二进制不足以证明原作还原，因为两者可能共同消费已经改色或裁切的素材。普通与闪光配色也必须分别核对。

当前所有游戏页的底色为白色。2bpp 色号 3 表示原图白色与透明背景：在白底上可以还原原图的白色区域；若将来允许图片叠加在非白底上，需要额外的透明掩码，不能再次把内部白色改成浅色。

`tools/inspector/template.html` 的历史 JS 设计稿同步白底与真实素材尺寸，但保留各方向的旧布局。它不用于证明整页与固件同构；P7/P8 仍为未实现的设计稿。验收入口为 `tools/inspector/firmware.html`。

像素与交互测试不能替代物理 LCD 刷新、DMA 中断和色彩校准验证；本次不刷写设备。

## 当前素材

正背素材统一为 `pret/pokecrystal` 固定提交 `7a7881d0d62e0ddbd82dcf10e7116807487ac651`：151 张正面首帧与 151 张完整背图。正面保持 40/48/56px，背面为 48px；普通、闪光使用原版配色，共 146 对。源路径、输入与产物哈希记录在 [pokemon_art_sources.json](../assets/pokemon_art_sources.json)。

旧转换器将 302 张图中的 53,510 个内部白像素改成了浅色，新入口不再做此处理。普通配色复现原版 `gbcpal.c` 与七种 Kanto 反序例外，闪光直接读取原版 `shiny.pal`。C 根据 FRNT 显式物种 ID 查找素材，解决三地鼠、白海狮仍带旧尺寸提示的问题；异常的 41/256px FRNT 会被拒绝，失败重载不会留下旧索引。

P3/P4 野怪和 P6 已捕获条目按各自闪光状态选配色。主宠当前世界模型没有闪光字段，P1/P5 与对战主宠继续使用普通配色。图像库包含全部普通与闪光的正背图配色，不代表主宠闪光状态已经持久化。

```bash
python3 tools/pipeline/convert_pokemon_art.py --src /path/to/pokecrystal --check
python3 tools/pipeline/verify_pokemon_art.py --src /path/to/pokecrystal
/usr/bin/python3 tools/pipeline/verify_front_asset_validation.py
/usr/bin/python3 tools/pipeline/verify_firmware_preview.py
/usr/bin/python3 tools/pipeline/verify_battle_layout.py
```

统一改造的 native 构建为 `41d2c15b14d213e7cd94`。302 张源图、604 次 C 普通/闪光渲染、151 种实际对战摆放、848 次横带重绘检查通过；浏览器七页完整 Canvas 与独立 native 帧哈希一致。素材检查使用独立 PNG 解码与上游调色板工具，未把产物当作原图参照。

详细结果见 [本轮验收](../reports/gsc-ui-art-2026-09-07.md) 和 [素材审计](../reports/pokemon-art-audit-2026-09-07.md)。Inspector 已重新构建并通过输入/产物新鲜度检查。ESP32-C3 构建通过；应用 0x1826c0 字节能放入 3MB 应用分区，原有 1MB recovery 分区过小的警告仍存在，未改变分区或刷写设备。

## 捕获间距与彩色开场跟进

最新 native 构建为 `f9ee0c79a1bf99b90099`。捕获蓝条按 frame 1 的真实内沿居中：y217–232，上下各留 2px，三种球一致。大木博士替换为同一固定 Crystal 提交的原版 `gfx/trainers/oak.png` 及开场配色，56px 完整整数放大到 112px；原白保留，其他 8 项 UI 素材逐字节不变。

此次 848 次横带重绘检查与固件构建通过，P0/P4 实际浏览器像素已与独立 native 输出对账。截图与验证见 [跟进记录](../reports/evidence/capture-oak-2026-09-07/notes.md)，原图与原配色核对见 [彩色大木博士](../reports/oak-color-2026-09-07.md)。

## 居中和精灵球更新

公共页脚按真实字形墨迹在原版框内部居中，补偿 ASCII/CJK 字形留白。P1/P5/P6 的精灵内容按可见范围居中；P6 编号保持同一中心轴。整数倍正面/背面点阵与图鉴的中心采样方法均保留。

精灵球改用固定 Crystal 源点阵、OAM 与 BallColors 配色，原作三种球同形异色。4 个球条目与上游实际 gfx 工具输出对照，3 套配色和真实 C 渲染全部通过。成功态显示闭球。见 [本轮检查](../reports/starter-capture-followup-2026-09-07.md)。
