# 长按输入修复与验证（2026-09-08）

背包的 B 长按上一项逻辑正确，问题出在输入生成。`main.c` 将 A/B 长按传入 `nav_key`，导航将事件传到 `play_bag_key`；P10 对 `BSP_BTN_LONG` 减一，对 `BSP_BTN_CLICK` 加一。

网页原来只绑定 `onclick` 和 `keydown`，真实按住没有计时，因此只会发送单击。现在默认手势下，鼠标/触屏按住 A、B 或键盘按住 A、B 达 600 ms，发送一次长按；松手不会再发送单击。短按松手发送单击。手势下拉仍支持显式注入双击、长按。取消、失去指针捕获、窗口失焦和页面隐藏会清除未完成的按住；所有完成输入仍通过原来的请求队列顺序发送。

硬件此前使用按键库默认 1500 ms。本地 `espressif__button` 有两个已复现的问题：

- `iot_button.c` 的 `PRESS_LONG_PRESS_UP_CHECK` 在首个 START 回调耗尽后，先访问 `cb_info[count]` 再检查数组长度，持续按住会越界读取。ASAN 已确认。
- 单击后很快再次按住会进入 `PRESS_REPEAT_UP_CHECK`，此分支不产生 START/HOLD；按住三秒也只有两次 PRESS。

BSP 现在为三个键分别建立一次计时器。去抖确认 PRESS_DOWN 后重新计时，PRESS_UP 取消；到点后检查实际 ADC 电平才发长按。A/B 为 600 ms，C 退出玩法保留 1500 ms。长按完成后抑制该次单/双击，下一次按下重新允许。没有修改 managed 库，也没有新增音频入口。计时/按键创建失败或返回空句柄会清理部分初始化；重复初始化被拒绝，计时启动失败不会伪造长按。

验证命令：

```sh
python3 tools/pipeline/verify_button_input.py --native --evidence reports/evidence/button-input-2026-09-08/bsp.json
node tools/pipeline/verify_firmware_input.js --evidence reports/evidence/button-input-2026-09-08/web.json
node tools/pipeline/verify_firmware_clock.js
```

实际 BSP、实际 ADC 按键驱动和实际按键状态机在宿主 ASAN/UBSAN 下通过三键单击、双击、长按、短点后接长按、阈值前后松开、换键与短毛刺测试。六类错误/空句柄/清理回调交错注入通过清理和恢复检查。恢复旧 START、去掉释放取消、把 A/B 改回 1500 ms、去掉初始化 PRESS_DOWN 门控、去掉清理 PRESS_UP 门控五个负向均被检测；最后两项是在删除计时器前后插入真实 ADC/按键状态机扫描，验证失败初始化时回调不会启动或访问已删除计时器。

模拟 ADC 产生的 B 长按事件回放到实际 C 的 nav/P10：选择从 0 到 18；释放并推进 1 秒仍为 18；下一次单击回到 0，横带检查无差异。Web 的 7 组输入检查与 4 个负向、原有 13 组时钟/请求队列检查与 5 个负向均通过。

边界：ADC 输入采用理想电压，ESP 计时器采用受控时钟；未测量实体按键电压噪声和 LVGL 任务争用。此专项的 Web 自动检查运行生产 JavaScript 的 Node VM。主任务随后在浏览器实测了鼠标 750 ms 长按，并完成静音烧录与真机队伍检查，详见 [总验收记录](team-menu-and-input-2026-09-08.md)。`sdkconfig` 与 `sdkconfig.defaults` 的 `CONFIG_POKEWALK_SILENT_BOOT=y` 保持启用。最终固件构建与硬件检查由主任务统一完成。
