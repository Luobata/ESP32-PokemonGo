#!/usr/bin/env python3
"""Bounds, source-track coverage, immutable outcomes and cleanup for all moves."""
import verify_trainer_campaign as h
h.CASES=r'''
#include "battle_fx.c"
#include "gold_fx.c"
static unsigned band,pixels;
static uint16_t raster[240*320];
uint16_t *screen_band(void){return raster+band*240;}
void screen_px(int x,int y,uint16_t color){
 assert(x>=0&&x<240&&y>=0&&y<80&&y+band<240);
 raster[(y+band)*240+x]=__builtin_bswap16(color);pixels++;
}
int main(void){
 assert(assets_init());unsigned moves=0,frames=0;
 for(unsigned fixture=0;fixture<2;fixture++){
  unsigned pet_id=fixture?129:25,enemy_id=fixture?95:143;
  sprite_asset_t back;assert(assets_back_sprite_info(pet_id,&back));
  uint8_t sz;const uint8_t *front=assets_front_sprite(enemy_id,&sz);assert(front);
  species_t sp;battle_fx_actor_t pet={.data=back.data,.w=back.w,.h=back.h},wild={.data=front,.w=sz,.h=sz};
  assert(assets_species(pet_id,&sp));assets_palette_variant(sp.palette,false,pet.palette);
  assert(assets_species(enemy_id,&sp));assets_palette_variant(sp.palette,false,wild.palette);
  for(unsigned id=1;id<=250;id++){
   move_t m;if(!combat_move(id,&m))continue;
   if(!fixture)moves++;
   for(unsigned side=0;side<2;side++)for(unsigned charge=0;charge<2;charge++){
    battle_round_t r={.move_id=id,.move_type=m.type,.by_pet=!side,.damage=m.power?40:0,.charging=charge};
    assert(gold_fx_enabled(&r));battle_round_t before=r;
    unsigned count=battle_fx_frames(&r);assert(count>=2&&count<=255);
    for(unsigned f=0;f<count;f++){
     for(unsigned k=0;k<240*320;k++)raster[k]=0xffff;pixels=0;
     for(band=0;band<320;band+=80)battle_fx_draw_scene_band(&r,f,band,(battle_fx_rect_t){8,140,96,96},(battle_fx_rect_t){124,24,112,112},&pet,&wild);
     if(f>=count-2)assert(!pixels);
     assert(!memcmp(&r,&before,sizeof(r)));frames++;
    }
    if(r.damage&&!r.charging){unsigned hidden=0;for(unsigned f=0;f<count;f++){assert(battle_fx_actor_visible(&r,f,r.by_pet));hidden+=!battle_fx_actor_visible(&r,f,!r.by_pet);}assert(hidden==6);}
    r.missed=true;for(unsigned f=0;f<battle_fx_frames(&r);f++)assert(battle_fx_actor_visible(&r,f,!r.by_pet));
   }
  }
 }
 assert(moves==191);
 printf("{\"moves\":%u,\"source_tracks_both_sides\":true,\"frames\":%u,\"clean_recovery\":true,\"message_window_protected\":true,\"immutable_outcomes\":true}\n",moves,frames);
}
'''
h.run()
