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
#   ./tools/inspector/serve.sh --rebuild    # 强制重建验收页，资产读 assets/
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

INSPECTOR_PYTHON="${INSPECTOR_PYTHON:-python3}"
if ! "$INSPECTOR_PYTHON" -c 'import fontTools' >/dev/null 2>&1; then
    if /usr/bin/python3 -c 'import fontTools' >/dev/null 2>&1; then
        INSPECTOR_PYTHON=/usr/bin/python3
    fi
fi

# Never open an old generated template after changing its renderer or assets.
if [ "$REBUILD" = 1 ] || ! "$INSPECTOR_PYTHON" "$REPO_ROOT/tools/pipeline/verify_sim_pages.py" >/dev/null 2>&1; then
    "$INSPECTOR_PYTHON" "$REPO_ROOT/tools/inspector/build.py" --src "$GEN1_SRC" || exit 1
fi

# 已在跑就不重复起；普通静态服务不能提供固件渲染接口。
if curl -fsS --max-time 2 "http://127.0.0.1:$PORT/api/firmware" >/dev/null 2>&1; then
    echo "端口 $PORT 已有服务在跑"
elif curl -sI --max-time 2 "http://127.0.0.1:$PORT/" >/dev/null 2>&1; then
    echo "端口 $PORT 被其他服务占用；请加 --port 8766 或停止旧的静态服务。" >&2
    exit 1
else
    nohup "$INSPECTOR_PYTHON" server.py --port "$PORT" \
        >/tmp/inspector-$PORT.log 2>&1 &
    INSPECTOR_PID=$!
    INSPECTOR_READY=0
    for ((i=0;i<120;i++)); do
        if curl -fsS --max-time 1 "http://127.0.0.1:$PORT/api/firmware" >/dev/null 2>&1; then
            INSPECTOR_READY=1; break
        fi
        if ! kill -0 "$INSPECTOR_PID" 2>/dev/null; then break; fi
        sleep .25
    done
    if [ "$INSPECTOR_READY" != 1 ]; then
        echo "固件预览未就绪，查看 /tmp/inspector-$PORT.log" >&2
        cat "/tmp/inspector-$PORT.log" >&2
        exit 1
    fi
fi

URL="http://127.0.0.1:$PORT/"
echo "验收页面：$URL"
echo
echo "固件同源预览：${URL}firmware.html"
echo "停止服务：pkill -f 'server.py --port $PORT'"

command -v open >/dev/null 2>&1 && open "$URL"
