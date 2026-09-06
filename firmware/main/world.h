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

#include "encounter.h"
#include "nurture.h"
#include "party.h"
#include "sensing.h"

// 页面看到的世界。**这是个值拷贝**，拿到后随便读，不用加锁。
typedef struct {
    nurture_t pet;                 // 三条轴 + 亲密度
    uint16_t species;              // 主宠 = 队伍首位
    uint32_t exp;                  // 主宠累计经验
    uint8_t level;                 // 由累计经验换算出的等级
    uint16_t explore_value;        // 主宠探索值；移动状态的每次扫描 +1

    // 今日行程 0~100。S1 的移动量累积映射来的 —— 见 world.c。
    uint8_t progress;

    uint8_t pending;               // 待处理遭遇数（= queue.count）
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

// 取一份一致的快照。任何 FreeRTOS 任务都能调，不要求持 LVGL 锁；
// 本函数不碰 LVGL，并会在内部短暂等待 world 自己的状态锁。
// LVGL 锁只保护界面对象，不能替代这里对跨任务游戏状态的同步。
// 不可从 ISR 调用（互斥量可能阻塞）。
void world_snapshot(world_t *out);

// 照料。**由按键触发，走 world 而不是页面自己改** ——
// 状态的唯一所有者是 world，页面只读。
void world_feed(void);
void world_play(void);
void world_rest(void);

// 发放主宠经验并立即存档。战斗页只调用一次，状态与持久化由 world 管。
void world_grant_exp(uint16_t amount);

// 原子完成队首进化并立即存档。会在锁内重新核对物种进化目标与两条
// 进度线；expected_species 防止页面快照过期后把另一只误进化。
bool world_evolve_leader(uint16_t expected_species, uint16_t evolve_to);

// 一次提交捕获：收容、点亮图鉴、按 uid 出队在同一个临界区完成，
// 随后立即把包含三者的完整状态存档。无效/已淘汰 uid 返回 false。
bool world_capture_uid(uint16_t uid, const mon_t *mon);

// 遭遇队列与图鉴。**返回指针而不是拷贝** —— 队列 128 字节、
// 图鉴 76 字节，每帧拷一遍不划算，而页面只读不写。
//
// 写操作走下面几个函数，它们内部加锁。
const enc_queue_t *world_queue(void);
const dex_t *world_dex(void);

// 按下标取走（P2 的丢弃 —— 那一刻下标是准的）。加锁。
bool world_take_encounter(uint8_t index, encounter_t *out);

// **按 uid 取走** —— 跨页面（P4 捕获成功/逃跑）必须用这个。
// 返回 false 表示那条已被后台淘汰，正常情况，调用方不用报错。
bool world_take_uid(uint16_t uid, encounter_t *out);

// 把战斗结果写回队列（P3 打完但没抓，HP 要留着给 P4 算窗口）。
void world_update_hp_uid(uint16_t uid, uint8_t hp_ratio);

// 首次结算时标记该遭遇已领取经验。返回 false 表示已领取或已被淘汰。
bool world_mark_exp_granted_uid(uint16_t uid);

// 图鉴登记。加锁。
void world_mark_seen(uint16_t sid, bool shiny);

// 调试用：立刻造一条遭遇。
//
// 真实遭遇要么等基地排程（4 小时一次），要么带着设备走动
// （猎场路径要移动量）。验证玩法链路时两个都等不起 ——
// 而「等 4 小时才能测一次捕获」会让存档这类改动根本没法验。
bool world_debug_spawn(void);

// 调试用：立刻存档。正常路径是捕获时立刻存 + 每 5 分钟节流存，
// 而验证「拔电不丢」时不想等那 5 分钟。
void world_debug_save(void);

// 调试用：把队首两条进化进度设到当前物种的门槛，不执行进化。
// 仅供 CONFIG_POKEWALK_DEBUG_KEYS 的串口验收入口调用。
#ifdef CONFIG_POKEWALK_DEBUG_KEYS
bool world_debug_evolution_ready(void);
#endif

// 与 PC 侧对账用：把移动量累积映射成 0~100 的今日行程。
// 单独暴露是为了能在宿主上测（见 tools/pipeline/verify_world.py）。
uint8_t world_progress_from_motion(uint32_t motion_units);
