// P15: shared route exploration, rendered identically on LCD and native preview.
#include <stdio.h>
#include "lvgl.h"
#include "esp_timer.h"
#include "assets.h"
#include "play.h"
#include "nav.h"
#include "world.h"
#include "game_ui.h"
#include "render.h"
#include "screen.h"
#include "battle.h"

static exploration_view_t view;
static exploration_event_t event;
static unsigned selected;
static bool routes, animating, journal;
static unsigned chapter_selected;
static uint64_t started;
static lv_timer_t *timer;
static const char *feedback;
static uint64_t millis(void){return esp_timer_get_time()/1000;}
static void rect(int band,int x,int y,int w,int h,uint16_t c){
 int lo=y>band?y:band,hi=y+h<band+SCREEN_BAND_H?y+h:band+SCREEN_BAND_H;
 for(int yy=lo;yy<hi;yy++)for(int xx=x;xx<x+w;xx++)screen_px(xx,yy-band,c);
}
static void portrait(int band,unsigned id,bool shiny,int y,int h,int scale){
 species_t sp;uint8_t size;const uint8_t *data=assets_front_sprite(id,&size);
 if(!data||!assets_species(id,&sp))return;
 uint16_t pal[4];assets_palette_variant(sp.palette,shiny,pal);
 game_ui_sprite_centered(band,24,y,192,h,data,size,size,scale,pal);
}
static void center(int band,int y,const char *text,uint16_t color){game_ui_text_centered(band,8,y,224,16,text,color);}
static void tile(int band,int x,int y,const char *const *rows,int n,const uint16_t *pal){
 for(int yy=0;yy<n;yy++)for(int xx=0;rows[yy][xx];xx++)if(rows[yy][xx]!='.')rect(band,x+xx*2,y+yy*2,2,2,pal[rows[yy][xx]-'0']);
}
static void scene(int band,unsigned route){
 static const char *const tree[]={
 ".....111111.....","...1122222211...","..122233322221..",".12233333222221.",
 "1223333222222221","1223322222232221","1222222222332221",".12222322222221.",
 "..122332222221..",".12233322222221.","1223332222232221","1223322222332221",
 "1222222223332221",".12222222222221.","..111222222111..",".....114411.....",
 "......1441......","......1441......",".....144441.....",".....111111....."};
 static const char *const rock[]={"...111111...",".1122222211.","123333222221","123332222221","122222222221","122222222211",".1222222211.","..11111111.."};
 static const uint16_t leaf[]={0,0x2245,0x4c49,0xaeea,0x9387};
 static const uint16_t stone[]={0,0x4a49,0x9c53,0xd659};
 rect(band,16,72,208,80,route==2?0xaeff:route==1?0xe6f6:0xeef5);
 if(route==0){
  rect(band,16,126,208,18,0xef75);
  for(int i=0;i<6;i++)tile(band,18+i*34,78+(i%2)*4,tree,20,leaf);
  for(int i=0;i<17;i++){int x=18+i*12;rect(band,x,148,2,2,0x4c49);rect(band,x+2,146,2,2,0x4c49);}
 }else if(route==1){
  for(int i=0;i<8;i++){tile(band,18+i*25,74,rock,8,stone);tile(band,18+i*25,134,rock,8,stone);}
  rect(band,108,82,24,20,0x4a49);rect(band,112,88,16,16,0x0000);
  for(int i=0;i<9;i++)rect(band,24+i*22,116+(i%3)*6,4,2,0x9c53);
 }else if(route==2){
  rect(band,16,132,208,20,0xef75);
  for(int i=0;i<7;i++)for(int k=0;k<3;k++){int x=18+i*30+(k%2)*8,y=82+k*18;rect(band,x,y,16,2,0x3d7f);rect(band,x+2,y-2,12,2,0xe79f);}
  for(int i=0;i<6;i++)rect(band,24+i*34,138+(i%2)*6,4,2,0xbd8c);
 }else{
  rect(band,16,128,208,24,0xc618);
  for(int i=0;i<4;i++){
   int x=26+i*50;rect(band,x,82,30,46,0x4a49);rect(band,x+2,84,26,42,0x9c53);
   rect(band,x+6,90,18,12,0x2245);rect(band,x+8,92,14,6,0xaeea);
   for(int k=0;k<3;k++)rect(band,x+6,108+k*4,12,2,0x4a49);
   rect(band,x+22,110,4,4,0xfde0);rect(band,x+14,76,4,6,0x4a49);rect(band,x-4,76,54,2,0x4a49);
  }
 }
}

static void progress(int band,unsigned n){
 for(unsigned i=0;i<3;i++){
  int x=66+i*40;rect(band,x,194,28,8,GAME_UI_INK);rect(band,x+2,196,24,4,i<n?exploration_route(view.state.route)->color:GAME_UI_BG);
 }
}
static const char *error_text(exploration_kind_t kind){
 switch(kind){
 case EXPLORE_NO_STAMINA:return "体力不足 请等待恢复";
 case EXPLORE_NO_ENERGY:return "机会不足 外出积累";
 case EXPLORE_BLOCKED:return "先处理列表中的同类伙伴";
 case EXPLORE_BUSY:return "请先完成当前对战";
 case EXPLORE_SAVE_FAILED:return "保存失败 机会未扣除";
 default:return "暂时无法探索";
 }
}
static void draw_all(void){
 char text[96];unsigned route=view.state.route;const exploration_route_t *r=exploration_route(route);
 for(int band=0;band<SCREEN_H;band+=SCREEN_BAND_H){
  screen_band_clear(GAME_UI_BG);snprintf(text,sizeof(text),"机会 %u/24",view.state.energy);game_ui_title(band,routes?"选择路线":"探索",text);
  if(journal){
   const exploration_chapter_t *c=exploration_chapter(chapter_selected);bool open=exploration_chapter_open(chapter_selected,view.defeated);
   center(band,44,"冒险笔记",GAME_UI_INK);game_ui_box(band,8,72,224,176);
   center(band,88,c->name,GAME_UI_INK);center(band,120,open?"已解锁":"下一段冒险",GAME_UI_ACCENT);
   center(band,152,c->condition,GAME_UI_INK);center(band,184,c->story,GAME_UI_MUTED);
   center(band,216,c->discovery,GAME_UI_INK);
   center(band,258,"线索事件有机会找到道具",GAME_UI_MUTED);game_ui_footer(band,"[A]探索 [B]翻页 [C]返回");
  }else if(routes){
   for(unsigned i=0;i<4;i++){
    int y=40+i*52;const exploration_route_t *row=exploration_route(i);game_ui_box(band,8,y,224,48);
    if(i==selected)game_ui_cursor(band,16,y+13);
    render_text(32,y+8-band,row->name,GAME_UI_INK);
    static const char *const habitats[]={"草虫","岩地","水冰","电毒"};
    snprintf(text,sizeof(text),"%s 线索%u/3",habitats[i],view.state.clues[i]);render_text(32,y+26-band,text,GAME_UI_MUTED);
    exploration_state_t focus=view.state;focus.route=i;unsigned target=exploration_focus(&focus,view.defeated);
    uint8_t size;species_t sp;const uint8_t *data=assets_front_sprite(target,&size);
    if(data&&assets_species(target,&sp)){uint16_t pal[4];assets_palette_variant(sp.palette,false,pal);game_ui_thumbnail_centered(band,182,y+6,40,36,data,size,32,pal);}
   }
   center(band,256,feedback?feedback:exploration_chapter(exploration_chapter_current(view.defeated))->name,GAME_UI_MUTED);
   game_ui_footer(band,"[A]选择 [B]下一 [C]返回");
  }else if(animating){
   center(band,44,r->name,GAME_UI_INK);scene(band,route);
   unsigned phase=(millis()-started)/120;for(unsigned i=0;i<=phase&&i<4;i++)rect(band,80+i*24,176,8,8,r->color);
   center(band,218,"寻找伙伴的踪迹",GAME_UI_INK);game_ui_footer(band,"正在探索……");
  }else if(event.kind==EXPLORE_ENCOUNTER||event.kind==EXPLORE_TARGET){
   center(band,44,event.kind==EXPLORE_TARGET?"追踪目标出现了！":"发现野生宝可梦！",GAME_UI_INK);
   portrait(band,event.species,event.shiny,68,144,2);
   species_t sp;world_t w;world_snapshot(&w);
   if(assets_species(event.species,&sp))snprintf(text,sizeof(text),"%.*s Lv%u",sp.name_zh_len,sp.name_zh,battle_wild_level_for_pet(event.rarity,w.level));else snprintf(text,sizeof(text),"#%03u",event.species);
   center(band,220,text,GAME_UI_INK);snprintf(text,sizeof(text),"稀有度 %u%s",event.rarity,event.shiny?" 闪光":"");center(band,244,text,GAME_UI_ACCENT);
   game_ui_footer(band,"[A]查看 [B]继续 [C]返回");
  }else if(event.kind==EXPLORE_CLUE){
   center(band,44,r->name,GAME_UI_INK);scene(band,route);
   center(band,164,"发现新的线索",GAME_UI_INK);progress(band,event.clues);
   static const char *const trail[]={"足迹延伸向路线深处","远处传来陌生的叫声","目标就在附近"};
   center(band,218,exploration_story(exploration_focus(&view.state,view.defeated),event.clues-1),GAME_UI_INK);
   if(event.item!=ITEM_NONE){snprintf(text,sizeof(text),event.item_full?"%s已满 未拾取":"发现 %s ×1",items_info(event.item)->name);center(band,248,text,GAME_UI_ACCENT);}
   else center(band,248,event.clues==3?"下次探索必定找到目标":"继续探索 追踪伙伴",GAME_UI_MUTED);
   game_ui_footer(band,"[A]继续 [B]路线 [C]返回");
  }else{
   center(band,44,r->name,GAME_UI_INK);scene(band,route);
   center(band,164,exploration_chapter(exploration_chapter_current(view.defeated))->name,GAME_UI_INK);progress(band,view.state.clues[route]);
   species_t target;uint16_t target_id=exploration_focus(&view.state,view.defeated);
   if(assets_species(target_id,&target))snprintf(text,sizeof(text),"%.*s 线索%u/3",target.name_zh_len,target.name_zh,view.state.clues[route]);else snprintf(text,sizeof(text),"线索 %u/3",view.state.clues[route]);center(band,214,text,GAME_UI_INK);
   const char *hint=feedback?feedback:(view.pending==5?"遭遇已满 将替换最早一只":view.state.tracked_species?"图鉴可更换或取消追踪":"长按A查看冒险笔记");
   center(band,238,hint,GAME_UI_MUTED);
   snprintf(text,sizeof(text),"体力%u -5/次 助力%u",view.stamina,view.party_bonus/10);center(band,258,text,GAME_UI_MUTED);
   game_ui_footer(band,"[A]探索 [B]路线 [C]返回");
  }
  screen_push_band(band);
 }
}
static void tick(lv_timer_t *t){
 (void)t;
 if(animating){if(millis()-started>=600)animating=false;draw_all();}
 else {exploration_view_t next;world_exploration_snapshot(&next);if(next.state.energy!=view.state.energy||next.pending!=view.pending||next.stamina!=view.stamina){view=next;draw_all();}}
}
void play_exploration_enter(void){
 world_exploration_snapshot(&view);selected=view.state.route;routes=animating=journal=false;event=(exploration_event_t){0};feedback=NULL;
 screen_set_redraw(draw_all);timer=lv_timer_create(tick,120,NULL);draw_all();
}
void play_exploration_exit(void){if(timer){lv_timer_delete(timer);timer=NULL;}animating=false;}
bool play_exploration_screen_busy(void){return animating;}
void play_exploration_key(bsp_btn_t btn,bsp_btn_ev_t ev){
 if(animating)return;
 if(btn==BSP_BTN_UP&&ev==BSP_BTN_LONG&&!journal){journal=true;chapter_selected=exploration_chapter_current(view.defeated);draw_all();return;}
 if(journal){
  unsigned limit=exploration_chapter_current(view.defeated)+2;if(limit>EXPLORATION_CHAPTERS)limit=EXPLORATION_CHAPTERS;
  if(btn==BSP_BTN_DOWN&&(ev==BSP_BTN_CLICK||ev==BSP_BTN_LONG))chapter_selected=(chapter_selected+limit+(ev==BSP_BTN_LONG?-1:1))%limit;
  else if(ev==BSP_BTN_CLICK&&(btn==BSP_BTN_OK||btn==BSP_BTN_UP))journal=false;
  draw_all();return;
 }
 if(routes){
  if(btn==BSP_BTN_DOWN&&(ev==BSP_BTN_CLICK||ev==BSP_BTN_LONG)){selected=(selected+4+(ev==BSP_BTN_LONG?-1:1))%4;feedback=NULL;}
  else if(ev!=BSP_BTN_CLICK)return;
  else if(btn==BSP_BTN_OK){routes=false;feedback=NULL;}
  else if(btn==BSP_BTN_UP){exploration_kind_t k=world_exploration_select(selected);if(k==EXPLORE_NONE){routes=false;feedback=NULL;event=(exploration_event_t){0};}else feedback=error_text(k);}
 }else{
  if(ev!=BSP_BTN_CLICK)return;
  if(btn==BSP_BTN_OK){if(event.kind){event=(exploration_event_t){0};feedback=NULL;}else {nav_back(PAGE_MENU);return;}}
  else if(btn==BSP_BTN_DOWN){if(event.kind==EXPLORE_ENCOUNTER||event.kind==EXPLORE_TARGET)event=(exploration_event_t){0};else {routes=true;selected=view.state.route;feedback=NULL;}}
  else if(btn==BSP_BTN_UP){
   if(event.kind==EXPLORE_ENCOUNTER||event.kind==EXPLORE_TARGET){
    encounter_t enc;if(world_get_encounter_uid(event.uid,&enc)){
     nav_ctx_t *ctx=nav_ctx();*ctx=(nav_ctx_t){.enc=enc,.uid=enc.uid,.valid=true,.exploring=true};nav_go(PAGE_BATTLE);return;
    }event=(exploration_event_t){0};feedback="伙伴已离开 请继续探索";
   }else{
    event=world_explore();
    if(event.kind==EXPLORE_ENCOUNTER||event.kind==EXPLORE_CLUE||event.kind==EXPLORE_TARGET){animating=true;started=millis();feedback=NULL;}
    else {feedback=error_text(event.kind);event=(exploration_event_t){0};}
   }
  }
 }
 world_exploration_snapshot(&view);draw_all();
}
