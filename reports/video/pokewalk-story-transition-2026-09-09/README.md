# 完整流程故事版 V2：博士到伙伴选择转场

- [完整视频（约 3 分 11 秒）](pokewalk-story-v2.mp4)
- [转场预览（10 秒）](oak-to-starter-preview.mp4)

在完整流程故事版基础上，将 28.4–30.967 秒的 77 帧非交互过渡替换为明确的章节转场：博士淡出 0.6 秒 →「选择你的第一位伙伴」章节卡停留约 1.17 秒 → 伙伴选择画面淡入 0.8 秒。章节卡属于宣传片剪辑，不是新增游戏界面。

此前的博士对白与之后的选择、探索、捕获、道馆等流程保持原来的时序。总帧数仍为 5719（30 fps）。原音轨直接复用，解码后的 PCM SHA-256 与原片一致；完整视频解码检查通过，见 verification.json。

复现：在项目根目录运行 `python3 tools/video/refine_oak_transition.py`，需要 FFmpeg、Pillow 和 macOS PingFang 字体。
