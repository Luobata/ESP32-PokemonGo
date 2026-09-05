// main/save.c —— S18 存档。设计与取舍见 save.h。

#include <string.h>

#include "esp_log.h"
#include "nvs.h"
#include "nvs_flash.h"

#include "save.h"

static const char *TAG = "save";

// NVS 初始化。**存档必须自己负责这件事**，不能指望别人先做。
//
// 第一版没有这个函数 —— nvs_flash_init 藏在 world.c 的
// wifi_bring_up() 里，而 world_start 的顺序是「先读档、后起 WiFi」。
// 于是读档时 NVS 还没挂载，nvs_open 直接失败，
// **表现为「每次开机都是新游戏」而写入明明成功**。
//
// 教训是所有权：存档不依赖 WiFi，就不该等 WiFi 顺手把 NVS 带起来。
// 幂等 —— 重复调用返回 ESP_OK，所以 wifi_bring_up 那边不用改。
bool save_init(void)
{
    esp_err_t e = nvs_flash_init();
    if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        ESP_LOGW(TAG, "NVS 需要擦除重建（版本变了或写满）");
        ESP_ERROR_CHECK(nvs_flash_erase());
        e = nvs_flash_init();
    }
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "NVS 初始化失败: %s —— 存档不可用", esp_err_to_name(e));
        return false;
    }
    return true;
}

#define NS "pokewalk"      // NVS 命名空间
#define KEY "state"        // 整个 save_t 当一个 blob 存

// 整块存而不是逐字段存 kv。
//
// 逐字段的好处是能单独更新（比如只改图鉴不动队列），
// 但那样**一次存档要 8 次 nvs_set + 8 次可能失败的点**，
// 而且字段加减时要同步维护键名表。
//
// 整块 292 字节，NVS 的 blob 上限是 508000 字节 —— 绰绰有余。
// 原子性也更好：要么整块新的，要么整块旧的，不会出现
// 「图鉴是新的而队列是旧的」这种半更新状态。

bool save_write(const save_t *s)
{
    nvs_handle_t h;
    esp_err_t e = nvs_open(NS, NVS_READWRITE, &h);
    if (e != ESP_OK) {
        ESP_LOGE(TAG, "打开失败: %s", esp_err_to_name(e));
        return false;
    }

    e = nvs_set_blob(h, KEY, s, sizeof(*s));
    if (e == ESP_OK) {
        // **commit 不能省** —— nvs_set_blob 只写进缓存，
        // 不 commit 的话拔电就丢了，而函数返回值是成功的。
        e = nvs_commit(h);
    }
    nvs_close(h);

    if (e != ESP_OK) {
        ESP_LOGE(TAG, "写入失败: %s", esp_err_to_name(e));
        return false;
    }
    return true;
}

bool save_read(save_t *out)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) return false;

    size_t len = sizeof(*out);
    esp_err_t e = nvs_get_blob(h, KEY, out, &len);
    nvs_close(h);

    if (e != ESP_OK) return false;

    // 长度与版本都要验。
    //
    // **长度对不上直接拒绝**：结构体加了字段但版本号忘了改时，
    // 旧存档会被按新布局解读 —— 那不会报错，只是所有字段错位，
    // 表现为「图鉴突然满了」「三条轴是天文数字」这种莫名其妙的状态。
    if (len != sizeof(*out)) {
        ESP_LOGW(TAG, "存档 %u 字节 ≠ 结构体 %u —— 格式变了，丢弃",
                 (unsigned)len, (unsigned)sizeof(*out));
        return false;
    }
    if (out->version != SAVE_VERSION) {
        ESP_LOGW(TAG, "存档版本 %u ≠ %d —— 丢弃",
                 out->version, SAVE_VERSION);
        return false;
    }
    return true;
}

bool save_exists(void)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READONLY, &h) != ESP_OK) return false;
    size_t len = 0;
    esp_err_t e = nvs_get_blob(h, KEY, NULL, &len);
    nvs_close(h);
    return e == ESP_OK && len == sizeof(save_t);
}

bool save_erase(void)
{
    nvs_handle_t h;
    if (nvs_open(NS, NVS_READWRITE, &h) != ESP_OK) return false;
    esp_err_t e = nvs_erase_key(h, KEY);
    if (e == ESP_OK || e == ESP_ERR_NVS_NOT_FOUND) e = nvs_commit(h);
    nvs_close(h);
    return e == ESP_OK;
}
