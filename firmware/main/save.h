// main/save.h —— S18 存档。
//
// ## 为什么用 NVS 而不是 S6 设计的双 buffer
//
// S6 文档设计了「A/B 两槽 + CRC32 + 单调递增序号」，理由是
// **任何时刻掉电都至少有一份完好**（写 A 时掉电就回退到 B）。
// 那个理由完全成立 —— 但 NVS 已经提供同样的保证：
// 每条记录带 CRC32、页级状态机、写入未完成的条目在下次挂载时被丢弃。
//
// 区别在于双 buffer 要我自己实现「先写数据后写 CRC」的顺序、
// 自己处理擦除块边界、自己做磨损均衡；而这三件事写错的表现都是
// 「拔电偶尔丢档」—— 概率性的、极难复现的那类缺陷。
//
// 用 NVS 是把这三件事交给已经被大量产品验证过的实现。
// 代价是存档格式不再与 sim/state.py 的字节布局一致 ——
// 但那份布局本来就只是**给固件参考的**，PC 侧不读设备存档。
//
// 分区：用现成的 nvs（0x6000 = 24 KB），不新增分区。
// 上游 AGENTS.md 那三条契约（app ≤3MB、cardid@0x356000、
// recovery@0x700000）都不受影响。
//
// ## 存什么
//
// 约 292 字节：遭遇队列 160 + 图鉴 76 + 养成 24 + 主宠 16 + 累积量 16。
// **不存的东西**：sensing 的地点记忆（2.6 KB，重启后重新学更省事，
// 且它本来就是滚动窗口）、招式列表（现算，见 assets_known_moves）。
#pragma once

#include <stdbool.h>
#include <stdint.h>

#include "encounter.h"
#include "nurture.h"

// 存档版本。**加字段时必须 +1** —— load 会拒绝不认识的版本，
// 那比读到错位的字段好（错位不报错，只是数值离谱）。
#define SAVE_VERSION 1

typedef struct {
    uint16_t version;

    // 养成（S4）
    nurture_t pet;

    // 主宠身份。物种与等级现在还是固定值，但存档里留好位置 ——
    // 接 S14 队伍时不用改格式。
    uint16_t species;
    uint8_t level;
    uint32_t exp;

    // 遭遇队列（S1）与图鉴（S5/S8）
    enc_queue_t queue;
    dex_t dex;

    // 累积量：今日行程的来源、诊断用的扫描计数
    uint32_t motion_q10;
    uint32_t scans;

    // 上次存盘时的开机微秒数。**不是墙钟** —— 设备没有 RTC 对时。
    // 用途是算「关机了多久」：下次开机的 esp_timer 从 0 开始，
    // 所以只能知道「上次跑了多久」，不知道中间隔了多久。
    // 这正是 S4 的 on_reunion（「好久不见」）现在接不上的原因。
    int64_t last_uptime_us;
} save_t;

// 初始化 NVS。**在任何 save_read/write 之前调**。
// 幂等，且不依赖 WiFi —— 见 save.c 里那段（这条依赖搞反过一次：
// NVS 初始化藏在 wifi_bring_up 里，而读档在起 WiFi 之前，
// 于是每次开机都读不到存档，而写入是成功的）。
bool save_init(void);

// 存。**会阻塞几毫秒**（flash 写），别在渲染循环里调。
bool save_write(const save_t *s);

// 读。没有存档或版本不认识时返回 false，调用方该用初始状态。
bool save_read(save_t *out);

// 清档（调试用）。
bool save_erase(void);

// 有没有存档 —— 开机时用它决定走「继续」还是「新游戏」。
bool save_exists(void);
