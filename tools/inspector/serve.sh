#!/bin/bash
# 启动验收页面 —— 在浏览器里看 151 只 sprite 与动效
#
# 为什么需要它：sprite 和动效用终端 ASCII 看不出好坏。
# 呼吸方向、体型对比、四阶灰层次这些只能在真实像素下判断。
#
# 页面从 gen1.bin / gen1_front.bin / gen1_back.bin **直接解码** ——
# 读的是固件真实产物，不是另画一份，否则验收就没意义。
#
# 用法：
#   ./tools/inspector/serve.sh              # 起服务并打开浏览器
#   ./tools/inspector/serve.sh --rebuild    # 先重新打包资产再起
#   ./tools/inspector/serve.sh --port 9000

set -uo pipefail
cd "$(dirname "$0")"
REPO_ROOT="$(cd ../.. && pwd)"

PORT=8765
REBUILD=0
GEN1_SRC="/tmp/gen1"

while [ $# -gt 0 ]; do
    case "$1" in
        --port) shift; PORT="$1" ;;
        --rebuild) REBUILD=1 ;;
        --src) shift; GEN1_SRC="$1"; REBUILD=1 ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) echo "未知参数：$1（--help 查看用法）" >&2; exit 2 ;;
    esac
    shift
done

if [ "$REBUILD" = 1 ]; then
    if [ ! -f "$GEN1_SRC/gen1.json" ]; then
        echo "错误：找不到 $GEN1_SRC/gen1.json" >&2
        echo "先跑：python3 tools/pipeline/fetch_gen1.py --out $GEN1_SRC" >&2
        exit 1
    fi
    echo "重新打包资产..."
    python3 "$REPO_ROOT/tools/inspector/build.py" --src "$GEN1_SRC" || exit 1
fi

if [ ! -f index.html ]; then
    echo "index.html 不存在，先构建：" >&2
    echo "  ./tools/inspector/serve.sh --rebuild" >&2
    exit 1
fi

# 已在跑就不重复起
if curl -sI --max-time 2 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    echo "端口 $PORT 已有服务在跑"
else
    nohup python3 -m http.server "$PORT" --bind 127.0.0.1 \
        >/tmp/inspector-$PORT.log 2>&1 &
    sleep 1
fi

URL="http://127.0.0.1:$PORT/"
echo "验收页面：$URL"
echo
echo "停止服务：pkill -f 'http.server $PORT'"

command -v open >/dev/null 2>&1 && open "$URL"
