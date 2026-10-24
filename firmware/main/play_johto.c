// P17: chapter travel, investigations, independent badges and the Togepi egg.
#include <stdio.h>
#include <string.h>
#include "play.h"
#include "nav.h"
#include "world.h"
#include "assets.h"
#include "game_ui.h"
#include "render.h"
#include "screen.h"
#include "pokemon_animation.h"
#include "johto_egg_assets.h"
#include "presentation_clock.h"
#include "screen_idle.h"
#include "esp_timer.h"
#include "lvgl.h"

enum { HOME, ROUTES, GYMS, EGG, LEGENDS, FOUND, PARTNER, HATCHED, REWARDS, GYM_INFO, ROUTE_HOME, PATHS, SEARCH_RESULT, ROUTE_ACTIVITIES, FIELD_NOTES, FIELD_PATHS, FIELD_PARTNER, FIELD_RESULT };
static unsigned view,selected,fade,hatch_frames,route,path,refresh_ms;
static bool resume_route,rewards_from_route,guided;
static unsigned requested_action,requested_index;
static bool requested_goal;
static unsigned available_probe=JOHTO_PROBE_NONE,probe_id=JOHTO_PROBE_NONE,probe_path;
static bool probe_help;
static world_party_t probe_party;
static mon_t probe_actor;
static presentation_clock_t probe_clock;
static const char *goal_title;
static unsigned next_scene;
static johto_search_t search;
static const char *notice;
static bool hatch_shiny;
static johto_state_t chapter;
static trainer_store_t progress;
static endgame_t endgame;
static world_t world;
static world_johto_result_t error;
static encounter_t found;
static uint16_t reward_claimed[JOHTO_REWARD_COUNT];
static pokemon_idle_t idle;
static lv_timer_t *timer;
static const unsigned starters[]={152,155,158};
static const char *const legends[]={"雷公","炎帝","水君","洛奇亚","凤王","时拉比"};
static unsigned count(void){
 if(chapter.phase==JOHTO_VOYAGE)return 3;
 if(view==ROUTES){unsigned n=0;while(n<8&&johto_route_open(&chapter,n))n++;return n;}
 if(view==GYMS){return chapter.phase==JOHTO_COMPLETE?11:world_johto_final_available()?9:johto_badges(&chapter)<8?johto_badges(&chapter)+1:8;}
 if(view==LEGENDS)return 6;
 if(view==PATHS||view==ROUTE_HOME||view==ROUTE_ACTIVITIES)return 3;
 if(view==SEARCH_RESULT)return search.kind==JOHTO_SEARCH_CLUE?3:2;
 if(view==REWARDS)return JOHTO_REWARD_COUNT;
 if(view==FIELD_NOTES||view==FIELD_PATHS)return 3;
 if(view==FIELD_PARTNER)return probe_party.count;
 if(view==FIELD_RESULT)return 1;
 return view==HOME?9:1;
}
static const char *failure(void){
 switch(error){case WORLD_JOHTO_LOCKED:return "条件未满足";case WORLD_JOHTO_BUSY:return "请先结束当前对战或秘境";case WORLD_JOHTO_FULL:return view==REWARDS?"道具已满 奖励仍保留":"仓库已满 请先整理仓库";
 case WORLD_JOHTO_NO_STAMINA:return "体能不足 等待恢复";case WORLD_JOHTO_SAVE_FAILED:return "保存失败 按C重试";
 case WORLD_JOHTO_WRONG_PATH:return "这里没有记录中的迹象";case WORLD_JOHTO_WRONG_PARTNER:return "这位伙伴还无法回应";default:return "";}
}
static void refresh(void){narrative_context_t c;world_narrative_snapshot(&c);goal_title=narrative_goal(&c).title;next_scene=narrative_next(&c);available_probe=johto_probe_next(&c.chapter,&c.story,c.feather,route,c.state.focus);world_johto_snapshot(&chapter);world_challenge_snapshot(&progress);world_endgame_snapshot(&endgame);world_snapshot(&world);world_johto_reward_progress(reward_claimed);}
static void sprite(int y,unsigned id,bool shiny){
 species_t sp;if(!assets_species(id,&sp))return;
 unsigned size=0;uint8_t original_size=0;
 const uint8_t *data=assets_front_sprite(id,&original_size);size=original_size;
 if(idle.species==id&&idle.sprite.data){data=idle.sprite.data;size=idle.sprite.w;}
 uint16_t pal[4];assets_palette_variant(sp.palette,shiny,pal);
 if(data&&size)game_ui_sprite_centered(y,16,56,208,128,data,size,size,2,pal);
 char name[48];snprintf(name,sizeof(name),"%.*s",sp.name_zh_len,sp.name_zh);
 game_ui_text_centered(y,8,194,224,16,name,GAME_UI_INK);
}
// Compact map tiles share the exploration page's pixel palette and band clipping.
static void rect(int band,int x,int y,int w,int h,uint16_t c){
 int lo=y>band?y:band,hi=y+h<band+SCREEN_BAND_H?y+h:band+SCREEN_BAND_H;
 for(int yy=lo;yy<hi;yy++)for(int xx=x;xx<x+w;xx++)screen_px(xx,yy-band,c);
}
static void scene(int band){
 bool water=route==6,snow=route==5,tower=route==3||route==4||route==7;
 rect(band,16,72,208,80,water?0xaeff:snow?0xe79f:tower?0xe71c:0xeef5);
 rect(band,16,134,208,18,water?0xef75:snow?0xc71f:0xef75);
 if(water){
  for(int k=0;k<3;k++)for(int i=0;i<6;i++){int x=22+i*32+(k%2)*6,y=82+k*18;rect(band,x,y,20,2,0x3d7f);rect(band,x+2,y-2,16,2,0xe79f);}
 }else if(tower){
  for(int i=0;i<3;i++){int x=36+i*64;rect(band,x,84,40,54,0x4a49);rect(band,x+4,88,32,46,0x9c53);rect(band,x-4,80,48,6,route==4?0x9387:0x630c);rect(band,x+14,114,12,24,0x2108);rect(band,x+10,94,20,10,route==7?0xfde0:0x4a49);}
 }else{
  static const char *const tree[]={
   ".....111111.....","...1122222211...","..122233322221..",".12233333222221.",
   "1223333222222221","1223322222232221","1222222222332221",".12222322222221.",
   "..122332222221..",".12233322222221.","1223332222232221","1223322222332221",
   "1222222223332221",".12222222222221.","..111222222111..",".....114411.....",
   "......1441......","......1441......",".....144441.....",".....111111....."};
  const uint16_t pal[]={0,0x2245,snow?0xc71f:0x4c49,snow?0xffff:0xaeea,0x9387};
  for(int i=0;i<5;i++)for(int yy=0;yy<20;yy++)for(int xx=0;xx<16;xx++)if(tree[yy][xx]!='.')rect(band,20+i*40+xx*2,80+(i%2)*6+yy*2,2,2,pal[tree[yy][xx]-'0']);
  for(int i=0;i<10;i++)rect(band,22+i*20,144-(i%2)*4,4,2,snow?0xffff:0x4c49);
 }
}
static void tracking(int band,int yy){
 unsigned clues=johto_track_clues(&chapter,route);species_t sp;char text[64];
 if(assets_species(johto_track_target(&chapter,route),&sp))snprintf(text,sizeof(text),"追踪 %.*s",sp.name_zh_len,sp.name_zh);else snprintf(text,sizeof(text),"追踪伙伴");
 game_ui_text_centered(band,8,yy,224,16,text,GAME_UI_INK);
 for(unsigned i=0;i<3;i++){int x=66+i*40;rect(band,x,yy+28,28,8,GAME_UI_INK);rect(band,x+2,yy+30,24,4,i<clues?GAME_UI_ACCENT:GAME_UI_BG);}
 snprintf(text,sizeof(text),clues==3?"线索齐全 下次发现目标":"线索 %u/3 每次探索推进",clues);game_ui_text_centered(band,8,yy+46,224,16,text,GAME_UI_MUTED);
}
static void path_names(int band,const johto_path_t *p,int yy){
 for(unsigned row=0;row<2;row++){char text[64]={0};size_t used=0;
  for(unsigned i=0;i<2;i++){species_t sp;if(!assets_species(p->species[row*2+i],&sp))continue;
   int n=snprintf(text+used,sizeof(text)-used,"%s%.*s",i?" / ":"",sp.name_zh_len,sp.name_zh);if(n<0||(size_t)n>=sizeof(text)-used)break;used+=n;}
  game_ui_text_fitted(band,36,yy+row*18,188,text,GAME_UI_MUTED);
 }
}
static bool field_screen(void){return view>=FIELD_NOTES&&view<=FIELD_RESULT;}
static bool route_screen(void){return view==ROUTE_HOME||view==PATHS||view==SEARCH_RESULT||view==ROUTE_ACTIVITIES||field_screen();}
static void probe_art(int y){
 scene(y);
 if(view!=FIELD_RESULT)return;
 species_t sp;uint8_t size;const uint8_t *art=assets_front_sprite(probe_actor.species_id,&size);
 unsigned ms=probe_clock.elapsed_ms;
 if(art&&assets_species(probe_actor.species_id,&sp)){uint16_t pal[4];assets_palette_variant(sp.palette,(probe_actor.flags&1)!=0,pal);
  int bob=ms<1200?(int[]){0,-2,0,1}[ms/150%4]:0;
  game_ui_sprite_centered(y,84,76+bob,72,72,art,size,size,1,pal);
 }
 if(ms<1200){int r=12+(ms%600)/20;for(int i=0;i<4;i++){int x=120+(int[]){-1,1,0,0}[i]*r,yy=112+(int[]){0,0,-1,1}[i]*r;rect(y,x-3,yy,7,2,0xfde0);rect(y,x,yy-3,2,7,0xfde0);}}
}
static const char *probe_type(unsigned t){static const char *const names[]={"普","火","水","电","草","冰","格","毒","地","飞","超","虫","岩","幽","龙","恶","钢"};return t<17?names[t]:"";}
static void draw_range(int top,int bottom){
 for(int y=top/SCREEN_BAND_H*SCREEN_BAND_H;y<bottom;y+=SCREEN_BAND_H){
  screen_band_clear(GAME_UI_BG);char text[64];snprintf(text,sizeof(text),"徽章 %u/8",johto_badges(&chapter));
  if(route_screen())snprintf(text,sizeof(text),"体能%u",nurture_stamina_points(&world.pet));
  game_ui_title(y,route_screen()?JOHTO_ROUTES[route].name:"城都之旅",chapter.phase>=JOHTO_ACTIVE?text:"");
  bool actions=false;
  const char *hint=GAME_UI_NAV_HINT;
  const johto_probe_t *probe=johto_probe(probe_id);
  if(field_screen()&&probe){
   if(view==FIELD_NOTES||view==FIELD_RESULT){
    game_ui_text_fitted(y,12,40,216,probe->title,GAME_UI_INK);probe_art(y);game_ui_box(y,8,164,224,110);
    if(view==FIELD_NOTES){
     game_ui_text_fitted(y,16,174,208,probe->clue[0],GAME_UI_INK);game_ui_text_fitted(y,16,198,208,probe->clue[1],GAME_UI_INK);
     game_ui_text_fitted(y,16,228,208,probe_help?probe->help:"观察地点，想想谁能帮忙。",GAME_UI_MUTED);
     game_ui_text_fitted(y,16,252,208,probe_help?probe->observation:"成功调查5体能 准备免费",GAME_UI_MUTED);
     const char *choices[]={"调查","提示","队伍"};game_ui_actions(y,choices,3,selected);actions=true;
    }else{
     game_ui_text_fitted(y,16,174,208,probe->action,GAME_UI_INK);game_ui_text_fitted(y,16,202,208,probe->found,GAME_UI_INK);game_ui_text_fitted(y,16,236,208,probe->next,GAME_UI_MUTED);
     hint="[C]记录线索并继续";
    }
   }else if(view==FIELD_PATHS){
    game_ui_text_fitted(y,12,40,216,probe->clue[0],GAME_UI_INK);game_ui_text_fitted(y,12,64,216,probe->clue[1],GAME_UI_MUTED);
    for(unsigned i=0;i<3;i++){int yy=96+i*48;game_ui_box(y,8,yy,224,40);if(i==selected)game_ui_cursor(y,20,yy+14);render_text(44,yy+10-y,johto_path(route,i)->name,GAME_UI_INK);}
    game_ui_text_fitted(y,12,252,216,error?failure():"依据线索选择地点 准备免费",error?GAME_UI_INK:GAME_UI_MUTED);
   }else{
    game_ui_text_centered(y,8,38,224,16,"让哪位同行伙伴来帮忙？",GAME_UI_INK);
    for(unsigned i=0;i<probe_party.count;i++){const mon_t *m=&probe_party.members[i];species_t sp;if(!assets_species(m->species_id,&sp))continue;int yy=70+i*28;
     if(i==selected)game_ui_cursor(y,12,yy+4);
     snprintf(text,sizeof(text),"%.*s Lv%u",sp.name_zh_len,sp.name_zh,m->level);game_ui_text_fitted(y,32,yy,130,text,GAME_UI_INK);
     snprintf(text,sizeof(text),"%s%s%s",probe_type(sp.type1),sp.type2==255?"":"/",probe_type(sp.type2));game_ui_text_fitted(y,166,yy,62,text,GAME_UI_MUTED);
    }
    game_ui_text_fitted(y,12,246,216,error==WORLD_JOHTO_WRONG_PARTNER?(selected<probe_party.count&&!probe_party.members[selected].hp?"这位伙伴需要先恢复体力":probe->help):error?failure():"合适才出发：5体能",GAME_UI_MUTED);
   }
  }else if(chapter.phase==JOHTO_HIDDEN){game_ui_text_centered(y,8,112,224,16,"获得四枚关都徽章后",GAME_UI_INK);game_ui_text_centered(y,8,144,224,16,"新的旅程将会开启",GAME_UI_INK);}
  else if(chapter.phase==JOHTO_INVITED){
   const uint8_t *art;uint16_t pal[4];trainer_art(TRAINER_JOHTO_FIRST+8,&art,pal);
   game_ui_sprite_centered(y,8,40,224,112,art,56,56,2,pal);
   game_ui_box(y,8,168,224,104);
   game_ui_text_centered(y,16,180,208,16,"来自空木博士的邀请",GAME_UI_INK);
   game_ui_text_centered(y,16,208,208,16,"城都发现了新的伙伴。",GAME_UI_INK);
   game_ui_text_centered(y,16,236,208,16,"一起去调查吧！",GAME_UI_INK);hint="[C]启程 长按B稍后";
  }else if(chapter.phase==JOHTO_VOYAGE){
   sprite(y,starters[selected],false);
   game_ui_text_centered(y,8,40,224,16,"选择城都伙伴",GAME_UI_INK);
   game_ui_text_centered(y,8,228,224,16,"Lv35 加入队伍或仓库",GAME_UI_MUTED);
  }else if(view==PARTNER||view==HATCHED){
   sprite(y,view==HATCHED?175:chapter.starter,view==HATCHED&&hatch_shiny);
   game_ui_text_centered(y,8,228,224,16,view==HATCHED?"波克比从蛋里孵出来了！":"新伙伴已经加入！",GAME_UI_INK);
   hint="[C]继续";
  }else if(view==ROUTE_HOME){
   snprintf(text,sizeof(text),"野生Lv%u-%u 每次5体能",JOHTO_ROUTES[route].min_level,JOHTO_ROUTES[route].max_level);
   game_ui_text_centered(y,8,44,224,16,text,GAME_UI_INK);scene(y);tracking(y,168);
   game_ui_text_centered(y,8,250,224,16,world.pending>=ENC_QUEUE_LIMIT?"遭遇已满 将替换最早一只":"选择分支 寻找伙伴与补给",GAME_UI_MUTED);
   const char *choices[]={"探索","路线","活动"};
   if(available_probe<JOHTO_PROBE_COUNT){const johto_probe_t *p=johto_probe(available_probe);game_ui_box(y,8,160,224,116);game_ui_text_fitted(y,16,172,208,p->title,GAME_UI_INK);game_ui_text_fitted(y,16,200,208,p->clue[0],GAME_UI_MUTED);game_ui_text_fitted(y,16,242,208,"关键调查：需要伙伴协助",GAME_UI_INK);choices[0]="调查";choices[1]="探索";}
   game_ui_actions(y,choices,3,selected);actions=true;
  }else if(view==PATHS){
   game_ui_text_centered(y,8,36,224,16,johto_track_clues(&chapter,route)==3?"线索齐全 本次追踪目标":"选择分支 · 探索消耗5体能",GAME_UI_INK);
   for(unsigned i=0;i<3;i++){const johto_path_t *p=johto_path(route,i);int yy=58+i*72;
    game_ui_box(y,8,yy,224,64);if(selected==i)game_ui_cursor(y,16,yy+10);render_text(36,yy+6-y,p->name,GAME_UI_INK);path_names(y,p,yy+26);
   }
  }else if(view==SEARCH_RESULT){
   if(search.kind==JOHTO_SEARCH_CLUE){
    game_ui_text_centered(y,8,44,224,16,"发现了新的足迹！",GAME_UI_INK);scene(y);tracking(y,168);
    if(search.quantity)snprintf(text,sizeof(text),"获得 %s ×%u",items_info(search.item)->name,search.quantity);else snprintf(text,sizeof(text),"补给已满 线索仍已记录");
    game_ui_text_centered(y,8,246,224,16,text,GAME_UI_INK);
    const char *choices[]={"继续","路线","活动"};game_ui_actions(y,choices,3,selected);
   }else{
    game_ui_text_centered(y,8,40,224,16,search.kind==JOHTO_SEARCH_TARGET?"追踪目标出现了！":"发现野生宝可梦！",GAME_UI_INK);
    sprite(y,search.encounter.species_id,search.encounter.is_shiny);
    snprintf(text,sizeof(text),"Lv%u 稀有度%u%s",search.encounter.level,search.encounter.rarity,search.encounter.is_shiny?" 闪光":"");game_ui_text_centered(y,8,224,224,16,text,GAME_UI_INK);
    snprintf(text,sizeof(text),search.kind==JOHTO_SEARCH_TARGET?"追踪完成 新目标已更新":"线索 %u/3 查看进入该遭遇",search.clues);game_ui_text_centered(y,8,252,224,16,text,GAME_UI_MUTED);
    const char *choices[]={"查看","继续"};game_ui_actions(y,choices,2,selected);
   }actions=true;
  }else if(view==ROUTE_ACTIVITIES){
   const char *labels[]={"研究奖励","特色活动","冒险笔记"};
   for(unsigned i=0;i<3;i++){render_text(48,72+i*48-y,labels[i],GAME_UI_INK);if(selected==i)game_ui_cursor(y,24,76+i*48);}
   game_ui_text_centered(y,8,236,224,16,JOHTO_ROUTES[route].activity,GAME_UI_MUTED);
  }else if(view==FOUND){
   sprite(y,found.species_id,found.is_shiny);snprintf(text,sizeof(text),"Lv%u %s",found.level,found.is_shiny?"闪光伙伴":"已加入遭遇列表");
   game_ui_text_centered(y,8,228,224,16,text,GAME_UI_INK);hint="[C]查看遭遇 长按B返回";
  }else if(view==EGG){
   int offset=hatch_frames?(int)(hatch_frames%6)-3:0;
   game_ui_sprite_centered(y,16+offset,60,208,120,JOHTO_EGG_ART,40,40,2,JOHTO_EGG_PAL);
   snprintf(text,sizeof(text),"孵化进度 %u/%u",chapter.egg_steps,JOHTO_EGG_STEPS);
   game_ui_text_centered(y,8,196,224,16,hatch_frames?"蛋开始晃动了！":chapter.egg_status?text:"空木博士的神秘蛋",GAME_UI_INK);
   const char *note=hatch_frames?"新伙伴就要出来了":chapter.egg_status==JOHTO_EGG_READY?"蛋里的伙伴要出来了！":chapter.egg_status?"城都探索一次 前进一步":!chapter.badges?"赢得首枚城都徽章后领取":chapter.explorations<chapter.next_egg_at?"继续探索 等待下一枚蛋":"可以领取新的神秘蛋";
   game_ui_text_centered(y,8,228,224,16,note,GAME_UI_MUTED);
   hint=chapter.egg_status==JOHTO_EGG_READY?"[C]孵化 长按B返回":chapter.egg_status?(guided?"[C]继续调查 长按B返回":GAME_UI_BACK_HINT):"[C]领取 长按B返回";
  }else if(view==GYM_INFO){
   const trainer_info_t *t=trainer_info_progress(TRAINER_JOHTO_FIRST+selected,&progress);
   bool champion=trainer_champion(&progress);unsigned rule=champion?(selected<8?selected+1:GYM_ELM):0;
   game_ui_text_centered(y,8,44,224,16,champion?"赤红之后 冠军挑战":"城都道馆挑战",GAME_UI_INK);
   const uint8_t *art;uint16_t pal[4];trainer_art(TRAINER_JOHTO_FIRST+selected,&art,pal);game_ui_sprite_centered(y,8,70,224,80,art,56,56,1,pal);
   snprintf(text,sizeof(text),"%s Lv%u-%u %u只",t->name,t->levels[0],t->levels[t->count-1],t->count);game_ui_text_fitted(y,8,154,224,text,GAME_UI_INK);
   game_ui_text_centered(y,8,180,224,16,gym_rules_name(rule),GAME_UI_INK);
   game_ui_text_fitted(y,8,204,224,gym_rules_effect(rule),GAME_UI_MUTED);
   game_ui_text_fitted(y,8,228,224,gym_rules_hint(rule),GAME_UI_MUTED);
   game_ui_text_centered(y,8,254,224,16,champion&&selected<8&&(endgame.champion_gyms&(1u<<selected))?"冠军首胜已记录":"挑战消耗10体能",GAME_UI_MUTED);
   hint="[C]挑战 长按B返回";
  }else if(view==HOME){
   const char *labels[]={"继续调查","调查路线","城都道馆","神秘蛋","传说调查","研究奖励","特色活动","冒险笔记","返回冒险"};
   for(unsigned i=0;i<9;i++){render_text(48,36+i*24-y,labels[i],GAME_UI_INK);if(selected==i)game_ui_cursor(y,24,40+i*24);}
   game_ui_text_fitted(y,8,258,224,goal_title,GAME_UI_MUTED);
  }else if(view==REWARDS){
   for(unsigned i=0;i<JOHTO_REWARD_COUNT;i++){
    render_text(32,40+i*26-y,items_info(ITEM_SUN_STONE+i)->name,GAME_UI_INK);if(selected==i)game_ui_cursor(y,12,48+i*28);
    unsigned ready=johto_reward_entitled(&chapter,i)-reward_claimed[i];snprintf(text,sizeof(text),"待领%u",ready);render_text(224-render_text_width(text),40+i*26-y,text,GAME_UI_MUTED);
   }
   const johto_research_reward_t *r=&JOHTO_REWARDS[selected];
   game_ui_text_centered(y,8,194,224,16,r->source,GAME_UI_INK);
   snprintf(text,sizeof(text),"调查%u次 已领%u个",chapter.research[r->route],reward_claimed[selected]);
   game_ui_text_fitted(y,8,222,224,text,GAME_UI_MUTED);
   snprintf(text,sizeof(text),"每%u次1个 需%u徽章",r->step,r->badges);game_ui_text_centered(y,8,250,224,16,text,GAME_UI_MUTED);
  }else {
   unsigned n=count(),top=selected>=6?selected-5:0;
   for(unsigned row=0;row<6&&top+row<n;row++){
    unsigned i=top+row;const char *label=view==ROUTES?JOHTO_ROUTES[i].name:view==GYMS?JOHTO_TRAINERS[i].name:legends[i];
    render_text(32,48+row*32-y,label,GAME_UI_INK);if(selected==i)game_ui_cursor(y,12,52+row*32);
    if(view==ROUTES)snprintf(text,sizeof(text),"%u-%u",JOHTO_ROUTES[i].min_level,JOHTO_ROUTES[i].max_level);
    else if(view==GYMS){const trainer_info_t *t=trainer_info_progress(TRAINER_JOHTO_FIRST+i,&progress);snprintf(text,sizeof(text),"%s%u",trainer_champion(&progress)?"冠":"Lv",t->levels[t->count-1]);}
    else snprintf(text,sizeof(text),"%u/3",chapter.legend_clues[i]);
    render_text(224-render_text_width(text),48+row*32-y,text,GAME_UI_MUTED);
   }

   const char *note=view==ROUTES?(selected==5?"红色身影线索见冒险笔记":"探索消耗5体能"):view==GYMS?(trainer_champion(&progress)?"冠军版 等级与规则强化":"击败赤红后自动强化"):world_story_legend_hint(selected);
   game_ui_text_centered(y,8,250,224,16,note,GAME_UI_MUTED);
  }
  if((error||notice)&&!field_screen()){game_ui_box(y,8,240,224,40);game_ui_text_centered(y,16,252,208,16,error?failure():notice,GAME_UI_INK);}
  if(!actions)game_ui_footer(y,hint);
  if(fade)game_ui_fade_background(y,fade);
  screen_push_band(y);
 }
}
static void draw(void){draw_range(0,SCREEN_H);}
static void reset_sprite(void){
 unsigned id=chapter.phase==JOHTO_VOYAGE?starters[selected]:view==PARTNER?chapter.starter:view==HATCHED?175:view==FOUND?found.species_id:view==SEARCH_RESULT&&search.kind!=JOHTO_SEARCH_CLUE?search.encounter.species_id:0;
 pokemon_idle_reset(&idle,id);
}
static void tick(lv_timer_t *t){
 (void)t;bool changed=false;
 unsigned old_ms=probe_clock.elapsed_ms;presentation_clock_sample(&probe_clock,(uint32_t)(esp_timer_get_time()/1000),screen_idle_is_off());
 if(screen_idle_is_off())return;
 if((refresh_ms+=50)>=1000){
  refresh_ms=0;unsigned stamina=nurture_stamina_points(&world.pet),pending=world.pending;
  world_snapshot(&world);changed=stamina!=nurture_stamina_points(&world.pet)||pending!=world.pending;
 }
 if(fade){fade--;changed=true;}
 if(hatch_frames){if(!--hatch_frames){view=HATCHED;fade=4;reset_sprite();}changed=true;}
 if(pokemon_idle_step(&idle,50))changed=true;
 if(changed)draw();
 else if(view==FIELD_RESULT&&old_ms<1200&&probe_clock.elapsed_ms/50!=old_ms/50)draw_range(60,160);
}
void play_johto_open_goal(unsigned action,unsigned index){requested_goal=true;requested_action=action;requested_index=index;nav_go(PAGE_JOHTO);}
void play_johto_enter(void){
 bool from_gym=guided&&nav_is_returning()&&view==GYM_INFO;
 bool returning=resume_route||(nav_is_returning()&&route_screen());
 if(!returning){view=HOME;selected=route=path=0;}else if(resume_route){view=ROUTE_HOME;selected=0;}
 resume_route=false;fade=refresh_ms=0;hatch_frames=0;notice=NULL;error=world_johto_visit();refresh();
 if(requested_goal){
  requested_goal=false;guided=requested_action!=N_GO_FREE;
  if(requested_action==N_GO_ROUTE){view=ROUTE_HOME;route=requested_index;selected=0;refresh();if(available_probe<JOHTO_PROBE_COUNT){probe_id=available_probe;probe_help=false;view=FIELD_NOTES;}}
  else if(requested_action==N_GO_GYM){view=GYM_INFO;selected=requested_index;}
  else if(requested_action==N_GO_EGG){view=EGG;selected=0;}
  else {view=HOME;selected=0;}
 }else if(from_gym){guided=false;nav_go(PAGE_NARRATIVE);return;}
 else if(!returning&&!error&&next_scene<N_SCENE_COUNT){nav_go(PAGE_NARRATIVE);return;}
 reset_sprite();
 presentation_clock_start(&probe_clock,(uint32_t)(esp_timer_get_time()/1000));
 screen_set_redraw(draw);timer=lv_timer_create(tick,50,NULL);draw();
}
void play_johto_exit(void){if(timer){lv_timer_delete(timer);timer=NULL;}fade=hatch_frames=0;}
void play_fieldwork_snapshot(play_fieldwork_view_t *out){*out=(play_fieldwork_view_t){view,probe_id,probe_path,selected,error,probe_clock.elapsed_ms,probe_help};}
bool play_johto_screen_busy(void){return fade||hatch_frames;}
void play_johto_key(bsp_btn_t btn,bsp_btn_ev_t ev){
 if(hatch_frames)return;
 fade=0;notice=NULL;
 if(nav_return(btn,ev)){
  if(field_screen()){
   if(view==FIELD_NOTES||view==FIELD_RESULT){if(guided){nav_go(PAGE_NARRATIVE);return;}view=ROUTE_HOME;}
   else view=view==FIELD_PARTNER?FIELD_PATHS:FIELD_NOTES;
   selected=0;error=0;refresh();draw();return;
  }
  if(guided&&(view==ROUTE_HOME||view==GYM_INFO||view==EGG||view==PARTNER)){guided=false;nav_go(PAGE_NARRATIVE);return;}
  if(route_screen()){
   if(view==ROUTE_HOME){view=ROUTES;selected=route;}else {view=ROUTE_HOME;selected=0;}
   error=0;refresh();reset_sprite();draw();return;
  }
  if(view==REWARDS&&rewards_from_route){view=ROUTE_ACTIVITIES;selected=0;error=0;draw();return;}
  if(view==GYM_INFO){view=GYMS;error=0;draw();return;}
  if(view==HOME||chapter.phase<JOHTO_ACTIVE){nav_back(PAGE_MENU);return;}
  view=HOME;selected=0;error=0;reset_sprite();draw();return;
 }
 if(nav_direction(btn,ev)&&view!=GYM_INFO){
  selected=nav_list_selection(btn,ev,count(),selected);error=0;reset_sprite();draw();return;
 }
 if(!nav_confirm(btn,ev))return;
 error=0;
 if(view==FIELD_NOTES){
  if(selected==0){view=FIELD_PATHS;selected=0;}
  else if(selected==1)probe_help=true;
  else {nav_open(PAGE_PARTY);return;}
 }else if(view==FIELD_PATHS){
  const johto_probe_t *p=johto_probe(probe_id);
  if(!p||selected!=p->path)error=WORLD_JOHTO_WRONG_PATH;
  else {probe_path=selected;world_party_snapshot(&probe_party);view=FIELD_PARTNER;selected=0;}
 }else if(view==FIELD_PARTNER){
  if(selected<probe_party.count){probe_actor=probe_party.members[selected];error=world_johto_investigate(probe_id,probe_path,selected,&probe_actor);
   if(!error){view=FIELD_RESULT;selected=0;presentation_clock_start(&probe_clock,(uint32_t)(esp_timer_get_time()/1000));}
   else if(error==WORLD_JOHTO_LOCKED)world_party_snapshot(&probe_party);
  }
 }else if(view==FIELD_RESULT){if(guided){nav_go(PAGE_NARRATIVE);return;}view=ROUTE_HOME;selected=0;}
 else if(chapter.phase==JOHTO_HIDDEN)error=world_johto_visit();
 else if(chapter.phase==JOHTO_INVITED){error=world_johto_depart();selected=0;fade=4;}
 else if(chapter.phase==JOHTO_VOYAGE){error=world_johto_starter(starters[selected]);if(!error){view=PARTNER;fade=4;}}
 else if(view==HOME){rewards_from_route=false;if(!selected){nav_open(PAGE_NARRATIVE);return;}if(selected==6){nav_open(PAGE_ACTIVITY);return;}if(selected==7){nav_open(PAGE_STORY);return;}if(selected==8){nav_back(PAGE_MENU);return;}view=(unsigned[]){ROUTES,GYMS,EGG,LEGENDS,REWARDS}[selected-1];selected=0;}
 else if(view==ROUTES){route=selected;path=selected=0;view=ROUTE_HOME;}
 else if(view==ROUTE_HOME||(view==SEARCH_RESULT&&search.kind==JOHTO_SEARCH_CLUE)){
  if(view==ROUTE_HOME&&available_probe<JOHTO_PROBE_COUNT&&selected<2){if(!selected){probe_id=available_probe;probe_help=false;view=FIELD_NOTES;selected=0;}else{view=PATHS;selected=path;}}
  else if(selected==0){if(guided&&view==SEARCH_RESULT){nav_go(PAGE_NARRATIVE);return;}view=PATHS;selected=path;}else if(selected==1){view=ROUTES;selected=route;}else {view=ROUTE_ACTIVITIES;selected=0;}
 }else if(view==PATHS){
  path=selected;error=world_johto_search(route,path,&search);if(!error){view=SEARCH_RESULT;selected=0;}
 }else if(view==SEARCH_RESULT){
  if(selected==0){encounter_t enc;if(world_get_encounter_uid(search.encounter.uid,&enc)){
   *nav_ctx()=(nav_ctx_t){.enc=enc,.uid=enc.uid,.valid=true,.exploring=true,.johto_exploring=true,.narrative=guided};resume_route=true;nav_go(PAGE_BATTLE);return;
  }notice="伙伴已离开 请继续探索";view=ROUTE_HOME;selected=0;}
  else {if(guided){nav_go(PAGE_NARRATIVE);return;}view=PATHS;selected=path;}
 }else if(view==ROUTE_ACTIVITIES){
  if(selected==0){rewards_from_route=true;view=REWARDS;selected=0;}else {nav_open(selected==1?PAGE_ACTIVITY:PAGE_STORY);return;}
 }else if(view==LEGENDS){error=world_johto_legend(selected,&found);if(!error){play_narrative_legend(selected);return;}}
 else if(view==REWARDS){error=world_johto_reward_claim(selected);}
 else if(view==FOUND){nav_open(PAGE_ENCOUNTER);return;}
 else if(view==GYMS){view=GYM_INFO;}
 else if(view==GYM_INFO){
  world_challenge_result_t r=world_challenge_start(TRAINER_JOHTO_FIRST+selected);
  if(r==WORLD_CHALLENGE_OK){nav_open(PAGE_TRAINER);return;}
  error=r==WORLD_CHALLENGE_NO_STAMINA?WORLD_JOHTO_NO_STAMINA:r==WORLD_CHALLENGE_BUSY?WORLD_JOHTO_BUSY:r==WORLD_CHALLENGE_LOCKED?WORLD_JOHTO_LOCKED:WORLD_JOHTO_SAVE_FAILED;
 }else if(view==EGG){
  if(chapter.egg_status==JOHTO_EGG_READY){hatch_shiny=johto_egg_shiny(&chapter);error=world_johto_egg(true);if(!error)hatch_frames=40;}
  else if(!chapter.egg_status)error=world_johto_egg(false);
  else if(guided){nav_go(PAGE_NARRATIVE);return;}
 }else {if(guided){nav_go(PAGE_NARRATIVE);return;}view=HOME;selected=0;}
 refresh();reset_sprite();draw();
}
