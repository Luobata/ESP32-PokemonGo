#!/usr/bin/env python3
"""Compare beam rendering with original OAM composed before portrait projection.

This catches inter-object seams: a four-object beam must behave as one image.
Source timing, palette, flips and object lifetime remain in the generated data.
"""
import verify_trainer_campaign as h
h.CASES=r'''
#include "battle_fx.c"
#include "gold_fx.c"
static unsigned band;
static uint16_t raster[240*320],source[256*256];
uint16_t *screen_band(void){return raster+band*240;}
void screen_px(int x,int y,uint16_t color){
 assert(x>=0&&x<240&&y>=0&&y<80);
 raster[(y+band)*240+x]=__builtin_bswap16(color);
}
int main(void){
 unsigned cases=0,frames=0;unsigned moves[]={62,63,76};
 for(unsigned m=0;m<3;m++)for(unsigned side=0;side<2;side++)for(unsigned param=0;param<2;param++){
  battle_round_t r={.move_id=moves[m],.by_pet=!side,.charging=param};
  if(moves[m]==76&&param){assert(!joined_beam(&r));continue;}
  const gold_span_t *clip=clip_for(&r);assert(clip&&joined_beam(&r));cases++;
  for(unsigned frame=0;frame<clip->count;frame++){
   const gold_frame_t *f=&gold_frames[gold_clip_frames[clip->offset+frame]];
   const uint16_t shades[]={0xffff,0xce59,0x6b4d,0};uint16_t bg=shades[f->bgp&3];
   for(unsigned i=0;i<256*256;i++)source[i]=bg;
   // Compose all original tiles in their original coordinate space first.
   const gold_span_t *span=&gold_object_spans[f->objects];
   for(int j=span->count-1;j>=0;j--){
    const gold_object_t *o=&gold_objects[span->offset+j];assert(o->tile<0x8000);
    for(unsigned y=0;y<8;y++)for(unsigned x=0;x<8;x++){
     unsigned index=raw_index(o->tile,o->flags&32?7-x:x,o->flags&64?7-y:y);
     int sx=o->x-8+(int)x,sy=o->y-16+(int)y;
     if(index&&sx>=0&&sx<256&&sy>=0&&sy<256)source[sy*256+sx]=rgb555(&gold_palettes[f->palette][(o->flags&7)*8+index*2]);
    }
   }
   for(unsigned i=0;i<240*320;i++)raster[i]=0xffff;
   for(band=0;band<240;band+=80)gold_fx_draw(&r,frame,band,0,0);
   // Independently inverse-sample the completed original image. A segment
   // cannot acquire a separate offset/scale at its join with the next one.
   for(int y=0;y<240;y++)for(int x=0;x<240;x++){
    int sx=-128,sy=-128;while(map_x(sx+1)<=x)sx++;while(map_y(sy+1)<=y)sy++;
    uint16_t expected=sx>=0&&sx<256&&sy>=0&&sy<256?source[sy*256+sx]:bg;
    assert(raster[y*240+x]==__builtin_bswap16(expected));
   }
   for(unsigned i=240*240;i<240*320;i++)assert(raster[i]==0xffff);
   frames++;
  }
 }
 printf("{\"beam_moves\":3,\"cases\":%u,\"frames\":%u,\"original_composite_projection\":true,\"solar_charge_unchanged\":true}\n",cases,frames);
}
'''
h.run()
