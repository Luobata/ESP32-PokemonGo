# tools/pipeline — 素材管线

把**初代 151 只宝可梦**的数据与 sprite 转成固件能直接用的紧凑格式，并核算 flash 预算。

**完全不依赖目标硬件**，是[硬件到手前可推进的工作](../../docs/07-roadmap.md#71-硬件到手前可做的四件事)之一。
零第三方依赖（自己解 PNG、只用标准库）。

> **项目范围：自用、不分发**（见 [docs/05-art-audio.md#54](../../docs/05-art-audio.md#54-如果将来想分发)）。
> 数据取自 PokeAPI，sprite 取自 PokeAPI/sprites 仓库，均为公开托管资源 ——
> 本项目不涉及 ROM 提取。

## 用法

```bash
# 1. 拉取数据与 sprite（带缓存，重跑不会重复请求）
python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1

# 2. 转成固件二进制
python3 tools/pipeline/convert_gen1.py --src /tmp/gen1 --out assets/

# 3. flash 预算核算
python3 tools/pipeline/budget.py
```

想目检某只转得对不对（**强烈建议做**，见下）：

```bash
python3 tools/pipeline/convert_gen1.py --src /tmp/gen1 --preview 25
```

会把 #25 皮卡丘的正面与背面以 ASCII 画在终端里（按原生尺寸）。

## 实测数据

| 项 | 结果 |
|---|---|
| 数据条目 | **151/151**，含种族值、进化链、capture_rate、habitat |
| sprite | **front 151/151、back 151/151**，零缺失 |
| 数据体积 | **7.1 KB**（32 B/条定长记录 + slug 与中文名池） |
| front（原生尺寸三档） | **88.2 KB** —— 40×40 有 48 只、48×48 有 48 只、56×56 有 55 只 |
| back @32×32 2bpp | **37.8 KB**（单张 256 B，151 只统一） |
| 调色板（10 普通 + 10 闪光 + 索引） | **0.32 KB** |
| **合计** | **133 KB，占 8MB flash 的 1.63%** |
| 拉取耗时 | 约 80 秒（并发 4，含 sprite） |

## sprite 的三个实测事实

### ① 用 gray 变体，不用默认路径

| 路径 | 实测 | 用不用 |
|---|---|---|
| `red-blue/{id}.png` | depth=2 + PLTE，4 色**彩色**（SGB/GBC 着色版） | ✗ |
| **`red-blue/gray/{id}.png`** | **depth=2、colortype=0、无 PLTE，真 4 级灰阶** | **✓ 已采用** |
| `transparent/{id}.png` | 96×96 upscale + depth=8 | ✗ 别用 |

gray 变体的灰度值 0~3 **就是** DMG 的 2bpp —— 转换只是重新打包位，
零有损步骤。彩色版还要多做一次 彩色→灰度 转换。

为此扩展了 `convert_sprites.py` 的 PNG 解码器支持 1/2/4 位色深
（低位深时多像素挤在一个字节里，filter 的偏移单位也要跟着变）。

### ② front 尺寸不固定，必须按原生尺寸存

实测 151 张 front 的 IHDR：

| 尺寸 | 数量 | 单张 | 段计 |
|---|---|---|---|
| 40×40 | 48 只 | 400 B | 18.8 KB |
| 48×48 | 48 只 | 576 B | 27.0 KB |
| 56×56 | 55 只 | 784 B | 42.1 KB |

RBY 按 5×5 / 6×6 / 7×7 tile 存精灵。**早期版本统一缩到 40×40，
等于把超梦、卡比兽这类大型宝可梦压小 30%，破坏了原版的体型对比。**

现在按原生尺寸分三段存放，记录里用 2 bit 存档位（flags 的 bit2-3）。
固件按档位算段内偏移，依然是 O(1) 寻址。

不统一 pad 到 56×56 的理由：那样要浪费约 28 KB，而分段只多花 2 bit/条。

back 则**151 只全部统一 32×32**，可直接按 id 索引。

### ③ 双视图刚好够用

原版每只只有 front 和 back，没有多角度，也没有 shiny（Gen 2 才引入）：

| 场景 | 用哪张 | 尺寸 |
|---|---|---|
| 遭遇野怪、图鉴翻页 | front | 40/48/56 三档 |
| 主宠待机（[4.3.4](../../docs/04-gameplay.md#434-待机画面即产品)） | back | 32×32 |

back 用于待机是因为**视角天然对**：你在它身后看着它。

**多帧动画初代没有**，GSC（金银水晶）才引入，且每只帧数不固定
（妙蛙种子 6 帧、皮卡丘 5 帧、超梦 4 帧）。真正的瓶颈不是 flash 而是
SPI 带宽与"屏幕不能常亮" —— 待机按"每次点亮的第一眼"设计，两三帧呼吸就够。

## 数据修正：还原初代属性

**PokeAPI 返回的是现代属性**，需要还原。妖精系是第六代引入的，
之后官方把一批初代宝可梦追认为妖精系。实测受影响的正好 5 只：

| # | 名字 | PokeAPI 返回 | 初代实际 |
|---|---|---|---|
| 35 | clefairy 皮皮 | fairy | **normal** |
| 36 | clefable 皮可西 | fairy | **normal** |
| 39 | jigglypuff 胖丁 | normal/fairy | **normal** |
| 40 | wigglytuff 胖可丁 | normal/fairy | **normal** |
| 122 | mr-mime 魔墙人偶 | psychic/fairy | **psychic** |

修正后主属性分布里 normal 从 22 涨到 24，且**不再出现任何非初代属性**。

初代 15 属性：一般/火/水/电/草/冰/格斗/毒/地面/飞行/超能/虫/岩石/幽灵/龙
—— 没有恶、钢（二代）与妖精（六代）。

### 初代只有一个 Special，且必须从 past_stats 读

初代不分特攻/特防，只有单一 Special。PokeAPI 把初代原值放在
`/pokemon/{id}` 的 **`past_stats[generation-i]`** 里。

**不能拿现代的 special_attack 替代** —— 实测 **46 只不相等**，差距很大：

| # | 名字 | 初代 Special | 现代 SpA | 现代 SpD |
|---|---|---|---|---|
| 113 | chansey 吉利蛋 | **105** | 35 | 105 |
| 72 | tentacool 玛瑙水母 | **100** | 50 | 100 |
| 96 | drowzee 催眠貘 | **90** | 43 | 90 |
| 6 | charizard 喷火龙 | **85** | 109 | 85 |

规律是初代 Special 通常等于现代的 **SpD**（官方拆分时把原 Special 留给了防御侧），
但也有例外（喷火龙 85 = SpD，而妙蛙种子 65 = SpA = SpD）。所以只能读 past_stats。

## habitat → biome 映射

PokeAPI 的 `habitat` 字段**只对初代有效**，恰好 9 种，
而且比 Tuxemon 的 terrains 更贴合本项目 —— `urban` / `cave` / `waters-edge`
能直接对上射频环境特征。

但只靠 habitat 会让 office/transit 存量过少（实测 13 和 8 只，全靠 cave 那 8 只撑）。
所以加了一层**属性提示**：urban 的 22 只里，超能系（凯西线）与电系（霹雳弹、
多边兽）明显更像"机房/办公区"，而喵喵、吉利蛋更像"住宅"。

这层同时呼应 [docs/03-spawning.md#32](../../docs/03-spawning.md#32-ssid-与-oui-是被低估的语义金矿)
的 OUI 语义（企业级 AP → 超能，运营商网关 → 电），两处保持一致。

**属性提示只在人造环境（urban/cave/rare）生效** ——
野生栖息地的怪不该因为是超能系就跑进写字楼，那会让 wild 与 office 的界限消失。

最终分布（一只可属多个 biome）：

| biome | 数量 |
|---|---|
| wild | 116 |
| residential | 41 |
| commercial | 27 |
| office | 21 |
| transit | 16 |

## 数据格式

两个产物都是**定长记录 + 独立字符串池**，让固件能 `base + id * size` 直接索引，
无需解析、无需动态分配 —— 把 flash 地址当数组用。

### gen1.bin

```
头部 16 B:  magic "GEN1" | version | record_size | count | pool_size
记录 32 B × 151:
   off  size  field
   0    2     name_offset      字符串池偏移
   2    1     name_len
   3    1     type_primary     初代 15 属性之一
   4    1     type_secondary   0xFF = 无
   5    1     biome_mask       5 个 biome 的位掩码
   6    1     capture_rate     原版数值直接用（皮卡丘 190，超梦 3）
   7    1     evolve_trigger   0=升级 1=道具 2=交换 0xFF=不进化
   8    1     evolve_to        目标 id（1~151），0 = 不进化
   9    1     evolve_level
   10   1     hp               种族值，原版 0~255 直接用
   11   1     attack
   12   1     defense
   13   1     special          初代单一 Special，取自 past_stats[generation-i]
   14   1     speed
   15   1     flags            bit0=传说 bit1=幻兽 bit2-3=front尺寸档(0:40 1:48 2:56)
   16   2     height           dm
   18   2     weight           hg
   20   2     zh_offset        中文名在字符串池的偏移
   22   1     zh_len           中文名 UTF-8 字节数
   23   1     palette_index    配色索引（低 4 位，10 套）
   24   8     reserved         预留：招式表偏移、图鉴描述偏移
字符串池: slug 段（英文）+ 中文名段，均靠 offset+len 定位
```

抽查验证（数值与原版逐条核对过）：

```
   # name        types         HP/At/Df/Sp/Sd   catch  evo         biome
   1 bulbasaur   grass/poison  45/ 49/ 49/ 65/ 45   45  升级#2@16   wild
  25 pikachu     electric      35/ 55/ 40/ 50/ 90  190  道具#26     wild
  93 haunter     ghost/poison  45/ 50/ 45/115/ 95   90  交换#94     offi,tran
 143 snorlax     normal       160/110/ 65/ 65/ 30   25  -           wild
 150 mewtwo      psychic      106/110/ 90/154/130    3  -           offi,comm ★
```

### gen1_front.bin（分段，因尺寸可变）

```
头部 8 B:   magic "FRNT" | version | segment_count(3)
段表 12 B × 3:  size | bytes_per_sprite | count | data_offset
段数据:     每项 = u16 id + 位图（段内定长）
            id 需显式存 —— 分段后 id 不再等于段内下标
```

### gen1_back.bin（定长，可直接按 id 索引）

```
头部 16 B:  magic "BACK" | version | width(32) | height(32) | per(256) | count(151)
位图 256 B × 151
```

两者的位图格式相同：2bpp，每字节 4 像素，高位在左（与常见 LCD 驱动一致），
0 = 最暗，3 = 最亮。

## 进化链的两个坑

**分支进化。** 走走可以进化成臭臭花或美丽花，一个 from 对多个 to。
初代分支很少，转换时只保留第一条。

**跨世代污染。** 美丽花（bellossom）是二代的，但 PokeAPI 的进化链里
它挂在初代走走下面。必须用 valid 集合过滤，否则会指向不存在的 id。

初代进化触发方式实测分布：**升级 52、道具 14、交换 4**。
交换进化的 4 只是胡地、怪力、隆隆岩、耿鬼 ——
这在单机自用场景下需要额外设计（[4.4 交换](../../docs/04-gameplay.md#44-交换与对战)当前延后）。

**跨代污染的一个具体例子**：进化链 #10 是 `pichu → pikachu → raichu`，
而皮丘是 Gen 2 的。不按 `id ≤ 151` 过滤，关都图鉴里会冒出皮丘、叉字蝠、幸福蛋。

## sprite 裁切踩的坑（值得一读）

处理 Tuxemon 素材时（现已弃用）连错三次，教训对任何 sprite sheet 都适用：

1. 按 `min(h,w)` 裁切 → 底部混进第二帧，一条龙下面又长出半条龙
2. 改成横向等分 → 还是有第二个图案，因为纵向也有帧
3. 改成 2×2 网格等分 → 腿被切掉了（帧内容不贴网格线）

**正解是按透明空隙分簇**（`split_frames_by_gaps`），而不是按名义网格等分。

> 教训：**转换器必须能目检。** 这三个 bug 全靠 `--preview` 的 ASCII 输出发现，
> 光看"413 张成功、232KB"这类统计数字完全看不出图是错的。

## 缩放的两个细节

**透明像素不计入区域平均。** 否则精灵边缘会被背景拉暗，
四阶灰下这个误差极明显（边缘糊掉一整圈）。

**保持长宽比，短边居中留白。** 直接拉成正方形会把立姿压变形，
低分辨率下很显眼。

## 中文名（已完成）

**151/151 全部拿到**，就在 PokeAPI 的 `species.names` 里（`zh-hans`），
不需要另找数据源。

151 个名字**共用 209 个不同汉字** —— 这个数字很关键，因为它决定字库预算：

| 点阵 | 209 字总计 |
|---|---|
| 12×12 | 3.7 KB |
| **16×16** | **6.5 KB** |

早先担心中文字体是 flash 大头，**完全不是**。可以直接上 16×16，比 12×12 清晰得多。
加上 UI 文案（菜单、提示语）估计再 100~200 字，总量仍不到 15 KB。

## 尚未实现


- **招式表** —— `reserved` 字段已留位。本项目的战斗系统尚未设计
- **图鉴描述文本** —— 同上
- **中文点阵字体子集化** —— 预算已算清（12×12 子集 14KB、全字库 118KB），
  需先定 UI 文案才知道保留哪些字
