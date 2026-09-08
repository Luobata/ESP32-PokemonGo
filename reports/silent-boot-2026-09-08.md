# 本次固件全程静音与刷写准备

`CONFIG_POKEWALK_SILENT_BOOT=y` 已写入当前 `firmware/sdkconfig` 和版本化的
`firmware/sdkconfig.defaults`。配置在 `firmware/main/Kconfig.projbuild` 的
PokeWalk 菜单中；它控制整个运行期，不只是开场音量。

`app_main()` 的第一条动作调用 `bsp_audio_boot_quiet()`。有主动高电平 PA
管脚的板子先把输出锁存器置低，再配置输出/下拉。本板实际定义是
`BSP_I2S_PA_CTRL=-1`（PA 未接 MCU），没有可以宣称已拉低的 PA GPIO。
本板采用 I2C ES8311 关闭路径：先写 DAC mute，再使用已安装
`esp_codec_dev/device/es8311/es8311.c::es8311_suspend` 的关断顺序，最后保留
mute。避免 MCU 复位后 codec 还保持旧固件的供电状态。

静音 BSP 分支不编入 codec 创建、打开或 I2S 初始化。`set_format`、`write`、
`read` 返回 `ESP_ERR_NOT_SUPPORTED`，音量设置无操作。`sfx_start`、`sfx_play`
为无操作函数，不创建队列或任务。已检查玩法、后台和 debug 调用：全部声音
输出最终经过 SFX/BSP，当前编译的 demo 没有其他 I2S/codec 直接入口。
GPIO 失败仍尝试 codec 关闭；I2C 任一操作失败不缓存“关闭成功”，后续初始化
可以重试。错误不会引发反复重启。

验证命令（仅宿主，不接设备）：

```bash
python3 tools/pipeline/verify_silent_boot.py
```

14 个场景通过，含 PA 未连接/已连接、所有 SFX、初始化前后 format/write/read/
volume 调用、GPIO/I2C 故障及重试、重复初始化、取消静音配置恢复原 I2S、codec
和 SFX 队列路径。ASan/UBSan 通过。5 个负向控制分别证明 PA 被拉高、DAC
关断丢失、失败被当作成功缓存、静音仍启动队列、关断被移到扫描之后都会失败。
记录及源文件 SHA256 见
[`verification.json`](evidence/silent-boot-2026-09-08/verification.json)。

该验证证明软件路径，不测真实扬声器、上电模拟瞬态或 ROM/bootloader 阶段。
最终 ESP-IDF 编译、设备备份和刷写由主任务执行，本子任务没有打开串口、调用
esptool、烧写或复位设备。新 Kconfig 首次加入，最终构建应重配置并核实
`firmware/build/config/sdkconfig.h` 含 `CONFIG_POKEWALK_SILENT_BOOT 1`。

## 只读刷写检查

现有备份 `.device-backup/flash-20260904-205828.bin` 为完整 8,388,608 B，SHA256：
`9bf19f76d43ac096000342d0453199dd60875a3ac6c467dc7f1f8bf4156b23b2`。
它的旧社区分区表 factory 长度只有 `0x110000`，不能用来证明当前设备已经是
3 MB app 分区。主任务正在重新备份；应解析新备份的 `0x8000` 分区表后决定。
本子任务仅通过文件目录查看到 `/dev/cu.usbmodem1101`，没有检查或改变端口状态。

项目分区与构建 metadata 保留如下契约：

| 区域 | 偏移 | 长度 |
|---|---:|---:|
| factory | 0x10000 | 0x300000 |
| cardid | 0x356000 | 0x4000 |
| recovery | 0x700000 | 0x100000 |

`fw.sh flash` 使用 `idf.py flash`，会写 bootloader@0、partition table@0x8000
和 app@0x10000。它不是只刷 app 的入口。`fw.sh backup` 没有指定 `--after`；
本机 esptool 默认 `hard_reset`，读完会重启旧固件。主任务本轮已选择显式
`--after no_reset`，读完留在 ROM 下载模式，避免这个重启。

可执行方案的条件与顺序如下，命令仅供主任务核实后使用：

1. 先完成新 8 MB 备份，检查文件长度、SHA256、分区表，保存旧备份。
2. 新备份表与本次表一致且当前 factory 能容纳完整新 app，才使用只刷 app。
   如果仍是旧 `0x110000` factory，须显式处理分区更新，不能强行只刷超长 app。
3. 下载模式不退出，以 `--before no_reset` 接续；只写 `0x10000` 的新静音
   `PokeWalk.bin`，使用构建 metadata 的 `dio / 8MB / 80m`。
4. 写入命令的 flash MD5 校验成功后才允许 `--after hard_reset` 启动新固件；
   失败时保持下载模式继续处理。不得写或擦除 `cardid`、`recovery`、NVS，也不用
   `erase_flash` 或整个 merged image 代替 app。

已在主任务开始备份前明确指出上述旧固件重启风险。恢复声音留待用户明天调试：
在 PokeWalk 菜单取消该选项，并同步调整 defaults 后重建；本次不提供运行期
“取消静音”入口。
