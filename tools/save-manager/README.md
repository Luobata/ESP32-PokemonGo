# PokeWalk 开发存档管理

USB 接在用户电脑。devbox 只提供静态网页；浏览器通过 Web Serial 直接收设备存档，通过目录授权保存到用户电脑，不上传任何存档。设备端需要包含 `usb_backup.c` 的新版固件。

## 本机开发

```sh
python3 tools/save-manager/server.py
```

桌面 Chrome / Edge 打开 http://localhost:8767 ，先选择私人备份目录，再连接 USB JTAG/serial 设备。先关闭串口日志工具。设备菜单 → 选项 → 备份存档，按 C 确认。网页保存、关闭文件并回读校验后才发送完成确认，设备显示「备份完成」。需要继续备份时保持页面打开，在设备上再次按 C。

开发预览不会导出模拟存档；没有电脑接收端时设备会提示打开存档管理页。连接本身不会自动导出，必须在设备上确认。页面不下载任何外部依赖，也没有存档上传 API。

## 部署到 devbox

```sh
tools/save-manager/deploy.sh devbox
ssh -N -L 8767:127.0.0.1:8767 devbox
```

再访问 http://localhost:8767 。浏览器限制串口和目录接口必须通过 HTTPS 或 localhost；不能直接使用开发机的 HTTP IP 地址。首次选择设备、目录时需要在网页点击并授权，断开重连也要确认授权是否仍有效。

服务在 `~/.local/share/pokewalk-save-manager`，用户级 systemd 单元 `pokewalk-save-manager.service`，只监听远端 127.0.0.1:8767。状态和日志：

```sh
ssh devbox 'systemctl --user status pokewalk-save-manager.service'
ssh devbox 'journalctl --user -u pokewalk-save-manager.service -n 30'
```

## 文件范围与兼容性

`.pksave` 为版本 1 JSON：设备标识、固件 ELF SHA-256 构建标识、存档版本、时间、NVS 布局、CRC32、SHA-256 和 base64 分区镜像。当前仅支持 ESP32-C3、存档 V15、NVS 0x9000/0x6000。

导出前 checkpoint 当前游戏状态；UI 锁阻止秘境/设置写入，保存锁阻止后台存盘，在锁内一次复制 24 KiB 镜像，随后分块发送。包含正式伙伴、仓库、图鉴、物品、养成、训练家进度、探索、秘境和已保存声音设置。仅保留持久化的内容：未结算野战、暂存页面光标、仅本次运行的译名选择不恢复。

这是原始 NVS 备份，可能包含设备设置等私人数据，不能公开分享。`.gitignore` 排除所有 `.pksave`；请选择仓库外的私人目录。文件独立保留，不自动清理旧备份。CRC32/SHA-256 检查意外损坏，并非来源签名，请只恢复自己可信的备份。

## 网页导入

1. 在网页选择备份目录、连接 USB，再选择 `.pksave` 文件。
2. 设备菜单 → 选项 → 导入存档；网页点「请求导入」。
3. 设备默认选中「取消」。按 B 选「确认覆盖」，按 C 确认。
4. 网页先把**当前**存档保存为 `PokeWalk-before-import-…pksave` 并回读校验，再发送待导入文件。
5. 设备校验、暂存、重启并应用存档。网页显示「设备已确认：存档导入完成」才算完成；若 USB 重启断开，点击重新连接核对结果。

取消、文件不兼容、备份目录写入失败或传输中断都不会覆盖当前存档。设备使用额外 64 KiB `save_restore` 分区保存新旧镜像，提交标记最后写入；重启时在 NVS 初始化前安装并校验，写入失败尝试回滚旧镜像。断电后重试未完成的已提交导入，校验失败且无法回滚时停止启动游戏，避免继续写坏存档。

首次升级此功能必须同时更新 **0x8000 分区表和 0x10000 应用**，不能只写应用。`save_restore` 位于 0x360000，现有 NVS、应用、cardid、recovery 的地址和大小都未移动；不要擦除整片 Flash。旧分区表仍可备份，无法网页导入。若待恢复日志尚未完成，不要切换其他固件构建；先完成恢复或通过开发工具检查日志。

## 开发用恢复命令

先关闭网页中的设备连接；设备要先装回与备份**相同固件构建**的 PokeWalk。恢复覆盖当前游戏存档，请先停止游戏。下面第一条只检查文件，打印恢复时需要的 device_id：

```sh
python3 tools/save-manager/restore.py /path/to/backup.pksave
source tools/device/idf-env.sh
python tools/save-manager/restore.py /path/to/backup.pksave \
  --restore --port /dev/cu.usbmodem11301 --confirm-device <device_id> \
  --backup-dir "$HOME/PokeWalk Backups"
```

开发时请同时保留备份对应的应用 `.bin`；即使代码相同，重新编译产生的构建校验值也可能不同。本次双向功能真机验证的应用、分区表和私人存档一起保留在 `.device-backup/usb-save-import-20260914/`（此前备份版在 `.device-backup/usb-save-manager-20260914/`）。

恢复需显式输入匹配的设备 ID。命令检查文件、设备 ID、分区布局、游戏名和固件版本；写入前将当前 NVS 另存为私人文件并校验。只写 NVS，不碰应用、cardid 或 recovery。写后回读逐字节核对，成功后重启。恢复期间请勿断电；若写入失败，保持设备连接，按错误信息使用预恢复备份重试。有待完成的网页导入日志时，CLI 会拒绝覆盖 NVS，先用对应固件完成恢复。拒绝不兼容文件后，设备可能停在下载模式，可重新插拔或复位。

网页和 CLI 均严格限制同一设备、同一固件构建；跨版本/跨设备迁移与逻辑存档格式另行实现，不能直接解除本版校验。CLI 适合固件不支持网页导入时使用，写入过程没有网页导入的暂存日志保护。

## 验证

```sh
python3 tools/pipeline/verify_usb_backup.py
python3 tools/pipeline/verify_usb_import.py
python3 tools/pipeline/verify_usb_backup_checkpoint.py
python3 tools/pipeline/verify_usb_backup_ui.py
tools/device/fw.sh build
```

协议以 `!PWBACKUP` 独占整行，畸形或超长请求也不下落到旧按键注入。连接令牌只作用于当前会话；每次备份的 ACK 必须匹配会话与请求。15 秒心跳失联或 60 秒未收到保存确认会失败。浏览器校验分块顺序、总长度、CRC，并在本地文件关闭、回读后回 ACK；失败保留设备存档，可重试。

真机验收已使用刚导出的当前存档完成取消、自动预备份、导入和重启校验。生产网页逻辑通过 Node 串口/文件接口适配器驱动真实设备；浏览器原生 USB/目录授权弹窗仍需首次使用时由用户操作。故障测试覆盖暂存与恢复共 871 个 I/O 中断位置（含部分写入/擦除）。
