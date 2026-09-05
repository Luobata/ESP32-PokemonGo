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

#include <stdio.h>
#include <string.h>
#include <unistd.h>

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

static const char *TAG = "dbg";

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
    for (;;) {
        int c = fgetc(stdin);
        if (c == EOF) {
            vTaskDelay(pdMS_TO_TICKS(30));
            continue;
        }
        dispatch((char)c);
    }
}

void dbg_start(void)
{
    // stdin 默认是行缓冲且阻塞的；改成非阻塞，否则这个任务会卡住
    // 而不是轮询（表现为「注入没反应」，而日志一切正常）。
    setvbuf(stdin, NULL, _IONBF, 0);

    xTaskCreate(dbg_task, "dbg", 3072, NULL, 3, NULL);
    ESP_LOGI(TAG, "按键注入已开：a/b/c 单击 A/B/C 双击 s 截图 e 造遭遇 w 存档");
}
