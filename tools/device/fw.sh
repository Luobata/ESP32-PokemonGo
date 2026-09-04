#!/usr/bin/env bash
# 构建 / 烧写 / 监控 —— 固件开发的三件事，一个脚本。
#
# 用法：
#   tools/device/fw.sh build          构建
#   tools/device/fw.sh flash          构建并烧写（会先确认备份存在）
#   tools/device/fw.sh monitor        烧写后看日志
#   tools/device/fw.sh backup         备份设备当前 8MB flash
#   tools/device/fw.sh restore FILE   把备份写回去
#
# ## 为什么烧写前强制要备份
#
# 这台设备出厂/社区固件是别人的成果（比如 sunny0826 的离线图鉴玩法，
# 1025 只精灵 + 叫声，5.9MB 数据分区）。覆盖掉就没了，
# 而重新装回去要走小程序 BLE 安装。
#
# 上游文档 STEP 05 明确写了「安装前保留可恢复版本」，这里把它变成硬门禁：
# 没有备份就不让烧。

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
FW="$REPO/firmware"
BACKUP_DIR="$REPO/.device-backup"
PORT="${ESPPORT:-/dev/cu.usbmodem11301}"

cmd="${1:-build}"

idf() {
  # shellcheck disable=SC1091
  source "$HERE/idf-env.sh" >/dev/null
  cd "$FW"
  "$@"
}

case "$cmd" in
build)
  idf idf.py build
  ;;

backup)
  mkdir -p "$BACKUP_DIR"
  out="$BACKUP_DIR/flash-$(date +%Y%m%d-%H%M%S).bin"
  echo "备份 8MB flash → $out（约几分钟）"
  idf python -m esptool --chip esp32c3 -p "$PORT" read_flash 0x0 0x800000 "$out"
  ls -la "$out"
  ;;

flash)
  # 硬门禁：没有任何备份就拒绝烧写
  if ! ls "$BACKUP_DIR"/flash-*.bin >/dev/null 2>&1; then
    echo "✗ 没有找到设备备份，拒绝烧写。" >&2
    echo "  设备上可能是别人的玩法，覆盖前先备份：" >&2
    echo "    tools/device/fw.sh backup" >&2
    exit 1
  fi
  newest="$(ls -t "$BACKUP_DIR"/flash-*.bin | head -1)"
  echo "已有备份：$newest"
  idf idf.py -p "$PORT" flash
  ;;

monitor)
  # 用我们自己的 monitor.py 而非 idf.py monitor —— 后者会独占终端，
  # 且解析不出硬件事实表。要原始日志加 --raw。
  python3 "$HERE/monitor.py" "${@:2}"
  ;;

restore)
  file="${2:-}"
  [ -f "$file" ] || { echo "用法: fw.sh restore <备份文件>" >&2; exit 1; }
  echo "把 $file 写回设备（覆盖当前固件）"
  idf python -m esptool --chip esp32c3 -p "$PORT" write_flash 0x0 "$file"
  ;;

*)
  sed -n '2,14p' "$0"
  exit 1
  ;;
esac
