#!/bin/bash
# 构建 wifi-collect
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v swiftc >/dev/null 2>&1; then
    echo "错误：找不到 swiftc。安装 Xcode Command Line Tools：" >&2
    echo "  xcode-select --install" >&2
    exit 1
fi

echo "编译 wifi-collect..."
swiftc -O wifi-collect.swift -o wifi-collect \
    -framework CoreWLAN -framework CoreLocation

echo "✓ 完成 → $(pwd)/wifi-collect"
echo
echo "试跑一次（扫 1 轮，输出到终端）："
echo "  ./wifi-collect --count 1"
