#!/usr/bin/env python3
"""Render actual combat outcomes for all 191 supported moves, both sides and varied actor sizes."""
import verify_trainer_campaign as h
h.CASES=r'''
#include "battle_fx.c"
static unsigned band,pixels,frames_checked;
static bool track_self;
static int center_x,center_y;
static uint16_t raster[240*320];
void screen_px(int x,int y,uint16_t color){
 assert(x>=0&&x<240&&y>=0&&y<80);int py=y+band;
 assert(py>=30&&py<236);assert(py<160||x<104);assert(!(x<120&&py<116));
 if(track_self){assert(x>=center_x-40&&x<=center_x+40);assert(py>=center_y-52&&py<=center_y+40);}
 raster[py*240+x]=color;pixels++;
}
typedef struct {int x,y,w,h;} scene_ink_bounds_t;
static bool scene_2bpp_bounds(const uint8_t *data,int w,int h,scene_ink_bounds_t *out){
 int left=w,top=h,right=0,bottom=0;
 for(int y=0;y<h;y++)for(int x=0;x<w;x++)if(((data[y*((w+3)/4)+x/4]>>(6-2*(x%4)))&3)!=3){if(x<left)left=x;if(y<top)top=y;if(x+1>right)right=x+1;if(y+1>bottom)bottom=y+1;}
 *out=(scene_ink_bounds_t){left,top,right-left,bottom-top};return right>left;
}
static void fx_all(void){
 unsigned ids_with_pixels=0;bool covered[251]={0};
 for(unsigned fixture=0;fixture<4;fixture++){
  unsigned pet_id=(unsigned[]){25,1,129,143}[fixture],enemy_id=(unsigned[]){74,95,149,132}[fixture];
  sprite_asset_t back;assert(assets_back_sprite_info(pet_id,&back));
  scene_ink_bounds_t ink;assert(scene_2bpp_bounds(back.data,back.w,back.h,&ink));
  int scale=96/back.w;battle_fx_rect_t pet={8+ink.x*scale,140+ink.y*scale,ink.w*scale,ink.h*scale};
  uint8_t sz;const uint8_t *front=assets_front_sprite(enemy_id,&sz);assert(scene_2bpp_bounds(front,sz,sz,&ink));
  battle_fx_rect_t wild={180-ink.w,80-ink.h,ink.w*2,ink.h*2};
  for(unsigned side=0;side<2;side++)for(unsigned id=1;id<=250;id++){
   move_t supported;if(!combat_move(id,&supported))continue;
   combat_mon_t a,d;combat_init(&a,side?enemy_id:pet_id,60,500);combat_init(&d,side?pet_id:enemy_id,50,500);a.hp=200;uint32_t rng=fixture>=2?2:123;
   // Also cover a valid physical counter; earlier fixtures cover its failure.
   if(id==68&&fixture>=2){a.last_damage=35;d.last_move=33;}
   battle_round_t r={.by_pet=!side};combat_turn(&a,&d,1024,&rng,50,id,&r);battle_round_t before=r;
   battle_fx_rect_t actor=side?wild:pet;center_x=actor.x+actor.w/2;center_y=actor.y+actor.h/2;
   track_self=r.self_target||r.charging||r.skipped;
   for(unsigned f=0;f<battle_fx_frames(&r);f++){
    pixels=0;for(unsigned i=0;i<240*320;i++)raster[i]=0xffff;
    for(band=0;band<320;band+=80)battle_fx_draw_band(&r,f,band,pet,wild);
    battle_fx_pose_t pose=battle_fx_pose_for_rects(&r,f,pet,wild);
    assert(pet.x+pose.pet_dx>=0&&pet.x+pet.w+pose.pet_dx<=120);
    assert(wild.x+pose.wild_dx>=120&&wild.x+wild.w+pose.wild_dx<=240);
    if(f>=battle_fx_frames(&r)-2u)assert(!pixels&&!pose.pet_dx&&!pose.wild_dx);
    if(pixels)covered[id]=true;frames_checked++;
    assert(!memcmp(&before,&r,sizeof(r)));
   }
  }
 }
 for(unsigned id=1;id<=250;id++){move_t supported;if(!combat_move(id,&supported))continue;if(covered[id])ids_with_pixels++;else{move_t m;combat_move(id,&m);assert(m.power>0);}}
 assert(ids_with_pixels==191);
 printf("{\"moves\":191,\"moves_with_effect_pixels\":%u,\"frames\":%u,\"self_targets_correct\":true,\"hud_protected\":true,\"clean_recovery\":true}\n",ids_with_pixels,frames_checked);
}
static void readability(void){
 track_self=false;
 unsigned minimum=1000,peak_min=100000;
 for(unsigned side=0;side<2;side++)for(unsigned i=0;i<8;i++){
  unsigned id=(unsigned[]){1,33,84,85,10,40,44,93}[i];move_t m;assert(combat_move(id,&m));
  battle_round_t r={.move_id=id,.move_type=m.type,.by_pet=!side,.damage=20};unsigned visible_frames=0,peak=0;
  for(unsigned f=0;f<battle_fx_frames(&r);f++){
   for(unsigned p=0;p<240*320;p++)raster[p]=0xffff;
   for(band=0;band<240;band+=80)battle_fx_draw_band(&r,f,band,(battle_fx_rect_t){8,140,96,96},(battle_fx_rect_t){148,40,64,64});
   unsigned contrast=0;for(unsigned p=0;p<240*320;p++)contrast+=raster[p]!=0xffff;
   if(contrast>=100)visible_frames++;if(contrast>peak)peak=contrast;
  }
  assert(visible_frames>=5);assert(peak>=100);
  if(visible_frames<minimum)minimum=visible_frames;if(peak<peak_min)peak_min=peak;
 }
 printf("{\"readability_moves\":8,\"both_sides\":true,\"min_visible_ms\":%u,\"min_peak_contrast_pixels\":%u}\n",minimum*BATTLE_FX_TICK_MS,peak_min);
}
int main(void){assert(assets_init());fx_all();readability();}
'''
h.run()
