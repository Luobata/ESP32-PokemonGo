#!/bin/bash
# collect.sh —— 采集入口。这是唯一正确的启动方式。
#
# 为什么不能直接跑 wifi-collect：
#   TCC 按「发起进程的 app 身份」判权。直接 exec .app 里的二进制时，
#   系统认的是调用方（你的 shell），而 shell 不在定位服务授权列表里，
#   于是授权状态永远是 notDetermined、BSSID 永远是 nil。
#   必须用 open -a 经 LaunchServices 启动，进程才真正以 WiFiCollect 的身份运行。
#
# 用法：
#   ./collect.sh                                    # 默认 30s 间隔，写 data/raw/
#   ./collect.sh -i 10 -o data/raw/commute.ndjson   # 相对路径按仓库根解析
#   ./collect.sh --count 1                          # 只扫一次（自检用）

set -uo pipefail
cd "$(dirname "$0")"

APP="$(pwd)/WiFiCollect.app"
# 仓库根 —— 相对路径按它解析，而不是按脚本所在目录。
# 否则 `-o data/raw/x.ndjson` 会落到 tools/collector/data/raw/ 去（踩过）。
REPO_ROOT="$(cd ../.. && pwd)"

if [ ! -d "$APP" ]; then
    echo "先打包：./build.sh && ./make-app.sh" >&2
    exit 1
fi

# 默认参数：30 秒间隔，输出到 data/raw/<日期>.ndjson
if [ $# -eq 0 ]; then
    mkdir -p "$REPO_ROOT/data/raw"
    set -- -i 30 -o "$REPO_ROOT/data/raw/$(date +%Y%m%d-%H%M).ndjson"
fi

# open --args 传参时，相对路径会相对于 app 的工作目录（不确定），
# 所以把 -o 的路径转成绝对路径
args=()
while [ $# -gt 0 ]; do
    case "$1" in
        -o|--out)
            shift
            p="$1"
            case "$p" in
                /*) ;;   # 已是绝对路径
                *)  # 相对路径按仓库根解析，符合「从仓库根敲命令」的直觉
                    p="$REPO_ROOT/$p"
                    mkdir -p "$(dirname "$p")" ;;
            esac
            args+=(-o "$p")
            ;;
        *) args+=("$1") ;;
    esac
    shift
done

# 找出输出路径用于提示
outfile=""
for ((i=0; i<${#args[@]}; i++)); do
    if [ "${args[i]}" = "-o" ]; then outfile="${args[i+1]}"; fi
done

echo "启动采集（经 LaunchServices，以 WiFiCollect 身份运行）"
[ -n "$outfile" ] && echo "输出：$outfile"
echo

open -a "$APP" --args "${args[@]}"

if [ -n "$outfile" ]; then
    echo "已在后台运行。查看进度："
    echo "  wc -l $outfile"
    echo "  tail -c 400 $outfile"
    echo
    echo "停止采集："
    echo "  pkill -f WiFiCollect"
    echo
    # 等第一行落盘，确认真的在工作
    for _ in $(seq 1 20); do
        if [ -s "$outfile" ]; then
            n=$(grep -c '"ts"' "$outfile" 2>/dev/null | tr -d ' \n' || echo 0)
            syn=$(grep -c '"b":"syn:' "$outfile" 2>/dev/null | tr -d ' \n' || echo 0)
            if [ "${syn:-0}" -gt 0 ] 2>/dev/null; then
                echo "⚠️  输出是合成伪 BSSID —— 授权未生效，见 README.md#定位授权"
            else
                echo "✓ 已写入 ${n:-?} 行，BSSID 正常"
            fi
            exit 0
        fi
        sleep 0.5
    done
    echo "（还没写入第一行，稍等几秒后用 wc -l 查看）"
fi
