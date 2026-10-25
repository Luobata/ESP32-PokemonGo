// P21/P22: one production renderer, bounded state, no canvas or full framebuffer.
#include "play.h"
#include "field_adventure.h"
#include "world.h"
#include "nav.h"
#include "game_ui.h"
#include "render.h"
#include "screen.h"
#include "screen_idle.h"
#include "presentation_clock.h"
#include "field_map_assets.h"
#include "lvgl.h"
#include "esp_timer.h"
#include <stdio.h>
#include <stdlib.h>

enum { LIST,MAP,RADAR,FOUND };
static unsigned view,selection,map_id,point,error;
static int px,py;
static unsigned start_cell,facing;
static bool walking;
static uint32_t walk_start,last_poll,last_pose;
static field_view_t status;
static encounter_t found;
static presentation_clock_t clock_state;
static lv_timer_t *timer;
static const char *const maps[]={"阿露福遗迹","捕虫公园","烧焦塔"};
static const char *const spots[3][6]={
 {"调查告示","石壁拓纹","石缝足迹","回声石室","遗迹解谜","伙伴协作"},
 {"公园告示","花丛叶痕","池边足迹","隐蔽草丛","捕虫调查","原野路线"},
 {"守塔人","焦木纹路","温热灰烬","暗影长廊","三兽异象","伙伴协作"}
};
static const char *const notes[3][3][2]={
 {{"观察石壁和石缝的痕迹。","三处记录指向回声石室。"},{"墙上刻纹被风磨得发亮。","石室方向传来细小回声。"},{"石缝留有刚刚踩过的尘土。","似乎有伙伴躲在深处。"}},
 {{"观察叶片和池边的足迹。","三处记录指向隐蔽草丛。"},{"嫩叶的边缘留下圆形缺口。","附近的草丛轻轻晃动。"},{"湿泥上留下了细小脚印。","足迹朝公园深处延伸。"}},
 {{"守塔人：请观察木纹。","温热灰烬通向暗影长廊。"},{"焦黑的木柱里藏着新划痕。","阴影中似乎有东西移动。"},{"灰烬中留下温热的足迹。","深处传来一阵轻响。"}}
};
// Cells, collision routes and original pixels are generated together. No path
// search, tile decompression or world-sized framebuffer in the device loop.
enum { MAP_X=8, MAP_Y=32, MAP_W=224, MAP_H=184, MAP_SCALE=2 };
static unsigned target_cell(void){return FIELD_MAP_TARGET[map_id][point];}
static bool at_target(void){unsigned c=target_cell();return px==(int)(c%FIELD_MAP_COLS)*16&&py==(int)(c/FIELD_MAP_COLS)*16;}
static int clamp(int v,int low,int high){return v<low?low:v>high?high:v;}
static uint32_t now(void){return esp_timer_get_time()/1000;}
static void refresh(void){
 world_field_snapshot(&status);
 if((error==FIELD_NO_SIGNAL&&status.signals)||(error==FIELD_NO_STAMINA&&status.stamina>=FIELD_COST)||
    (error==FIELD_COOLDOWN&&!field_remaining(&status.state,view==RADAR?FIELD_RADAR:map_id,status.online_s)))error=0;
}
static void rect(int b,int x,int y,int w,int h,uint16_t c){int a=y>b?y:b,z=y+h<b+SCREEN_BAND_H?y+h:b+SCREEN_BAND_H;for(int yy=a;yy<z;yy++)for(int xx=x;xx<x+w;xx++)screen_px(xx,yy-b,c);}
static void line(int b,int x,int y,int xx,int yy,uint16_t c){int dx=abs(xx-x),sx=x<xx?1:-1,dy=-abs(yy-y),sy=y<yy?1:-1,e=dx+dy;for(;;){screen_px(x,y-b,c);if(x==xx&&y==yy)break;int e2=2*e;if(e2>=dy){e+=dy;x+=sx;}if(e2<=dx){e+=dx;y+=sy;}}}
static void text(int b,int y,const char *s,uint16_t c){game_ui_text_centered(b,8,y,224,16,s,c);}
static const char *failure(void){switch(error){case FIELD_LOCKED:return "取得对应城都徽章后开放";case FIELD_BUSY:return "请先结束当前对战或活动";case FIELD_FULL:return "遭遇已满 请先处理伙伴";case FIELD_NO_STAMINA:return "体能不足 需要 5 点";case FIELD_SAVE_FAILED:return "保存失败 未消耗 请重试";case FIELD_COOLDOWN:return "附近伙伴还在休息";case FIELD_NO_SIGNAL:return "等待附近 Wi-Fi 信号";case FIELD_NEED_CLUES:return "先观察告示和两处痕迹";default:return "";}}
static void radar(int b){
 char t[64];game_ui_title(b,"遭遇雷达",status.simulated?"模拟信号":"Wi-Fi");
 game_ui_box(b,8,40,224,152);rect(b,16,48,208,136,0xef9a);
 // Stylised sweep, deliberately no compass, metres or false GPS coordinates.
 static const int ring[16][2]={{0,-60},{23,-55},{42,-42},{55,-23},{60,0},{55,23},{42,42},{23,55},{0,60},{-23,55},{-42,42},{-55,23},{-60,0},{-55,-23},{-42,-42},{-23,-55}};
 for(int r=1;r<=3;r++)for(unsigned i=0;i<16;i++)line(b,120+ring[i][0]*r/3,116+ring[i][1]*r/3,120+ring[(i+1)%16][0]*r/3,116+ring[(i+1)%16][1]*r/3,0xa571);
 unsigned sweep=(clock_state.elapsed_ms/160)%16;line(b,120,116,120+ring[sweep][0],116+ring[sweep][1],0x3c68);
 for(unsigned i=0;i<status.signals&&i<12;i++){unsigned a=(i*7+status.place)%16;int scale=1+i%3;rect(b,118+ring[a][0]*scale/4,114+ring[a][1]*scale/4,3,3,0x3c68);}
 rect(b,118,114,5,5,GAME_UI_ACCENT);
 snprintf(t,sizeof(t),"附近信号 %u  体能 %u",status.signals,status.stamina);text(b,200,t,GAME_UI_INK);
 unsigned wait=field_remaining(&status.state,FIELD_RADAR,status.online_s);
 if(wait)snprintf(t,sizeof(t),"下次追踪 %u:%02u",wait/60,wait%60);else snprintf(t,sizeof(t),"%s",status.signals?"可以追踪 消耗 5 体能":"扫描中 请稍候");text(b,222,t,GAME_UI_INK);
 text(b,244,error?failure():"闪光 1/32 · 连胜另有加成",error?C_HP_RED:GAME_UI_ACCENT);
 text(b,264,"环境感应 不代表方向距离",GAME_UI_MUTED);
 game_ui_footer(b,selection?"A/B选择 C查看遭遇 长按B返回":"A/B选择 C追踪 长按B返回");
}
// Integer scaling preserves the original pixel silhouette. Clip BOTH map and
// LCD band before reading pixels, so 20-row bands never scan the full scene.
static void map_blit(int b,int x,int y,int size,const uint8_t *data,
                     const uint16_t *pal,bool transparent,bool flip){
 int left=clamp(x,MAP_X,MAP_X+MAP_W),right=clamp(x+size*2,MAP_X,MAP_X+MAP_W);
 int top=clamp(y,MAP_Y,MAP_Y+MAP_H),bottom=clamp(y+size*2,MAP_Y,MAP_Y+MAP_H);
 if(top<b)top=b;
 if(bottom>b+SCREEN_BAND_H)bottom=b+SCREEN_BAND_H;
 if(left>=right||top>=bottom)return;
 uint16_t *pixels=screen_band();
 for(int sy=(top-y)/2;sy<(bottom-y+1)/2;sy++){
  for(int sx=(left-x)/2;sx<(right-x+1)/2;sx++){
   unsigned source_x=flip?size-1-sx:sx;
   unsigned shade=(data[sy*(size/4)+source_x/4]>>(6-(source_x%4)*2))&3;
   if(transparent&&shade==3)continue;
   int yy0=y+sy*2,xx0=x+sx*2;
   int yy1=yy0+2<bottom?yy0+2:bottom,xx1=xx0+2<right?xx0+2:right;
   if(yy0<top)yy0=top;
   if(xx0<left)xx0=left;
   for(int yy=yy0;yy<yy1;yy++)for(int xx=xx0;xx<xx1;xx++)pixels[(yy-b)*SCREEN_W+xx]=pal[shade];
  }
 }
}
static void person(int b,int cx,int cy,unsigned which,int x,int y,unsigned dir,bool moving){
 // Gold FacingStepDown/Up/Left/Right: stand, stride, stand, mirrored stride.
 // Four VBlanks per pose, sampled from elapsed time; no frame increment.
 unsigned pose=moving?((clock_state.elapsed_ms-walk_start)*4194304ULL/(70224ULL*1000*4))%4:0;
 unsigned base=dir<2?dir:2,frame=base+(pose&1?3:0);
 bool flip=dir==3||(dir<2&&pose==3);
 map_blit(b,MAP_X+(x-cx)*2,MAP_Y+(y-8-cy)*2,16,FIELD_PEOPLE[which][frame],FIELD_PERSON_PAL[which],true,flip);
}
static void npc(int b,int cx,int cy,unsigned i){
 const uint8_t *p=FIELD_MAP_NPCS[map_id][i];if(p[0]==255)return;
 int x=p[1]*16,y=p[2]*16;unsigned dir=0;
 if(abs(x-px)+abs(y-py)<=32)dir=abs(x-px)>abs(y-py)?(px<x?2:3):(py<y?1:0);
 person(b,cx,cy,p[0],x,y,dir,false);
}
static void map_art(int b){
 if(b+SCREEN_BAND_H<=MAP_Y||b>=MAP_Y+MAP_H)return;
 int cx=clamp(px+8-MAP_W/4,0,FIELD_MAP_COLS*16-MAP_W/2);
 int cy=clamp(py-MAP_H/4,0,FIELD_MAP_ROWS*16-MAP_H/2);
 int top=b>MAP_Y?b:MAP_Y,bottom=b+SCREEN_BAND_H<MAP_Y+MAP_H?b+SCREEN_BAND_H:MAP_Y+MAP_H;
 int first=(cy+(top-MAP_Y)/2)/8,last=(cy+(bottom-MAP_Y+1)/2+7)/8;
 for(int row=first;row<last;row++)for(int col=cx/8;col<(cx+MAP_W/2+7)/8;col++){
  unsigned tile=FIELD_MAP_TILES[map_id][row][col],pal=FIELD_TILE_PAL[map_id][tile];
  map_blit(b,MAP_X+(col*8-cx)*2,MAP_Y+(row*8-cy)*2,8,FIELD_TILES[map_id][tile],FIELD_BG_PAL[map_id==2][pal],false,false);
 }
 for(unsigned i=0;i<2;i++)if(FIELD_MAP_NPCS[map_id][i][2]*16<=py)npc(b,cx,cy,i);
 person(b,cx,cy,0,px,py,facing,walking);
 for(unsigned i=0;i<2;i++)if(FIELD_MAP_NPCS[map_id][i][2]*16>py)npc(b,cx,cy,i);
 // A small waypoint arrow stays inside the viewport. Offscreen destinations
 // retain direction without moving the camera away from the walking player.
 if(!walking&&!at_target()){
  unsigned c=target_cell();int x=MAP_X+((int)(c%FIELD_MAP_COLS)*16+8-cx)*2;
  int y=MAP_Y+((int)(c/FIELD_MAP_COLS)*16-cy)*2-6;
  int xx=clamp(x,MAP_X+8,MAP_X+MAP_W-9),yy=clamp(y,MAP_Y+7,MAP_Y+MAP_H-8);
  for(int k=0;k<5;k++){rect(b,xx-5+k,yy+k,11-2*k,1,GAME_UI_INK);if(k<3)rect(b,xx-3+k,yy+k+1,7-2*k,1,0xffe0);}
 }
}
static void map_draw(int b){
 char t[64];unsigned n=status.state.visited[map_id];n=(n&1)+((n>>1)&1)+((n>>2)&1);
 snprintf(t,sizeof(t),"记录 %u/3",n);game_ui_title(b,maps[map_id],t);map_art(b);
 // Gold frame-1 dialogue tiles; keep readable margins at native 240x320.
 game_ui_box(b,0,224,240,96);
 snprintf(t,sizeof(t),"%u/6 %s",point+1,spots[map_id][point]);render_text(16,236-b,t,GAME_UI_INK);
 if(error){game_ui_text_fitted(b,16,258,208,failure(),C_HP_RED);render_text(16,278-b,"未消耗资源 可以稍后重试",GAME_UI_MUTED);}
 else if(point<3){
  game_ui_text_fitted(b,16,258,208,notes[map_id][point][0],GAME_UI_INK);
  game_ui_text_fitted(b,16,278,208,notes[map_id][point][1],GAME_UI_INK);
  if(status.state.visited[map_id]&(1u<<point))render_text(176,236-b,"已记录",GAME_UI_MUTED);
 }else if(point==3){
  unsigned wait=field_remaining(&status.state,map_id,status.online_s);
  if(wait)snprintf(t,sizeof(t),"休息中 %u:%02u",wait/60,wait%60);else snprintf(t,sizeof(t),"三处记录齐全后 消耗 5");
  game_ui_text_fitted(b,16,258,208,t,GAME_UI_INK);
  game_ui_text_fitted(b,16,278,208,"闪光 1/24 连胜另有加成",GAME_UI_INK);
 }else{
  game_ui_text_fitted(b,16,258,208,point==4?(map_id==1?"与工作人员开始捕虫调查":"进入现场 继续调查剧情"):"向研究员询问伙伴协作",GAME_UI_INK);
  render_text(16,278-b,"已有调查进度会保留",GAME_UI_MUTED);
 }
 const char *hint=walking?"行进中  长按B返回":at_target()?"A/B选择 C互动 长按B返回":"A/B选择 C前往 长按B返回";
 game_ui_text_centered(b,8,299,224,16,hint,GAME_UI_INK);
}
static void draw_band(int b){
 screen_band_clear(GAME_UI_BG);
 if(view==RADAR)radar(b);
 else if(view==MAP)map_draw(b);
 else if(view==LIST){game_ui_title(b,"地图漫游","城都");text(b,48,"走到现场 观察伙伴的痕迹",GAME_UI_MUTED);for(unsigned i=0;i<3;i++){int y=82+i*54;game_ui_box(b,12,y,216,46);render_text(36,y+6-b,maps[i],GAME_UI_INK);char t[48];snprintf(t,sizeof(t),status.open_maps&(1u<<i)?"开放 · 闪光 1/24":"需要 %u 枚城都徽章",field_map_badges(i));render_text(36,y+25-b,t,GAME_UI_MUTED);if(selection==i)game_ui_cursor(b,20,y+11);}text(b,254,error?failure():"观察免费 搜寻消耗 5 体能",error?C_HP_RED:GAME_UI_MUTED);game_ui_footer(b,GAME_UI_NAV_HINT);}
 else{game_ui_title(b,"发现伙伴",found.is_shiny?"闪光":"");species_t sp;uint8_t size;const uint8_t *sprite=assets_front_sprite(found.species_id,&size);char t[64];if(assets_species(found.species_id,&sp)){uint16_t pal[4];assets_palette_variant(sp.palette,found.is_shiny,pal);if(sprite)game_ui_sprite_centered(b,16,50,208,126,sprite,size,size,2,pal);snprintf(t,sizeof(t),"%.*s Lv%u",sp.name_zh_len,sp.name_zh,found.level);text(b,194,t,GAME_UI_INK);}text(b,224,"已经加入遭遇列表",GAME_UI_INK);text(b,250,"可以战斗或直接尝试捕获",GAME_UI_MUTED);game_ui_footer(b,"C查看遭遇 长按B继续探索");}
 screen_push_band(b);
}
static void draw(void){for(int b=0;b<SCREEN_H;b+=SCREEN_BAND_H)draw_band(b);}
static void draw_art(void){int begin=view==MAP?20:40,end=view==MAP?220:200;for(int b=begin;b<end;b+=SCREEN_BAND_H)draw_band(b);}
static void tick(lv_timer_t *t){(void)t;screen_cadence_begin(50);unsigned ms=presentation_clock_sample(&clock_state,now(),screen_idle_is_off());if(screen_idle_is_off()){screen_cadence_end();return;}
 if(walking){
  unsigned distance=(ms-walk_start)/10,c=start_cell,steps=distance/16;
  while(steps--&&c!=target_cell())c=FIELD_MAP_NEXT[map_id][point][c];
  unsigned next=FIELD_MAP_NEXT[map_id][point][c];int x=c%FIELD_MAP_COLS*16,y=c/FIELD_MAP_COLS*16;
  int dx=(int)(next%FIELD_MAP_COLS)*16-x,dy=(int)(next/FIELD_MAP_COLS)*16-y;
  if(c==target_cell()){px=x;py=y;walking=false;facing=FIELD_MAP_FACING[map_id][point];}
  else{px=x+dx*(int)(distance%16)/16;py=y+dy*(int)(distance%16)/16;facing=dx?(dx<0?2:3):(dy<0?1:0);}
  draw_art();if(!walking)draw();
 }
 else if(view==RADAR&&ms/160!=last_pose){last_pose=ms/160;draw_art();}
 if(ms-last_poll>=1000){last_poll=ms;field_view_t before=status;refresh();if(memcmp(&before,&status,sizeof(status))&&!walking){if(view==RADAR&&(before.signals!=status.signals||before.place!=status.place))draw_art();for(int b=200;b<SCREEN_H;b+=SCREEN_BAND_H)draw_band(b);}}
 screen_cadence_end();}
static void enter(bool radar_mode){if(!nav_is_returning()){view=radar_mode?RADAR:LIST;selection=point=error=0;walking=false;}else if(view==FOUND)view=radar_mode?RADAR:MAP;refresh();presentation_clock_start(&clock_state,now());last_poll=last_pose=0;screen_own_display();screen_set_redraw(draw);timer=lv_timer_create(tick,50,NULL);draw();}
void play_radar_enter(void){enter(true);}void play_fieldmap_enter(void){enter(false);}
void play_field_exit(void){if(timer){lv_timer_delete(timer);timer=NULL;}}
bool play_field_screen_busy(void){return walking;}
static void search(unsigned mode){encounter_t e;error=world_field_search(mode,&e);refresh();if(!error){found=e;view=FOUND;}draw();}
void play_field_key(bsp_btn_t btn,bsp_btn_ev_t ev){
 if(nav_return(btn,ev)){error=0;if(view==FOUND){view=nav_current()==PAGE_RADAR?RADAR:MAP;draw();}else if(view==MAP){walking=false;view=LIST;selection=map_id;draw();}else nav_back(PAGE_MENU);return;}
 if(walking)return;
 int dir=nav_direction(btn,ev);if(dir){error=0;if(view==MAP)point=(point+6+dir)%6;else if(view==LIST)selection=(selection+3+dir)%3;else if(view==RADAR)selection^=1;draw();return;}
 if(!nav_confirm(btn,ev))return;
 error=0;
 if(view==FOUND){nav_open(PAGE_ENCOUNTER);return;}
 if(view==RADAR){if(selection)nav_open(PAGE_ENCOUNTER);else search(FIELD_RADAR);return;}
 if(view==LIST){refresh();if(!(status.open_maps&(1u<<selection))){error=FIELD_LOCKED;draw();return;}map_id=selection;point=0;unsigned c=FIELD_MAP_SPAWN[map_id];px=c%FIELD_MAP_COLS*16;py=c/FIELD_MAP_COLS*16;facing=1;view=MAP;draw();return;}
 if(!at_target()){start_cell=py/16*FIELD_MAP_COLS+px/16;walk_start=clock_state.elapsed_ms;walking=true;draw();return;}
 if(point<3){error=world_field_observe(map_id,point);refresh();draw();}
 else if(point==3)search(map_id);
 else if(point==4){if(map_id==1)play_activity_open_goal(ACT_BUG);else play_story_open_goal(map_id==0?N_GO_RUIN:N_GO_TOWER);}
 else play_johto_open_goal(N_GO_ROUTE,(unsigned[]){3,2,4}[map_id]);
}
void play_field_inspect(unsigned *v,unsigned *m,unsigned *p,int *x,int *y,bool *w,unsigned *e){*v=view;*m=map_id;*p=point;*x=px;*y=py;*w=walking;*e=error;}
