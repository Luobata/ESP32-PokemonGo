# 城都剧情与调查提示：真机烧录验证

2026-10-24，按用户“烧录验证”要求，将调查提示与攻略对应的 V31 开发版写入 ESP32-C3 AI Passport。验证中复现并修复一处 USB 输出并发问题；没有推送代码或发布社区/网站。

## 烧录与进度保护

- 应用：3,202,208 B；应用分区 3,407,872 B，剩余 205,664 B；总 Flash 仍为 8 MiB，分区没有变化。最终应用 SHA-256：`bd7eb3b4b2be3df9a3e89fdca705fa5f8c27171738096cbdc3761bbb7eb3ac56`。
- 源码为 `67a4a25749463d50750c9448ff9d5217d1379094` 加既有未提交城都工作区。最终追加串口修复的 [源码校验值](evidence/johto-story-hardware-2026-10-24/console-source-sha256.json)。剧情和提示对应 [本次提示构建记录](evidence/johto-hints-guide-2026-10-24/build.json)、[提示源码校验值](evidence/johto-hints-guide-2026-10-24/source-sha256.json) 及此前剧情/调查记录；不能只用 HEAD 代表此固件。
- 写前通过生产网页 Receiver/容器模块与真实 USB 串口导出 V30、格式 4、72 KiB 备份，写文件后回读并校验；另由保档更新器备份受保护 Flash。所有原始备份留在忽略目录 `.device-backup/johto-story-hardware-20261024/`，没有放入本报告附件或提交。
- 使用生产保档更新器，只写 `0x10000` 应用区。应用写后校验通过；`0x8000/0x8000`、`0x350000/0x30000`、`0x380000/0x20000` 三段保护范围回读与写前相同。没有写 `full.bin` 或修改分区表。
- 烧录器自动复位后首次串口查询无响应；补一次正常 RTS 复位后启动成功，LCD 流水传输启用。设备读出原 Lv.58 伙伴、经验和城都一徽章进度；未发生空档初始化。后续 USB 导入的自动重启单独核对。

## 实际页面与性能范围

真机使用已有进度，验证空木博士对老玩家的简短衔接、两页对话、暂停后继续原页、完成后调查册、自由探索入口，以及照料和队伍页面。暂停/继续重复三次；当前目标正确为阿笔道馆、第二枚城都徽章。测试结束恢复原备份，让玩家仍可亲自阅读新剧情。

[开场](evidence/johto-story-hardware-2026-10-24/chapter-entry.png)、[第二页](evidence/johto-story-hardware-2026-10-24/welcome-page-2.png)、[暂停](evidence/johto-story-hardware-2026-10-24/paused-guide.png)、[继续原页](evidence/johto-story-hardware-2026-10-24/resumed-page-2.png)、[调查册](evidence/johto-story-hardware-2026-10-24/after-welcome-guide.png)、[城都菜单](evidence/johto-story-hardware-2026-10-24/johto-free-explore.png) 均来自设备自身画面导出，不是宿主预览，也不是摄像机实拍。

采样与截图/USB 传输分开进行。实际计数见 [performance.json](evidence/johto-story-hardware-2026-10-24/performance.json)。

| 场景 | 观察 | 定时器间隔 P95 | 最大绘制耗时 |
| --- | --- | ---: | ---: |
| 新剧情第一页 | 约 10 秒 | 56 ms（目标 50 ms） | 46.9 ms |
| 对话暂停后继续 | 3 次，逐字出现至静止 | 56 / 64 / 56 ms | 48.4 / 48.4 / 48.5 ms |
| 照料动作 | 约 10 秒 | 88 ms（目标 80 ms） | 22.4 ms |
| 队伍选中动作 | 约 10 秒 | 88 ms（目标 80 ms） | 14.7 ms |

直方图为 8 ms 桶上界。剧情文字完成后仅每 800 ms 小幅摆动，伙伴动作之间也有设计停顿；原始帧间隔 P95 的溢出桶不表示精确时间，不能用这些稀疏呈现帧求“恒定 FPS”。完整重画三次中位数：待机约 41.1 ms、城都菜单 40.6 ms、照料 56.6 ms、队伍 49.7 ms；这些是绘制成本，不能当作刷新率。没有在本轮重跑所有野战、训练家、捕获和进化动画；此前舒缓动作实现未改变，仍见 [原实测](comfort-motion-2026-10-24.md)。

当前玩家只有一枚城都徽章，后段 17 个伙伴协作现场未解锁，没有改写徽章来制造真机通过记录。这部分仍以 [生产事务和 UI 检查](johto-fieldwork-2026-10-24.md)、[提示/攻略检查](johto-hints-guide-2026-10-24.md) 为依据，不称为本轮真机全剧情通关。当前显示的“神秘蛋”“传说调查”等为菜单入口，仍受剧情和进度条件控制。

## 验证中发现的 USB 并发问题

初始提示构建 `262815a6…` 的旧档恢复已通过；补测 V31 时却在上传 offset 48000 后超时。原始串口流中，设备返回的 `!PWBACKUP NEXT 2 48128` 前面已有 384 字节 Wi-Fi JSON，确认消息不在行首，Receiver 因此没有推进。该次没有 STAGED 或恢复提交，设备原进度和 89% 测试亮度仍保留。[脱敏失败记录](evidence/johto-story-hardware-2026-10-24/console-failure.json)。这是本次实际复现，不能用成功重试删除失败记录，也不将其等同于所有历史导出缺块的根因。

原实现只在 Wi-Fi 记录外持有 `flockfile(stdout)`，先前宿主测试共用一个 FILE 因而通过，却不足以证明这次真机路径互斥。增加 `console_record` 的显式跨任务保护，将 Wi-Fi 整条 JSON 与 USB 整条协议输出及 flush 串行化；扫描本身继续运行。没有改变接收校验、重试/超时阈值、旧档迁移、预备份 ACK、目标固件日志绑定或导入提交顺序，也没有在网页宽松解析夹杂日志来掩盖问题。

锁在工作任务启动前静态初始化，共 88 B，目标函数最大栈帧 16 B，不新增导入动态分配。绘图源文件与初始提示构建相同，整帧重画不持有此锁，避免引入反向获取世界状态锁的路径。`verify_usb_console.py` 执行实际锁代码，覆盖共享 FILE 和不同 FILE 共用同一输出端，并让去掉跨任务锁但保留 FILE 锁的负向版本复现交错；不同 FILE 是测试模型，不宣称已经证明设备上的 FILE 指针差异。

[19 项回归](evidence/johto-story-hardware-2026-10-24/console-checks/checks.json) 全部通过，含生产 USB、V5～V31、真实隔离 NVS、失败回滚、网页/分发、剧情/调查、显示所有权、声音及静音启动；[最终目标栈/RTC/IRAM](evidence/johto-story-hardware-2026-10-24/console-checks/verify_save_stack.py.final.log) 通过。最终应用又经保档更新器写入、验证，并确认所有保护区不变。后续真机恢复以最终 `bd7eb3b4…` 构建单独记录。

## 存档覆盖与资源

本节的最终结果由 [acceptance.json](evidence/johto-story-hardware-2026-10-24/acceptance.json) 记录。V30 → V31 旧档覆盖已完成：正常设置菜单将亮度从 100 改为 89 并 checkpoint；设备覆盖确认、当前进度预备份及回读 ACK、完整上传、暂存和重启后，匹配源载荷 CRC 的成功回执到达，亮度恢复 100。重新导出为 V31，通过正式容器与生产 save decoder 核对，伙伴/仓库及技能策略、等级经验、图鉴、道具、成就、挑战、秘境摘要、城都活动、故事、终局和新增叙事默认状态一致。见 [旧档对照](evidence/johto-story-hardware-2026-10-24/restored-v30-comparison.txt)。

最终 `bd7eb3b4…` 固件完成两轮覆盖：一轮从原始 V30 导入，另一轮使用最终固件自身导出的 V31。每轮都核对设备预备份回读 ACK、576 个连续上传确认、匹配的重启回执、亮度 89 → 100 和重新导出后的全部上述进度；V31 轮次还确认测试中开始的对话状态回到源备份。两轮传输各伴随 3 次 Wi-Fi 扫描，没有内嵌协议行。见 [最终 V30 对照](evidence/johto-story-hardware-2026-10-24/fixed-v30-comparison.txt)、[最终 V31 对照](evidence/johto-story-hardware-2026-10-24/fixed-v31-comparison.txt)、[V30 串口统计](evidence/johto-story-hardware-2026-10-24/fixed-v30-wire.json) 和 [V31 串口统计](evidence/johto-story-hardware-2026-10-24/fixed-v31-wire.json)。设备最终回到首页，亮度 100，原始收集及挑战进度保留。自然时间、养成随时间变化与 Wi-Fi 扫描计数不作为逐字节相等条件；没有用相同现状导入代替实际设置恢复。

本轮真机覆盖使用生产网页 Receiver/容器模块配合串口测试驱动，不冒称浏览器 WebSerial 点击端到端或离线网页点击验收。V5～V31 历史格式及在线/离线协议的自动化覆盖见此前对应检查，不能泛化为每个历史玩家文件都已上真机。

连续操作和恢复过程中 Wi-Fi 扫描保持开启。实际堆、最大连续块与任务栈水位见 [runtime-queries.json](evidence/johto-story-hardware-2026-10-24/runtime-queries.json)，最终构建实测最小堆 9,956 B、最大连续块 9,728 B；两次导入校验均 valid=1，资源细节见 [导入水位](evidence/johto-story-hardware-2026-10-24/fixed-import-resources.json)。最终正常剧情/照料定时器间隔 P95 仍为 56/88 ms，照料最大绘制约 22.5 ms，与修复前同页样本接近；待机完整重画中位数约 41.0 ms。本轮没有扬声器声学采样；供数统计不能证明实听绝对无卡顿。此前旧构建出现过 USB 导出偶发缺块，本轮没有修改该传输实现，不能声称已定位或根治。

两次导航脚本误判首页光标：一次把返回后的保留位置当作默认位置，另一次没有区分剧情 nav_go 清空返回栈后的默认位置，分别进入野战选择/遭遇列表；均没有开始攻击。已按实际页面与返回栈修正测试驱动，单独保留断言及后续重做记录，并从原备份恢复。这些脚本断言不作为固件缺陷或游戏验收通过记录。

另在验证截图完整性时发现，最终剧情截图的一带只收到 6,612/9,600 B，旧截图解析器把尾部缺失内容填黑，造成伪黑横条。这张图已拒绝并移到私人诊断目录，不作为 LCD 缺陷或验收通过依据。截图工具现在严格校验完整条带、唯一位置、Base64 与长度；两种字节序和 8 类损坏样例通过 [检查](evidence/johto-story-hardware-2026-10-24/console-checks/verify_device_screenshot.py.log)。最终首页抓图第一次也因非 Base64 内容被拒绝，重抓完整成功；[最终首页](evidence/johto-story-hardware-2026-10-24/final-idle.png)。原先公开的剧情/菜单截图重新核对完整字节数；没有用补黑图替代传输完整性检查。此工具修复不改变已烧录应用。

## 交付边界

新的剧情和提示需要本次固件；仅刷新网页不能改变旧设备。攻略具体答案保留在本地 `http://localhost:8767/guide/#fieldwork` 的折叠章节；本轮没有部署 GitHub Pages/devbox，也没有更新社区版本。将来公开城都 V31 时仍需按 AGENTS.md 完成剩余发布门禁并同步网页/离线工具，不能以本轮有限场景验收替代全部版本发布验收。
