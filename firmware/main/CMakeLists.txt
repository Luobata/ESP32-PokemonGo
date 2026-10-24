# Isolated asset capacity probe; never enabled by the shipping build.
set(POKEWALK_ASSET_PROBE_DIR "" CACHE PATH "Candidate 251-species assets, build-only")
set(POKEWALK_ART_DIR "${CMAKE_CURRENT_LIST_DIR}/../../assets")
set(POKEWALK_FONT "${POKEWALK_ART_DIR}/font16.bin")
if(POKEWALK_ASSET_PROBE_DIR)
    set(POKEWALK_ART_DIR "${POKEWALK_ASSET_PROBE_DIR}")
    set(POKEWALK_FONT "${POKEWALK_ART_DIR}/font16.bin")
    message(WARNING "Asset capacity probe: gameplay/save support remains 151. Do not flash or publish.")
endif()

idf_component_register(
    SRCS "main.c"
         "ui_pixel.c"
         "ui_pixel_math.c"
         "assets.c"
         "pokemon_names.c"
         "sensing.c"
         "nurture.c"
         "items.c"
         "exp.c"
         "evolution.c"
         "party.c"
         "box_view.c"
         "world.c" "wifi_time.c" "johto.c" "johto_routes.c" "johto_story.c" "story_transactions.c" "johto_activity.c" "activity_transactions.c"
         "combat.c" "trainer.c" "gym_rules.c" "achievements.c" "play_achievements.c"
         "battle.c"
         "battle_escape.c"
         "battle_presentation.c"
         "pokemon_animation.c"
         "shiny_entry.c"
         "battle_fx.c"
         "gold_fx.c"
         "battle_hud.c"
         "game_ui.c"
         "growth_ui.c"
         "evolution_ui.c"
         "capture.c"
         "encounter.c"
         "exploration.c"
         "play_exploration.c"
         "save.c" "save_bank.c" "save_bank_device.c"
         "opening.c"
         "transition.c"
         "nav.c"
         "audio.c"
         "music.c"
         "cry.c" "sound_mixer.c"
         "music_director.c"
         "sfx.c" "audio_settings.c" "display_settings.c"
         "play_opening.c"
         "play_starter.c"
         "dbg.c" "console_record.c" "usb_backup.c" "usb_backup_device.c" "restore_journal.c"
         "play_enc.c"
         "play_battle.c"
         "play_capture.c"
         "play_dex.c"
         "screen.c"
         "battery_ui.c"
         "screen_idle.c"
         "render.c"
         "play_idle.c"
         "play_care.c"
         "play_bag.c"
         "play_menu.c"
         "play_party.c"
         "play_trainer.c" "dungeon.c" "dungeon_rewards.c" "play_dungeon.c" "play_johto.c" "play_activity.c" "play_story.c" "play_narrative.c" "narrative_script.c"
         "play_collect.c"
         "demo_button.c"
         "demo_battery.c"
         "demo_radio.c"
         "demo_wifi.c"
    INCLUDE_DIRS "."
    REQUIRES esp_http_server lwip esp_app_format esp_partition bsp esp_event esp_hw_support esp_netif esp_timer esp_wifi nvs_flash esp_driver_usb_serial_jtag
    # 资产直接嵌进 app 分区（158.8 KB，占 3MB 的 5%）——
    # 不另开数据分区：那要多一套分区表与烧写步骤，而这点体积完全放得下。
    #
    # 符号名由文件名推导：gen1_front.bin → _binary_gen1_front_bin_start
    EMBED_FILES "${POKEWALK_ART_DIR}/gen1.bin"
                "${POKEWALK_ART_DIR}/gen1_front.bin"
                "${POKEWALK_ART_DIR}/gen1_back.bin"
                "${POKEWALK_ART_DIR}/palettes.bin"
                "${POKEWALK_FONT}"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/moves.bin"
                "${CMAKE_CURRENT_LIST_DIR}/../../assets/ui.bin"
)

# 开发机默认保留串口验收入口；发布构建可用
# `-DCONFIG_POKEWALK_DEBUG_KEYS=OFF` 编译掉状态注入命令。
option(CONFIG_POKEWALK_DEBUG_KEYS "Enable PokeWalk debug key injection" ON)
if(CONFIG_POKEWALK_DEBUG_KEYS)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE CONFIG_POKEWALK_DEBUG_KEYS=1)
endif()

if(POKEWALK_ASSET_PROBE_DIR)
    target_compile_definitions(${COMPONENT_LIB} PRIVATE
        POKEWALK_ANIMATION_HEADER="${POKEWALK_ART_DIR}/pokemon_animation_assets.h")
endif()

# Raster hot loops run on every 20-row band. Keep debug symbols/assertions, but
# optimize these stateless pixel kernels as in the native preview (-O2).
set_source_files_properties(screen.c render.c game_ui.c gold_fx.c battle_hud.c
    battle_fx.c pokemon_animation.c PROPERTIES COMPILE_OPTIONS "-O2")

# The higher-priority PCM producer shares the C3's single core with LVGL.
# Preserve every sample and tempo; reduce time spent in synthesis per chunk.
set_source_files_properties(audio.c music.c cry.c sound_mixer.c
    PROPERTIES COMPILE_OPTIONS "-O2")
