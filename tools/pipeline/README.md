# tools/pipeline — 素材管线

把 Tuxemon 的怪物数据和精灵图转成固件能直接用的紧凑格式，并核算 flash 预算。

**完全不依赖目标硬件**，是[硬件到手前可推进的工作](../../docs/07-roadmap.md#71-硬件到手前可做的四件事)之一。
零第三方依赖（自己解 PNG 与 YAML 子集，只用标准库）。

## 用法

```bash
tools/pipeline/fetch-tuxemon.sh              # 稀疏克隆素材（约 20MB）

python3 tools/pipeline/convert_monsters.py \
    --src /tmp/tuxemon/mods/tuxemon/db/monster \
    --out assets/monsters.bin --index assets/monsters.txt

python3 tools/pipeline/convert_sprites.py \
    --src /tmp/tuxemon/mods/tuxemon/gfx/sprites/battle \
    --out assets/sprites.bin --size 48

python3 tools/pipeline/budget.py             # flash 预算核算
```

想目检某张精灵图转得对不对（**强烈建议做**，见下）：

```bash
python3 tools/pipeline/convert_sprites.py --src ... --limit 4 --preview 3
```

会以 ASCII 把它画在终端里。

## 实测数据

| 项 | 结果 |
|---|---|
| 怪物条目 | **411 / 411 全部解析成功** |
| 怪物数据体积 | **12.9 KB**（24 B/条定长记录 + 字符串池） |
| 精灵图 | **413 张全部转换成功，零失败** |
| 精灵体积 @48×48 2bpp | **231 KB**（单张 576 B） |
| 转换耗时 | 约 6 秒 |
| **flash 已用** | **17.8%，剩 6.6 MB** |

## 一个被推翻的担心

我早先说过"中文字体和几百张精灵图很容易吃掉大半 flash"——**这是错的**。

实测：**12×12 中文全字库（6700 字）只要 117 KB**。之前那个判断是按矢量字体或
16×16 估的，点阵字体便宜得多。

所以 8MB 对这个项目**非常充裕**，17.8% 就装完了全部素材。
这反过来意味着精灵尺寸可以往大取——48×48 只占 2.8%，
即使上到 64×64（411 KB）也毫无压力。

## 数据格式

两个产物都是**定长记录 + 独立字符串池**，让固件能 `base + id * size` 直接索引，
无需解析、无需动态分配 —— 把 flash 地址当数组用。

### monsters.bin

```
头部 16 B:  magic "TXMN" | version | record_size | count | pool_size
记录 24 B × 411:
   off  size  field
   0    2     name_offset      字符串池偏移
   2    1     name_len
   3    1     type_primary     13 属性之一
   4    1     type_secondary   0xFF = 无
   5    1     stage            basic/stage1/stage2/standalone
   6    1     shape            14 种体型
   7    1     biome_mask       5 个 biome 的位掩码
   8    2     evolve_to        目标 id，0xFFFF = 不进化
   10   1     evolve_level
   11   1     catch_rate       0~255（原 float 量化）
   12   2     height           cm
   14   2     weight           kg
   16   2     sprite_index     与记录序号一致
   18   2     txmn_id          原始编号，便于回溯查证
   20   4     reserved         预留：种族值、稀有度权重
字符串池: 紧密排列的 slug（UTF-8，无分隔符，靠 offset+len 定位）
```

### sprites.bin

```
头部 16 B:  magic "SPRT" | version | width | height | bytes_per_sprite | count
位图 576 B × 413:  2bpp，每字节 4 像素，高位在左（与常见 LCD 驱动一致）
                   0 = 最暗，3 = 最亮
```

## Tuxemon 数据的两个意外收获

### ① 它用的是自研 13 属性，不是宝可梦的 18 属性

`normal / fire / water / wood / earth / metal / lightning / frost /
venom / shadow / cosmic / sky / heroic`

这对本项目是**好事**：自研属性名天然规避了 IP 问题
（[docs/05-art-audio.md#54](../../docs/05-art-audio.md#54-如果将来想分发)）。
所以属性系统可以直接沿用，不需要另起一套。

### ② 每只怪都标了 `terrains`，可直接映射 biome

这是素材管线里最有价值的一块——**省掉手工给 411 只怪分配 biome 的工作**。

但两套分类的"轴"不同：Tuxemon 的地形是自然向的（草原/丛林/雪原），
而我们的 biome 是城市向的（住宅/办公/商业）。
**一对一直译会让 wild 吃掉 88%、commercial 为 0**（实测过）。

所以按**射频环境的相似性**分配，而不是按字面意思。修正后的分布：

| biome | 怪物数 |
|---|---|
| wild | 362 |
| residential | 130 |
| commercial | 104 |
| office | 61 |
| transit | 45 |

每个 biome 都有足够存量（最少 45 只）。wild 仍最多，但这符合直觉。

## 精灵图裁切踩的坑（值得一读）

Tuxemon 的 sheet 是 128×88，我一开始以为是"横向 2 帧"，**连错三次**：

1. **按 `min(h,w)=88` 裁切** → 底部混进第二帧，一条龙下面又长出半条龙
2. **改成横向等分 64×88** → 还是有第二个图案，因为纵向也有 2 帧
3. **改成 2×2 网格 64×44** → 腿被切掉了

最后逐行统计非透明像素才搞清真实布局：左上帧占 **y∈[10,53]**，
而 `rows[:44]` 从 0 切，正好把 y∈[44,53]（腿部）丢掉。

**正解是按透明空隙分簇，而不是按网格等分**（`split_frames_by_gaps`）——
帧内容并不贴着名义网格线。

> 教训：**转换器必须能目检。** 这三个 bug 全是靠 `--preview` 的 ASCII 输出发现的，
> 光看"413 张成功、232KB"这种统计数字完全看不出图是错的。

## 缩放的两个细节

**透明像素不计入区域平均。** 否则精灵边缘会被背景拉暗，
四阶灰下这个误差极明显（边缘糊掉一整圈）。

**保持长宽比，短边居中留白。** 直接拉成正方形会把横向立姿压变形，
低分辨率下很显眼。

## 尚未实现

- **中文点阵字体子集化** —— 预算已算清（12×12 子集 14KB、全字库 118KB），
  但需要先定 UI 文案才知道要保留哪些字
- **DawnLike 素材转换** —— 与 Tuxemon 精灵图路径相同，可复用 `convert_sprites.py`
- **种族值** —— Tuxemon 这个版本的 YAML 里没有 stats 字段（`reserved` 字段已留位），
  本项目的数值体系本来也要重新设计
