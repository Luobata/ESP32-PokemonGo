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
static uint8_t s_selected;
static bool s_details,s_skills;
static unsigned s_skill;
static bool s_box_mode;
static mon_t s_box[BOX_SPECIES];
static uint8_t s_box_ids[BOX_SPECIES],s_box_count,s_box_row;
static char s_feedback[72];
static bool s_success;
static lv_timer_t *s_tick;
static pokemon_idle_t s_motion;
static uint8_t s_sway_tick;
static int s_sway;

static void reset_motion(void)
{
    pokemon_idle_reset(&s_motion, s_selected < s_party.count ? s_party.members[s_selected].species_id : 0);
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
    if (member == &s_party.members[s_selected] && s_motion.species == member->species_id && s_motion.sprite.data) {
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
    for (unsigned index = 0; index < PARTY_MAX; index++) {
        int y = ROW_Y + index * ROW_H;
        if (index >= s_party.count) {
            render_text(64, y + 10 - band_y, "空位", GAME_UI_MUTED);
            continue;
        }
        const mon_t *member = &s_party.members[index];
        draw_front(band_y, member, 24, y + 2, THUMB_SIZE, THUMB_SIZE, true);
        member_name(member, name, sizeof(name));
        render_text(64, y + 2 - band_y, name, GAME_UI_INK);
        snprintf(text, sizeof(text), "Lv%u", member->level);
        render_text(228 - render_text_width(text), y + 2 - band_y, text, GAME_UI_INK);
        snprintf(text, sizeof(text), index?"经验分享20%%":"亲密 %u", member->intimacy);
        render_text(64, y + 20 - band_y, text, GAME_UI_MUTED);
        if (index == 0) render_text(196, y + 20 - band_y, "出战", GAME_UI_ACCENT);
        if (index == s_selected) game_ui_cursor(band_y, 10, y + 14);
    }
    if(!s_feedback[0]) { render_text(12, 260 - band_y, "长A换入", GAME_UI_MUTED);
    snprintf(text, sizeof(text), "仓库%u只", s_party.box_count);
    render_text(228 - render_text_width(text), 260 - band_y, text, GAME_UI_MUTED);
    } else game_ui_text_centered(band_y,8,260,224,16,s_feedback,GAME_UI_ACCENT);
    game_ui_footer(band_y, "[A]详情 [B]下一 [C]返回");
}

static void draw_detail(int band_y)
{
    const mon_t *member = &s_party.members[s_selected];
    char name[48], text[64], level[16];
    member_name(member, name, sizeof(name));
    snprintf(level, sizeof(level), "Lv%u", member->level);
    game_ui_title(band_y, name, level);
    snprintf(text, sizeof(text), "#%03u", member->species_id);
    render_text(12, 40 - band_y, text, GAME_UI_MUTED);
    if (s_selected) snprintf(text, sizeof(text), "队员 %u", s_selected + 1);
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
    const char *hint = s_feedback[0] ? s_feedback : s_party.switch_locked
        ? "请先结束当前对战" : s_selected ? "长A查看全部技能" : "长A查看全部技能";
    game_ui_text_centered(band_y, 16, 244, 208, 16, hint,
                         s_success ? GAME_UI_ACCENT : GAME_UI_INK);
    game_ui_footer(band_y, "[A]出战 [B]道具 [C]列表");
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
  mon_t *m=&s_box[s_box_ids[top+i]];int y=52+i*32;member_name(m,name,sizeof(name));render_text(34,y-band,name,GAME_UI_INK);
  snprintf(text,sizeof(text),"Lv%u%s",m->level,m->flags&1?"★":"");render_text(216-render_text_width(text),y-band,text,GAME_UI_INK);
  if(top+i==s_box_row)game_ui_cursor(band,18,y+4);
 }
 member_name(&s_party.members[s_selected],name,sizeof(name));snprintf(text,sizeof(text),"换出 %s",name);game_ui_text_centered(band,8,230,224,16,text,GAME_UI_INK);
 game_ui_text_centered(band,8,254,224,16,s_feedback[0]?s_feedback:"换出的伙伴会进入仓库",GAME_UI_MUTED);
 game_ui_footer(band,"[A]换入 [B]下一 [C]返回");
}
static void draw_all(void)
{
    for (int y = 0; y < SCREEN_H; y += SCREEN_BAND_H) {
        screen_band_clear(GAME_UI_BG);
        if(s_box_mode)draw_box(y);
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
    if (s_selected >= s_party.count) { s_selected = 0; s_details = false; s_skills = false; }
    return changed;
}

static void refresh_tick(lv_timer_t *timer)
{
    (void)timer;
    bool changed = refresh_snapshot();
    if (s_selected < s_party.count && s_motion.species != s_party.members[s_selected].species_id) reset_motion();
    if (screen_idle_is_off()) return;
    static const int8_t sway[] = {0, 1, 1, 0, -1, -1, 0, 0};
    int previous = s_sway;
    s_sway_tick = (s_sway_tick + 1) % 40;
    s_sway = sway[s_sway_tick / 5];
    if (pokemon_idle_step(&s_motion, 80) || changed || previous != s_sway) draw_all();
}

void play_party_enter(void)
{
    if (!nav_is_returning()) { s_selected = 0; s_details = false; s_skills = false; }
    s_feedback[0] = '\0';
    s_box_mode=false;
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
    if (out) *out = (play_party_view_t){.selected = s_selected, .details = s_details,
        .species = s_selected < s_party.count ? s_party.members[s_selected].species_id : 0,
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
    if(s_box_mode){
        if(btn==BSP_BTN_DOWN&&(ev==BSP_BTN_CLICK||ev==BSP_BTN_LONG)){
            if(s_box_count)s_box_row=(s_box_row+s_box_count+(ev==BSP_BTN_LONG?-1:1))%s_box_count;
            s_feedback[0]=0;
        }else if(ev==BSP_BTN_CLICK&&btn==BSP_BTN_OK){s_box_mode=false;s_feedback[0]=0;}
        else if(ev==BSP_BTN_CLICK&&btn==BSP_BTN_UP&&s_box_count){
            world_switch_result_t result=world_box_exchange(s_selected,&s_party.members[s_selected],&s_box[s_box_ids[s_box_row]]);
            const char *message=result==WORLD_SWITCH_OK?"队伍已更换":result==WORLD_SWITCH_BUSY?"请先结束当前对战":result==WORLD_SWITCH_SAVE_FAILED?"保存失败 请重试":result==WORLD_SWITCH_INVALID?"仓库选择无效 请重试":"伙伴已变 请重试";
            snprintf(s_feedback,sizeof(s_feedback),"%s",message);refresh_snapshot();load_box();
            if(result==WORLD_SWITCH_OK){s_box_mode=false;reset_motion();}
        }
        draw_all();return;
    }
    if(!s_details&&btn==BSP_BTN_UP&&ev==BSP_BTN_LONG&&s_party.count){s_box_mode=true;s_box_row=0;s_feedback[0]=0;load_box();draw_all();return;}

    if(s_skills){
        if(btn==BSP_BTN_OK&&ev==BSP_BTN_CLICK)s_skills=false;
        else if(btn==BSP_BTN_DOWN&&(ev==BSP_BTN_CLICK||ev==BSP_BTN_LONG)){
            uint16_t ids[COMBAT_MOVE_CAP];int count=combat_known_moves(s_party.members[s_selected].species_id,s_party.members[s_selected].level,ids,COMBAT_MOVE_CAP);
            if(count)s_skill=(s_skill+count+(ev==BSP_BTN_LONG?-1:1))%count;
        }
        draw_all();return;
    }
    if(s_details&&s_party.count&&btn==BSP_BTN_UP&&ev==BSP_BTN_LONG){s_skills=true;s_skill=0;draw_all();return;}
    if (!s_details && btn == BSP_BTN_DOWN && (ev == BSP_BTN_CLICK || ev == BSP_BTN_LONG)) {
        if (s_party.count)
            s_selected = (s_selected + s_party.count + (ev == BSP_BTN_LONG ? -1 : 1)) % s_party.count;
        s_feedback[0] = '\0';
        s_success = false;
        reset_motion();
        draw_all();
        return;
    }
    if (ev != BSP_BTN_CLICK) return;
    if (btn == BSP_BTN_OK) {
        if (s_details) { s_details = false; s_feedback[0] = '\0'; draw_all(); }
        else nav_back(PAGE_MENU);
    } else if (btn == BSP_BTN_UP && s_party.count) {
        if (s_details) select_leader();
        else { s_details = true; s_feedback[0] = '\0'; s_success = false; }
        draw_all();
    } else if (btn == BSP_BTN_DOWN && s_details) {
        if (s_selected) {
            s_success = false;
            snprintf(s_feedback, sizeof(s_feedback), "先按A设为出战");
            draw_all();
        } else nav_open(PAGE_BAG);
    }
}
