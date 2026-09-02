#!/bin/bash
# 拉取 Tuxemon 素材（稀疏克隆，只要怪物数据和战斗精灵图）
#
# 完整仓库很大，这里只取两个目录：
#   mods/tuxemon/db/monster        411 个怪物 YAML
#   mods/tuxemon/gfx/sprites/battle 413 张 128×88 精灵图（约 1.2MB）
#
# 素材许可：自用不分发场景下不触发义务。若将来要分发，
# 必须逐文件比对 ATTRIBUTIONS.md（含 13 个 NC 文件）——见 docs/05-art-audio.md#54

set -euo pipefail

DEST="${1:-/tmp/tuxemon}"

if [ -d "$DEST/.git" ]; then
    echo "已存在 $DEST，跳过克隆。要重新拉取先删掉它。"
    exit 0
fi

echo "稀疏克隆 Tuxemon → $DEST"
git clone --depth 1 --filter=blob:none --sparse \
    https://github.com/Tuxemon/Tuxemon.git "$DEST"

cd "$DEST"
git sparse-checkout set \
    mods/tuxemon/db/monster \
    mods/tuxemon/gfx/sprites/battle \
    ATTRIBUTIONS.md

echo
echo "✓ 完成"
echo "  怪物 YAML: $(ls mods/tuxemon/db/monster/*.yaml 2>/dev/null | wc -l | tr -d ' ') 个"
echo "  精灵图:    $(ls mods/tuxemon/gfx/sprites/battle/*.png 2>/dev/null | wc -l | tr -d ' ') 张"
echo
echo "下一步："
echo "  python3 tools/pipeline/convert_monsters.py --src $DEST/mods/tuxemon/db/monster"
echo "  python3 tools/pipeline/budget.py"
