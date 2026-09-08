# 原版正面动作交付与验证

新增 `pokemon_animation.c/.h`、生成资源 `pokemon_animation_assets.h` 和转换器，覆盖固定 pokecrystal 提交 `7a7881d0d62e0ddbd82dcf10e7116807487ac651` 的 151 个关都物种。资源使用 789 张原始 PNG 方形帧和每种 `anim.asm`，只读数组 86,583 字节，单帧解码缓存最多 784 字节。背面维持原版静态。

`verify_pokemon_animation.py --negative`：151 个物种、24,163 个时点、789 帧 2bpp、1,578 次正常/闪光实际 C 渲染全部通过，19,794,432 个 RGB565 像素差异为零，ASan/UBSan 无报告。三个编译成功的损坏版本均报错。

独立页面布局验证在 build `6607edd983a8355fdd29` 通过：原 PNG/脚本并集确定原点，等待滑入和动作完毕，151 页共 2,355,600 个 ROI 像素差异为零；661,080 个非白放大像素完整，最终可见区域并集为 `(120,30)..(232,142)`。原有四边裁剪和删除可见像素五个负向仍被拒绝。

同一 build 的 `verify_firmware_preview.py` 通过 8 页 1,115 次横带/全屏对照、65,536 色解码、DMA 等待和遗漏脏带负向测试。等待逻辑按实际阶段推进，保留每 60 ms 的重绘检查。

证据位于 `reports/pokemon-animation-verification-2026-09-08.json` 与 `reports/evidence/pokemon-animation-2026-09-08/aligned-layout.json`；接口、时序和再生成步骤见 `docs/systems/S3-front-animation.md`。这些结果证明原图、原帧序、共享 C 解码和原生页面像素；本子任务没有烧写硬件。
