// P20: the production story player. Desktop preview uses this same renderer.
#include "play.h"
#include "world.h"
#include "nav.h"
#include "narrative_script.h"
#include "presentation_clock.h"
#include "battle_motion.h"
#include "game_ui.h"
#include "render.h"
#include "screen.h"
#include "screen_idle.h"
#include "pokemon_animation.h"
#include "music_director.h"
#include "sfx.h"
#include "esp_timer.h"
#include "lvgl.h"
#include <stdio.h>

enum { GUIDE,DIALOG,MEMORIES };
static unsigned view,scene,page,selected,error,misses;
static bool replay,complete_text;
static narrative_context_t context;
static presentation_clock_t clock_state;
static pokemon_idle_t mon;
static lv_timer_t *timer;
static const narrative_script_t *script;
static uint32_t now(void){return (uint32_t)(esp_timer_get_time()/1000);}
static void refresh(void){world_narrative_snapshot(&context);}
static const narrative_page_t *current(void){return script&&page<narrative_pages(scene)?&script->page[page]:NULL;}
static bool choosing(void){return view==DIALOG&&script->choices&&page+1==narrative_pages(scene);}
static unsigned chars(const char *s){unsigned n=0;for(;s&&*s;s++)if(((uint8_t)*s&0xc0)!=0x80)n++;return n;}
static unsigned visible(void){return complete_text?256:clock_state.elapsed_ms>300?(clock_state.elapsed_ms-300)/35:0;}
static unsigned text_length(void){const narrative_page_t *p=current();return p?chars(p->line[0])+chars(p->line[1])+chars(p->line[2]):0;}
static void prefix(char out[64],const char *s,unsigned n){unsigned bytes=0;while(s&&s[bytes]&&n){bytes++;while(((uint8_t)s[bytes]&0xc0)==0x80)bytes++;n--;}if(bytes>63)bytes=63;memcpy(out,s,bytes);out[bytes]=0;}
static void rect(int band,int x,int y,int w,int h,uint16_t c){int lo=y>band?y:band,hi=y+h<band+SCREEN_BAND_H?y+h:band+SCREEN_BAND_H;for(int yy=lo;yy<hi;yy++)for(int xx=x;xx<x+w;xx++)screen_px(xx,yy-band,c);}
static void background(int y,unsigned art){
 const int t=42;rect(y,16,t,208,112,art==N_ART_SEA||art==N_ART_JOURNEY?0xc71f:0xeef5);
 if(art==N_ART_SEA||art==N_ART_JOURNEY){
  unsigned shift=(clock_state.elapsed_ms/240)%4;
  for(int k=0;k<4;k++)for(int x=24;x<202;x+=32)rect(y,x+shift,t+20+k*22,22,2,0x3d7f);
  if(art==N_ART_JOURNEY){int x=52+(clock_state.elapsed_ms<1800?clock_state.elapsed_ms:1800)/30;rect(y,x,t+45,52,12,0x630c);rect(y,x+20,t+18,2,28,0x2108);rect(y,x+22,t+20,22,20,0xffff);}
 }else if(art==N_ART_TOWER||art==N_ART_RUINS){
  for(int i=0;i<3;i++){int x=36+i*64;rect(y,x,t+20,40,76,0x9c53);rect(y,x-4,t+16,48,6,0x630c);rect(y,x+14,t+66,12,30,0x2108);}
  if(art==N_ART_RUINS)for(int i=0;i<3;i++)render_text(49+i*64,t+35-y,(const char*[]){"日","月","星"}[i],GAME_UI_INK);
 }else{
  for(int i=0;i<5;i++){int x=24+i*40;rect(y,x+12,t+62,8,38,0x9387);rect(y,x,t+24,32,48,0x4c49);rect(y,x+6,t+16,20,14,0x4c49);rect(y,x+4,t+30,20,4,0xaeea);}
 }
}
static void artwork(int y){
 const narrative_page_t *p=current();if(!p)return;
 int dy=clock_state.elapsed_ms%1600>=800?-1:0;
 if(p->art!=N_ART_PERSON&&p->art!=N_ART_MON){background(y,p->art);return;}
 if(p->art==N_ART_MON){
  species_t sp;uint8_t size;const uint8_t *art=assets_front_sprite(p->species,&size);
  if(mon.sprite.data){art=mon.sprite.data;size=mon.sprite.w;}
  if(art&&assets_species(p->species,&sp)){uint16_t pal[4];bool shiny=(scene==N_LAKE_INVITE||scene==N_LAKE_REPORT)||(context.state.legend&&context.state.pending.is_shiny);assets_palette_variant(sp.palette,shiny,pal);game_ui_sprite_centered(y,8,42,224,112,art,size,size,2,pal);}return;
 }
 if(p->actor==N_ACTOR_OAK){ui_art_t art;if(assets_ui("oak",&art)){const uint16_t pal[]={0,0x6c20,0xc4eb,0xffff};game_ui_sprite_centered(y,8,42+dy,224,112,art.data,art.w,art.h,1,pal);}return;}
 const uint8_t *art;uint16_t pal[4];trainer_art(p->actor,&art,pal);game_ui_sprite_centered(y,8,42+dy,224,112,art,56,56,2,pal);
}
static unsigned memories(unsigned ids[N_SCENE_COUNT]){unsigned n=0;for(unsigned s=0;s<N_SCENE_COUNT;s++)if(narrative_seen(&context.state,s))ids[n++]=s;return n;}
static void draw_range(int top,int bottom){
 for(int y=top/SCREEN_BAND_H*SCREEN_BAND_H;y<bottom;y+=SCREEN_BAND_H){
  screen_band_clear(GAME_UI_BG);
  if(view==DIALOG){
   const narrative_page_t *p=current();if(!p)continue;char b[64];snprintf(b,sizeof(b),"%u/%u",page+1,narrative_pages(scene));game_ui_title(y,p->speaker,b);artwork(y);
   game_ui_box(y,8,164,224,112);
   if(choosing()){
    // Inference keeps its observation visible; explicit failure explains why.
    game_ui_text_fitted(y,16,172,208,misses?script->hint:p->line[0],GAME_UI_INK);
    for(unsigned i=0;i<script->choices;i++){game_ui_text_fitted(y,38,200+i*24,182,script->choice[i],GAME_UI_INK);if(i==selected)game_ui_cursor(y,18,204+i*24);}
   }else{unsigned remaining=visible();for(unsigned i=0;i<3;i++){prefix(b,p->line[i],remaining);game_ui_text_fitted(y,16,180+i*28,208,b,GAME_UI_INK);unsigned n=chars(p->line[i]);remaining=remaining>n?remaining-n:0;}}
   game_ui_footer(y,replay?"[C]继续 长按B结束回看":choosing()?GAME_UI_NAV_HINT:"[C]继续 长按B暂停");
   if(clock_state.elapsed_ms<300)game_ui_fade_background(y,16-clock_state.elapsed_ms*16/300);
  }else if(view==MEMORIES){
   game_ui_title(y,"旅途回顾","只读");unsigned ids[N_SCENE_COUNT],n=memories(ids),toprow=selected>=6?selected-5:0;
   for(unsigned row=0;row<6&&toprow+row<n;row++){unsigned i=toprow+row;game_ui_text_fitted(y,34,48+row*34,190,narrative_script(ids[i])->title,GAME_UI_INK);if(i==selected)game_ui_cursor(y,14,52+row*34);}
   if(!n)game_ui_text_centered(y,8,124,224,16,"新的旅程正等着你",GAME_UI_MUTED);
   game_ui_text_centered(y,8,256,224,16,"回看不扣体能 不发奖励",GAME_UI_MUTED);game_ui_footer(y,GAME_UI_NAV_HINT);
  }else{
   narrative_goal_t g=narrative_goal(&context);game_ui_title(y,"当前调查","");game_ui_box(y,8,42,224,132);
   game_ui_text_fitted(y,20,54,200,g.title,GAME_UI_INK);game_ui_text_fitted(y,20,90,200,g.place,GAME_UI_ACCENT);game_ui_text_fitted(y,20,126,200,g.task,GAME_UI_INK);
   if(g.action==N_GO_LEGEND)game_ui_text_fitted(y,20,150,200,context.state.legend?"已定位 再次接近不扣体能":"首次定位消耗10体能",GAME_UI_MUTED);
   const char *choices[]={context.state.scene?"继续未完的对话":"继续调查","自由探索","回顾已读剧情"};
   for(unsigned i=0;i<3;i++){game_ui_text_fitted(y,40,190+i*28,180,choices[i],GAME_UI_INK);if(i==selected)game_ui_cursor(y,16,194+i*28);}game_ui_footer(y,GAME_UI_NAV_HINT);
  }
  if(error&&error!=N_WRONG){game_ui_box(y,8,238,224,38);game_ui_text_fitted(y,16,248,208,error==N_BUSY?"先结束当前活动 再继续":error==N_SAVE_FAILED?"保存失败 按C重试":error==N_NO_STAMINA?"体能不足 等待恢复后再接近":"条件未满足 返回查看目标",GAME_UI_INK);}
  screen_push_band(y);
 }
}
static void draw(void){draw_range(0,SCREEN_H);}
static void reset_page(void){
 selected=misses=0;complete_text=false;presentation_clock_start(&clock_state,now());
 const narrative_page_t *p=current();pokemon_idle_reset(&mon,p?p->species:0);
 if(p){music_director_play(p->actor==N_ACTOR_OAK?MUSIC_OAK:p->art==N_ART_PERSON?MUSIC_LAB:MUSIC_ROUTE);if(p->species)sfx_cry(p->species);}
}
static bool begin(unsigned id,bool readonly){
 if(id>=N_SCENE_COUNT)return false;
 if(!readonly){error=world_narrative_update(id,0,0,true);if(error)return false;refresh();}
 replay=readonly;view=DIALOG;scene=id;script=narrative_script(scene);page=readonly?0:context.state.page;reset_page();return true;
}
static void guide(void){view=GUIDE;selected=0;error=0;replay=false;refresh();}
static void launch(narrative_goal_t g){
 switch(g.action){
 case N_GO_ACTIVITY:play_activity_open_goal(g.index);return;
 case N_GO_BATTLE:nav_open(PAGE_TRAINER);return;
 case N_GO_DUNGEON:nav_open(PAGE_DUNGEON);return;
 case N_GO_BUG:play_activity_open_goal(ACT_BUG);return;
 case N_GO_SEA:play_activity_open_goal(ACT_SEA);return;
 case N_GO_RUIN:play_story_open_goal(N_GO_RUIN);return;
 case N_GO_TOWER:play_story_open_goal(N_GO_TOWER);return;
 case N_GO_LAKE:play_story_open_goal(N_GO_LAKE);return;
 case N_GO_RESCUE:play_story_open_goal(N_GO_RESCUE);return;
 case N_GO_PURIFY:play_story_open_goal(N_GO_PURIFY);return;
 case N_GO_LEGEND:{
  encounter_t e;world_johto_result_t r=world_johto_legend(g.index,&e);
  if(r){error=r==WORLD_JOHTO_SAVE_FAILED?N_SAVE_FAILED:r==WORLD_JOHTO_BUSY?N_BUSY:r==WORLD_JOHTO_NO_STAMINA?N_NO_STAMINA:N_LOCKED;return;}
  refresh();unsigned id=N_LEGEND_RAI+g.index;
  if(!narrative_seen(&context.state,id)){begin(id,false);return;}
  *nav_ctx()=(nav_ctx_t){.enc=e,.uid=e.uid,.valid=true,.narrative=true};nav_go(PAGE_BATTLE);return;
 }
 case N_GO_KANTO:nav_open(PAGE_TRAINER);return;
 case N_GO_KANTO_ROUTE:nav_open(PAGE_EXPLORATION);return;
 case N_GO_FREE:play_johto_open_goal(N_GO_FREE,0);return;
 case N_GO_STARTER:
  if(context.chapter.phase==JOHTO_INVITED){world_johto_result_t r=world_johto_depart();if(r){error=r==WORLD_JOHTO_BUSY?N_BUSY:N_SAVE_FAILED;return;}refresh();begin(N_ARRIVAL,false);return;}
  play_johto_open_goal(N_GO_STARTER,0);return;
 default:play_johto_open_goal(g.action,g.index);return;
 }
}
static void follow_scene(unsigned id){
 guide();
 if(id==N_LETTER){launch((narrative_goal_t){.action=N_GO_STARTER});return;}
 if(id==N_ARRIVAL){launch((narrative_goal_t){.action=N_GO_STARTER});return;}
 if(id==N_EGG&&!context.chapter.eggs_hatched){launch((narrative_goal_t){.action=N_GO_EGG});return;}
 if(id>=N_LEGEND_RAI){launch((narrative_goal_t){.action=N_GO_LEGEND,.index=id-N_LEGEND_RAI});return;}
}
static void tick_frame(lv_timer_t *t){
 (void)t;unsigned old=clock_state.elapsed_ms,prev=visible();
 unsigned ms=presentation_clock_sample(&clock_state,now(),screen_idle_is_off());
 if(screen_idle_is_off()||view!=DIALOG)return;
 bool moved=pokemon_idle_step(&mon,battle_motion_delta(old,ms));
 if(old<300){draw();return;}
 const narrative_page_t *p=current();
 if(moved||old/800!=ms/800||(p&&p->art!=N_ART_PERSON&&p->art!=N_ART_MON&&old/240!=ms/240))draw_range(40,160);
 if(!choosing()&&prev<text_length()&&visible()!=prev)draw_range(160,280);
}
static void tick(lv_timer_t *t){screen_cadence_begin(50);tick_frame(t);screen_cadence_end();}
void play_narrative_enter(void){
 guide();unsigned next=narrative_next(&context);
 if(next<N_SCENE_COUNT)begin(next,false);
 screen_set_redraw(draw);timer=lv_timer_create(tick,50,NULL);draw();
}
void play_narrative_exit(void){if(timer){lv_timer_delete(timer);timer=NULL;}}
bool play_narrative_screen_busy(void){return view==DIALOG&&(clock_state.elapsed_ms<300||(!choosing()&&visible()<text_length()));}
void play_narrative_legend(unsigned id){encounter_t e;if(world_johto_legend(id,&e)!=WORLD_JOHTO_OK)return;nav_open(PAGE_NARRATIVE);}
void play_narrative_key(bsp_btn_t b,bsp_btn_ev_t e){
 if(nav_return(b,e)){if(view==GUIDE){play_johto_open_goal(N_GO_FREE,0);return;}guide();draw();return;}
 if(nav_direction(b,e)){
  unsigned ids[N_SCENE_COUNT],n=view==GUIDE?3:view==MEMORIES?memories(ids):choosing()?script->choices:0;
  selected=nav_list_selection(b,e,n,selected);error=0;draw();return;
 }
 if(!nav_confirm(b,e))return;
 error=0;
 if(view==GUIDE){
  if(selected==1){play_johto_open_goal(N_GO_FREE,0);return;}
  if(selected==2){view=MEMORIES;selected=0;draw();return;}
  refresh();unsigned next=narrative_next(&context);
  if(next<N_SCENE_COUNT)begin(next,false);else launch(narrative_goal(&context));
 }else if(view==MEMORIES){unsigned ids[N_SCENE_COUNT],n=memories(ids);if(selected<n)begin(ids[selected],true);}
 else {
  if(!choosing()&&visible()<text_length()){complete_text=true;draw();return;}
  if(replay){if(++page>=narrative_pages(scene)){view=MEMORIES;selected=0;replay=false;}else reset_page();}
  else{
   error=world_narrative_update(scene,page,selected,false);
   if(error==N_WRONG){misses++;sfx_play(SFX_MENU);draw();return;}
   if(!error){refresh();if(context.state.scene){page=context.state.page;reset_page();}else{unsigned finished=scene;follow_scene(finished);}}
  }
 }
 if(nav_current()==PAGE_NARRATIVE)draw();
}
void play_narrative_presentation_snapshot(play_narrative_view_t *out){*out=(play_narrative_view_t){view,scene,page,selected,error,visible(),clock_state.elapsed_ms,replay};}
