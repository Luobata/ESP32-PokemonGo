#!/bin/bash
# 检查能否读到 BSSID（定位授权是否生效）
#
# 用法：./check-auth.sh
#
# macOS 12+ 要求定位授权才能读取 BSSID/SSID，而 BSSID 是指纹方案的核心字段。
# 授权步骤见 README.md#定位授权。

set -uo pipefail
cd "$(dirname "$0")"

if [ ! -x ./wifi-collect ]; then
    echo "先编译：./build.sh" >&2
    exit 1
fi

echo "检查 BSSID 可读性..."
echo

# 扫一次，不走降级模式 —— 拿不到 BSSID 就会退出并给指引
if out=$(./wifi-collect --count 1 --quiet 2>&1); then
    # 数一下有多少个 AP、多少个 2.4G
    total=$(printf '%s' "$out" | grep -o '"b":' | wc -l | tr -d ' ')
    g24=$(printf '%s' "$out" | python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read().strip().split("\n")[-1])
    print(sum(1 for a in d.get("aps", []) if 0 < a.get("c", 0) <= 14))
except Exception:
    print("?")
' 2>/dev/null)
    sample=$(printf '%s' "$out" | python3 -c '
import sys, json
try:
    d = json.loads(sys.stdin.read().strip().split("\n")[-1])
    aps = sorted(d.get("aps", []), key=lambda a: -a.get("r", -100))
    for a in aps[:3]:
        print(f"    {a[\"b\"]}  {a.get(\"s\") or \"(隐藏)\":<24} {a[\"r\"]:>4}dBm  ch{a[\"c\"]}")
except Exception:
    pass
' 2>/dev/null)

    if printf '%s' "$out" | grep -q '"b":"syn:'; then
        echo "✗ 仍是合成伪 BSSID —— 授权未生效"
        echo
        echo "  按 README.md#定位授权 给 iTerm 授权后重试。"
        exit 1
    fi

    echo "✓ BSSID 可读，授权已生效"
    echo
    echo "  本次扫到 $total 个 AP，其中 2.4GHz $g24 个"
    echo "  （ESP32-C3 只能看到 2.4GHz 那部分）"
    echo
    echo "  最强的几个："
    printf '%s\n' "$sample"
    echo
    echo "可以开始采集了："
    echo "  ./wifi-collect -i 30 -o ../../data/raw/home.ndjson"
    exit 0
else
    # wifi-collect 自己会打印详细指引
    printf '%s\n' "$out"
    exit 1
fi
