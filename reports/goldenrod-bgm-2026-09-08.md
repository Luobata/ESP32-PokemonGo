待机 BGM 由若叶镇（newbarktown）替换为满金市（goldenrodcity）。保留 MUSIC_HOME 的编号 3，因此原有待机与无背景音乐时的默认回退自然使用新曲。照料、遇敌、战斗及音效曲目保持原有映射；音量和静音偏好未改。

曲目采用本地已固定版本 pret/pokecrystal（7a7881d0d62e0ddbd82dcf10e7116807487ac651）的 audio/music/goldenrodcity.asm，通过原管线转换音符、四声道与循环，不单独提高速度。合成器仍是项目已有的单声道硬件适配，不是原机录音。

验证：15 首曲目各离线渲染 130 秒，包含音效叠加、分块一致性及 ASan/UBSan，全部通过。新固件编译、应用分区烧录哈希验证及启动读档通过。原音量／静音控制保留。

20 秒试听：reports/evidence/goldenrod-bgm-2026-09-08/goldenrod-preview.wav。此文件由生产混音器输出，未套用扬声器音量或实际喇叭频响。
