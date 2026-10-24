#!/usr/bin/env python3
"""Compare byte-wise ink bounds with an independent per-pixel oracle."""
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include <assert.h>
#include <stdlib.h>
#include "render.c"
const uint8_t test_font_start[14] asm("_binary_font16_bin_start") = {0};
const uint8_t test_font_end[1] asm("_binary_font16_bin_end") = {0};
void screen_px(int x, int y, uint16_t c) {(void)x; (void)y; (void)c;}
static uint32_t rng = 0x723718;
static uint8_t random_byte(void) {rng = rng * 1664525u + 1013904223u; return rng >> 24;}
static void point(render_bounds_t *b, bool *found, int x, int y) {
 if (!*found) {*b=(render_bounds_t){x,y,1,1}; *found=true; return;}
 int right=b->x+b->w, bottom=b->y+b->h;
 if(x<b->x)b->x=x;if(y<b->y)b->y=y;
 if(x+1>right)right=x+1;if(y+1>bottom)bottom=y+1;
 b->w=right-b->x;b->h=bottom-b->y;
}
static void equal(bool a, bool b, render_bounds_t x, render_bounds_t y) {
 assert(a==b);assert(x.x==y.x&&x.y==y.y&&x.w==y.w&&x.h==y.h);
}
int main(void) {
 unsigned checks=0;uint8_t data[1024];
 for(int w=1;w<=64;w++)for(int h=1;h<=64;h++)for(int mode=0;mode<4;mode++){
  int stride=(w+3)/4;
  for(int i=0;i<stride*h;i++)data[i]=mode==0?255:mode==1?0:random_byte();
  if(mode==3){memset(data,255,stride*h);int x=w-1,y=h-1;data[y*stride+x/4]&=~(3u<<(6-2*(x%4)));}
  render_bounds_t want={0},got={0};bool found=false;
  for(int y=0;y<h;y++)for(int x=0;x<w;x++)
   if(((data[y*stride+x/4]>>(6-2*(x%4)))&3)!=3)point(&want,&found,x,y);
  equal(found,render_sprite_ink_bounds(data,w,h,&got),want,got);checks++;
 }
 uint16_t codes[]={65,66};uint8_t glyphs[256];
 for(unsigned size=1;size<=32;size++)for(unsigned trial=0;trial<50;trial++){
  unsigned row=(size+7)/8,per=row*size;
  for(unsigned i=0;i<2*per;i++)glyphs[i]=trial==0?0:random_byte();
  s_font.codes=codes;s_font.glyphs=glyphs;s_font.size=size;s_font.per=per;s_font.count=2;s_font.ok=true;
  const char *text="ABBA";render_bounds_t want={0},got={0};bool found=false;int pen=0;
  for(unsigned c=0;c<4;c++){
   const uint8_t *g=glyphs+(text[c]-'A')*per;
   for(unsigned y=0;y<size;y++)for(unsigned x=0;x<size;x++)
    if(g[y*row+x/8]&(0x80>>(x%8)))point(&want,&found,pen-(int)(size/4)+x,y);
   pen+=render_char_advance(text[c]);
  }
  equal(found,render_text_ink_bounds(text,&got),want,got);checks++;
 }
 printf("{\"passed\":true,\"oracle_checks\":%u,\"sanitizers\":\"ASan/UBSan fatal\"}\n",checks);
}
'''

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)
    (tmp / 'test.c').write_text(DRIVER)
    subprocess.run(['cc', '-std=gnu11', '-O1', '-g', '-fsanitize=address,undefined',
                    '-fno-sanitize-recover=all', '-I', str(ROOT / 'firmware/main'),
                    '-I', str(ROOT / 'tools/inspector/host/include'),
                    str(tmp / 'test.c'), '-o', str(tmp / 'test')], check=True)
    result = subprocess.check_output([str(tmp / 'test')], text=True)
    print(json.dumps(json.loads(result)))
