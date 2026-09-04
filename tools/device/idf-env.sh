#!/usr/bin/env bash
# 进入 ESP-IDF 环境。用法： source tools/device/idf-env.sh
#
# ## 为什么需要这个包装
#
# 直接 `. ~/esp/esp-idf/export.sh` 在这台机器上会失败：
# pyenv 把 python3 指向 3.12.0，而那个 3.12 是自己编的、**缺 lzma 模块**，
# 解不开 IDF 工具链的 .tar.xz 包：
#
#     tarfile.CompressionError: lzma module is not available
#
# 于是 venv 建在 idf5.5_py3.12_env 却装不全，export.sh 又去找那个路径，
# 报「virtual environment not found」。
#
# 解法是**用系统 Python 3.9.6**（自带 lzma，且满足 IDF ≥3.9 的要求）：
# 把 PATH 前置成系统路径，绕开 pyenv 的 shim。
#
# 环境装好后 venv 是 idf5.5_py3.9_env，与这里的 PATH 设置一致。
# 若将来换机器或修好了 pyenv 的 lzma，直接用官方 export.sh 即可，
# 这个脚本只是为了不再踩同一个坑。

# 让 PATH 以系统目录开头 —— 关键是让 `python3` 解析到 /usr/bin/python3。
# 但 cmake / ninja 装在 homebrew，得跟在后面，否则 idf.py 报
# 「"cmake" must be available on the PATH」。
export PATH="/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:$PATH"
export IDF_PATH="${IDF_PATH:-$HOME/esp/esp-idf}"

if [ ! -f "$IDF_PATH/export.sh" ]; then
  echo "找不到 ESP-IDF：$IDF_PATH" >&2
  echo "安装：" >&2
  echo "  git clone --depth 1 -b v5.5.3 --recursive \\" >&2
  echo "    https://github.com/espressif/esp-idf.git ~/esp/esp-idf" >&2
  echo "  cd ~/esp/esp-idf && /usr/bin/python3 ./tools/idf_tools.py install-python-env" >&2
  echo "  /usr/bin/python3 ./tools/idf_tools.py install --targets=esp32c3" >&2
  return 1 2>/dev/null || exit 1
fi

. "$IDF_PATH/export.sh" >/dev/null 2>&1

if command -v idf.py >/dev/null 2>&1; then
  echo "ESP-IDF $(idf.py --version 2>&1 | head -1) · $(python --version 2>&1)"
else
  echo "export.sh 跑完但 idf.py 仍不可用 —— 检查 ~/.espressif/python_env/" >&2
  return 1 2>/dev/null || exit 1
fi
