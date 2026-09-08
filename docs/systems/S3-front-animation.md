# P3 原版正面出场动作

双方滑入结束后，野生宝可梦播放自己的水晶版正面动作，再进入操作选择。151 个物种均读取原版 `front.png` 的多帧图和各自的 `anim.asm`，共 789 张帧图；没有用统一位移代替物种动作。原版背面资源没有对应的多帧脚本，主宠背图保留静态。

原始来源是 [pret/pokecrystal](https://github.com/pret/pokecrystal/tree/7a7881d0d62e0ddbd82dcf10e7116807487ac651)，固定提交 `7a7881d0d62e0ddbd82dcf10e7116807487ac651`。转换器核对源文件 Git blob，使用实际 PNG、`macros/scripts/pic_anims.asm` 和 `engine/gfx/pic_animation.asm`；不依赖 `/tmp/gen1c` 的静态导出图。

正常速度按 60 Hz 解释 `frame / setrepeat / dorepeat / endanim`。设置循环或跳回循环不消耗显示时间，循环计数耗尽的 `dorepeat` 会多保持当前帧一拍；`endanim` 恢复首帧。转换器将控制流展开成有截止时点的帧序列，运行时按毫秒纯采样。P3 的 60 ms 绘制节拍会跳过间隔内未被采样的原版时点，图形和当前时点的帧选择保持原版语义；不是模拟 Game Boy 的完整刷新、叫声或菜单待机流程。

资源按相对于原始首帧的 8×8 图块补丁保存，相同补丁图块跨物种去重。完整原始 2bpp 帧数据为 477,712 字节；生成的只读数组数据共 86,583 字节，包含帧索引、物种元数据和展开的时序，另有编译器对齐和解码代码。调用方只需一个最多 784 字节的帧缓存，解码器不分配堆内存，也不增加整屏缓存。

公共接口在 `firmware/main/pokemon_animation.h`：

| 接口 | 用途 |
|---|---|
| `pokemon_anim_info(species, &info)` | 返回源尺寸、帧数、持续 tick，以及实际播放帧和首帧的非白像素并集 |
| `pokemon_anim_sample(species, elapsed_ms)` | 纯采样原版帧号和 `finished`；结束后永远返回首帧 0 |
| `pokemon_anim_decode(species, frame, buffer, capacity, &sprite)` | 从当前 FRNT 首帧解码补丁，输出常规 `sprite_asset_t` |

只在帧号变化时解码；渲染继续使用当前物种的正常或闪光调色板与整数 2× 放大。非法物种、越界帧号、源尺寸不匹配或缓存过短会返回失败并清空输出描述符。正常采样无隐含状态，截图和重绘不会推动动作；毫秒转 tick 使用 64 位乘法，长时间暂停后不会整数回绕。

整个动作使用一个固定绘制原点。对源坐标并集 `(x,y,w,h)`，P3 原点为 `(232-(x+w)*2, 30-y*2)`，使所有播放帧都处于野怪的右侧区域。首帧和动作末帧也保留这个原点，避免切换时跳位。部分物种的首帧本身不再贴着 y=30 或右边 x=232，这是为动作中伸出的耳朵、尾巴等保留空间。原点和时序都在实际 C 页面中使用，浏览器同源预览不另算一份。

再生成和验证：

```sh
python3 tools/pipeline/convert_pokemon_animation.py --src /tmp/pokecrystal
python3 tools/pipeline/convert_pokemon_animation.py --src /tmp/pokecrystal --check
python3 tools/pipeline/verify_pokemon_animation.py --negative
python3 tools/pipeline/verify_battle_layout.py --evidence-dir reports/evidence/pokemon-animation-2026-09-08
python3 tools/pipeline/verify_firmware_preview.py
```

转换先核对当前 `assets/gen1_front.bin` 是否与源首帧一致；更新正面素材时应同时重跑此转换。生成的头文件已作为固件和原生预览共同的只读输入，元数据在 `assets/pokemon_animation_sources.json` 中记录。

独立验证使用 Pillow、原版 `gbcpal.c` 和逐 tick 的脚本解释器，不读取生成资源来构造期望值。它覆盖 151 个物种、24,163 个时点、789 张完整帧，以及 1,578 次正常/闪光实际 C LCD 绘制，共比较 19,794,432 个 RGB565 像素；ASan/UBSan 同时检查缓冲区和解码边界。错误图块行、半速采样和结束时保留动作帧这三个能编译的损坏版本均被拦截。

整页验证另用原始 PNG/脚本计算并集，等待 P3 完成滑入和原动作后检查全部 151 张首帧，确认所有非白像素完整。预览门禁按页面实际 `entry / entrance-motion / choice` 阶段推进并检查横带重绘，不再将 720 ms 当作整个出场过程的结束。

2026-09-08：P12 队伍选中成员与 P5 照料复用同一 `pokemon_idle_t` 页内缓存。每页最多一份 784 字节解码缓存，按 80ms 时钟采样原版动作，动作之间休息两秒；绘制仅读取已缓存帧，横带重绘不会推进动作。照料成功会重启动作；进化演出优先，循环装饰动画暂停。两页循环动作不延长屏幕空闲计时。
