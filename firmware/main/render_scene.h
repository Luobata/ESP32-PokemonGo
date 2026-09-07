// Shared scene recipe: integer screen coordinates and logical RGB565 colors.
// Backends consume rectangles/text; they do not calculate layout or fallback.
#pragma once

#include <stdbool.h>
#include <stdio.h>
#include "render.h"
#include "screen.h"
#include "render_layout_budget.h"

#define SCENE_P3_PET_HP_X 112
#define SCENE_P3_PET_HP_Y 192
#define SCENE_P3_PET_HP_W 120
#define SCENE_P3_PET_HP_H 10

#define SCENE_P3_PET_BACK_X 8
#define SCENE_P3_PET_BACK_Y 140
#define SCENE_P3_PET_BACK_SIZE 96

// Coordinates belong to the recipe; width budget comes from VAR_ELEMENTS.
#define SCENE_P3_PET_NAME_X 112
#define SCENE_P3_PET_NAME_Y 168
#define SCENE_P3_PET_NAME_RIGHT (SCENE_P3_PET_NAME_X + LAYOUT_P3_PET_NAME_BUDGET)

// Text is borrowed for the duration of this synchronous callback only.
typedef void (*scene_text_fn)(void *ctx, int x, int y, const char *text,
                              uint16_t color);

static inline void scene_p3_pet_name_sized(scene_text_fn text, void *ctx,
                                      const char *name, uint8_t name_len,
                                      uint8_t level, uint16_t font_size)
{
    char buf[64];
    snprintf(buf, sizeof(buf), "%.*s Lv%u", (int)name_len, name, (unsigned)level);
    // Preserve D53: only remove the space, never abbreviate the species name.
    if (render_text_width_sized(buf, font_size) > SCENE_P3_PET_NAME_RIGHT - SCENE_P3_PET_NAME_X) {
        snprintf(buf, sizeof(buf), "%.*sLv%u", (int)name_len, name, (unsigned)level);
    }
    text(ctx, SCENE_P3_PET_NAME_X, SCENE_P3_PET_NAME_Y, buf, C_INK);
}

// Firmware compatibility entry: keep existing call sites and font state.
static inline void scene_p3_pet_name(scene_text_fn text, void *ctx,
                                      const char *name, uint8_t name_len,
                                      uint8_t level)
{
    scene_p3_pet_name_sized(text, ctx, name, name_len, level, render_font_size());
}

typedef void (*scene_rect_fn)(void *ctx, int x, int y, int w, int h,
                              uint16_t color);

// Input is a snapshot of the same cur/max pair used by the battle page.
// Rectangles use half-open bounds; later rectangles overwrite earlier ones.
static inline void scene_p3_pet_hp(scene_rect_fn rect, void *ctx,
                                    uint16_t cur, uint16_t max)
{
    const int x = SCENE_P3_PET_HP_X, y = SCENE_P3_PET_HP_Y;
    const int w = SCENE_P3_PET_HP_W, h = SCENE_P3_PET_HP_H;
    int filled = max ? (int)((uint32_t)w * cur / max) : 0;
    uint16_t color = filled >= w * 50 / 100 ? C_HP_GREEN
        : (filled >= w * 21 / 100 ? C_HP_YELLOW : C_HP_RED);
    // The original draw_bar tests dx < filled, then gives the border priority.
    int inner = filled > 1 ? filled - 1 : 0;
    if (inner > w - 2) inner = w - 2;
    rect(ctx, x, y, w, h, C_INK);
    rect(ctx, x + 1, y + 1, w - 2, h - 2, C_HP_TRACK);
    if (inner) rect(ctx, x + 1, y + 1, inner, h - 2, color);
}

// Decode once in the shared recipe, including scale, transparency and palette.
// Backends still consume only rectangles, never source pixels or scale rules.
// The caller supplies a validated w*h 2bpp asset (ceil(w/4) bytes per row).
static inline bool scene_p3_pet_back(scene_rect_fn rect, void *ctx,
                                      const uint8_t *data, int w, int h,
                                      int shake_dx, const uint16_t palette[4])
{
    if (!data || !palette || w != h || (w != 32 && w != 48)) return false;
    const int scale = SCENE_P3_PET_BACK_SIZE / w;
    const int row_bytes = (w + 3) / 4;
    for (int sy = 0; sy < h; sy++) {
        // Coalesce adjacent equal shades into a rectangle; no extra buffer.
        for (int sx = 0; sx < w;) {
            int start = sx;
            uint8_t shade = (data[sy * row_bytes + sx / 4] >> (6 - 2 * (sx % 4))) & 3;
            do {
                sx++;
            } while (sx < w &&
                     ((data[sy * row_bytes + sx / 4] >> (6 - 2 * (sx % 4))) & 3) == shade);
            if (shade != 3) {
                rect(ctx, SCENE_P3_PET_BACK_X + shake_dx + start * scale,
                     SCENE_P3_PET_BACK_Y + sy * scale,
                     (sx - start) * scale, scale, palette[shade]);
            }
        }
    }
    return true;
}
