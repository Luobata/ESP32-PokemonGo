// main/world.h —— 跨页面的游戏状态与后台扫描（F9-①）。
//
// ## 这个模块解决什么
//
// 在它之前，WiFi 扫描绑在 Collect 页的 lv_timer 上。两个后果：
//
//   · **离开那一页扫描就停** —— P1 的「今日行程」没有数据源，
//     只能写死 70；长跑采集必须把设备停在 Collect 页
//   · **开机得进 Collect 而不是 P1** —— 产品形态上主页应该是 P1，
//     但为了不丢数据只能让开机进采集页（main.c 里那段 BOOT_DEMO
//     的注释就是在解释这个妥协）
//
// world 把扫描 + sensing 收成一个独立 FreeRTOS 任务，
// 页面只读结果。谁在前台都不影响采集。
//
// ## 线程契约
//
// 扫描任务与 LVGL 任务是两个线程。上游 AGENTS.md 的硬规矩是
// **LVGL 非线程安全**，所以：
//
//   · world 任务里**绝不碰 LVGL** —— 只更新自己的状态
//   · 页面读状态走 world_snapshot()，它在**互斥锁内拷一份出来**，
//     调用方拿到的是一致的快照，不会读到改到一半的结构
//
// 为什么是快照而不是直接暴露指针：页面渲染一帧要读七八个字段
// （四条轴 + 遭遇数 + 地点），逐个读会撞上任务在中间改了其中几个 ——
// 屏幕上就是「饱食是新的、心情是旧的」。快照一次锁住全部。
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "nurture.h"
#include "sensing.h"

// 页面看到的世界。**这是个值拷贝**，拿到后随便读，不用加锁。
typedef struct {
    nurture_t pet;                 // 三条轴 + 亲密度

    // 今日行程 0~100。S1 的移动量累积映射来的 —— 见 world.c。
    uint8_t progress;

    // 待处理遭遇数。**F9-② 之前恒为 0** —— S1 的遭遇生成还没移植，
    // 所以 P1 的角标现在是不可达代码。留着字段是因为角标的绘制逻辑
    // 已经写好并且能测（把这里改成非零就能看到它闪），
    // 而不是等 S1 好了再回来加。
    uint8_t pending;
    sens_state_t state;            // 移动 / 驻留
    uint16_t place_id;
    uint8_t biome;

    uint32_t scans;                // 已完成扫描次数（诊断用）
    uint8_t last_ap_count;
} world_t;

// 启动后台任务。**只调一次**（main.c 里，在页面之前）。
// WiFi 起不来时返回 false —— 那时页面照常能画，只是没有感知数据。
//
// **world 是 WiFi 的唯一所有者。** 页面不要再自己 esp_wifi_init ——
// 两个所有者会争同一个射频：Collect 页原本自己 bring_up，
// 与这里撞上就是 esp_wifi_init 返回 ESP_ERR_INVALID_STATE，
// 而它没判那个返回值，会当成初始化失败。
bool world_start(void);

// WiFi 是否可用。Collect 页用它判断该不该自己起 —— 见 world_start。
bool world_wifi_ready(void);

// 取一份一致的快照。任何线程都能调。
void world_snapshot(world_t *out);

// 照料。**由按键触发，走 world 而不是页面自己改** ——
// 状态的唯一所有者是 world，页面只读。
void world_feed(void);

// 与 PC 侧对账用：把移动量累积映射成 0~100 的今日行程。
// 单独暴露是为了能在宿主上测（见 tools/pipeline/verify_world.py）。
uint8_t world_progress_from_motion(uint32_t motion_units);
