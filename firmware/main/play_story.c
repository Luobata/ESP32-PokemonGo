// Adventure journal: persistent choices, receipts, and full-box confirmation.
#include "play.h"
#include "nav.h"
#include "world.h"
#include "game_ui.h"
#include "screen.h"
#include "render.h"
#include "assets.h"
#include "esp_timer.h"
#include "presentation_clock.h"
#include "capture_presentation.h"
static presentation_clock_t story_clock;
#include "lvgl.h"
#include "ball_assets.h"
#include "sfx.h"
#include "music_director.h"
#include "screen_idle.h"
#include <stdio.h>
enum { HOME,RESCUE,RUINS,PUZZLE,LETTERS,TOWER,PURIFY,ENDING,PRIZE,BOX,CONFIRM,FOUND,LAKE,LAKE_CAPTURE };
static unsigned view,selected,group,box,frame,claim_op;
static bool requested_lake,capture_seen,guided;
static unsigned requested_view;
static endgame_t endgame;
static lv_timer_t *timer;
static johto_story_t story;
static johto_state_t chapter;
static bool feather,kanto_ready;
static bool bug_evidence,legacy_final;
static mon_t replaced;
static activity_result_t error;
static story_result_t result;
static void refresh(void){world_story_snapshot(&story);world_endgame_snapshot(&endgame);world_johto_snapshot(&chapter);feather=world_story_feather();kanto_ready=world_story_kanto_ready();narrative_context_t c;world_narrative_snapshot(&c);bug_evidence=c.state.bug_evidence||c.bug_completed;legacy_final=c.state.legacy_final;}
static unsigned menu(unsigned ids[8]){unsigned n=0,b=johto_badges(&chapter);if(b>=2)ids[n++]=RESCUE;if(b>=3){ids[n++]=RUINS;ids[n++]=LETTERS;}if(b>=4)ids[n++]=TOWER;if(b>=5)ids[n++]=LAKE;if(chapter.legend_clues[2]==2)ids[n++]=PURIFY;ids[n++]=ENDING;if(chapter.phase==JOHTO_COMPLETE&&!chapter.final_reward_claimed)ids[n++]=PRIZE;return n;}
static const char *label(unsigned v){switch(v){case LAKE:return "愤怒之湖 红色的身影";case RESCUE:return "满金伙伴救助";case RUINS:return "遗迹符号调查";case LETTERS:return "未知图腾字母册";case TOWER:return "烧焦塔调查";case PURIFY:return "水君净水试炼";case ENDING:return "空木研究笔记";case PRIZE:return "领取研究纪念奖励";default:return "返回";}}
static unsigned count(void){unsigned ids[8];if(view==HOME)return menu(ids);if(view==PUZZLE||view==PURIFY||(view==LAKE&&endgame.lake_stage==LAKE_GUARD_DONE))return 3;if(view==RESCUE)return story.rescue_step&&story.rescue_step<3?3:1;if(view==RUINS){unsigned b=johto_badges(&chapter);return b>=7?4:b>=6?3:b>=4?2:1;}if(view==LETTERS)return 26;if(view==BOX)return BOX_CAPACITY;if(view==CONFIRM)return 2;if(view==PRIZE)return JOHTO_REWARD_COUNT;return 1;}
static void text(int y,int top,const char *s){game_ui_text_fitted(y,8,top,224,s,GAME_UI_INK);}
static void row(int y,unsigned i,int top,const char *s){game_ui_text_fitted(y,32,top,192,s,GAME_UI_INK);if(selected==i)game_ui_cursor(y,12,top+4);}
static void sprite(int y,unsigned id,unsigned form,bool shiny,int x,int top,int scale){
 species_t sp;uint8_t size;const uint8_t *art=assets_front_form(id,form,&size);if(!art||!assets_species(id,&sp))return;
 uint16_t pal[4];assets_palette_variant(sp.palette,shiny,pal);game_ui_sprite_centered(y,x,top+((frame/5)%4==0?-2:0),size*scale,size*scale,art,size,size,scale,pal);
}
static void draw(void){
 for(int y=0;y<SCREEN_H;y+=SCREEN_BAND_H){char b[96];screen_band_clear(GAME_UI_BG);game_ui_title(y,"冒险笔记","");
 if(view==HOME){unsigned ids[8],n=menu(ids);for(unsigned i=0;i<n;i++)row(y,i,42+i*29,label(ids[i]));if(johto_badges(&chapter)<2)text(y,230,"两枚城都徽章开放伙伴救助");}
 else if(view==RESCUE){if(story.rescue_step<3)text(y,44,"满金原野的伙伴求救了");if(!story.rescue_step){snprintf(b,sizeof(b),"满金调查 %u/%u",chapter.research[2],johto_rescue_at(&story));text(y,84,b);text(y,126,story.rescues<2?"前两次救助补齐未选御三家":"后续救助发现幼年伙伴");text(y,170,"无需额外体能 可暂停续接");text(y,220,johto_rescue_ready(&story,&chapter)?"[C]跟随求救声":"继续探索满金原野");}
 else if(story.rescue_step<3){unsigned a=johto_rescue_answer(&story);snprintf(b,sizeof(b),"%s指向%s",story.rescue_step==1?"脚印":"求救声",(const char*[]){"左侧草丛","中间树林","右侧山坡"}[a]);text(y,84,b);text(y,120,"观察线索 找到安全的方向");for(unsigned i=0;i<3;i++)row(y,i,168+i*30,(const char*[]){"走左侧草丛","穿过中间树林","沿右侧山坡"}[i]);}
 else{species_t sp;assets_species(story.rescue_partner.species_id,&sp);snprintf(b,sizeof(b),"%.*s Lv35%s",sp.name_zh_len,sp.name_zh,story.rescue_partner.flags&1?" ★":"");sprite(y,story.rescue_partner.species_id,0,story.rescue_partner.flags&1,64,44,2);text(y,166,b);text(y,194,"伙伴已脱险 一起回家吧！");text(y,228,"[C]接回伙伴");}}
 else if(view==LAKE){
  if(endgame.lake_stage!=LAKE_GUARD_DONE){sprite(y,130,0,true,64,44,2);}
  if(!endgame.lake_stage){text(y,168,"湖边发现了红色的身影。");text(y,198,"首次调查消耗10体能");text(y,226,"失败可续接 伙伴固定闪光");text(y,254,"[C]前往愤怒之湖");}
  else if(endgame.lake_stage==LAKE_RUMOR){text(y,166,"湖面泛起异常的波纹。");text(y,196,"红色鳞片指向湖边旧设施。");text(y,226,"空木：先关闭干扰电波！");text(y,254,"[C]跟随线索");}
  else if(endgame.lake_stage==LAKE_FACILITY){text(y,168,"守卫挡住了设施的入口。");snprintf(b,sizeof(b),"对手 Lv%u-%u",endgame.lake_level-5,endgame.lake_level-1);text(y,198,b);text(y,226,"重试免费 战败影响养成");text(y,254,"[C]挑战电波守卫");}
  else if(endgame.lake_stage==LAKE_GUARD_DONE){text(y,54,"控制台指示：先切断电源");text(y,86,"再拆下发射装置。");text(y,120,"避免让湖中的伙伴受伤。");for(unsigned i=0;i<3;i++)row(y,i,170+i*32,(const char*[]){"提高发射功率","切断干扰电源","继续等待"}[i]);}
  else if(endgame.lake_stage==LAKE_SIGNAL_OFF){text(y,166,"电波停止了！它仍很愤怒。");snprintf(b,sizeof(b),"红色暴鲤龙 Lv%u",endgame.lake_level);text(y,194,b);text(y,222,"降攻或控制平息狂怒");text(y,254,"[C]安抚它 重试免费");}
  else if(endgame.lake_stage==LAKE_CALM){text(y,166,"暴鲤龙终于平静下来了。");text(y,196,capture_seen?"它愿意成为新的同行伙伴。":"空木：它已经信任你了。");text(y,226,"剧情收服必定成功 不耗球");text(y,254,capture_seen?"[C]接回伙伴":"[C]投出精灵球");}
  else{snprintf(b,sizeof(b),"红色暴鲤龙 Lv%u ★",endgame.lake_level);text(y,168,b);text(y,198,"空木：谢谢你救下它。");text(y,228,"红色的羁绊 已记录");text(y,256,"成就页可领取纪念奖励");}
 }
 else if(view==LAKE_CAPTURE){
  unsigned ms=story_clock.elapsed_ms,source=capture_source_frame(ms);
  if(source<80)sprite(y,130,0,true,64,60,2);
  capture_ball_pose_t pose=capture_ball_pose(ms);ui_art_t ball;
  if(assets_ui(source>=37&&source<97?"ball_open":"ball_24",&ball))render_sprite_2bpp_wh(pose.x-12,pose.y-12-y,ball.data,ball.w,ball.h,1,ball_assets_palette(0));
  if(source>=CAPTURE_RESULT_SOURCE_FRAME&&source<CAPTURE_END_SOURCE_FRAME){render_text(80,146-y,"★",GAME_UI_ACCENT);render_text(145,140-y,"★",GAME_UI_ACCENT);render_text(114,114-y,"★",GAME_UI_ACCENT);}
  text(y,234,source>=CAPTURE_RESULT_SOURCE_FRAME?"红色暴鲤龙成为伙伴了！":"精灵球轻轻晃动着……");
 }
 else if(view==RUINS){for(unsigned i=0;i<count();i++){snprintf(b,sizeof(b),"%s遗迹 %s",(const char*[]){"化石","海流","羽翼","生命"}[i],story.ruins&(1u<<i)?"已解谜":"观察墙面");row(y,i,62+i*40,b);}text(y,240,"解谜免费 调查消耗5体能");}
 else if(view==PUZZLE){unsigned step=story.ruin_group==group?story.ruin_step:0;snprintf(b,sizeof(b),"%s",(const char*[]){"先日出 再月升 后星明","星光渐隐 日出后月升","月光渐暗 星落后日出","星落月隐 日光照石壁"}[group]);text(y,66,b);snprintf(b,sizeof(b),"放置第 %u/3 个符号",step+1);text(y,112,b);for(unsigned i=0;i<3;i++)row(y,i,164+i*32,(const char*[]){"日","月","星"}[i]);}
 else if(view==LETTERS){text(y,44,"捕获后点亮对应字母");for(unsigned i=0;i<26;i++){snprintf(b,sizeof(b),"%c",'A'+i);int x=18+(i%7)*31,top=78+(i/7)*34;render_text(x,top-y,b,story.forms_caught&(1u<<i)?GAME_UI_INK:GAME_UI_MUTED);if(selected==i)for(unsigned dx=0;dx<16;dx++)screen_px(x+dx,top+18-y,GAME_UI_INK);}sprite(y,201,selected,false,92,212,1);}
 else if(view==TOWER){for(unsigned i=0;i<3;i++)sprite(y,243+i,0,false,18+i*75,52+(i%2)*10,1);text(y,132,"三道身影穿过烟尘离开。");text(y,168,"雷鸣、焦痕与清澈的水流");text(y,200,"留下了不同方向的线索。");text(y,230,story.tower_seen?"传说调查中可查看下一站":"[C]记录三兽踪迹");}
 else if(view==PURIFY){text(y,62,"水流被落枝挡住了。");text(y,98,"先疏通源头 再让清水流下");for(unsigned i=0;i<3;i++)row(y,i,158+i*34,(const char*[]){"继续搅动下游","移开源头的落枝","堵住河流"}[i]);}
 else if(view==ENDING){if(chapter.phase==JOHTO_COMPLETE){text(y,62,"空木：这一路的相遇");text(y,96,"让我们的研究更加完整。");text(y,138,"谢谢你和伙伴们的努力！");text(y,182,"研究大师纪念章已记录");text(y,218,"森林中还有新的时空线索");text(y,252,"[C]记下这段旅程");}else{bool legends=true;for(unsigned i=0;i<5;i++)if(chapter.legend_clues[i]!=3)legends=false;const bool done[]={chapter.badges==255,kanto_ready,story.rescues>=1,!!(story.ruins&1),feather,story.tower_seen,legends,bug_evidence};const char *names[]={"八枚城都徽章","关都八徽章及赤红","完成一次伙伴救助","解开首组遗迹","漩涡远征银色之羽","烧焦塔三兽调查","三兽与双塔线索齐全","捕虫六节点观察"};for(unsigned i=0;i<8;i++){snprintf(b,sizeof(b),"%s %s",done[i]?"已":"待",names[i]);text(y,40+i*26,b);}text(y,258,legacy_final?"原挑战资格保留 可直接挑战":"线索完成即可 无需捕获");}}
 else if(view==PRIZE){text(y,44,"一次性研究纪念奖励");for(unsigned i=0;i<count();i++)row(y,i,86+i*32,items_info(ITEM_SUN_STONE+i)->name);}
 else if(view==BOX){text(y,40,"仓库已满 选择替换伙伴");unsigned start=selected/6*6;for(unsigned i=0;i<6&&start+i<BOX_CAPACITY;i++){mon_t m;if(!world_box_at(start+i,&m))continue;species_t sp;assets_species(m.species_id,&sp);snprintf(b,sizeof(b),"%u %.*s Lv%u%s",start+i+1,sp.name_zh_len,sp.name_zh,m.level,m.flags&1?"★":"");row(y,start+i,70+i*30,b);}text(y,260,"长按B保留待接回伙伴");}
 else if(view==CONFIRM){species_t sp;assets_species(replaced.species_id,&sp);snprintf(b,sizeof(b),"替换 %.*s Lv%u%s？",sp.name_zh_len,sp.name_zh,replaced.level,replaced.flags&1?"★":"");text(y,82,b);text(y,126,"原伙伴和技能设置会移除");row(y,0,190,"取消");row(y,1,226,"确认替换");}
 else if(view==FOUND){sprite(y,201,result.encounter.biome,result.encounter.is_shiny,64,46,2);text(y,178,"未知图腾出现了！");snprintf(b,sizeof(b),"形态 %c  Lv%u",'A'+result.encounter.biome,result.encounter.level);text(y,210,b);text(y,248,"[C]查看遭遇");}
 if(error){game_ui_box(y,8,238,224,42);text(y,252,error==ACT_SAVE_FAILED?"保存失败 请重试":error==ACT_FULL?"空间不足 奖励仍保留":error==ACT_STAMINA?"体能不足":error==ACT_BUSY?"请先结束正在进行的活动":"再观察一下线索或条件");}
 game_ui_footer(y,view==LAKE_CAPTURE?"收服中……":GAME_UI_NAV_HINT);screen_push_band(y);}
}
static bool action(unsigned op,unsigned choice,unsigned slot){story_request_t q={.op=op,.choice=choice,.group=group,.box_slot=slot,.expected=replaced,.seed=(uint32_t)esp_timer_get_time()};error=world_story_action(&q,&result);refresh();return !error;}
static void tick(lv_timer_t *t){
 (void)t;unsigned old=story_clock.elapsed_ms;
 unsigned ms=presentation_clock_sample(&story_clock,(uint32_t)(esp_timer_get_time()/1000),screen_idle_is_off());
 if(screen_idle_is_off())return;
 unsigned previous=frame;frame=ms/50;
 if(view==LAKE_CAPTURE){
  for(unsigned i=0;i<3;i++){unsigned cue=capture_frame_ms(287+i*49);if(old<cue&&ms>=cue)sfx_play(SFX_MENU);}
  if(old<capture_frame_ms(CAPTURE_RESULT_SOURCE_FRAME)&&ms>=capture_frame_ms(CAPTURE_RESULT_SOURCE_FRAME))music_director_play(MUSIC_CAUGHT);
  if(ms>=capture_frame_ms(CAPTURE_END_SOURCE_FRAME)+3200u){capture_seen=true;view=LAKE;}draw();return;
 }
 if(frame/5!=previous/5&&(view==TOWER||view==LETTERS||view==FOUND||view==LAKE||(view==RESCUE&&story.rescue_step==3)))draw();
}
void play_story_open_goal(unsigned action){requested_view=action==N_GO_RUIN?RUINS:action==N_GO_TOWER?TOWER:action==N_GO_LAKE?LAKE:action==N_GO_RESCUE?RESCUE:PURIFY;guided=true;nav_open(PAGE_STORY);}
void play_story_open_lake(void){requested_lake=true;nav_go(PAGE_STORY);}
void play_story_enter(void){view=requested_lake?LAKE:requested_view?requested_view:HOME;requested_lake=false;requested_view=0;capture_seen=false;claim_op=STORY_RESCUE_CLAIM;selected=0;frame=0;presentation_clock_start(&story_clock,(uint32_t)(esp_timer_get_time()/1000));error=0;refresh();screen_set_redraw(draw);draw();timer=lv_timer_create(tick,50,NULL);}
void play_story_exit(void){if(timer){lv_timer_delete(timer);timer=NULL;}}
void play_story_key(bsp_btn_t b,bsp_btn_ev_t e){
 if(view==LAKE_CAPTURE)return;
 if(nav_return(b,e)){if(view==HOME){if(guided){guided=false;nav_go(PAGE_NARRATIVE);}else nav_back(PAGE_JOHTO);return;}if(view==PUZZLE&&story.ruin_step){action(STORY_RUIN_BACK,0,BOX_CAPACITY);}else{view=HOME;selected=0;error=0;}draw();return;}
 if(nav_direction(b,e)){selected=nav_list_selection(b,e,count(),selected);error=0;draw();return;}
 if(!nav_confirm(b,e))return;
 error=0;
 if(view==HOME){unsigned ids[8];menu(ids);view=ids[selected];selected=0;}
 else if(view==RESCUE){if(!story.rescue_step)action(STORY_RESCUE_BEGIN,0,BOX_CAPACITY);else if(story.rescue_step<3)action(STORY_RESCUE_CHOOSE,selected,BOX_CAPACITY);else if((claim_op=STORY_RESCUE_CLAIM,action(STORY_RESCUE_CLAIM,0,BOX_CAPACITY))){view=HOME;selected=0;}else if(error==ACT_FULL){view=BOX;selected=0;error=0;}}
 else if(view==LAKE){
  if(!endgame.lake_stage)action(STORY_LAKE_BEGIN,0,BOX_CAPACITY);
  else if(endgame.lake_stage==LAKE_RUMOR)action(STORY_LAKE_CLUE,0,BOX_CAPACITY);
  else if(endgame.lake_stage==LAKE_FACILITY||endgame.lake_stage==LAKE_SIGNAL_OFF){world_challenge_result_t r=world_challenge_start(endgame.lake_stage==LAKE_FACILITY?TRAINER_LAKE_GUARD:TRAINER_LAKE_BOSS);if(!r){nav_open(PAGE_TRAINER);return;}error=r==WORLD_CHALLENGE_BUSY?ACT_BUSY:ACT_SAVE_FAILED;}
  else if(endgame.lake_stage==LAKE_GUARD_DONE){if(action(STORY_LAKE_SWITCH,selected,BOX_CAPACITY))selected=0;}
  else if(endgame.lake_stage==LAKE_CALM){if(!capture_seen){frame=0;presentation_clock_start(&story_clock,(uint32_t)(esp_timer_get_time()/1000));view=LAKE_CAPTURE;music_director_play(MUSIC_NONE);sfx_play(SFX_BALL_THROW);}else{claim_op=STORY_LAKE_CLAIM;if(!action(claim_op,0,BOX_CAPACITY)&&error==ACT_FULL){view=BOX;selected=0;error=0;}}}
  else {view=HOME;selected=0;}
 }
 else if(view==RUINS){group=selected;selected=0;if(story.ruins&(1u<<group)){if(action(STORY_RUIN_EXPLORE,0,BOX_CAPACITY))view=FOUND;}else view=PUZZLE;}
 else if(view==PUZZLE){if(action(STORY_RUIN_CHOOSE,selected,BOX_CAPACITY)&&(story.ruins&(1u<<group))){view=RUINS;selected=group;}}
 else if(view==TOWER){if(story.tower_seen||action(STORY_TOWER,0,BOX_CAPACITY)){view=HOME;selected=0;}}
 else if(view==PURIFY){if(action(STORY_PURIFY,selected,BOX_CAPACITY)){view=HOME;selected=0;}}
 else if(view==ENDING){if(chapter.phase==JOHTO_COMPLETE)action(STORY_ENDING,0,BOX_CAPACITY);view=HOME;selected=0;}
 else if(view==PRIZE){if(action(STORY_FINAL_PRIZE,selected,BOX_CAPACITY)){view=HOME;selected=0;}}
 else if(view==BOX){box=selected;if(world_box_at(box,&replaced)){view=CONFIRM;selected=0;}}
 else if(view==CONFIRM){if(!selected){view=BOX;selected=box;}else if(action(claim_op,0,box)){view=HOME;selected=0;}}
 else if(view==FOUND){nav_open(PAGE_ENCOUNTER);return;}
 else {view=HOME;selected=0;}
 if(guided&&!error&&(view==HOME||(view==RUINS&&(story.ruins&1)))){guided=false;nav_go(PAGE_NARRATIVE);return;}draw();
}

bool play_story_screen_busy(void){return view==LAKE_CAPTURE;}
