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

会把 #25 皮卡丘的正面与背面以 ASCII 画在终端里。

## 实测数据

| 项 | 结果 |
|---|---|
| 数据条目 | **151/151**，含种族值、进化链、capture_rate、habitat |
| sprite | **front 151/151、back 151/151**，零缺失 |
| 数据体积 | **5.4 KB**（28 B/条定长记录 + 名字池） |
| front @40×40 2bpp | **59.0 KB**（单张 400 B） |
| back @32×32 2bpp | **37.8 KB**（单张 256 B） |
| **合计** | **102 KB，占 8MB flash 的 1.24%** |
| 拉取耗时 | 约 80 秒（并发 4，含 sprite） |

## 一个意外收获：原版 sprite 本来就是 4 色

实测 RBY sprite 的 PNG 是 **`depth=2`、`colortype=3`（4 色索引图）**，
调色板是 GB 绿 `(255,255,255) (165,214,132) (25,16,16) (74,165,90)`。

**索引值 0~3 直接就是我们要的 2bpp 四阶灰** —— 不需要转灰度、不需要量化。
这比处理彩色素材质量高得多（后者要经历 彩色→灰度→4级 两次有损转换）。

为此扩展了 `convert_sprites.py` 的 PNG 解码器支持 1/2/4 位色深
（低位深时多像素挤在一个字节里，filter 的偏移单位也要跟着变）。

## 双视图：初代只有两张，而且刚好够

原版每只**只有 front 和 back**，没有侧面或多角度。这恰好匹配本项目：

| 场景 | 用哪张 | 尺寸 |
|---|---|---|
| 遭遇野怪、图鉴翻页 | front | 40×40 |
| 主宠待机（[4.3.4](../../docs/04-gameplay.md#434-待机画面即产品)） | back | 32×32 |

back 用于待机是因为**视角天然对**：你在它身后看着它。

**多帧动画建议先不做。** 初代没有，GSC（金银水晶）才引入。
真正的瓶颈不是 flash 而是 SPI 带宽与"屏幕不能常亮" ——
待机按"每次点亮的第一眼"设计，两三帧呼吸就够。

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

另外初代**只有一个「特殊」值**，不分特攻/特防。转换时取 PokeAPI 的
special_attack 作为初代的特殊值。

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
记录 28 B × 151:
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
   13   1     special          初代只有一个「特殊」
   14   1     speed
   15   1     flags            bit0=传说 bit1=幻兽
   16   2     height           dm
   18   2     weight           hg
   20   8     reserved         预留：招式表偏移、图鉴描述偏移
字符串池: 紧密排列的 slug（UTF-8，靠 offset+len 定位）
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

### gen1_front.bin / gen1_back.bin

```
头部 16 B:  magic "SPRT" | version | width | height | bytes_per_sprite | count
位图:  2bpp，每字节 4 像素，高位在左（与常见 LCD 驱动一致）
       0 = 最暗，3 = 最亮
```

## 进化链的两个坑

**分支进化。** 走走可以进化成臭臭花或美丽花，一个 from 对多个 to。
初代分支很少，转换时只保留第一条。

**跨世代污染。** 美丽花（bellossom）是二代的，但 PokeAPI 的进化链里
它挂在初代走走下面。必须用 valid 集合过滤，否则会指向不存在的 id。

初代进化触发方式实测分布：**升级 52、道具 14、交换 4**。
交换进化的 4 只是胡地、怪力、隆隆岩、耿鬼 ——
这在单机自用场景下需要额外设计（[4.4 交换](../../docs/04-gameplay.md#44-交换与对战)当前延后）。

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

## 尚未实现

- **中文名字** —— 当前存的是英文 slug（bulbasaur）。中文名需另找数据源，
  且要配合中文点阵字体
- **招式表** —— `reserved` 字段已留位。本项目的战斗系统尚未设计
- **图鉴描述文本** —— 同上
- **中文点阵字体子集化** —— 预算已算清（12×12 子集 14KB、全字库 118KB），
  需先定 UI 文案才知道保留哪些字
