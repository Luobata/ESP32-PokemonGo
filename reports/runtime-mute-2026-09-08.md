# 硬件持久化静音开关 · 2026-09-08

已加入「菜单 → 选项 → 静音」，按 A 切换，默认开（静音）。控制背景音乐与所有游戏音效，单独存入 NVS `pokewalk:mute`，重启保留；游戏 V7 数据结构不变。保存失败不改变当前状态，显示重试提示。

当前构建允许运行时发声，关闭了原先整次启动硬锁 `CONFIG_POKEWALK_SILENT_BOOT`。启动第一步仍关闭 PA/ES8311，读取偏好后才运行音频任务；默认静音时不会初始化 codec/I2S。取消静音时延迟初始化，静音/熄屏时关闭 codec，并丢弃过期音效。网页 C 预览也支持该开关，浏览器试听开关是另一层播放授权。

## 验证

- 生产 `audio_settings.c` + 模拟 NVS：默认值、非法/缺失数据、开关重启恢复、open/set/commit 失败回滚；只访问 mute 键。
- 生产 `sfx.c` + BSP + 模拟设备/调度器：静音启动零 codec 创建；取消静音才 open/write；静音、熄屏 close；重新开声正确复用设备，静音期间不输出旧 PCM。
- 编译期硬静音与可发声两分支、GPIO/I2C 失败注入测试通过；ASan/UBSan。
- 同源页面：显示、按键、PCM 开关、保存失败提示、长 B 导航、熄屏与全帧/分带一致性通过。构建 `30df9cd69b42fe2e062d`。
- 真机烧录写入哈希通过，启动日志 `Audio preference: muted=1`，无 codec 初始化/打开日志；原六人队伍、图鉴 5/151、队首 #129 Lv5 正常读取。只查看选项并返回待机，未现场取消静音或播放声音。

## 二进制与备份

- 应用 1,796,832 B，SHA256 `999b117890e31e98bb8e3069c81f15e4a90e46f9da637dd62b7e049c26a62c6f`，仅烧录 `0x10000`。
- 旧 NVS+应用备份 `.device-backup/nvs-and-app-before-runtime-mute-20260908.bin`，1,713,120 B，SHA256 `1ca9515461a11650efac506004e84994b58ddb0c3c459ee464aaac1065b93b43`。
- 备份应用片段已核对为上版 `b7bc10de2fb044ddc0b637d09eaf1a0441fd2ed4ee7f846d4df745ba0d8506bc`，备份静音偏好为空，故新固件首次启动静音。

证据：[runtime-mute-2026-09-08](evidence/runtime-mute-2026-09-08/)。
