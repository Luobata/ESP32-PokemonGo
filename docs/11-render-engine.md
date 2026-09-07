# 双端渲染：共享 C 场景配方与矩形输出

状态：D64 六问设计与元素级最小验证完成（2026-09-07）。共享 C 配方 → 固件横带后端 / 构建期矩形 payload → JS 软件 RGB565 后端，125 组输入、9600000 像素逐值一致。固件 build 与十三项回归通过。**这是逻辑像素缓冲的一致性证据，不是正式 inspector、Canvas 或真实 LCD 的整页 1:1 验收。**

## 1. 边界：共享“这一帧画什么”，设备继续负责“什么时候推屏”

建议建一个小的共享 C 场景层，不建通用布局引擎。输入是页面的一份只读状态快照，输出是有序绘制指令。布局、整数比例、颜色选择只在 C 配方中算一次。固件调用同一配方，web 的 JS 后端消费该配方导出的绘制指令；web 不重新计算 HP 百分比、边框厚度或元素位置。

本轮只实现 `P3 主宠 HP 条` 和一种原语 `rect(x,y,w,h,rgb565)`。坐标是整屏整数，矩形区间为 `[x,x+w) × [y,y+h)`，后画覆盖先画，颜色是逻辑 RGB565，不是 SPI 字节序。配方与协议在 `firmware/main/render_scene.h:7`、`:12`、`:17`。

不管理以下内容：

- 战斗、养成、按键与存档：它们决定状态，渲染只读取状态。现有 P3 从 `s_res` 与 `s_play_i` 取当前 HP（`firmware/main/play_battle.c:142`），无需让绘制层执行战斗。
- 帧时钟与脏带调度：由现有页面驱动。P3 tick 已按受击对象重画带 1/2（`firmware/main/play_battle.c:308`），接管它会扩大此次改动。
- LCD、DMA、串口截图和色序交换：保留在 screen 层。横带与 DMA 同步由 `firmware/main/screen.c:38`、`:109`、`:115` 管理；截图在交换后取数据（`:130`）。共享配方不能代替这些硬件机制。
- CSS 排版、自动换行、主题编辑器和约束求解器：当前文本是单行接口（`firmware/main/render.h:21`），引入换行会改变元素高度与带约束。本方案明确保持不自动折行。
- 资产重新绘制：共享资产字节与元数据，沿用现有格式。front 接口已返回尺寸，back 接口目前未返回尺寸（`firmware/main/assets.h:60`、`:63`）；不能凭显示目标尺寸推断源位图尺寸。

## 2. 共享定义与两端后端

| 层 | 唯一来源 | 固件 | web |
|---|---|---|---|
| 场景几何、颜色与状态到绘制的计算 | C 场景配方 + screen.h 色表 | 原生编译执行 | 消费同一 C 执行后导出的指令 |
| 状态 | 调用方给一份快照 | 传 cur/max | 原型重放对应快照的指令 |
| 输出 | 有序 rect，整数坐标、逻辑 RGB565 | 写横带 | JS RGB565 像素缓冲；Canvas 呈现后续接入 |
| 时间与更新范围 | 页面调度规则 | 保留现有 tick | 当前原型只验证帧，不验证时间轴 |

当前最小定义为 `SCENE_P3_PET_HP_X/Y/W/H`；C 配方最多输出三个矩形：完整边框底、内槽、有效填充（`firmware/main/render_scene.h:20`）。填充仍按原函数的 `dx < filled` 语义，内区宽度为 `max(0,min(w-2,filled-1))`；没有擅自改成“内槽宽乘百分比”。旧函数作为未改的野怪 HP 绘制函数保留（`firmware/main/play_battle.c:117`）。

必须纠正契约的一个起点：差异不只有坐标。现有 web `bar()` 使用 `Math.round((w-2)*pct/100)` 和 Canvas strokeRect（`tools/inspector/template.html:3522`），固件用 `w*cur/max` 的整数除法、再让边框覆盖（`firmware/main/play_battle.c:119`）。web `hp3()` 也仍按百分比判断（`tools/inspector/template.html:3577`）。仅共用 x/y/w/h 不能保证像素相同。

### web 如何得到 C 的输出

本轮是**构建/探针时原生执行 C → 导出指令 → 浏览器离线播放**。没有运行时服务器，payload 自带状态对应的指令；它没有能力在用户随意输入新 cur/max 后自行调用 C。该限制必须保留在交付声明里。

可先迁移已有的确定性演示时间线：它本来就在构建时导出页面数据（`tools/pipeline/verify_sim_pages.py:9`、`:20`）。由同一 C CLI 为每个快照导出指令，再播放即可。对于任意交互输入，要么本地开发服务调用该 CLI，要么把同一 C 编译为 WebAssembly。**本轮两者均未实现，不把 WASM 当成已验证依赖。** 若要求纯静态 web 任意交互，应先独立证明同一 C 的 WASM 编译/运行，然后再迁移；不能退回 JS 重写配方。

矩形消费只允许坐标裁剪与颜色格式转换，不允许求解布局。后续字体和 sprite 也应由共享 C 解码/测宽后输出像素行或矩形，避免后端各自实现 UTF-8、透明色和缩放；为优化体积改成位图指令时，必须另证解码一致。本轮没有新增这些原语。

### 32×3 → 48×2 怎么接住

现有 back 绘制调用在 C 与 web 各自写了缩放参数（`firmware/main/play_battle.c:226`、`tools/inspector/template.html:3793`）。目标定义应该是“资产 ID + view + 96px 显示尺寸”，资产元数据提供源宽高；共享 C 只在整数倍可缩放时计算 scale，32 得 3、48 得 2，不整除则显式报不能按该规则显示。后端只消费已经解析的绘制指令，因而不再改两处调用参数。back 的元数据接口和这条配方迁移均属于下一步，**当前 HP 原型尚未证明 sprite 路径**。

## 3. 与现有机制共存

### 编译期带断言

场景位置继续用 C 宏常量，不把 y/h 放到运行时配置文件中。本轮原有 `battle_pet_bar` 断言改为引用同一配方的 y/h（`firmware/main/play_battle.c:87`），仍由 `SCREEN_ASSERT_WITHIN_BAND` 的 `_Static_assert` 检查（`firmware/main/screen.h:24`）。没有弱化断言。

动态 x 与带保护可以共存；动态 y/折行高度不在当前设计范围。跨带 sprite 仍要使用 `SCREEN_ASSERT_ALLOW_CROSS_BAND` 并重画覆盖的所有带，宏本身不负责调度（`firmware/main/screen.h:31`）。

### 横带坐标与脏带重画

场景只输出绝对坐标。固件适配器与目标 band 求交后，将 y 减 band_y，再调用现有 screen_px；调用时栈上的 band_y 指针只在同步回调中使用，不可缓存（`firmware/main/render_scene_screen.h:6`、`:20`）。screen_px 的最终裁剪继续有效（`firmware/main/screen.c:75`）。

适配器不申请帧缓冲，复用既有 `screen_band` 的 240×80 RGB565 缓冲。像素对账的主机探针会拼完整帧，但这不是固件内存需求。P3 的 draw_all/tick 不改；固定的 HP 元素仍在带 2（`firmware/main/play_battle.c:299`、`:308`）。

### VAR_ELEMENTS 宽度检查

当前 `VAR_ELEMENTS` 包含模板、预算、回退格式和来源位置，检查也会代入回退模板（`sim/strings.py:451`、`:486`）。本轮没有文本元素迁移，不修改该表。

未来迁移文本时，C 负责实际测宽、回退与 x 计算，构建时导出同一预算/模板/来源 ID 供原有检查消费；运行时变化的名字不能预先算成一个 x。保留数据池最坏输入检查，不再手抄第二张场景布局表。这个导出桥尚未实现，不能提前宣称 VAR_ELEMENTS 已由新引擎生成。原始 render.c 还有嵌入字体链接符号，不是只去掉 esp_log.h 就能在任意后端运行（`firmware/main/render.c:42`、`:56`）。

## 4. 分步迁移与独立验收

1. **本轮 HP 元素**：两个小头文件；P3 一个 include、三个常量别名、一个断言参数、一个调用点，共影响 6 个源代码行。仅主宠 HP 改走共享配方，野怪原函数作为对照保留。不改 CMake，因为实现是内联头文件，不增加独立编译单元。
2. **在 web 接一个元素**：将确定性 P3 演示快照交共享 CLI 求绘制指令，在现有页面构建产物中导出，移除该元素的 JS 百分比绘制。验收是现有页面真实调用链上的 Canvas readback 对账。本轮禁止写 tools，因此未接入正式 inspector。
3. **sprite 一个元素**：先补统一资产尺寸元数据，再迁移 P3 back 的 96px 目标尺寸；验证 32/48 两套输入均保持相同显示边界、跨带重画完整。未满足之前保留现有路径。
4. **文本一个元素**：共享实际字体、测宽与回退，接通 VAR_ELEMENTS 的预算导出。用 D53 五字名 Lv100 边界验收，再按页面逐元素替换。
5. **需要任意输入的纯静态 web 时才加 WASM**：复用 C 配方，先验 RGB565/资产内存接口。没有需求就不引入额外工具链。

每步仅覆盖已迁移元素；未迁移部分继续沿用既有行为。不要把一次元素级通过当作整页通过，也不要用换设计主题掩盖既有像素差异。

## 5. 一致性验证、当前证据与失败形式

三段证据分开，不把结构性共享等同于所有后端必然正确：

1. **行为保持**：原生共享配方 + 实际横带适配器，与当前未改的 draw_bar 输出逐 RGB565 像素相同。探针从 play_battle.c 提取 draw_bar 编译，不只检验自己写的理想模型。
2. **后端一致**：C 导出已求值矩形 payload；Node 执行一个可移植的 JS `renderRects`，只做矩形裁剪与写 Uint16Array。将这份完整 RGB565 像素缓冲与原生四个横带拼帧比较。JS 不计算 cur/max、段色或布局，因而不是第二份 HP 实现；比较也不是相同二进制输出两次自比。
3. **实际显示链路**：Canvas 的 RGB565→RGB888 呈现、缩放、以及真实 LCD 传输仍需各自验证。逻辑像素相等不包含这些环节。screen_dump 截图取交换后数据（`firmware/main/screen.c:130`），主机测试不能替代它。本轮没有烧写或真机结果。

当轮第 1、2 段各比较 125 个快照、9600000 个 RGB565 像素，均完全相同。输入包括 cur=0..120/max=120（覆盖每个填充整数与段色边界）、max=0 两例、cur>max、最大 uint16_t 与极小比例。`cc -O2 -Wall -Wextra -Werror` 通过；JS 实际由本机 node 执行。

有意把消费的 payload 每个矩形 x 加 1，立即得到首个差异：frame=0，cur=0/max=120，x=112/y=192，RGB565低字节 expected=0、actual=240。反向控制证明消费端几何变化会被比较发现；未改生产文件或常跑门禁。

复现输出：

```text
native vs original draw_bar: 125 cases, 9600000 RGB565 pixels identical
JS rect consumer vs native band backend: 125 cases, 9600000 RGB565 pixels identical
negative payload x+1 detected: frame=0 cur=0 max=120 x=112 y=192 byte=0 want=0 got=240
unique_rectangle_outputs=119 payload_bytes=11518
```

`bash tools/device/fw.sh build` 当轮 exit 0，十三项既有回归逐项 exit 0。构建仍警告 recovery 分区不足（0x1732e0 > 0x100000），本轮不修。日志在 `/tmp/pokemon-render-engine/build.log`、`regressions.json`；对账结果在 `result.json`。

### 为什么不重复 C 自比，也没有新增门禁

同一个 C 二进制对同一输入求值两次，再比较 JSON，仅能验证确定性/序列化，不能证明后端消费正确。本轮选择比较 JS 实际落到像素缓冲的结果：它多验证了指令顺序、裁剪、坐标与颜色写入，仍没有复制 HP 求解。

当前 `verify_ui.py` 验素材打包与点阵（`tools/pipeline/verify_ui.py:10`），`verify_sim_pages.py` 验导出 payload（`tools/pipeline/verify_sim_pages.py:15`）。本原型未接正式 inspector，所以不把独立对账列入常跑列表。以后接入正式 payload 时，可把这条元素对账挂入现有 verify_sim_pages 的显式渲染选项；没有理由先新增一个常跑门禁。本轮仅 `/tmp` 探针，源码在文末持久保存。

实现者在修改配方/后端时跑该元素对照，Hub 用同一命令独立复验。遇到失败输出状态、首个像素坐标、字节、期望与实际值，便于定位；不新增自动审批流程。

### 证据边界

最初 Canvas headless 探针超过60秒未返回，按合同停止。Hub 随后明确不再调浏览器，本轮改用无浏览器依赖的 JS 逻辑像素后端；未把超时忽略成“Canvas 已通过”。正式 web 页面没有接入这个后端，不能用本结果覆盖既有 template.html 的 bar()。

## 6. 代价与为什么不做得更大

本轮新增头文件 31+23=54 行，影响既有 P3 源代码 6 行；无动态分配、无常驻绘制列表、无新增固件整屏缓存。每次最多 3 个同步矩形回调，只有几个整数局部变量（`firmware/main/render_scene.h:17`、`render_scene_screen.h:20`）。

代价不能忽略：旧函数在 HP 条内写 1200 次像素，新配方满血时先画底再覆盖，最多 1200+944+944=3088 次写入，约 2.57 倍。但适配器在带外不逐像素循环，旧函数会遍历后由 screen_px 裁剪；全页重画四个带与只重画带 2 的收益/代价不同。**没有真机耗时证据，不声称性能改善。** 本轮 app 大小 0x1732e0，上一 D53 当轮为 0x1731d0，相差 272B；共享工作区可能同时有其他变化，不能把它全归因为本头文件。

虽然本轮两个逻辑像素后端已通过，真实显示链路和其它元素仍未覆盖。目前不建区域树、依赖求解器、布局 DSL、指令虚拟机、插件注册或新网络服务。原因不是“抽象不好”，而是尚只有一个元素经过两种逻辑像素后端验证；增加这些设施不会自动证明 Canvas、字体和传输一致。先将该元素接入正式 web 消费路径并验证，再决定通用化程度。

本设计最重要的取舍是：**共享计算与消费指令可以消除 C/JS 的两份求解，但任意状态的静态 web 仍需要 C 执行能力。** 当前原型只对预先求出的快照成立。若产品要求独立静态网页任意交互，而又不接受 WASM 或服务，就不能声称这种路径已满足目标；需要 Hub 与用户重新选边界。

### 预生成状态的扩展边界：不需要穷举所有原始输入

合同说 `(cur,max)` “无穷组合”，对这里的接口不准确：两项均为 uint16_t（`firmware/main/render_scene.h:18`），原始输入最多 2^32 组；虽然有限，逐个构建也不合理。更有用的是看**输出等价类**。

对固定120px HP条，颜色只取决于填充像素数，内区填充被边框限制。按共享 C 求值，当前125个覆盖边界的输入只产生119种不同矩形列表；本轮包含cur/max元数据的payload总大小11518字节（`/tmp/pokemon-render-engine/result.json`，可用文末脚本再生成）。连续比例被显示器像素离散化，多个输入本来就有同一显示结果，因此“预生成”不必等同于“近似采样”。

但输出表小**不等于任意输入已能自动选表**。计算 filled 或把任意 cur/max 映射成119类，仍是求解；不能为了查表方便在JS再抄 `w*cur/max`。允许的三种用法为：

- 已确定的演示时间线：构建时对每个实际状态执行 C，给该状态关联准确指令，web 逐帧播放，不做近似插值。
- 用户只在已导出的场景/状态之间选择：可按状态 ID 取指令。缺失的状态明确不支持，重新构建再加入。
- 任意输入或真实实时状态：必须有共享 C 执行入口（本地服务、设备输出或同源码 WASM）；本轮未实现这些入口。不能静默改由 JS 求解。

这个边界对字体/sprite更重要：任意文字、资产、位置与动画会令组合数量剧增，不能把整个游戏的每个像素帧穷举成查表。保留共享算法，按实际快照按需求值；先对已有确定性演示迁移，实时动态场景等共享执行能力具备后再迁移。若产品不接受这样的边界，应先决定是否引入 WASM/服务，而不是扩大静态输出表。

### 不做 JS 侧求解的明确结论

Hub 最终采纳 C 唯一求解、JS 消费已求值指令，并保留“不调浏览器、不写第二份JS求解、不新增常跑门禁”。本设计按此交付。曾提出的“纯JS输入cur/max计算矩形，再与C比”不采用：双实现加对账能发现漂移，但仍重新制造了两份维护点。

同样，“web 不求解”只保证配方的单一来源，不能保证后端结构上绝无分叉。裁剪、覆盖顺序、色序仍可错；本轮x+1负向对照就是这种可观测错误。生产调用点确实已替换，不是只重定向常量（`firmware/main/play_battle.c:240`）。

## 复现

当前探针：

```sh
python3 /tmp/pokemon-render-engine/run.py
```

依赖本机 cc、Python 3 与 node，不启动浏览器，也不需要npm依赖。脚本在/tmp生成C探针、payload与JS消费后端；文末是完整持久副本，清理/tmp后可按下面命令恢复。移仓时调整 REPO 路径即可。

```sh
python3 - <<'PY'
from pathlib import Path
s = Path('docs/11-render-engine.md').read_text()
code = s.split('<!-- D64_PROBE_BEGIN -->\n```python\n', 1)[1].split('\n```\n<!-- D64_PROBE_END -->', 1)[0]
p = Path('/tmp/pokemon-render-engine/run.py')
p.parent.mkdir(parents=True, exist_ok=True)
p.write_text(code + '\n')
PY
```

<!-- D64_PROBE_BEGIN -->
```python
#!/usr/bin/env python3
"""One-off D64 native/band/JS rectangle consumer comparison; not a repository gate."""
import json, pathlib, subprocess

REPO = pathlib.Path('/Users/bytedance/luobata/ESP32-PokemonGo')
OUT = pathlib.Path('/tmp/pokemon-render-engine')
OUT.mkdir(exist_ok=True)
source = (REPO / 'firmware/main/play_battle.c').read_text()
# Keep the current, unmodified wild-bar implementation as the independent oracle.
legacy = source[source.index('static void draw_bar('):source.index('static void draw_band(')]
wrapper = r'''
#include <stdio.h>
#include <stdbool.h>
#include <stdlib.h>
#include "render_scene_screen.h"
static uint16_t band[SCREEN_W * SCREEN_BAND_H];
void screen_px(int x,int y,uint16_t c) {
 if (x>=0 && x<SCREEN_W && y>=0 && y<SCREEN_BAND_H) band[y*SCREEN_W+x]=c;
}
static void emit(void *ctx,int x,int y,int w,int h,uint16_t c) {
 (void)ctx; printf("%d %d %d %d %u\n",x,y,w,h,c);
}
'''+legacy+r'''
int main(int argc,char **argv) {
 if(argc!=4) return 2;
 int mode=atoi(argv[1]); unsigned cur=(unsigned)atoi(argv[2]),max=(unsigned)atoi(argv[3]);
 if(mode==2) { scene_p3_pet_hp(emit,NULL,cur,max);return 0; }
 for(int by=0;by<SCREEN_H;by+=SCREEN_BAND_H) {
  for(int i=0;i<SCREEN_W*SCREEN_BAND_H;i++) band[i]=C_BG;
  if(mode==0) scene_screen_p3_pet_hp(by,cur,max);
  else draw_bar(SCENE_P3_PET_HP_X,SCENE_P3_PET_HP_Y-by,SCENE_P3_PET_HP_W,SCENE_P3_PET_HP_H,cur,max);
  /* Explicit RGB565 little endian wire form; independent of host endianness. */
  for(int i=0;i<SCREEN_W*SCREEN_BAND_H;i++) { putchar(band[i]&255);putchar(band[i]>>8); }
 }
 return 0;
}
'''
(OUT/'probe.c').write_text(wrapper)
subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-I',str(REPO/'firmware/main'),str(OUT/'probe.c'),'-o',str(OUT/'probe')],check=True)
# Get canvas geometry/colors from C preprocessing, without a second literal table.
def macro(name):
 p=subprocess.run(['cc','-E','-P','-I',str(REPO/'firmware/main'),'-x','c','-'],input='#include "screen.h"\n'+name,text=True,capture_output=True,check=True)
 return int(p.stdout.splitlines()[-1].rstrip('uU'),0)
w,h,bg=map(macro,['SCREEN_W','SCREEN_H','C_BG'])
frames=[]
cases=[(i,120) for i in range(121)]+[(0,0),(100,0),(65535,1),(1,65535)]
for cur,maximum in cases:
 def call(mode):return subprocess.check_output([str(OUT/'probe'),str(mode),str(cur),str(maximum)])
 native,old=call(0),call(1)
 assert native==old,(cur,maximum,'native differs from original draw_bar')
 rects=[list(map(int,line.split())) for line in call(2).decode().splitlines()]
 frames.append({'cur':cur,'max':maximum,'rects':rects,'expected':native})
print(f'native vs original draw_bar: {len(cases)} cases, {w*h*len(cases)} RGB565 pixels identical',flush=True)

# The portable JS backend consumes rects only; no HP/layout calculation.
backend = r"""
const fs=require('fs');
const payload=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));
function renderRects(w,h,bg,rects) {
 const pixels=new Uint16Array(w*h);pixels.fill(bg);
 for(const [x,y,rw,rh,color] of rects) {
  const left=Math.max(0,x),right=Math.min(w,x+rw);
  const top=Math.max(0,y),bottom=Math.min(h,y+rh);
  for(let py=top;py<bottom;py++) for(let px=left;px<right;px++) pixels[py*w+px]=color;
 }
 return pixels;
}
const chunks=[];
for(const frame of payload.frames) {
 const rects=process.argv[4]==='shift'?frame.rects.map(([x,...rest])=>[x+1,...rest]):frame.rects;
 const pixels=renderRects(payload.w,payload.h,payload.bg,rects);
 const out=Buffer.alloc(pixels.length*2);
 for(let i=0;i<pixels.length;i++)out.writeUInt16LE(pixels[i],i*2);
 chunks.push(out);
}
fs.writeFileSync(process.argv[3],Buffer.concat(chunks));
"""
(OUT/'consume.cjs').write_text(backend)
payload={'w':w,'h':h,'bg':bg,'frames':[{k:v for k,v in f.items() if k!='expected'} for f in frames]}
(OUT/'payload.json').write_text(json.dumps(payload,separators=(',',':')))
expected=b''.join(f['expected'] for f in frames)
subprocess.run(['node',str(OUT/'consume.cjs'),str(OUT/'payload.json'),str(OUT/'js.rgb565')],check=True)
actual=(OUT/'js.rgb565').read_bytes()
def mismatch(a,b):
 if len(a)!=len(b):return {'expected_bytes':len(a),'actual_bytes':len(b)}
 for offset,(want,got) in enumerate(zip(a,b)):
  if want!=got:
   pixel=offset//2;frame=pixel//(w*h);xy=pixel%(w*h)
   return {'frame':frame,'cur':frames[frame]['cur'],'max':frames[frame]['max'],'x':xy%w,'y':xy//w,'byte':offset%2,'want':want,'got':got}
 return None
bad=mismatch(expected,actual)
assert bad is None,bad
print(f'JS rect consumer vs native band backend: {len(cases)} cases, {w*h*len(cases)} RGB565 pixels identical',flush=True)
subprocess.run(['node',str(OUT/'consume.cjs'),str(OUT/'payload.json'),str(OUT/'shift.rgb565'),'shift'],check=True)
negative=mismatch(expected,(OUT/'shift.rgb565').read_bytes())
assert negative is not None,'negative control unexpectedly matched'
print('negative payload x+1 detected: '+json.dumps(negative),flush=True)
unique=len({json.dumps(f['rects']) for f in frames})
summary={'cases':len(cases),'pixels':w*h*len(cases),'native_equals_legacy':True,'js_logical_rgb565_equals_native':True,'unique_rectangle_outputs':unique,'payload_bytes':(OUT/'payload.json').stat().st_size,'negative':negative}
(OUT/'result.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary),flush=True)
```
<!-- D64_PROBE_END -->


## 第 3 步实做：D78 P3 back sprite（2026-09-07）

本段追加实做记录，不覆盖前面 D64 的历史验证边界。P3 back 已迁移到共享矩形配方；正式 web 的 sprite 消费链本轮仍未迁移，web-coder 正在接第 2 步 HP 条，不能据此声称 sprite 已完成 Canvas 验收。

### 接线与资产尺寸

- `render_scene.h:12` 固定显示目标 x=8/y=140/size=96，`:41` 的 `scene_p3_pet_back` 接收2bpp数据、源宽高、抖动偏移与调色板，按32→3倍、48→2倍计算。色号3透明；每行相邻同色合成一个矩形，后端仍不解码或求缩放。不建sprite专用指令体系。
- `render_scene_screen.h:25` 调用现有rect横带后端；`play_battle.c`的P3主宠取图改用metadata API。原96px跨带断言保留，y/显示尺寸改引用配方常量，tick的带1+2调度没有改写。
- `assets.c:239` 从BACK头读取宽、高和per，接受32×32/48×48，并核对每记录字节数和总长度；索引步长不再写死256。`assets_back_sprite_info`（`:270`）返回指针及宽高，异常时清零输出。
- 兼容边界：旧 `assets_back_sprite` 仍是32px接口（`assets.c:263`），对48px返回NULL；P1/P5/P6等旧调用方尚未迁移。现有32px资产行为保持；不能直接全局换48px图集并宣称所有页已支持。这里验证的是P3和新增metadata路径，无新真实GSC资产进入仓库。

### 当轮专项证据

`python3 /tmp/pokemon-d78/sprite.py`，host `cc -O1 -Wall -Wextra -Werror`，exit0。

```text
real BACK: 755 full-frame comparisons identical to render_sprite_2bpp_wh
source=32 scale=3 bounds=[8,104)x[140,236) pixels=9216
source=32 actual tick shake phases=4: bands 1+2, incremental frame equals full redraw
source=32 negative missing band1 detected
source=48 scale=2 bounds=[8,104)x[140,236) pixels=9216
source=48 actual tick shake phases=4: bands 1+2, incremental frame equals full redraw
source=48 negative missing band1 detected
metadata stride/ID/truncation checks and unsupported size rejection passed
```

755=当前151张真实BACK图×5个抖动位置（含静止）。比较实际共享配方/横带适配器，与从render.c原样提取的旧2bpp解码器整帧输出。32/48边界用可控不透明夹具确保可测到完整显示边缘；四种色号与透明另作对照，并非声称两种不同原图的墨迹天然相同。

动画证明运行当前tick的抖动分支提取代码，记录draw_band调用并进行实际像素重画；32/48各4阶段都只重画带1和2，增量帧与目标相位的完整重画相同。临时副本故意漏上带时整帧不等，验证能抓到半幅残影；不是只grep代码。LVGL时钟、真实LCD与真机截图不在此host证据内。

### factor 同轮变更的边界（非渲染引擎职责）

`battle.c`只调整factor施加位置：先对有效attack/special作Q10缩放、下限1，再计算带+2的伤害公式。+2不被能力系数缩放；类型免疫和STAB仍按原流程处理。代表场景Lv12/A55/D60/P40从5→7，正常factor1保持10。

本轮144组每系数的实测：factor1前后0组改变；614与同Q10参考不符133→0；614与精确浮点0.6不符143→19，最大差3。后者源于614/1024<0.6，未改系数/容差，不能声称两端所有消沉伤害归零。提前取整还使5组比旧式低，但没有组超过同输入factor1伤害。

### 验收状态与剩余协同

- fw.sh build exit0；PokeWalk.bin=0x173500，既有recovery分区不足警告仍在。
- 本轮十五项检查13绿；verify_sensing仍new6/dist8共14处，verify_web_coords因sprite旧调用正则失配而exit1。后者需要tools写区修改，已报Hub协调，未自行改门禁。具体后续状态以本轮报告为准。
- 尚未测量sprite配方真机耗时/导出完整动画payload大小。解码流式、无新动态缓冲；同色行段合并仅减少指令数，不能当作性能结论。

### 恢复本轮一次性探针

以下两个代码块是本轮脚本的持久副本。恢复到/tmp后，运行sprite.py和factor.py current可复验当前实现；before.json为修改前当轮记录，不能用当前代码重新标记成before。探针没有加入常跑门禁。

<!-- D78_SPRITE_BEGIN -->
```python
from pathlib import Path
import subprocess
R=Path('/Users/bytedance/luobata/ESP32-PokemonGo');O=Path('/tmp/pokemon-d78')
a=(R/'firmware/main/assets.c').read_text()
parser=a[a.index('static struct {\n    const uint8_t *d;\n    uint16_t count, per;'):a.index('#define FRONT_MAX_SEGMENTS')]
r=(R/'firmware/main/render.c').read_text()
legacy=r[r.index('void render_sprite_2bpp_wh('):r.index('// 正方形是长方形的特例')]
shake=r[r.index('int render_shake_dx('):r.index('bool render_flash_on(')]
p=(R/'firmware/main/play_battle.c').read_text()
tick=p[p.index('static void tick('):p.index('    // 回合间隔：')]+ '}\n'
bad=tick.replace('static void tick(', 'static void tick_bad(').replace('draw_band(BAND_H);               // 主宠上半（y=140..159）','/* negative: missing upper band */')
assert bad.count('negative:')==1
blob=(R/'assets/gen1_back.bin').read_bytes()
code=r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include "assets.h"
#include "render_scene_screen.h"
#define ESP_LOGE(...) ((void)0)
static const uint8_t *back_bin_start,*back_bin_end;
static uint16_t rd16(const uint8_t *p){return (uint16_t)(p[0]|p[1]<<8);}
static uint32_t rd32(const uint8_t *p){return (uint32_t)p[0]|(uint32_t)p[1]<<8|(uint32_t)p[2]<<16|(uint32_t)p[3]<<24;}
'''+parser+r'''
static const uint8_t real_back[]={'''+','.join(map(str,blob))+r'''};
static uint8_t fixture[16+2*576];
static uint16_t canvas[SCREEN_W*SCREEN_H],expected[SCREEN_W*SCREEN_H];
static int active_band;
void screen_px(int x,int y,uint16_t c){
 if(x>=0&&x<SCREEN_W&&y>=0&&y<SCREEN_BAND_H)canvas[(active_band+y)*SCREEN_W+x]=c;
}
'''+legacy+shake+r'''
static const uint16_t pal[4]={0x1234,0x4567,0x789a,0};
static const uint8_t *test_data;
static int test_size;
static bool s_playing=true;
static unsigned s_shake_i,s_play_i=1;
typedef struct {bool by_pet;} battle_round_t;
static struct {battle_round_t rounds[1];} s_res;
typedef int lv_timer_t;
#define SHAKE_FRAMES 4
#define SHAKE_AMP 3
#define BAND_H SCREEN_BAND_H
static unsigned band_mask;
static void draw_band(int by){
 band_mask|=1u<<(by/SCREEN_BAND_H);active_band=by;
 for(int i=0;i<SCREEN_W*SCREEN_BAND_H;i++)canvas[by*SCREEN_W+i]=C_BG;
 assert(scene_screen_p3_pet_back(by,test_data,test_size,test_size,
         render_shake_dx(s_shake_i,SHAKE_FRAMES,SHAKE_AMP),pal));
}
'''+tick+bad+r'''
static void clear(void){for(int i=0;i<SCREEN_W*SCREEN_H;i++)canvas[i]=C_BG;}
static void full(int legacy_mode,int dx){
 clear();
 for(active_band=0;active_band<SCREEN_H;active_band+=SCREEN_BAND_H){
  if(legacy_mode)render_sprite_2bpp_wh(SCENE_P3_PET_BACK_X+dx,SCENE_P3_PET_BACK_Y-active_band,test_data,test_size,test_size,SCENE_P3_PET_BACK_SIZE/test_size,pal);
  else assert(scene_screen_p3_pet_back(active_band,test_data,test_size,test_size,dx,pal));
 }
}
static void set_fixture(int size){
 memset(fixture,0,sizeof(fixture));memcpy(fixture,"BACK",4);fixture[4]=1;
 fixture[6]=fixture[8]=(uint8_t)size;
 unsigned per=(unsigned)size*size/4;fixture[10]=per&255;fixture[11]=per>>8;fixture[12]=2;
 memset(fixture+16+per,0x55,per);
 back_bin_start=fixture;back_bin_end=fixture+16+2*per;
 assert(parse_back());sprite_asset_t info;
 assert(assets_back_sprite_info(2,&info));assert(info.data==fixture+16+per&&info.w==size&&info.h==size);
 assert((assets_back_sprite(2)!=NULL)==(size==32));
 assert(!assets_back_sprite_info(0,&info)&&info.data==NULL&&info.w==0);
 assert(!assets_back_sprite_info(3,&info));
 assert(assets_back_sprite_info(1,&info));test_data=info.data;test_size=info.w;
}
int main(void){
 unsigned comparisons=0;
 back_bin_start=real_back;back_bin_end=real_back+sizeof(real_back);assert(parse_back());
 for(unsigned id=1;id<=s_back.count;id++){
  sprite_asset_t info;assert(assets_back_sprite_info(id,&info));assert(assets_back_sprite(id)==info.data);
  test_data=info.data;test_size=info.w;
  for(int phase=0;phase<=SHAKE_FRAMES;phase++){
   int dx=render_shake_dx(phase,SHAKE_FRAMES,SHAKE_AMP);
   full(1,dx);memcpy(expected,canvas,sizeof(canvas));full(0,dx);assert(!memcmp(expected,canvas,sizeof(canvas)));comparisons++;
  }
 }
 printf("real BACK: %u full-frame comparisons identical to render_sprite_2bpp_wh\n",comparisons);
 for(int size=32;size<=48;size+=16){
  set_fixture(size);full(0,0);
  int x0=SCREEN_W,y0=SCREEN_H,x1=0,y1=0,n=0;
  for(int y=0;y<SCREEN_H;y++)for(int x=0;x<SCREEN_W;x++)if(canvas[y*SCREEN_W+x]!=C_BG){if(x<x0)x0=x;if(y<y0)y0=y;if(x>x1)x1=x;if(y>y1)y1=y;n++;}
  assert(x0==8&&y0==140&&x1==103&&y1==235&&n==96*96);
  printf("source=%d scale=%d bounds=[%d,%d)x[%d,%d) pixels=%d\n",size,96/size,x0,x1+1,y0,y1+1,n);
  // All shades including transparency; equality is checked against the old decoder.
  memset(fixture+16,0x1b,(size_t)size*size/4);full(1,0);memcpy(expected,canvas,sizeof(canvas));full(0,0);assert(!memcmp(expected,canvas,sizeof(canvas)));
  memset(fixture+16,0,(size_t)size*size/4);
  for(unsigned phase=0;phase<SHAKE_FRAMES;phase++){
   full(0,render_shake_dx((int)phase+1,SHAKE_FRAMES,SHAKE_AMP));memcpy(expected,canvas,sizeof(canvas));
   full(0,render_shake_dx((int)phase,SHAKE_FRAMES,SHAKE_AMP));s_shake_i=phase;band_mask=0;tick(NULL);
   assert(band_mask==6&&s_shake_i==phase+1&&!memcmp(expected,canvas,sizeof(canvas)));
  }
  printf("source=%d actual tick shake phases=4: bands 1+2, incremental frame equals full redraw\n",size);
  full(0,render_shake_dx(1,SHAKE_FRAMES,SHAKE_AMP));memcpy(expected,canvas,sizeof(canvas));
  full(0,render_shake_dx(0,SHAKE_FRAMES,SHAKE_AMP));s_shake_i=0;tick_bad(NULL);assert(memcmp(expected,canvas,sizeof(canvas)));
  printf("source=%d negative missing band1 detected\n",size);
  fixture[10]--;assert(!parse_back());sprite_asset_t info;assert(!assets_back_sprite_info(1,&info));
 }
 set_fixture(32);sprite_asset_t info;back_bin_end--;assert(!parse_back()&&!assets_back_sprite_info(1,&info));
 clear();assert(!scene_screen_p3_pet_back(80,test_data,40,40,0,pal));
 for(int i=0;i<SCREEN_W*SCREEN_H;i++)assert(canvas[i]==C_BG);
 puts("metadata stride/ID/truncation checks and unsupported size rejection passed");return 0;
}
'''
(O/'sprite_probe.c').write_text(code)
subprocess.run(['cc','-O1','-Wall','-Wextra','-Werror','-I',str(R/'firmware/main'),str(O/'sprite_probe.c'),'-o',str(O/'sprite_probe')],check=True)
r=subprocess.run([str(O/'sprite_probe')],text=True,capture_output=True)
(O/'sprite.log').write_text(r.stdout+r.stderr)
print(r.stdout+r.stderr);assert r.returncode==0,r.returncode
```
<!-- D78_SPRITE_END -->

<!-- D78_FACTOR_BEGIN -->
```python
from pathlib import Path
import sys,json,tempfile,itertools
R=Path('/Users/bytedance/luobata/ESP32-PokemonGo')
sys.path[:0]=[str(R/'tools/pipeline'),str(R/'sim')]
import verify_battle as V
import systems as S
rows=[]
with tempfile.TemporaryDirectory() as td:
 d=V.Driver(V.build(td))
 try:
  for f in (1024,614):
   for lv,a,p,de,sp in itertools.product((5,12,50),(30,55,90,130),(1,40,90),(30,60),(0,1)):
    line=f'dmg {lv} 3 255 0 255 50 {a} 47 {a+7} 41 50 37 {de} {de+11} 31 0 {p} {sp} {f}'
    dmg,mult,miss=map(int,d.ask(line).split())
    attack=a+7 if sp else a; defense=de+11 if sp else de
    qexpected=S.damage_of(lv,max(1,attack*f//1024),p,defense,100,100)
    exact=S.damage_of(lv,max(1,int(attack*(1.0 if f==1024 else .6))),p,defense,100,100)
    rows.append(dict(f=f,lv=lv,a=a,p=p,de=de,sp=sp,c=dmg,qexpected=qexpected,exact=exact))
 finally:d.close()
label=sys.argv[1]
Path('/tmp/pokemon-d78/'+label+'.json').write_text(json.dumps(rows,indent=2))
for f in (1024,614):
 rr=[r for r in rows if r['f']==f]
 print(label,f,'cases',len(rr),'vs_same_q10_bad',sum(r['c']!=r['qexpected'] for r in rr),'vs_exact_float_bad',sum(r['c']!=r['exact'] for r in rr))
print('Lv12 A55 D60 P40 physical:',[r for r in rows if (r['lv'],r['a'],r['de'],r['p'],r['sp'])==(12,55,60,40,0)])
```
<!-- D78_FACTOR_END -->


### D78 验收口径后续明确（Hub 18:3x）

Hub解除本角色阻塞并要求直接交result：既有verify_sensing保持state0/trans0/new6/dist8即接受；verify_web_coords的新sprite调用识别由工具侧协调。factor只修施加位置，614/1024与0.6量化差异保留，不改sim或系数。本角色实现和专项证据已完成，仍不把联合检查表写成十五项全绿。


## 第 4 步前置核查：D85 文本迁移停止记录（2026-09-07）

本轮尚未迁移文本元素。测宽前置检查触发合同Stop2/4，已向Hub报告并停止生产修改；没有修改测宽函数、VAR_ELEMENTS、模板或预算。

### 当轮实际测宽结果

从当前render.c提取utf8_next/render_char_advance/render_text_width原实现，字体size从当前font16.bin头读取（16），以cc -Wall -Wextra -Werror编译。JS直接提取当前template.html的textW原函数，由Node运行；不是手写两个等价模型。

| 输入集 | 数量 | 固件/web不等 |
|---|---:|---:|
| gen1.bin实际151名 × Lv1..100 | 15100 | 0 |
| U+0080..U+00FF逐字 | 128 | 128 |
| 高级球 ×99、÷、°、é | 4 | 4 |
| 两只五字名去空格Lv100 | 2 | 0 |

两只五字名带空格Lv100两端均128px；去空格均120px。这里仅证明现有宽度与边界字串，不声称新配方已经实现或15100组新配方零溢出。

`高级球 ×99`固件88px、web80px；÷/°/é固件16px、web8px。固件条件为cp<0x80（render.c:120），web条件为charCodeAt(0)>0xFF（template.html:3496）。

契约“当前上屏文案不含该区间”的前提不成立：`firmware/main/play_capture.c:195`实际拼接`%s ×%u`并随后绘制。差异不只是未来可能用到的é；当前捕获页已有×。没有据此擅自改规则或重启text_px_fixed方案。

### 字体与预算来源的边界

web不是直接用font16.bin绘制：build.py:1243把它转成TTF/data URI；template.html:3456异步加载Kanto16，:3478在字体不可用或字符未登记时用宿主字体。源资产同源不等于当前浏览器字形像素已相同。本轮未验证字体加载状态/浏览器glyph像素，不作该结论。

VAR_ELEMENTS的P3主宠名牌记录（sim/strings.py:452）已有x=112、right=232和两个模板，可作为构建期数据源，**没有发现表结构本身不能用**。但当前scene_cli/build路径只求值HP（tools/pipeline/scene_cli.c:20、tools/inspector/build.py:49），未发现Python预算表→固件编译数据的生成桥。把112/232再写入C不满足单一来源。

建议由Hub明确导出责任：构建步骤选择该记录，导出x/right/格式/回退格式，固件与host配方共同include同一生成产物；运行时仅传物种名和等级。当前本角色无tools、sim/strings.py及CMake写权，不能自行补桥或新增生成头路径。待Hub决定测宽处理与生成路径后再迁移。

### 复现（一次性探针，不是新门禁）

`python3 /tmp/pokemon-d85/width.py`，exit0表示探针成功完成测量，不表示两端等价。结果在/tmp/pokemon-d85/result.json。以下保存可恢复源码：

<!-- D85_WIDTH_BEGIN -->
```python
from pathlib import Path
import json,subprocess,struct,sys
R=Path('/Users/bytedance/luobata/ESP32-PokemonGo');O=Path('/tmp/pokemon-d85')
sys.path.insert(0,str(R/'tools/pipeline'))
from inventory_assets import parse_gen1
names=[m['zh'] for m in parse_gen1(str(R/'assets/gen1.bin'))['mons']]
font=(R/'assets/font16.bin').read_bytes();size=struct.unpack_from('<H',font,6)[0]
render=(R/'firmware/main/render.c').read_text()
width=render[render.index('static uint8_t utf8_next('):render.index('// 画一个字形')]
web=(R/'tools/inspector/template.html').read_text()
func=next(line for line in web.splitlines() if line.startswith('function textW(str)'))
cases=[{'kind':'name','s':f'{n} Lv{lv}'} for n in names for lv in range(1,101)]
cases += [{'kind':'latin1','s':chr(cp),'cp':f'U+{cp:04X}'} for cp in range(0x80,0x100)]
cases += [{'kind':'context','s':s} for s in ['高级球 ×99','÷','°','é']]
cases += [{'kind':'fallback','s':n+'Lv100'} for n in ('三合一磁怪','多刺菊石兽')]
(O/'cases.json').write_text(json.dumps(cases,ensure_ascii=True))
source='#include <stdint.h>\n#include <stdio.h>\n#include <string.h>\nstatic struct {int size;} s_font={'+str(size)+'};\n'+width+'\nint main(void){char s[512];while(fgets(s,sizeof(s),stdin)){s[strcspn(s,"\\n")]=0;printf("%d\\n",render_text_width(s));}return 0;}\n'
(O/'width.c').write_text(source)
subprocess.run(['cc','-Wall','-Wextra','-Werror',str(O/'width.c'),'-o',str(O/'width')],check=True)
c=list(map(int,subprocess.run([str(O/'width')],input='\n'.join(v['s'] for v in cases)+'\n',text=True,capture_output=True,check=True).stdout.splitlines()))
script=func+'\nconst fs=require("fs");const a=JSON.parse(fs.readFileSync(process.argv[1],"utf8"));process.stdout.write(JSON.stringify(a.map(v=>textW(v.s))));'
j=json.loads(subprocess.run(['node','-e',script,str(O/'cases.json')],text=True,capture_output=True,check=True).stdout)
assert len(c)==len(j)==len(cases)
for case,cw,jw in zip(cases,c,j):case.update(c=cw,web=jw)
summary={kind:{'count':sum(v['kind']==kind for v in cases),'different':sum(v['kind']==kind and v['c']!=v['web'] for v in cases)} for kind in ['name','latin1','context','fallback']}
summary['examples']=[v for v in cases if v['kind'] in ('context','fallback') or v['kind']=='name' and v['s'] in ('三合一磁怪 Lv100','多刺菊石兽 Lv100')]
summary['font_size']=size
(O/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
```
<!-- D85_WIDTH_END -->

## 第 4 步实做（D85，2026-09-07，Hub 收敛合同后）

P3 主宠名牌已由 `scene_p3_pet_name` 统一决定绝对位置 (112,168)、右边界232、格式与超预算去空格回退。`play_battle.c` 只传物种名字节段和等级；同步文本回调中的字符串仅在回调期间有效。`render_scene_screen.h` 把绝对 y 转为当前横带局部 y，仍调用原来的 `render_text`。没有新增渲染器、字符集限制或门禁，`render.c/h` 未修改；字体像素绘制尚未共享，本步不能声称两侧像素等价。

测宽直接调用已有 `render_text_width`，因此依赖原渲染器完成字体初始化，使用其 `<0x80` 半宽规则，没有另写一套模型。主宠名牌输入沿用已有物种名字节长度及 uint8 等级，局部缓冲仍为64字节，不新定义超长自定义名称或更小预算的多级截断政策。

### 明确欠账：预算桥和测宽分叉

`SCENE_P3_PET_NAME_X/RIGHT` 的112/232及两个格式与 `sim/strings.py:452` 的 `VAR_ELEMENTS` 主宠名牌项重复。**桥未建，下一轮要合并**。本轮 Hub 已从 Objective 删除导出桥：相关 `sim/` 和 `tools/` 不在本写区，且要先决定 Python 生成 C 头还是 C 导出供 Python 消费的数据，才能确立预算和模板的唯一来源。不能把当前硬编码称作表驱动导出。

当前运行再测15100个“物种名 Lv1..100”字串，固件/web宽度逐值差异0；这仅覆盖名牌数据集，不代表所有上屏文本。U+0080..00FF的128个码位全部不同（16 vs 8px）；实际使用的“高级球 ×99”为88 vs 80px。按 Hub 处置保留差异，没有限定输入字符集或修改测宽函数。

### 当前运行验证

- `python3 /tmp/pokemon-d85/recipe.py`：编译真实共享头及横带后端，使用从当前render.c提取的原测宽实现、当前font16.bin字号。151名×100级均与原位置/格式回退一致，零溢出；两处回退为“三合一磁怪Lv100”“多刺菊石兽Lv100”，120px，band160内y=8。
- 反向测试只改临时头副本 `SCENE_P3_PET_NAME_RIGHT` 为240（预算128）：两个Lv100名牌均保留空格，宽度128。生产预算未改。
- `python3 /tmp/pokemon-d85/width.py`：上述宽度差异实测，完整探针已在前置核查节留档。
- `bash tools/device/fw.sh build`：exit0，产物 `firmware/build/PokeWalk.bin`，大小0x173550；既有recovery分区0x100000不足警告仍在，未刷机。
- inventory_assets、verify_battle/encounter/nurture/exp/party/opening/transitions/audio/ui/layout/evolution/sim_pages共13项exit0。verify_web_coords exit1：旧的名牌render_text正则失配1处，已通过relay交Hub协调tools写者。verify_sensing exit1，state/trans=0，new6+dist8=14，与基线一致。

固件部分已完成；本记录时web接线和坐标检查适配仍待其负责者完成，**未宣称十四项全绿或两侧接线验收完成**。验证输出位于 `/tmp/pokemon-d85/`。下面留存本轮配方探针，复制为该目录下recipe.py后运行即可复查。

<!-- D85_RECIPE_BEGIN -->
```python
from pathlib import Path
import json, subprocess, sys, struct
R=Path('/Users/bytedance/luobata/ESP32-PokemonGo'); O=Path('/tmp/pokemon-d85')
sys.path.insert(0,str(R/'tools/pipeline'))
from inventory_assets import parse_gen1
names=[m['zh'] for m in parse_gen1(str(R/'assets/gen1.bin'))['mons']]
r=(R/'firmware/main/render.c').read_text()
width=r[r.index('static uint8_t utf8_next('):r.index('// 画一个字形')]
size=struct.unpack_from('<H',(R/'assets/font16.bin').read_bytes(),6)[0]
source='''#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "render_scene_screen.h"
static struct {int size;} s_font={FONT_SIZE};
WIDTH
static int calls;
int render_text(int x,int y,const char *s,uint16_t c){calls++;printf("%d\t%d\t%u\t%d\t%s\\n",x,y,c,render_text_width(s),s);return x+render_text_width(s);}
int main(void){char name[64];unsigned level;while(scanf("%63s %u",name,&level)==2){calls=0;scene_screen_p3_pet_name(160,name,(uint8_t)strlen(name),(uint8_t)level);if(calls!=1)return 2;}return 0;}
'''.replace('FONT_SIZE',str(size)).replace('WIDTH',width)
(O/'recipe.c').write_text(source)
# Local include copies allow a negative mutation without touching production files.
for f in ('render_scene.h','render_scene_screen.h'):(O/f).write_text((R/'firmware/main'/f).read_text())
def compile_run(tag, inputs):
    exe=O/tag
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(R/'firmware/main'),str(O/'recipe.c'),'-o',str(exe)],check=True)
    out=subprocess.run([str(exe)],input=''.join(f'{n} {l}\n' for n,l in inputs),text=True,capture_output=True,check=True).stdout.splitlines()
    return [line.split('\t') for line in out]
cases=[(n,l) for n in names for l in range(1,101)]
rows=compile_run('recipe',cases)
assert len(rows)==15100
fallback=0
for (n,l),(x,y,c,w,s) in zip(cases,rows):
    old=f'{n} Lv{l}'
    # Independent old layout oracle for this actual ASCII+CJK name set.
    oldw=sum(8 if ord(ch)<128 else 16 for ch in old)
    if oldw>120:old=old.replace(' Lv','Lv');fallback+=1
    assert s==old and (int(x),int(y),int(c))==(112,8,0)
    assert int(w)<=120
boundary=[(n,100) for n in ('三合一磁怪','多刺菊石兽')]
positive=compile_run('recipe_boundary',boundary)
assert all(int(v[3])==120 and ' Lv' not in v[4] for v in positive)
p=O/'render_scene.h';p.write_text(p.read_text().replace('#define SCENE_P3_PET_NAME_RIGHT 232','#define SCENE_P3_PET_NAME_RIGHT 240'))
negative=compile_run('recipe_negative',boundary)
assert all(int(v[3])==128 and ' Lv' in v[4] for v in negative)
p.write_text((R/'firmware/main/render_scene.h').read_text())
result={'cases':len(rows),'old_behavior_mismatches':0,'overflows':0,'fallback_count':fallback,'band_local_y':8,'boundary':positive,'budget_128_negative':negative,'font_size':size}
(O/'recipe-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
```
<!-- D85_RECIPE_END -->

## D90 预算桥（2026-09-07，第二十二轮）

采用 B，先只生成已迁移消费者需要的预算。新增65行 `tools/pipeline/gen_layout_budget.py`，从 `VAR_ELEMENTS` 按 `(P3, 主宠名牌)` 查唯一条目，生成 `firmware/main/render_layout_budget.h` 的 `LAYOUT_P3_PET_NAME_BUDGET = right - x = 120`。生成物带自动生成标记。其余22项尚未迁移，不预建闲置常量；将来有消费者时向 EXPORTS 加键名映射即可。

`render_scene.h` 保留绝对坐标X=112/Y=168及格式/回退代码；RIGHT改为X+生成预算，不再手写232。生成头不导出坐标，也不转换Python模板。因此本轮清掉的是**P3预算的重复数值**：坐标与VAR_ELEMENTS仍需原坐标检查约束，模板仍在表和配方分别表达，不能称全文本配置单一来源。表中的格式化语法不妨碍这条只取数值的桥，无需复杂转换。

静态inline与生成include的组合先在临时副本中用真实scene_cli以 `cc -std=c11 -Wall -Wextra -Werror` 编译并运行，再用当前固件构建验证；均通过。没有将整个配方改成生成物。

使用：

```sh
python3 tools/pipeline/gen_layout_budget.py
python3 tools/pipeline/gen_layout_budget.py --check
```

第一条重生成；第二条比较当前表和已有头，缺失/陈旧exit1，相同exit0。**没有自动挂入fw.sh、UI.audit或已有十四检查**，这些既有入口不在本轮写区。运行构建本身不会替代--check；需要自动调用时由入口写者接入这条命令即可。没有新增独立门禁脚本或改旧门禁。参考的gen_pages.py当前190行，新增生成器65行，未达到合同150行停止阈值。

### 本轮运行证据

- `python3 tools/pipeline/gen_layout_budget.py --check` exit0。
- `python3 /tmp/pokemon-d90/verify_bridge.py` exit0：实际头/后端+当前render.c测宽函数、font16.bin字号，15100组合与旧回退一致且零溢出；两个五字名Lv100均去空格120px。
- 同一探针仅在临时目录复制的sim/strings.py把该项right232→240：不重新生成--check exit1；生成后--check exit0；编译消费新头，两个名字保留空格128px。工作区sim/strings.py未改。探针删除临时Python缓存，避免同秒同长度改值复用旧字节码。
- `bash tools/device/fw.sh build` exit0，PokeWalk.bin仍0x173550。recovery 1MB容量不足的既有警告保留；未刷机或宣称硬件验证。
- inventory_assets、verify_battle/encounter/nurture/exp/party/opening/transitions/audio/ui/layout/evolution/sim_pages/web_coords共14项exit0。verify_sensing exit1，state0/trans0/new6/dist8，总14与既有基线相同。

D91 web文本接线由web-coder单独交付；本轮坐标检查绿色不等于证明web已使用文本配方。Latin1测宽分叉未修改，本轮没有重做全站字形像素等价性。

下面保留本轮负向验证源码；复制到/tmp/pokemon-d90/verify_bridge.py运行，fixtures均在临时目录。

<!-- D90_BRIDGE_BEGIN -->
```python
from pathlib import Path
import json, subprocess, sys, shutil, struct
R=Path('/Users/bytedance/luobata/ESP32-PokemonGo');O=Path('/tmp/pokemon-d90');T=O/'fixture'
for d in ('tools/pipeline','sim','firmware/main'):(T/d).mkdir(parents=True,exist_ok=True)
for f in ('tools/pipeline/gen_layout_budget.py','sim/strings.py','firmware/main/render_layout_budget.h','firmware/main/render_scene.h','firmware/main/render_scene_screen.h'):shutil.copyfile(R/f,T/f)
def gen(*args):
 p=subprocess.run([sys.executable,str(T/'tools/pipeline/gen_layout_budget.py'),*args],text=True,capture_output=True)
 print('generator',args,p.returncode,p.stdout.strip(),p.stderr.strip());return p.returncode
assert gen('--check')==0
# Use production measurement functions and current font metadata, not another width model.
r=(R/'firmware/main/render.c').read_text();width=r[r.index('static uint8_t utf8_next('):r.index('// 画一个字形')]
size=struct.unpack_from('<H',(R/'assets/font16.bin').read_bytes(),6)[0]
c='''#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "render_scene_screen.h"
static struct {int size;} s_font={SIZE};
WIDTH
int render_text(int x,int y,const char*s,uint16_t color){printf("%d|%d|%u|%d|%s\\n",x,y,color,render_text_width(s),s);return x+render_text_width(s);}
int main(void){char n[64];unsigned lv;while(scanf("%63s %u",n,&lv)==2)scene_screen_p3_pet_name(160,n,(uint8_t)strlen(n),(uint8_t)lv);return 0;}
'''.replace('SIZE',str(size)).replace('WIDTH',width)
# Outside O to avoid the earlier include smoke-test's local header.
(T/'probe.c').write_text(c)
def run(cases):
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(T/'firmware/main'),'-I',str(R/'firmware/main'),str(T/'probe.c'),'-o',str(T/'probe')],check=True)
 return subprocess.run([str(T/'probe')],input=''.join(f'{n} {lv}\n' for n,lv in cases),capture_output=True,text=True,check=True).stdout.splitlines()
sys.path.insert(0,str(R/'tools/pipeline'));from inventory_assets import parse_gen1
names=[m['zh'] for m in parse_gen1(str(R/'assets/gen1.bin'))['mons']]
cases=[(n,lv) for n in names for lv in range(1,101)];rows=run(cases)
assert len(rows)==15100
for (n,lv),row in zip(cases,rows):
 x,y,col,w,s=row.split('|');old=f'{n} Lv{lv}'
 if sum(8 if ord(ch)<128 else 16 for ch in old)>120:old=old.replace(' Lv','Lv')
 assert (x,y,col)==('112','8','0') and int(w)<=120 and s==old
boundary=[('三合一磁怪',100),('多刺菊石兽',100)]
before=run(boundary);assert all('|120|' in s and ' Lv' not in s for s in before)
p=T/'sim/strings.py';s=p.read_text();needle='("P3", "主宠名牌", 112, 232,';assert s.count(needle)==1
p.write_text(s.replace(needle,'("P3", "主宠名牌", 112, 240,'))
# Avoid same-second Python bytecode caching after a same-length fixture mutation.
shutil.rmtree(T/'sim/__pycache__',ignore_errors=True)
assert gen('--check')==1
assert gen()==0 and gen('--check')==0
after=run(boundary);assert all('|128|' in s and ' Lv' in s for s in after)
result={'all_cases':15100,'overflows':0,'legacy_mismatches':0,'before':before,'after_table_budget_128':after,'stale_check_exit':1,'regenerated_check_exit':0,'production_table_modified':False}
(O/'bridge-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
```
<!-- D90_BRIDGE_END -->

D90收尾补充：Hub明确本轮不自动挂载。生成器docstring已写明手动--check，以及挂载前阅读sim/strings.py:326附近gen_pages误红导致停更的教训；新增说明后脚本共68行，--check复跑exit0。

## D92 测宽解耦（2026-09-07）

`render.h` 现在内联定义唯一一套 `render_utf8_next`、`render_char_advance_sized(cp, font_size)`、`render_text_width_sized(text, font_size)`。原UTF8行为（BMP三字节上限、非法字节按原规则前进）和ASCII半宽判据原样迁移，没有修Latin1差异或改变非法输入政策。`render.c` 的原测宽/步进函数保留签名，包装新函数；绘字与自检也使用同一解码函数。新增 `render_font_size()` 返回原uint16字号，避免从返回uint8的字宽反推字号丢信息。

宿主入口为 `scene_p3_pet_name_sized(callback, ctx, name, name_len, level, font_size)`；当前字体头size=16。原 `scene_p3_pet_name` 包装此入口并传真实字体状态，现有页面及横带调用点不变。宿主只include头文件即可求值，不需要ESP日志、字库链接符号或链接render.c。callback仍为同步借用文本指针，宿主需在回调内消费或拷贝。未在CLI复制测宽实现，也未更改tools里的宿主接线。

### 当前运行验证与边界

- `/tmp/pokemon-d92/verify.py` 编译实际头+从当前render.c提取的兼容包装，与改前保留的旧实现作oracle。10种字号（含0/奇数/超过uint8的边界）×65536码点共655360组步进一致；10种字符串（含Latin1、截断序列、四字节等旧行为）×10字号共100组测宽一致；15100个实际名牌的旧入口和sized入口均与旧结果一致，零溢出。AddressSanitizer及UndefinedBehaviorSanitizer通过。
- 临时复制当前scene_cli.c，只增加调用新sized配方的测试分支，以 `cc -std=c11 -Wall -Wextra -Werror` 编译，不链接render.c、不写测宽桩。两个五字名Lv100输出均为x112/y168/C_INK/120px/无空格。该结果验证宿主接口，**不代替D91正式web接线或浏览器验证**。
- `bash tools/device/fw.sh build` exit0，PokeWalk.bin 0x1736c0；相较上一轮0x173550增加0x170（368）字节。头内纯函数有内联体积取舍，没有新增运行时缓冲或服务。
- inventory_assets、verify_battle/encounter/nurture/exp/party/opening/transitions/audio/ui/layout/evolution/sim_pages/web_coords共14项exit0。verify_sensing仍exit1，state0/trans0/new6/dist8，总14不变。`gen_layout_budget.py --check` exit0。
- 既有recovery分区容量不足警告保留，未刷机；未测全站字形像素等价。历史D85/D90探针按旧render.c函数文本切片，迁移后应使用下面D92探针，不应把旧切片脚本失败当作产品行为回归。

<!-- D92_WIDTH_BEGIN -->
```python
from pathlib import Path
import subprocess,sys,json
R=Path.cwd();O=Path('/tmp/pokemon-d92')
# Captured pre-D92 measurement oracle; production has only the shared implementation.
old="static uint8_t utf8_next(const char *s, uint16_t *cp)\n{\n    uint8_t c = (uint8_t)s[0];\n    if (c < 0x80) { *cp = c; return 1; }\n    if ((c & 0xE0) == 0xC0 && (s[1] & 0xC0) == 0x80) {\n        *cp = (uint16_t)(((c & 0x1F) << 6) | (s[1] & 0x3F));\n        return 2;\n    }\n    if ((c & 0xF0) == 0xE0 && (s[1] & 0xC0) == 0x80 && (s[2] & 0xC0) == 0x80) {\n        *cp = (uint16_t)(((c & 0x0F) << 12) | ((s[1] & 0x3F) << 6) |\n                         (s[2] & 0x3F));\n        return 3;\n    }\n    *cp = '?';\n    return 1;\n}\n\nuint8_t render_char_advance(uint16_t cp)\n{\n    // 这一行就是 P1-③ 的解法：ASCII 半宽。\n    // 与 sim/strings.py 的 text_px() 保持一致 ——\n    // 页面文档的所有排版数字都基于它。\n    return (cp < 0x80) ? (uint8_t)(s_font.size / 2) : (uint8_t)s_font.size;\n}\n\nint render_text_width(const char *s)\n{\n    int w = 0;\n    while (*s) {\n        uint16_t cp;\n        s += utf8_next(s, &cp);\n        w += render_char_advance(cp);\n    }\n    return w;\n}\n\n"
old=old.replace('render_char_advance','old_advance').replace('render_text_width','old_width')
cur=(R/'firmware/main/render.c').read_text();wrappers=cur[cur.index('uint16_t render_font_size('):cur.index('// 画一个字形')]
source='''#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "render_scene.h"
static struct {uint16_t size;} s_font;
OLD
WRAPPERS
static char got[64];
static void capture(void*ctx,int x,int y,const char*s,uint16_t c){(void)ctx;assert(x==112&&y==168&&c==0);snprintf(got,sizeof(got),"%s",s);}
int main(void){
 const uint16_t sizes[]={0,1,8,15,16,32,255,256,511,65535};
 const char *bad[]={"", "ASCII", "高级球 ×99", "é÷°", "\\xC2", "\\xE4\\xB8", "\\xF0\\x9F\\x98\\x80", "\\x80", "\\xC0\\xAF", "\\xED\\xA0\\x80"};
 for(unsigned k=0;k<sizeof(sizes)/sizeof(*sizes);k++){
  s_font.size=sizes[k];assert(render_font_size()==sizes[k]);
  for(unsigned cp=0;cp<65536;cp++)assert(old_advance(cp)==render_char_advance(cp)&&old_advance(cp)==render_char_advance_sized(cp,sizes[k]));
  for(unsigned i=0;i<sizeof(bad)/sizeof(*bad);i++)assert(old_width(bad[i])==render_text_width(bad[i])&&old_width(bad[i])==render_text_width_sized(bad[i],sizes[k]));
 }
 s_font.size=16;char n[64],expected[64];unsigned lv;int count=0;
 while(scanf("%63s %u",n,&lv)==2){
  snprintf(expected,sizeof(expected),"%.*s Lv%u",(int)strlen(n),n,lv);
  if(old_width(expected)>120)snprintf(expected,sizeof(expected),"%.*sLv%u",(int)strlen(n),n,lv);
  scene_p3_pet_name(capture,NULL,n,strlen(n),lv);assert(strcmp(got,expected)==0&&old_width(got)<=120);
  scene_p3_pet_name_sized(capture,NULL,n,strlen(n),lv,16);assert(strcmp(got,expected)==0);count++;
 }
 printf("advance_checks=655360 widths=100 names=%d mismatches=0\\n",count);return 0;
}
'''.replace('OLD',old).replace('WRAPPERS',wrappers)
(O/'probe.c').write_text(source)
subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-I',str(R/'firmware/main'),str(O/'probe.c'),'-o',str(O/'probe')],check=True)
sys.path.insert(0,str(R/'tools/pipeline'));from inventory_assets import parse_gen1
names=[m['zh'] for m in parse_gen1(str(R/'assets/gen1.bin'))['mons']]
p=subprocess.run([str(O/'probe')],input=''.join(f'{n} {lv}\n' for n in names for lv in range(1,101)),text=True,capture_output=True,check=True);print(p.stdout)
# Compile a real scene_cli copy with only a new host text dispatch branch.
s=(R/'tools/pipeline/scene_cli.c').read_text()
cb='''static void host_text(void*ctx,int x,int y,const char*s,uint16_t c){(void)ctx;printf("%d|%d|%u|%d|%s\\n",x,y,c,render_text_width_sized(s,16),s);}
'''
s=s.replace('int main(int argc, char **argv)',cb+'\nint main(int argc, char **argv)',1)
s=s.replace('    if (argc < 3)', '    if (argc==3 && strcmp(argv[1],"d92_name")==0){scene_p3_pet_name_sized(host_text,NULL,argv[2],strlen(argv[2]),100,16);return 0;}\n    if (argc < 3)',1)
(O/'scene_cli.c').write_text(s)
subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-I',str(R/'firmware/main'),str(O/'scene_cli.c'),'-o',str(O/'scene_cli')],check=True)
rows=[]
for name in ['三合一磁怪','多刺菊石兽']:
 out=subprocess.run([str(O/'scene_cli'),'d92_name',name],text=True,capture_output=True,check=True).stdout.strip();assert out==f'112|168|0|120|{name}Lv100';rows.append(out)
result={'regression':p.stdout.strip(),'host_cli':rows,'host_links_render_c':False,'sanitizers':'address+undefined'}
(O/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
```
<!-- D92_WIDTH_END -->
