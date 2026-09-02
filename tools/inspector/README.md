# tools/inspector — 验收页面

在浏览器里看 151 只 sprite 与动效。

**为什么需要它**：sprite 和动效用终端 ASCII 看不出好坏。呼吸浮动方向、
体型对比、四阶灰层次这些只能在真实像素下判断 —— 而这几样恰好是
「初代情怀」成不成立的关键。

**页面从 `gen1.bin` / `gen1_front.bin` / `gen1_back.bin` 直接解码**，
读的是固件真实产物，不是另画一份，否则验收就没意义。
页面里的 JS 解码逻辑（2bpp 解包、分段寻址）就是固件侧那份逻辑的对照参考。

## 用法

```bash
./tools/inspector/serve.sh              # 起服务并打开浏览器
./tools/inspector/serve.sh --rebuild    # 资产变了，重新打包
./tools/inspector/serve.sh --port 9000
```

停止：`pkill -f 'http.server 8765'`

首次使用需先有数据：

```bash
python3 tools/pipeline/fetch_gen1.py --out /tmp/gen1
./tools/inspector/serve.sh --rebuild
```

## 文件

| 文件 | 说明 |
|---|---|
| `template.html` | 页面模板，含 `ASSETS_JSON` 占位符 |
| `build.py` | 解码 .bin → JSON → 内嵌进模板，输出 `index.html` |
| `serve.sh` | 起本地 http.server |
| `index.html` | 产物，**不入库**（217 KB，含内嵌资产） |

改页面改 `template.html`，然后 `--rebuild`。

## 五个验收要点

页面底部列了详细说明，摘要：

1. **front 尺寸必须是三档** —— 格子右上角标着原生尺寸。
   对比超梦（#150，56）与妙蛙种子（#1，40），体型差异应当明显
2. **数值是初代原版** —— 抽查吉利蛋（#113）的 Special 应为 **105**，
   现代特攻只有 35
3. **属性只有初代 15 种** —— 用属性筛选器确认妖精不在列表里
4. **待机呼吸只向上浮动** —— 图应整体上移再回落，底部不能被切
5. **动效零素材成本** —— 缩放/闪白/抖动/进化都是对静态图做变换
