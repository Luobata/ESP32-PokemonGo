// main/dbg.c —— 串口注入按键，让整条玩法链路可以自动走一遍。
//
// ## 为什么需要这个
//
// P1→P2→P3→P4→P6 这条链路要按十几次键才能走完，而验证一次改动
// 就得走一遍。靠人按的问题不是累 —— 是**我自己没法验证**：
// 改完只能烧进去然后请人帮忙按，一个来回几分钟。
//
// 有了它，PC 侧一条命令就能走完整条链路并逐页截图：
//     python3 tools/device/walk.py
//
// 这与截图通道是同一个思路的两半：截图解决「我看不见屏幕」，
// 这个解决「我按不了键」。两个都有了，渲染与交互才能自助验证。
//
// ## 只在调试构建里
//
// 用 CONFIG_POKEWALK_DEBUG_KEYS 控制（默认开，因为这台设备就是开发机）。
// 关掉之后整个文件编译成空 —— 不留后门。
//
// ## 为什么是轮询而不是中断
//
// USB-JTAG 的 stdin 没有可靠的「有数据」中断，而这个通道只在
// 调试时用，30ms 一次轮询的开销可以忽略（对比 WiFi 扫描 1.4 秒）。

#include <inttypes.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "bsp_audio.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "esp_vfs_dev.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "bsp_display.h"
#include "dbg.h"
#include "nav.h"
#include "world.h"
#include "screen.h"
#include "sfx.h"

static const char *TAG = "dbg";

// 战斗种子覆盖。0 = 不覆盖（用 enc.ts，与正常路径一致）。
// play_battle.c 在 battle_run() 前读这个值。
// 设为特定值（如 31）可让第一场战斗第一回合就 miss，
// 用来截「的攻击落空了！」的真机图 —— miss 是随机事件，不注入截不到。
uint32_t dbg_battle_seed = 0;

#define AUDIO_PROBE_SAMPLES 480
static int16_t s_audio_probe_pcm[AUDIO_PROBE_SAMPLES];

typedef struct {
    uint64_t square_sum;
    uint32_t samples;
    uint32_t peak;
    uint32_t adc_clip;
    uint32_t read_errors;
} audio_probe_stats_t;

static uint32_t isqrt_u64(uint64_t value)
{
    uint64_t result = 0;
    uint64_t bit = 1ULL << 62;
    while (bit > value) bit >>= 2;
    while (bit) {
        if (value >= result + bit) {
            value -= result + bit;
            result = (result >> 1) + bit;
        } else {
            result >>= 1;
        }
        bit >>= 2;
    }
    return (uint32_t)result;
}

static audio_probe_stats_t audio_probe_capture(uint32_t total)
{
    audio_probe_stats_t stats = {0};
    while (stats.samples < total) {
        uint32_t count = total - stats.samples;
        if (count > AUDIO_PROBE_SAMPLES) count = AUDIO_PROBE_SAMPLES;
        if (bsp_audio_read(s_audio_probe_pcm,
                           count * sizeof(s_audio_probe_pcm[0])) != ESP_OK) {
            stats.read_errors++;
            break;
        }
        for (uint32_t i = 0; i < count; i++) {
            int32_t sample = s_audio_probe_pcm[i];
            uint32_t magnitude = (uint32_t)(sample < 0 ? -sample : sample);
            stats.square_sum += (uint64_t)magnitude * magnitude;
            if (magnitude > stats.peak) stats.peak = magnitude;
            if (magnitude >= 32767u) stats.adc_clip++;
        }
        stats.samples += count;
    }
    return stats;
}

static void audio_probe(void)
{
    const uint32_t samples = audio_sfx_samples(SFX_EVOLVE);
    audio_probe_stats_t quiet = audio_probe_capture(samples);

    sfx_play(SFX_EVOLVE);
    vTaskDelay(pdMS_TO_TICKS(10));
    audio_probe_stats_t sound = audio_probe_capture(samples);

    uint32_t quiet_rms = quiet.samples
        ? isqrt_u64(quiet.square_sum / quiet.samples) : 0;
    uint32_t sound_rms = sound.samples
        ? isqrt_u64(sound.square_sum / sound.samples) : 0;
    uint32_t ratio_q8 = sound_rms * 256u / (quiet_rms ? quiet_rms : 1u);

    ESP_LOGI(TAG, "@@AUDIO_PROBE volume=%u quiet_samples=%" PRIu32
             " quiet_rms=%" PRIu32 " quiet_peak=%" PRIu32
             " sound_samples=%" PRIu32 " sound_rms=%" PRIu32
             " sound_peak=%" PRIu32 " ratio_q8=%" PRIu32
             " adc_clip=%" PRIu32 " read_errors=%" PRIu32,
             SFX_VOLUME_PERCENT, quiet.samples, quiet_rms, quiet.peak,
             sound.samples, sound_rms, sound.peak, ratio_q8,
             sound.adc_clip, quiet.read_errors + sound.read_errors);
}

// 单字符命令 → (按键, 事件)。
//
// 小写 = 单击，大写 = 双击，'!' 前缀 = 长按。
// 选这套映射是因为它能在一行 shell 字符串里表达完整路径：
//     printf 'c\\nb\\na\\n' —— C 进遭遇、B 战斗、A 捕获
static void dispatch(char c)
{
    bsp_btn_t btn;
    bsp_btn_ev_t ev = BSP_BTN_CLICK;

    switch (c) {
    case 'a': btn = BSP_BTN_UP;   break;
    case 'b': btn = BSP_BTN_DOWN; break;
    case 'c': btn = BSP_BTN_OK;   break;
    case 'A': btn = BSP_BTN_UP;   ev = BSP_BTN_DOUBLE; break;
    case 'B': btn = BSP_BTN_DOWN; ev = BSP_BTN_DOUBLE; break;
    case 'C': btn = BSP_BTN_OK;   ev = BSP_BTN_DOUBLE; break;
    case 's':                       // 截图，不经过按键
        if (bsp_lvgl_lock(2000)) { screen_dump(); bsp_lvgl_unlock(); }
        return;
    case 'e':                       // 造一条遭遇（不然要等 4 小时排程）
        world_debug_spawn();
        return;
    case 'w':                       // 立刻存档（验证掉电不丢）
        world_debug_save();
        return;
    case 'r':                       // 静音基线 + 扬声器播放期间的麦克风 RMS
        audio_probe();
        return;
#ifdef CONFIG_POKEWALK_DEBUG_KEYS
    case 'v':                       // 只注入进化判定输入，不绕过 evo_check
        world_debug_evolution_ready();
        return;
#endif
    default:
        return;
    }

    ESP_LOGI(TAG, "注入 %c", c);
    // **必须加 LVGL 锁** —— 这是独立任务，而页面回调会碰 LVGL 对象。
    // 真实按键路径由 bsp_button 的回调加锁（见 main.c 的 on_key），
    // 这条路径要自己加，否则偶发崩在 lv_obj_delete 里。
    if (bsp_lvgl_lock(2000)) {
        nav_key(btn, ev);
        bsp_lvgl_unlock();
    }
}

static void dbg_task(void *arg)
{
    (void)arg;
    bool sfx_command = false;
    int sfx_id = -1;
    bool seed_command = false;
    uint32_t seed_val = 0;
    for (;;) {
        int c = fgetc(stdin);
        if (c == EOF) {
            vTaskDelay(pdMS_TO_TICKS(30));
            continue;
        }
        if (sfx_command) {
            if (c >= '0' && c <= '9') {
                if (sfx_id < 0) sfx_id = 0;
                sfx_id = sfx_id * 10 + c - '0';
                continue;
            }
            if ((c == ' ' || c == '\t') && sfx_id < 0) continue;
            if (c == '\n' || c == '\r') {
                if (sfx_id >= 0 && sfx_id < SFX_COUNT) {
                    ESP_LOGI(TAG, "播放音效 %d", sfx_id);
                    sfx_play((sfx_id_t)sfx_id);
                } else {
                    ESP_LOGW(TAG, "音效编号无效：%d", sfx_id);
                }
            }
            sfx_command = false;
            sfx_id = -1;
            continue;
        }
        if (seed_command) {
            if (c >= '0' && c <= '9') {
                seed_val = seed_val * 10u + (uint32_t)(c - '0');
                continue;
            }
            if ((c == ' ' || c == '\t') && seed_val == 0) continue;
            if (c == '\n' || c == '\r') {
                dbg_battle_seed = seed_val;
                ESP_LOGI(TAG, "战斗种子注入：%u", (unsigned)seed_val);
            }
            seed_command = false;
            seed_val = 0;
            continue;
        }
        if (c == 'p') {
            sfx_command = true;
            sfx_id = -1;
            continue;
        }
        if (c == 'm') {
            seed_command = true;
            seed_val = 0;
            continue;
        }
        dispatch((char)c);
    }
}

void dbg_start(void)
{
    sfx_start();

    // stdin 默认是行缓冲且阻塞的；改成非阻塞，否则这个任务会卡住
    // 而不是轮询（表现为「注入没反应」，而日志一切正常）。
    setvbuf(stdin, NULL, _IONBF, 0);

    xTaskCreate(dbg_task, "dbg", 3072, NULL, 3, NULL);
#ifdef CONFIG_POKEWALK_DEBUG_KEYS
    ESP_LOGI(TAG, "按键注入已开：a/b/c 单击 A/B/C 双击 s 截图 e 造遭遇 w 存档 v evo-ready p <id> 音效 m <seed> 战斗种子 r 回采");
#else
    ESP_LOGI(TAG, "按键注入已开：a/b/c 单击 A/B/C 双击 s 截图 e 造遭遇 w 存档 p <id> 音效 m <seed> 战斗种子 r 回采");
#endif
}
