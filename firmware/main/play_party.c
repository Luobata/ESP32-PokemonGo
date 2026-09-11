// P12: six visible party slots and a member detail view.
// Only world_set_leader publishes a change; expected is the displayed mon_t.
#include <stdio.h>
#include <string.h>

#include "lvgl.h"
#include "assets.h"
#include "game_ui.h"
#include "nav.h"
#include "play.h"
#include "render.h"
#include "screen.h"
#include "screen_idle.h"
#include "pokemon_animation.h"
#include "world.h"
#include "combat.h"
#include "exp.h"

#define ROW_Y 36
#define ROW_H 36
#define THUMB_SIZE 32

SCREEN_ASSERT_WITHIN_BAND(party_title, 8, 16);
SCREEN_ASSERT_ALLOW_CROSS_BAND(party_detail_front, 64, 112);
SCREEN_ASSERT_WITHIN_BAND(party_detail_stats, 184, 16);
SCREEN_ASSERT_WITHIN_BAND(party_detail_exp, 208, 16);
SCREEN_ASSERT_WITHIN_BAND(party_detail_feedback, 244, 16);
SCREEN_ASSERT_WITHIN_BAND(party_box_count, 260, 16);

static world_party_t s_party;
static uint8_t s_selected, s_action;
static bool s_details,s_skills;
static unsigned s_skill;
static bool s_box_mode,s_box_details;
static mon_t s_box[BOX_SPECIES];
static uint8_t s_box_ids[BOX_SPECIES],s_box_count,s_box_row;
static char s_feedback[72];
static bool s_success;
static lv_timer_t *s_tick;
static pokemon_idle_t s_motion;
static uint8_t s_sway_tick;
static int s_sway;

static const mon_t *view_member(void)
{
    if (s_box_mode) return s_box_count ? &s_box[s_box_ids[s_box_row]] : NULL;
    return s_selected < s_party.count ? &s_party.members[s_selected] : NULL;
}

static void reset_motion(void)
{
    const mon_t *member = view_member();
    pokemon_idle_reset(&s_motion, member ? member->species_id : 0);
    s_sway_tick = 0;
    s_sway = 0;
}

static void member_name(const mon_t *member, char *out, size_t capacity)
{
    species_t species;
    if (assets_species(member->species_id, &species))
        snprintf(out, capacity, "%.*s", species.name_zh_len, species.name_zh);
    else snprintf(out, capacity, "#%03u", member->species_id);
}

static void draw_front(int band_y, const mon_t *member, int x, int y, int w, int h, bool thumbnail)
{
    uint8_t size;
    const uint8_t *front = assets_front_sprite(member->species_id, &size);
    if (member == view_member() && s_motion.species == member->species_id && s_motion.sprite.data) {
        front = s_motion.sprite.data;
        size = s_motion.sprite.w;
        if (thumbnail) x += s_sway;
    }
    species_t species;
    if (!front || !assets_species(member->species_id, &species)) return;
    uint16_t palette[4];
    assets_palette_variant(species.palette, (member->flags & 1) != 0, palette);
    if (thumbnail)
        game_ui_thumbnail_centered(band_y, x, y, w, h, front, size, THUMB_SIZE, palette);
    else game_ui_sprite_centered(band_y, x, y, w, h, front, size, size, 2, palette);
}

static void draw_list(int band_y)
{
    char text[64], name[48];
    snprintf(text, sizeof(text), "%u/%u", s_party.count, PARTY_MAX);
    game_ui_title(band_y, "队伍", text);
    unsigned highest=1;for(unsigned i=0;i<s_party.count;i++)if(s_party.members[i].level>highest)highest=s_party.members[i].level;
    for (unsigned index = 0; index < PARTY_MAX; index++) {
        int y = ROW_Y + index * ROW_H;
        if (index >= s_party.count) {
            render_text(64, y + 10 - band_y, "空位", GAME_UI_MUTED);
            continue;
        }
        const mon_t *member = &s_party.members[index];
        int sprite_x = 24;
        int text_x = 64;
        draw_front(band_y, member, sprite_x, y + 2, THUMB_SIZE, THUMB_SIZE, true);
        member_name(member, name, sizeof(name));
        render_text(text_x, y + 2 - band_y, name, GAME_UI_INK);
        snprintf(text, sizeof(text), "Lv%u", member->level);
        render_text(228 - render_text_width(text), y + 2 - band_y, text, GAME_UI_INK);
        if(index)snprintf(text,sizeof(text),"分享%u%%",exp_party_percent(member->level,highest,false));
        else snprintf(text,sizeof(text),"亲密 %u",member->intimacy);
        render_text(text_x, y + 20 - band_y, text, GAME_UI_MUTED);
        if (index == 0) render_text(196, y + 20 - band_y, "出战", GAME_UI_ACCENT);
        game_ui_list_marker(band_y, 8, y + 10, index, s_party.count, s_selected);
    }
    if(!s_feedback[0]) { render_text(12, 260 - band_y, "C查看详情", GAME_UI_MUTED);
    snprintf(text, sizeof(text), "仓库%u只", s_party.box_count);
    render_text(228 - render_text_width(text), 260 - band_y, text, GAME_UI_MUTED);
    } else game_ui_text_centered(band_y,8,260,224,16,s_feedback,GAME_UI_ACCENT);
    game_ui_footer(band_y, game_ui_list_hint(s_party.count));
}

static void draw_detail(int band_y)
{
    const mon_t *member = view_member();
    if (!member) return;
    char name[48], text[64], level[16];
    member_name(member, name, sizeof(name));
    snprintf(level, sizeof(level), "Lv%u", member->level);
    game_ui_title(band_y, name, level);
    snprintf(text, sizeof(text), "#%03u", member->species_id);
    render_text(12, 40 - band_y, text, GAME_UI_MUTED);
    if (s_box_mode) snprintf(text, sizeof(text), "仓库伙伴");
    else if (s_selected) snprintf(text, sizeof(text), "队员 %u", s_selected + 1);
    else snprintf(text, sizeof(text), "出战伙伴");
    render_text(228 - render_text_width(text), 40 - band_y, text, GAME_UI_INK);
    draw_front(band_y, member, 64, 64, 112, 112, false);
    snprintf(text, sizeof(text), "亲密 %u", member->intimacy);
    render_text(12, 184 - band_y, text, GAME_UI_INK);
    snprintf(text, sizeof(text), "探索 %u", member->explore_value);
    render_text(228 - render_text_width(text), 184 - band_y, text, GAME_UI_INK);
    snprintf(text, sizeof(text), "经验 %lu", (unsigned long)member->exp);
    render_text(12, 208 - band_y, text, GAME_UI_MUTED);
    if (member->flags & 1) render_text(196, 208 - band_y, "闪光", GAME_UI_ACCENT);
    game_ui_box(band_y, 8, 232, 224, 40);
    const char *hint = s_feedback[0] ? s_feedback : s_box_mode ? GAME_UI_BACK_HINT : GAME_UI_NAV_HINT;
    game_ui_text_centered(band_y, 16, 244, 208, 16, hint,
                         s_success ? GAME_UI_ACCENT : GAME_UI_INK);
    static const char *const party_actions[] = {"出战", "道具", "技能", "换入"};
    static const char *const box_actions[] = {"换入", "技能"};
    game_ui_actions(band_y, s_box_mode ? box_actions : party_actions,
                    s_box_mode ? 2 : 4, s_action);

}

static void load_box(void){
 world_box_snapshot(s_box);s_box_count=0;
 for(unsigned i=0;i<BOX_SPECIES;i++)if(s_box[i].species_id)s_box_ids[s_box_count++]=i;
 if(s_box_row>=s_box_count)s_box_row=0;
}
static void draw_box(int band){
 char text[72],name[48];snprintf(text,sizeof(text),"换入第%u位",s_selected+1);game_ui_title(band,"仓库",text);
 game_ui_box(band,8,40,224,176);
 if(!s_box_count)game_ui_text_centered(band,16,112,208,16,"仓库暂无伙伴",GAME_UI_MUTED);
 for(unsigned i=0,top=s_box_row/5*5;i<5&&top+i<s_box_count;i++){
  mon_t *m=&s_box[s_box_ids[top+i]];int y=52+i*32;member_name(m,name,sizeof(name));render_text(54,y-band,name,GAME_UI_INK);
  if(m->flags&1)render_text(34,y-band,"★",GAME_UI_ACCENT);
  snprintf(text,sizeof(text),"Lv%u",m->level);render_text(216-render_text_width(text),y-band,text,GAME_UI_INK);
  game_ui_list_marker(band,8,y,top+i,s_box_count,s_box_row);
 }
 member_name(&s_party.members[s_selected],name,sizeof(name));snprintf(text,sizeof(text),"换出 %s",name);game_ui_text_centered(band,8,230,224,16,text,GAME_UI_INK);
 game_ui_text_centered(band,8,254,224,16,s_feedback[0]?s_feedback:"★闪光 C查看详情",GAME_UI_MUTED);
 game_ui_footer(band,game_ui_list_hint(s_box_count));
}
static void draw_all(void)
{
    for (int y = 0; y < SCREEN_H; y += SCREEN_BAND_H) {
        screen_band_clear(GAME_UI_BG);
        if(s_box_mode && s_skills && view_member())game_ui_moves(y,view_member()->species_id,view_member()->level,s_skill,false);
        else if(s_box_mode && s_box_details)draw_detail(y);
        else if(s_box_mode)draw_box(y);
        else if(s_skills && s_selected<s_party.count)game_ui_moves(y,s_party.members[s_selected].species_id,s_party.members[s_selected].level,s_skill,false);
        else if (s_details && s_selected < s_party.count) draw_detail(y);
        else draw_list(y);
        screen_push_band(y);
    }
}

static bool refresh_snapshot(void)
{
    world_party_t fresh;
    memset(&fresh, 0, sizeof(fresh));
    world_party_snapshot(&fresh);
    bool changed = memcmp(&fresh, &s_party, sizeof(fresh)) != 0;
    s_party = fresh;
    if (s_selected >= s_party.count) { s_selected = s_action = 0; s_details = false; s_skills = false; }
    return changed;
}

static void refresh_tick(lv_timer_t *timer)
{
    (void)timer;
    bool changed = refresh_snapshot();
    const mon_t *member = view_member();
    if (member && s_motion.species != member->species_id) reset_motion();
    if (screen_idle_is_off()) return;
    static const int8_t sway[] = {0, 1, 1, 0, -1, -1, 0, 0};
    int previous = s_sway;
    s_sway_tick = (s_sway_tick + 1) % 40;
    s_sway = sway[s_sway_tick / 5];
    if (pokemon_idle_step(&s_motion, 80) || changed || previous != s_sway) draw_all();
}

void play_party_enter(void)
{
    if (!nav_is_returning()) { s_selected = s_action = 0; s_details = false; s_skills = false; }
    s_feedback[0] = '\0';
    s_box_mode=s_box_details=false;
    s_success = false;
    s_tick = NULL;
    refresh_snapshot();
    reset_motion();
    screen_set_redraw(draw_all);
    draw_all();
    s_tick = lv_timer_create(refresh_tick, 80, NULL);
}

void play_party_exit(void)
{
    if (s_tick) { lv_timer_delete(s_tick); s_tick = NULL; }
}

void play_party_presentation_snapshot(play_party_view_t *out)
{
    if (out) *out = (play_party_view_t){.selected = s_selected, .details = s_box_mode ? s_box_details : s_details,
        .box = s_box_mode, .box_row = s_box_row, .skills = s_skills,
        .species = view_member() ? view_member()->species_id : 0,
        .feedback = s_feedback};
}

static void select_leader(void)
{
    world_switch_result_t result = world_set_leader(s_selected, &s_party.members[s_selected], &s_party);
    s_success = result == WORLD_SWITCH_OK || result == WORLD_SWITCH_ALREADY_LEADER;
    const char *message = "伙伴已变 请重试";
    switch (result) {
    case WORLD_SWITCH_OK: s_selected = 0; message = "已设为出战伙伴"; break;
    case WORLD_SWITCH_ALREADY_LEADER: s_selected = 0; message = "已经是出战伙伴"; break;
    case WORLD_SWITCH_BUSY: message = "请先结束当前对战"; break;
    case WORLD_SWITCH_SAVE_FAILED: message = "保存失败 请重试"; break;
    case WORLD_SWITCH_STORAGE_UNAVAILABLE: message = "存档暂不可用"; break;
    default: break;
    }
    if (!s_success) refresh_snapshot();
    snprintf(s_feedback, sizeof(s_feedback), "%s", message);
}

void play_party_key(bsp_btn_t btn, bsp_btn_ev_t ev)
{
    int direction = nav_direction(btn, ev);
    bool confirm = nav_confirm(btn, ev), back = nav_return(btn, ev);
    if (!direction && !confirm && !back) return;
    if (s_skills) {
        if (back) s_skills = false;
        else if (ev==BSP_BTN_CLICK && view_member()) {
            uint16_t ids[COMBAT_MOVE_CAP];
            int count = combat_known_moves(view_member()->species_id, view_member()->level, ids, COMBAT_MOVE_CAP);
            if (count) s_skill = nav_list_selection(btn,ev,count,s_skill);
        }
        draw_all(); return;
    }
    if (back) {
        if (s_box_details) { s_box_details = false; s_action = 0; }
        else if (s_box_mode) { s_box_mode = false; s_action = 3; reset_motion(); }
        else if (s_details) s_details = false;
        else { nav_back(PAGE_MENU); return; }
        s_feedback[0] = 0; draw_all(); return;
    }
    bool detail = s_box_mode ? s_box_details : s_details;
    unsigned count = detail ? (s_box_mode ? 2 : 4) : s_box_mode ? s_box_count : s_party.count;
    unsigned choice = detail ? s_action : s_box_mode ? s_box_row : s_selected;
    choice = nav_list_selection(btn, ev, count, choice);
    if (detail) s_action = choice; else if (s_box_mode) s_box_row = choice; else s_selected = choice;
    if (!nav_list_activate(btn, ev, count)) {
        s_feedback[0] = 0; s_success = false; reset_motion(); draw_all(); return;
    }
    if (!view_member()) return;
    if (!detail) {
        if (s_box_mode) s_box_details = true; else s_details = true;
        s_action = 0; s_feedback[0] = 0; reset_motion(); draw_all(); return;
    }
    if (s_box_mode) {
        if (s_action == 1) { s_skills = true; s_skill = 0; }
        else {
            world_switch_result_t result = world_box_exchange(s_selected, &s_party.members[s_selected], &s_box[s_box_ids[s_box_row]]);
            const char *message = result == WORLD_SWITCH_OK ? "队伍已更换" : result == WORLD_SWITCH_BUSY ? "请先结束当前对战" : result == WORLD_SWITCH_SAVE_FAILED ? "保存失败 请重试" : result == WORLD_SWITCH_INVALID ? "仓库选择无效 请重试" : "伙伴已变 请重试";
            snprintf(s_feedback, sizeof(s_feedback), "%s", message); refresh_snapshot(); load_box();
            if (result == WORLD_SWITCH_OK) { s_box_mode = s_box_details = false; s_action = 3; reset_motion(); }
        }
    } else if (s_action == 0) select_leader();
    else if (s_action == 1) {
        if (s_selected) { s_success = false; snprintf(s_feedback, sizeof(s_feedback), "请先设为出战伙伴"); }
        else { nav_open(PAGE_BAG); return; }
    } else if (s_action == 2) { s_skills = true; s_skill = 0; }
    else { s_box_mode = true; s_box_details = false; s_box_row = s_action = 0; s_feedback[0] = 0; load_box(); reset_motion(); }
    draw_all();
}
