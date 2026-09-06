idf_component_register(
    SRCS "main.c"
         "ui_pixel.c"
         "ui_pixel_math.c"
         "assets.c"
         "sensing.c"
         "nurture.c"
         "exp.c"
         "evolution.c"
         "party.c"
         "world.c"
         "battle.c"
         "capture.c"
         "encounter.c"
         "save.c"
         "opening.c"
         "transition.c"
         "nav.c"
         "audio.c"
         "sfx.c"
         "play_opening.c"
         "dbg.c"
         "play_enc.c"
         "play_battle.c"
         "play_capture.c"
         "play_dex.c"
         "screen.c"
         "render.c"
         "play_idle.c"
         "play_care.c"
         "play_collect.c"
         "demo_button.c"
         "demo_battery.c"
         "demo_radio.c"
         "demo_wifi.c"
    INCLUDE_DIRS "."
    REQUIRES bsp esp_event esp_hw_support esp_netif esp_timer esp_wifi nvs_flash
    # 资产直接嵌进 app 分区（158.8 KB，占 3MB 的 5%）——
    # 不另开数据分区：那要多一套分区表与烧写步骤，而这点体积完全放得下。
    #
    # 符号名由文件名推导：gen1_front.bin → _binary_gen1_front_bin_start
    EMBED_FILES "${CMAKE_CURRENT_LIST_DIR}/../../assets/gen1.bin"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/gen1_front.bin"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/gen1_back.bin"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/palettes.bin"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/font16.bin"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/moves.bin"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/ui.bin"
)

# 开发机默认保留串口验收入口；发布构建可用
# `-DCONFIG_POKEWALK_DEBUG_KEYS=OFF` 编译掉状态注入命令。
option(CONFIG_POKEWALK_DEBUG_KEYS "Enable PokeWalk debug key injection" ON)
if(CONFIG_POKEWALK_DEBUG_KEYS)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE CONFIG_POKEWALK_DEBUG_KEYS=1)
endif()
