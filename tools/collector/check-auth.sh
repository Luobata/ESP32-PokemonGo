#!/bin/bash
# 检查能否读到 BSSID（定位授权是否生效）
#
# 用法：
#   ./check-auth.sh          检查裸可执行文件
#   ./check-auth.sh --app    检查打包版（推荐 —— 裸文件拿不到 TCC 授权）
#
# 为什么必须打包成 .app：macOS 的 TCC 按 bundle identifier 判定权限，
# 裸可执行文件没有身份，既进不了「定位服务」列表，sudo 也提不了权（已实测）。

set -uo pipefail
cd "$(dirname "$0")"

BIN=./wifi-collect
if [ "${1:-}" = "--app" ]; then
    BIN=./WiFiCollect.app/Contents/MacOS/wifi-collect
    if [ ! -x "$BIN" ]; then
        echo "先打包：./make-app.sh" >&2
        exit 1
    fi
elif [ ! -x "$BIN" ]; then
    echo "先编译：./build.sh" >&2
    exit 1
fi

echo "检查 BSSID 可读性（${BIN}）..."
echo

if out=$("$BIN" --count 1 --quiet 2>&1); then
    if printf '%s' "$out" | grep -q '"b":"syn:'; then
        echo "✗ 仍是合成伪 BSSID —— 授权未生效"
        echo
        echo "  走 .app 流程：./make-app.sh，详见 README.md#定位授权"
        exit 1
    fi

    total=$(printf '%s' "$out" | grep -o '"b":' | wc -l | tr -d ' ')

    read -r g24 sample <<<"$(printf '%s' "$out" | python3 -c '
import sys, json
try:
    line = [l for l in sys.stdin.read().split("\n") if l.strip()][-1]
    aps = json.loads(line).get("aps", [])
    n24 = sum(1 for a in aps if 0 < a.get("c", 0) <= 14)
    top = sorted(aps, key=lambda a: -a.get("r", -100))[:3]
    parts = ["%s %s %sdBm ch%s" % (
        a["b"], (a.get("s") or "(隐藏)"), a["r"], a["c"]) for a in top]
    print(n24, " | ".join(parts))
except Exception:
    print("?", "")
' 2>/dev/null)"

    echo "✓ BSSID 可读，授权已生效"
    echo
    echo "  扫到 $total 个 AP，其中 2.4GHz $g24 个"
    echo "  （ESP32-C3 只能看到 2.4GHz 那部分）"
    echo
    if [ -n "$sample" ]; then
        echo "  最强的几个："
        printf '%s\n' "$sample" | tr '|' '\n' | sed 's/^ */    /'
        echo
    fi
    echo "可以开始采集了："
    echo "  $BIN -i 30 -o ../../data/raw/home.ndjson"
    exit 0
else
    printf '%s\n' "$out"
    exit 1
fi
