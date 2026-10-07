# PokeWalk 开发存档管理

USB 接在用户电脑。devbox 只提供静态网页；浏览器通过 Web Serial 直接收设备存档，通过目录授权保存到用户电脑，不上传任何存档。设备端需要包含 `usb_backup.c` 的新版固件。

## GitHub Pages（直接使用）

https://Luobata.github.io/ESP32-PokemonGo/

桌面 Chrome / Edge 打开 HTTPS 页面即可选择目录、授权 USB，并在设备上备份或确认导入。不需要 Python、开发机网络或下载本地工具；存档仍只写入用户选择的本地目录。首次访问需要用户操作原生授权弹窗。

`.github/workflows/save-manager-pages.yml` 在 main 的存档工具变更时自动发布，也可手动运行。构建只包含 `server.py` 中 `WEB_FILES` 明确列出的存档网页与游戏手册资源、`.nojekyll` 和本地工具 ZIP；不发布源码树、固件或玩家存档。

## 本机开发

```sh
python3 tools/save-manager/server.py
```

桌面 Chrome / Edge 打开 http://localhost:8767 ，先选择私人备份目录，再连接 USB JTAG/serial 设备。先关闭串口日志工具。设备菜单 → 选项 → 备份存档，按 C 确认。网页保存、关闭文件并回读校验后才发送完成确认，设备显示「备份完成」。需要继续备份时保持页面打开，在设备上再次按 C。

开发预览不会导出模拟存档；没有电脑接收端时设备会提示打开存档管理页。连接本身不会自动导出，必须在设备上确认。页面不下载任何外部依赖，也没有存档上传 API。

## 字节内网访问入口

访问 http://10.37.197.13:8767/ ，下载本地工具 ZIP。解压后在该文件夹打开终端：macOS / Linux 运行 `python3 server.py`，Windows 运行 `py -3 server.py`，再用 Chrome / Edge 打开 http://localhost:8767/ 。需要 Python 3.8 或以上，无需 pip 依赖，也不需要开发机 SSH 权限。保持终端运行；Ctrl+C 停止。端口占用时加 `--port 8768` 并打开 localhost:8768。

内网 HTTP 页面仅作为下载入口，USB 操作在本机 localhost 完成，不需要关闭浏览器安全限制。ZIP 只包含明确列出的服务与网页文件，不包含任何存档。下载后无需持续连接 devbox，文件只写入用户授权的本地目录。

## 部署到 devbox

```sh
tools/save-manager/deploy.sh devbox 0.0.0.0
ssh -N -L 8767:127.0.0.1:8767 devbox
```

再访问 http://localhost:8767 。浏览器限制串口和目录接口必须通过 HTTPS 或 localhost；不能直接使用开发机的 HTTP IP 地址。首次选择设备、目录时需要在网页点击并授权，断开重连也要确认授权是否仍有效。

服务在 `~/.local/share/pokewalk-save-manager`，用户级 systemd 单元 `pokewalk-save-manager.service`，当前监听 0.0.0.0:8767，供内网下载和本机 SSH 转发使用（脚本不传第二参数时仅监听 127.0.0.1）。状态和日志：

```sh
ssh devbox 'systemctl --user status pokewalk-save-manager.service'
ssh devbox 'journalctl --user -u pokewalk-save-manager.service -n 30'
```

## 文件范围与兼容性

`.pksave` 为版本 1 JSON：设备标识、固件 ELF SHA-256 构建标识、存档版本、时间、NVS 布局、CRC32、SHA-256 和 base64 分区镜像。当前支持 ESP32-C3、备份格式 v1、NVS 0x9000/0x6000。游戏的 `save_version` 是原样保留的版本元数据，不维护逐版白名单；接受固件 `uint16_t` 字段范围内的正整数（1–65535）。因此后续游戏新增字段、提升存档版本时，网页与已下载的离线工具无需跟着升级。

网页与离线网页工具允许同一设备跨固件构建导入，由设备的实际读档能力决定兼容性。当前固件支持 V5–V21；旧存档先在隔离的暂存分区挂载，使用与启动相同的解码、迁移、队伍和遭遇校验，通过后才提交恢复日志。文件声明版本必须与实际存档一致；未知较新版本、损坏数据、不同设备或不同分区布局均拒绝覆盖。固件构建标识仍记录在备份中，用于追溯，不再作为网页导入的硬性相等条件。

**从旧版升级时，需要更新设备固件，并刷新网页或重新下载离线工具。** 旧固件及旧离线工具仍保留“同一构建”限制，不能只修改备份 JSON 中的版本号或哈希绕过。备份文件无需转换，保留原文件即可。未来格式迁移由固件负责；不承诺将新格式存档导入旧固件。

导出前 checkpoint 当前游戏状态；UI 锁阻止秘境/设置写入，保存锁阻止后台存盘，在锁内一次复制 24 KiB 镜像，随后分块发送。包含正式伙伴、仓库、图鉴、物品、养成、训练家进度、探索、秘境、累计游戏时长和已保存声音与亮度设置。仅保留持久化的内容：未结算野战、暂存页面光标、仅本次运行的译名选择不恢复。

这是原始 NVS 备份，可能包含设备设置等私人数据，不能公开分享。`.gitignore` 排除所有 `.pksave`；请选择仓库外的私人目录。文件独立保留，不自动清理旧备份。CRC32/SHA-256 检查意外损坏，并非来源签名，请只恢复自己可信的备份。

## 网页导入

1. 在网页选择备份目录、连接 USB，再选择 `.pksave` 文件。
2. 设备菜单 → 选项 → 导入存档；网页点「请求导入」。
3. 设备默认选中「取消」。按 B 选「确认覆盖」，按 C 确认。
4. 网页先把**当前**存档保存为 `PokeWalk-before-import-…pksave` 并回读校验，再发送待导入文件。
5. 设备校验、暂存、重启并应用存档。网页显示「设备已确认：存档导入完成」才算完成；若 USB 重启断开，点击重新连接核对结果。

取消、文件不兼容、备份目录写入失败或传输中断都不会覆盖当前存档。设备使用额外 64 KiB `save_restore` 分区保存新旧镜像，提交标记最后写入；重启时在 NVS 初始化前安装并校验，写入失败尝试回滚旧镜像。断电后重试未完成的已提交导入，校验失败且无法回滚时停止启动游戏，避免继续写坏存档。

首次升级此功能必须同时更新 **0x8000 分区表和 0x10000 应用**，不能只写应用。`save_restore` 位于 0x360000，现有 NVS、应用、cardid、recovery 的地址和大小都未移动；不要擦除整片 Flash。旧分区表仍可备份，无法网页导入。若待恢复日志尚未完成，不要切换其他固件构建；先完成恢复或通过开发工具检查日志。

### 导入暂存失败的诊断（2026-10-08）

旧固件的 `ERROR STAGE` 同时代表内存不足、暂存读写失败和内容校验失败；仅凭“存档内容不兼容或暂存失败”不能判断旧备份损坏或格式不受支持。请保留原始 `.pksave`，不要修改版本号或校验值；若提供排查样本，应私下传递，不能上传公开社区。

本次修复复用保存锁保护的世界工作缓冲区，去掉 V21 导入解码额外申请的约 13 KiB 堆内存；仍在隔离 NVS 中执行真实读档、迁移和队伍/遭遇校验。设备在 `ERROR STAGE` 后附加失败原因，新网页显示具体阶段：`MEMORY` 内存不足，`FLASH` 暂存写入，`NVS` 暂存挂载/关闭，`READ` 存档读取，`VERSION` 声明版本不符，`CONTENT` 数据校验，`CHECKPOINT` 当前进度保存，`JOURNAL` 恢复日志，`LAYOUT` 分区布局。未通过校验不提交覆盖，不显示导入完成。

减少内存占用需要升级固件；仅刷新网页不能修复旧固件的分配失败。细分提示需要新固件配合刷新网页或重新下载离线工具。旧网页仍能安全拒绝带细节的新错误，新网页遇到旧固件的简略错误仍显示原提示。本次不改变存档布局，来源支持范围保持 V5–V21，也不放宽导入保护。发布时必须同步 Pages、devbox 及离线 ZIP；测试和真机覆盖边界见 [发布验证](../../reports/import-stage-release-2026-10-08.md)。

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

命令行 `restore.py` 直接操作原始 Flash，无法调用目标固件的存档校验器，因此仍要求同一设备、同一固件构建。跨版本导入请使用更新后的网页或离线网页工具。CLI 仅供开发恢复，写入过程没有网页导入的暂存日志保护。

## 验证

```sh
python3 tools/pipeline/verify_usb_backup.py
python3 tools/pipeline/verify_usb_import.py
python3 tools/pipeline/verify_save_import_compatibility.py
python3 tools/pipeline/verify_usb_import_device.py
node tools/pipeline/verify_save_import_web.mjs
python3 tools/pipeline/verify_save_manager_distribution.py
python3 tools/pipeline/verify_usb_backup_checkpoint.py
python3 tools/pipeline/verify_usb_backup_ui.py
tools/device/fw.sh build
```

协议以 `!PWBACKUP` 独占整行，畸形或超长请求也不下落到旧按键注入。连接令牌只作用于当前会话；每次备份的 ACK 必须匹配会话与请求。15 秒心跳失联或 60 秒未收到保存确认会失败。浏览器校验分块顺序、总长度、CRC，并在本地文件关闭、回读后回 ACK；失败保留设备存档，可重试。

真机验收已使用刚导出的当前存档完成取消、自动预备份、导入和重启校验。生产网页逻辑通过 Node 串口/文件接口适配器驱动真实设备；浏览器原生 USB/目录授权弹窗仍需首次使用时由用户操作。故障测试覆盖暂存与恢复共 871 个 I/O 中断位置（含部分写入/擦除）。

## 导入结果与更新方式（2026-10-05）

只有本页已暂存的文件与重启后设备回执匹配，才能显示本次导入完成。历史回执不再触发成功提示；刷新同一标签页会保留待核对信息，结果不匹配不会被隐藏为普通重启提示。新固件还会确认游戏启动确实读取了存档，读取失败单独报错。网页修复需刷新，离线工具需重新下载；启动读档确认需要同时升级固件。尚未重新连接或缺少回执时，结果仍未确认，可在核实设备进度后结束本次核对，不要删除原备份。

社区完整安装包的 NVS 空白填充会覆盖旧存档，必须先备份后安装，再导入；仅修改导入网页无法阻止安装清档。新提供的 [USB 更新包](../release/UPDATE.md) 只写应用并核对数据区域，适用于当前分区布局相同的 PokeWalk 设备。该工具生成的原始分区备份不等于可直接导入网页的 `.pksave`。

## 游戏手册

`web/guide/` 为可搜索的游戏介绍与攻略；存档首页、更新说明和攻略相互链接。在线与离线 ZIP 使用同一份公开文件清单，不读取玩家存档。提供“当前发布版 / 上一发布版”切换；默认对应 2026.10.08 的 V21 存档修复固件，可切回 10 月 7 日招式设置版攻略。功能开关与发布状态分别记录，避免把新版玩法误标为开发功能。

发布玩法时运行 `python3 tools/pipeline/export_guide.py --release-ref <已验证源码提交> --release-version <版本名称> --previous-ref <上一公开提交> --previous-version <上一版本名称>`，从两个固定提交分别导出图鉴、路线、道具、招式和成就。默认版本为 10 月 8 日与 10 月 7 日，不能把未发布的 HEAD 自动写成公开版。发布新固件时同步更新导出器中的公开来源、网页版本文案与兼容范围，执行 `python3 tools/pipeline/verify_guide.py` 和存档分发检查，再同步 Pages、devbox 与离线 ZIP。
