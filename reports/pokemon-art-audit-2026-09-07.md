# 151 种正背图来源审计与水晶素材修复

当前已切换为固定 `pret/pokecrystal` 提交的 **151 张正面首帧 + 151 张 48×48 背面**，保留原始四档像素和原版普通/闪光配色。302 张源图与产物逐像素零差异；实际 `assets.c + render.c + screen.c` 的 604 次普通/闪光正背渲染也全部零差异。

## 原来的问题

实际嵌入的是 `gen1_front.bin` / `gen1_back.bin` / `palettes.bin`。旧拉取地址为 `PokeAPI/sprites/master/sprites/pokemon/versions/generation-i/red-blue`，没有固定上游提交；仓库的 web build manifest 只记录本地输入哈希，不能证明上游来源。

将 `/tmp/gen1c` 的 302 张缓存 PNG 对照固定 `pret/pokered` 提交 `a1a22aaf84d1675bcdbaeb194592379d586d838e` 的原始正背 PNG，形状逐像素一致。但已嵌入的 302 张图**全部**被 `fill_interior_white()` 改过：正面 44,570 个像素、背面 8,940 个像素从源白色 3 改成浅色 2，总计 **53,510 个源像素**。这不是零损失转换。原图参照来自 [pokered 正背图目录](https://github.com/pret/pokered/tree/a1a22aaf84d1675bcdbaeb194592379d586d838e/gfx/pokemon)。逐图计数保存在 [原始审计 JSON](pokemon-art-baseline-2026-09-07.json)。

旧普通配色为 10 套 RBY/SGB 分组配色；闪光配色是 HSV 色相旋转 140° 的项目生成结果。另存的 `gen2_*.bin` / `palettes2.bin` 没有被当前固件嵌入，且走同一内部白合并与自定义闪光转换流程，所以直接替换文件名也不能恢复原版。

旧 `assets_back_sprite()` 是 32×32 专用 API。当前旧资产为 32px 时不会错读；切换 48px 后它返回 NULL，旧调用页会缺图。P1/P4 的调用迁移由页面任务处理。新图统一由 `assets_back_sprite_info()` 提供实际宽高与跨度。

## 已实施的来源与映射

来源固定为 `7a7881d0d62e0ddbd82dcf10e7116807487ac651`。转换器检查每个输入文件的 Git blob 与该提交一致，并在 [素材来源清单](../assets/pokemon_art_sources.json) 保存输入/输出哈希、逐物种源路径、调色板和白色像素计数。

- 正面取 `gfx/pokemon/<name>/front.png` 的第一个原生方形帧，保持 40/48/56px；背面完整保留 `back.png` 的 48×48px。没有缩放后重新量化、内部填色或手画补图。
- 普通调色板遵循原版 `Makefile` 和 `tools/gbcpal.c`：合并 front/back 的 RGB5 色，固定白/黑端点，并处理烈雀、大嘴雀、大葱鸭、飞腿郎、飞天螳螂、迷唇姐、多边兽的 `--reverse`。核验器直接编译原版 `gbcpal.c` 作独立参照。[原版构建规则](https://github.com/pret/pokecrystal/blob/7a7881d0d62e0ddbd82dcf10e7116807487ac651/Makefile#L223)、[原版调色板生成器](https://github.com/pret/pokecrystal/blob/7a7881d0d62e0ddbd82dcf10e7116807487ac651/tools/gbcpal.c)
- 闪光的两个中间色直接读取每种宝可梦的 `shiny.pal`，不再由普通颜色推导。按完整 `(normal, shiny)` 配对去重，得到 **146 对**；两个普通配色相同的物种仍可保留不同的原版闪光颜色。[原版调色板表](https://github.com/pret/pokecrystal/blob/7a7881d0d62e0ddbd82dcf10e7116807487ac651/data/pokemon/palettes.asm)
- 原 RGB5 无损放入 RGB565，绿色 5→6 位使用位复制。图中 3 仍然是源白色；现有渲染器把它作为透明，因此源图零差异成立的前提是统一白底。本轮未添加 mask，也未声称非白背景下原白会保持不透明。

## 格式与接线

| 项 | 当前值 |
|---|---|
| 正面 | 40px ×48 种、48px ×46 种、56px ×57 种；90,730 B |
| 背面 | 151 张 48×48；86,992 B |
| 调色板 | 146 对普通/闪光 +151 个索引；2,499 B |
| 版本和嵌入名称 | FRNT/BACK/PALS v1 不变；继续使用 gen1_front/back、palettes 文件名 |

`gen1.bin` 只修改 150 条记录的 byte 23 配色索引；其他字节逐字节保持原样，包括玩法数值、flags、预留区和名字池。三地鼠 #51、白海狮 #87 的水晶正面从 48 变为 56px，因此 C 读取器按 FRNT 显式 ID 找图；web 的 `mons.fsize` 也从实际图像记录重建，不再依赖保留的旧 flags 尺寸提示。

`assets_palette_variant(set_idx, shiny, out)` 使用足够宽的内部偏移，原版闪光实际组合索引最高为 291；旧 `assets_palette()` 保留为普通配色包装。页面是否选闪光由主任务接线，不把加载了真实闪光表当作所有页面已经使用它的证据。

## 独立验证

复现命令：

```bash
python3 tools/pipeline/convert_pokemon_art.py --src /path/to/pokecrystal --check
python3 tools/pipeline/verify_pokemon_art.py --src /path/to/pokecrystal
```

正式资产目录已通过生成复核和独立验证。验证器使用 Pillow 解码原始 PNG，与转换器的 PNG 读取实现分开；普通配色由固定上游 C 工具生成，闪光直接取源文本。随后编译实际资产读取、sprite 绘制和横带 screen 实现，以白底 2 倍绘制全部普通/闪光正背图，跨越多个横带，并比较完整 RGB565 帧。

最终复跑已包含 FRNT 解析器的 40/48/56 尺寸限制与失败重载状态清理；以下 302/604 结果来自该修复后的 C 源码。复跑时 `assets.c` SHA-256 为 `2226a5ce7c99d4b32eb286db3d3a094fcf6420f723ef8ffa6a7ca4c36afb1cdd`，`render.c` 为 `cf330cf7062850b625c55caa9296881850f5b1cf896d98f006a0d2c9b0068f91`，`screen.c` 为 `a60cb43120d630f3222b3ecccc1e6824033900110c979e8461a9bcfeb0d9465e`。

- **302 张图、709,440 个源像素：0 索引差异。** 383,338 个白像素原样保留，包含外部画布及内部白。
- **151 种普通 +151 种闪光调色板：0 差异。** 包含全部反序例外与高索引。
- **604 次实际 C 渲染、46,387,200 个屏幕像素：0 差异。** ASan/UBSan 无错误，48px 背图、原普通包装与色号 3 的透明规则均已覆盖。
- 与转换前的 `gen1.bin` 独立副本对比，仅允许每条记录的 byte 23 变化，其余字节一致。

机器结果见 [验证 JSON](pokemon-art-verification-2026-09-07.json)。本检查只覆盖源素材、配色、读取和 sprite 像素路径；全页布局、浏览器 Canvas 对账和固件构建由主任务统一验证。这里只采用水晶正面首帧，没有实现原版全部 sprite 动画。**P6 的 32px 最近邻缩略图是缩小呈现，不能称源像素 1:1。**

原先可选的另一条路线是保留 RBY 图形并取消内部白合并、恢复明确的 RBY/SGB 配色，同时把闪光标成项目自定义。当前选择的是上述水晶路线，未混用两代正背图。
