// 共享渲染配方的构建期 CLI（D77 第 2 步，web-coder 第二十六派活）。
//
// 用途：把 render_scene.h 的配方对给定 (cur,max) 求值成绝对矩形，
// 以 JSON 打到 stdout，供 tools/inspector/build.py 在构建期导出进 payload。
//
// 为什么是「构建期 CLI」而不是 WASM 或运行时服务：
//   docs/11-render-engine.md:36 判定过 —— 确定性演示时间线本来就在构建期
//   导出页面数据，所以同一条 C 只要能在构建期求值就够，不必引入 WASM 工具链。
//   本文件就是那条判定的落地。任意交互输入才需要 WASM，那是第 5 步。
//
// 与 /tmp/pokemon-render-engine/probe.c 的区别（那是 cep-coder 的验证探针）：
//   探针有 mode 0/1/2 三条路径（含 legacy draw_bar 复刻与整屏 RGB565 dump），
//   用来证明「配方 == 旧实现」和「JS 消费 == native」。**那是一次性证据。**
//   正式流程只需要 mode 2 那一条：求矩形、输出。**不搬运脚手架。**
//
// 编译（build.py 自动做，无需手工）：
//   cc -std=c11 -I firmware/main -o <tmp>/scene_cli tools/pipeline/scene_cli.c
//
// 用法：
//   scene_cli p3_pet_hp <cur> <max>        单帧
//   scene_cli p3_pet_hp_batch <c0>/<m0> <c1>/<m1> ...   多帧（一次进程调用）
//
// 输出（stdout，JSON）：
//   {"w":240,"h":320,"rects":[[x,y,w,h,rgb565], ...]}
//   batch 模式：{"w":240,"h":320,"frames":[{"cur":..,"max":..,"rects":[...]}, ...]}

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "render_scene.h"

static int g_first;

static void emit_json(void *ctx, int x, int y, int w, int h, uint16_t color)
{
    (void)ctx;
    printf("%s[%d,%d,%d,%d,%u]", g_first ? "" : ",", x, y, w, h, color);
    g_first = 0;
}

static void one_frame(unsigned cur, unsigned max)
{
    printf("{\"cur\":%u,\"max\":%u,\"rects\":[", cur, max);
    g_first = 1;
    scene_p3_pet_hp(emit_json, NULL, (uint16_t)cur, (uint16_t)max);
    printf("]}");
}

static void emit_text_json(void *ctx, int x, int y, const char *text,
                           uint16_t color)
{
    (void)ctx;
    // text 是 borrowed 指针（render_scene.h:24「only for the duration of this
    // synchronous callback」）—— 这里**同步拷进 stdout**，不留存指针，符合契约。
    printf("{\"x\":%d,\"y\":%d,\"color\":%u,\"text\":\"", x, y, color);
    for (const char *p = text; *p; p++) {
        if (*p == '"' || *p == '\\') putchar('\\');
        putchar(*p);
    }
    printf("\"}");
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "用法: scene_cli p3_pet_hp <cur> <max>\n"
                        "      scene_cli p3_pet_hp_batch <cur>/<max> ...\n"
                        "      scene_cli p3_pet_name <name> <level>\n");
        return 2;
    }
    if (strcmp(argv[1], "p3_pet_name") == 0) {
        // D91 第 4 步：文本配方。输出是「文本 + 位置 + 颜色」不是矩形 ——
        // 截断（D53 去空格回退）由配方自己判定，web 侧零逻辑。
        // font_size 传 16：与 assets/font16.bin 的字号一致
        // （render_char_advance_sized 的规则是 cp<0x80 ? size/2 : size）。
        if (argc != 4) return 2;
        const char *name = argv[2];
        size_t nlen = strlen(name);
        if (nlen > 255) return 2;
        printf("{\"w\":%d,\"h\":%d,\"item\":", SCREEN_W, SCREEN_H);
        scene_p3_pet_name_sized(emit_text_json, NULL, name, (uint8_t)nlen,
                                (uint8_t)atoi(argv[3]), 16);
        printf("}\n");
        return 0;
    }
    if (strcmp(argv[1], "p3_pet_hp") == 0) {
        if (argc != 4) return 2;
        printf("{\"w\":%d,\"h\":%d,\"rects\":[", SCREEN_W, SCREEN_H);
        g_first = 1;
        scene_p3_pet_hp(emit_json, NULL,
                        (uint16_t)atoi(argv[2]), (uint16_t)atoi(argv[3]));
        printf("]}\n");
        return 0;
    }
    if (strcmp(argv[1], "p3_pet_hp_batch") == 0) {
        printf("{\"w\":%d,\"h\":%d,\"frames\":[", SCREEN_W, SCREEN_H);
        for (int i = 2; i < argc; i++) {
            const char *slash = strchr(argv[i], '/');
            if (!slash) {
                fprintf(stderr, "参数 %s 不是 <cur>/<max> 形式\n", argv[i]);
                return 2;
            }
            if (i > 2) printf(",");
            one_frame((unsigned)atoi(argv[i]), (unsigned)atoi(slash + 1));
        }
        printf("]}\n");
        return 0;
    }
    fprintf(stderr, "未知配方: %s\n", argv[1]);
    return 2;
}
