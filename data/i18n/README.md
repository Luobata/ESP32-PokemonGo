# 简体中文 / 繁體中文 / English

设置中的界面语言覆盖菜单、剧情、动态消息、道具和配网页。简体和繁体保留「官方／怀旧」译名偏好；英文按物种及招式编号显示原版英文名称，切回中文后恢复原译名选择。只改变显示，不改变规则、编号、存档结构或动画时钟。

繁体转换来自 [OpenCC 1.1.9](https://github.com/BYVoid/OpenCC/tree/ver.1.1.9)，固定提交、文件摘要及许可证见 `opencc/`。`overrides.json` 保存游戏语境例外，例如「尼多后」。这是繁体字形转换，不宣称使用某个地区的完整官方中文译名。`generate_traditional.py` 按现有文案生成转换表和 PingFang TC 的 16×16 字形，来源摘要见 `glyphs.json`，简体原字库独立保留。

英文目录在 `en.json`；`english_sources.json` 列出必须覆盖的生产文案源。`english_names.json` 固定 Gold 的 251 个物种、251 个招式名称和源文件摘要。英文 ASCII 点阵由同一固定 Gold 来源的 `gold_font.png` / `gold_charmap.asm` 生成，少量标点沿用项目字形；输出摘要见 `latin_glyphs.json`。原作名称、美术素材不因本目录附带 OpenCC 许可证而改变权利归属。

英文翻译目录使用 Flash 字符串池、8 字节索引与两段摘要；生成时检查全目录无碰撞。运行时二分查找，不分配堆缓存。动态消息使用有界 `language_snprintf`，翻译格式及字符串参数；支持实际 UI 使用的整数、字符、字符串、固定宽度和 `.*` 字符串边界。剧情与说明按英文单词换行，名称、列表和按钮使用各自的空间限制。

新增文案后运行：

```sh
python3 tools/pipeline/generate_traditional.py
python3 tools/pipeline/generate_english.py
python3 tools/pipeline/convert_font.py
python3 tools/pipeline/verify_language.py
python3 tools/pipeline/verify_english.py
python3 tools/pipeline/verify_language_ui.py
```

繁体字形生成需要 macOS PingFang 和 Pillow；英文原作字形生成只需要 Pillow。两种 `--check` 不依赖系统字体，可在 Linux CI 检查已提交产物。英文回归使用实际 C 查表、格式化和名称代码，并检查所有目录项、ASan/UBSan、非 NUL 结尾的资产名称、缓冲边界和字形；UI 回归检查切换、保存失败、闪光队伍行、动态战斗/捕获以及横带一致性。真机仍需分别测量各语言的绘制成本和实际动画提交。

`pokewalk/language` 固定为 0 简体、1 繁体、2 英文。旧备份缺键时默认简体，未知值仅回退语言，不改变进度。保存失败保留当前选择。新键纳入真实 NVS 迁移、共享占用、满仓容量、导入覆盖回归；世界存档版本与 72 KiB 容器保持不变。
