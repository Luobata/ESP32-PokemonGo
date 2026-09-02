#!/bin/bash
# 把 wifi-collect 打包成 .app —— 这是拿到 BSSID 的正解
#
# 为什么需要这一步：
#   macOS 的 TCC（隐私授权）按 bundle identifier 判定权限。
#   裸可执行文件没有 bundle id，所以既不会出现在「定位服务」列表里，
#   也无法通过 sudo 提权绕过 —— 实测 sudo 同样拿不到 BSSID。
#   打包成 .app 后它有了身份，才能被授权。

set -euo pipefail
cd "$(dirname "$0")"

APP="WiFiCollect.app"
BUNDLE_ID="local.esp32pokemongo.wificollect"

if [ ! -x ./wifi-collect ]; then
    echo "先编译：./build.sh" >&2
    exit 1
fi

echo "打包 $APP ..."
rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS"

cp wifi-collect "$APP/Contents/MacOS/wifi-collect"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>wifi-collect</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleName</key>
    <string>WiFiCollect</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>LSUIElement</key>
    <true/>
    <key>NSLocationUsageDescription</key>
    <string>读取周围 WiFi 的 BSSID，用于构建环境指纹。数据只存本地。</string>
    <key>NSLocationWhenInUseUsageDescription</key>
    <string>读取周围 WiFi 的 BSSID，用于构建环境指纹。数据只存本地。</string>
</dict>
</plist>
PLIST

# 自签名。TCC 要求有稳定签名身份才能记住授权决定；
# ad-hoc 签名（-）足够本地使用，不需要开发者账号。
codesign --force --deep --sign - "$APP" 2>/dev/null \
    || echo "警告：签名失败，授权可能不被记住" >&2

BIN="$(pwd)/$APP/Contents/MacOS/wifi-collect"

echo "✓ 完成 → $(pwd)/$APP"
echo
echo "接下来："
echo
echo "  1. 跑一次，触发授权弹窗（首次会弹「是否允许使用位置」→ 点允许）："
echo "     $BIN --count 1 --quiet | head -c 200"
echo
echo "  2. 如果没弹窗，去系统设置 → 隐私与安全性 → 定位服务，"
echo "     找到 WiFiCollect 打开开关（现在它会出现在列表里了）"
echo
echo "  3. 验证：./check-auth.sh --app"
echo
echo "  4. 采集时用 .app 里的这个可执行文件："
echo "     $BIN -i 30 -o ../../data/raw/home.ndjson"
