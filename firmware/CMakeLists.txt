cmake_minimum_required(VERSION 3.16)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)

# 上游 AGENTS.md 的强制契约：社区固件经 USB 安装时会替换 bootloader，
# 所有衍生构建都必须保留 factory Recovery 手势（上键长按 5 秒），
# 否则 USB 开发会把设备卡在小程序 BLE 安装路径之外。
idf_build_set_property(
    BOOTLOADER_EXTRA_COMPONENT_DIRS
    "${CMAKE_CURRENT_LIST_DIR}/bootloader_components/"
    APPEND)

project(PokeWalk)
