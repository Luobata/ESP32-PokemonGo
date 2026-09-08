"""Compare compiled C HUD pixels with original PNG tiles at a pinned commit.

Run from repo root; --source may select a local pret/pokecrystal checkout.
Only the probe uses that checkout. The production C includes all its tile bytes.
"""
import argparse
import ctypes as C
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from PIL import Image

parser = argparse.ArgumentParser()
parser.add_argument('--source', type=Path, default=Path('/tmp/pokecrystal'))
args = parser.parse_args()
root = Path(__file__).resolve().parents[3]
upstream = args.source
commit = '7a7881d0d62e0ddbd82dcf10e7116807487ac651'
assert subprocess.check_output(['git', '-C', str(upstream), 'rev-parse', 'HEAD'], text=True).strip() == commit
sources = {
    'font/font_battle_extra.png': '23b8791b24648789e284d69d2e7f6c14e6b98c08cb56a783f67e1eca0ca6b6a1',
    'battle/enemy_hp_bar_border.png': '218cce2af1967ad07fc6083895476baa4e7f30d9f3980ce87e1d36ff3abfbcdc',
    'frames/1.png': '34cb93e39aacdc78c43c2f1af85939b8d19be4fc648d7c315f1de2ac11f05973',
    'battle/expbar.png': '61303808ff6b2e7168807489cbb3ddfd9ecb2e0798f5ee01a00058e3321ca355',
}
png = {}
for name, digest in sources.items():
    path = upstream / 'gfx' / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    png[name] = Image.open(path).convert('L').point(lambda v: (255-v)//85)

def tile(name, i):
    im = png[name]
    x, y = i % (im.width//8) * 8, i // (im.width//8) * 8
    return im.crop((x, y, x+8, y+8))

RECT = C.CFUNCTYPE(None, C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_int, C.c_uint16)
BG = 0xFFFF

def image565(values, size):
    im = Image.new('RGB', size)
    im.putdata([(((v>>11)<<3)|(v>>13),
                 (((v>>5)&63)<<2)|((v>>9)&3),
                 ((v&31)<<3)|((v&31)>>2)) for v in values])
    return im

with tempfile.TemporaryDirectory(prefix='battle-hud-probe-') as tmp:
    libpath = Path(tmp) / 'hud.dylib'
    subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', '-dynamiclib',
                    str(root/'firmware/main/battle_hud.c'), '-o', str(libpath)], check=True)
    lib = C.CDLL(str(libpath))
    lib.battle_hud_draw_hp.argtypes = [RECT, C.c_void_p, C.c_int, C.c_int, C.c_uint8,
        C.c_uint8, C.c_int, C.c_uint16, C.c_uint16, C.c_uint16]
    lib.battle_hud_draw_hp.restype = C.c_bool
    lib.battle_hud_draw_message_box.argtypes = [RECT, C.c_void_p, C.c_int, C.c_int,
        C.c_uint8, C.c_uint8, C.c_uint8, C.c_uint16]
    lib.battle_hud_draw_message_box.restype = C.c_bool
    lib.battle_hud_draw_exp.argtypes = [RECT, C.c_void_p, C.c_int, C.c_int,
        C.c_uint8, C.c_uint8, C.c_uint32, C.c_uint32, C.c_uint16]
    lib.battle_hud_draw_exp.restype = C.c_bool
    lib.battle_hud_hp_color.argtypes = [C.c_uint16, C.c_uint16]
    lib.battle_hud_hp_color.restype = C.c_uint16

    def draw(w, h, fn):
        pixels = [0xDEAD] * (w*h)
        invalid = []
        def rect(_ctx, x, y, rw, rh, color):
            if not (0 <= x < x+rw <= w and 0 <= y < y+rh <= h):
                invalid.append((x,y,rw,rh))
                return
            for py in range(y,y+rh): pixels[py*w+x:py*w+x+rw] = [color]*rw
        assert fn(RECT(rect))
        assert not invalid, invalid
        assert 0xDEAD not in pixels
        return pixels

    count = 0
    for cur in range(65536):
        e = 48*cur//65535
        assert lib.battle_hud_hp_color(cur,65535) == (0x05E0 if e>=24 else 0xFD60 if e>=10 else 0xF800)
    for d in [1,4,6,16]:
        for scale in [1,2,3,4]:
            for side in [0,1]:
                for cur,maxhp in [(0,100),(1,65535),(9,48),(10,48),(23,48),(24,48),
                                  (20,100),(21,100),(49,100),(50,100),(100,100),(200,100),(1,0)]:
                    w,h = (d+3)*8*scale,8*scale
                    actual = draw(w,h,lambda rect: lib.battle_hud_draw_hp(rect,None,0,0,d,scale,side,cur,maxhp,BG))
                    n = min(d*8,d*8*cur//maxhp) if maxhp else 0
                    if cur and maxhp: n=max(1,n)
                    indices = [0,1] + [2+min(8,max(0,n-i*8)) for i in range(d)]
                    expected = Image.new('L',((d+3)*8,8),0)
                    for i, ti in enumerate(indices): expected.paste(tile('font/font_battle_extra.png',ti),(i*8,0))
                    cap = tile('battle/enemy_hp_bar_border.png',0) if side else tile('font/font_battle_extra.png',11)
                    expected.paste(cap,((d+2)*8,0))
                    expected = expected.resize((w,h),Image.Resampling.NEAREST)
                    e = min(48,48*cur//maxhp) if maxhp else 0
                    palette = [BG,0xF6AF,0x05E0 if e>=24 else 0xFD60 if e>=10 else 0xF800,0]
                    assert actual == [palette[v] for v in expected.get_flattened_data()], (d,scale,side,cur,maxhp)
                    count += 1

    exp_count = 0
    for d in [1,7,8,16]:
        for scale in [1,2,3,4]:
            for cur,maxexp in [(n,64) for n in range(65)] + [(1,0),(2**32-1,2**32-1),(2**32-2,2**32-1)]:
                w,h = d*8*scale,8*scale
                actual = draw(w,h,lambda rect: lib.battle_hud_draw_exp(rect,None,0,0,d,scale,cur,maxexp,BG))
                filled = min(d*8,d*8*cur//maxexp) if maxexp else 0
                expected = Image.new('L',(d*8,8),0)
                for col in range(d):
                    n = min(8,max(0,filled-(d-1-col)*8))
                    pattern = tile('font/font_battle_extra.png',10 if n==8 else 2) if n in [0,8] else tile('battle/expbar.png',n-1)
                    expected.paste(pattern,(col*8,0))
                expected=expected.resize((w,h),Image.Resampling.NEAREST)
                assert actual==[[BG,0xF6AF,0x247F,0][v] for v in expected.get_flattened_data()],(d,scale,cur,maxexp)
                exp_count+=1

    box_count = 0
    for cols,rows in [(3,3),(15,5)]:
        for scale in [1,2,3,4]:
            w,h = cols*8*scale,rows*8*scale
            actual = draw(w,h,lambda rect: lib.battle_hud_draw_message_box(rect,None,0,0,cols,rows,scale,BG))
            expected = Image.new('L',(cols*8,rows*8),0)
            for row in range(rows):
                for col in range(cols):
                    if row==0: t=0 if col==0 else 2 if col==cols-1 else 1
                    elif row==rows-1: t=4 if col==0 else 5 if col==cols-1 else 1
                    elif col==0 or col==cols-1: t=3
                    else: continue
                    expected.paste(tile('frames/1.png',t),(col*8,row*8))
            expected = expected.resize((w,h),Image.Resampling.NEAREST)
            assert actual == [0 if v else BG for v in expected.get_flattened_data()]
            box_count += 1
            if (cols,rows,scale)==(15,5,2):
                for y in [16,34,52]:
                    assert all(actual[py*w+px]==BG for py in range(y,y+16) for px in range(12,228))
                # Negative control: the initially suggested y248/x8 would hit the frame.
                assert any(actual[py*w+px]==0 for py in range(8,24) for px in range(8,232))

    # Identical scene composed at once or through four independently clipped
    # 80px bands, including an intentionally cross-band HP at y73.
    def band_scene(rect):
        assert lib.battle_hud_draw_hp(rect,None,8,73,4,2,0,24,48,BG)
        assert lib.battle_hud_draw_hp(rect,None,120,192,4,2,1,10,48,BG)
        assert lib.battle_hud_draw_exp(rect,None,120,224,7,2,17,64,BG)
        assert lib.battle_hud_draw_message_box(rect,None,0,240,15,5,2,BG)
    def compose(bands):
        pixels=[BG]*(240*320)
        for top,bottom in bands:
            def rect(_ctx,x,y,w,h,color):
                for py in range(max(y,top),min(y+h,bottom)):
                    pixels[py*240+x:py*240+x+w]=[color]*w
            band_scene(RECT(rect))
        return pixels
    assert compose([(0,320)])==compose([(0,80),(80,160),(160,240),(240,320)])

    sheet = Image.new('RGB',(240,320),(255,255,255))
    for row,cur in enumerate([100,50,21,20,1,0]):
        for side,x in [(0,8),(1,120)]:
            pixels=draw(112,16,lambda rect: lib.battle_hud_draw_hp(rect,None,0,0,4,2,side,cur,100,BG))
            sheet.paste(image565(pixels,(112,16)),(x,8+row*32))
    for x,cur in [(8,17),(120,48)]:
        pixels=draw(112,16,lambda rect: lib.battle_hud_draw_exp(rect,None,0,0,7,2,cur,64,BG))
        sheet.paste(image565(pixels,(112,16)),(x,204))
    pixels=draw(240,80,lambda rect: lib.battle_hud_draw_message_box(rect,None,0,0,15,5,2,BG))
    sheet.paste(image565(pixels,(240,80)),(0,240))
    output=Path(__file__).with_name('battle-hud-gsc-tiles.png')
    sheet.save(output)

    # Exercise the production decoder under memory/undefined-behavior sanitizers.
    safety = Path(tmp)/'safety.c'
    safety.write_text('''#include "battle_hud.h"
#include <assert.h>
#include <stddef.h>
static void rect(void*c,int x,int y,int w,int h,uint16_t color){
 (void)c;(void)color;assert(x>=0&&y>=0&&w>0&&h>0&&x+w<=1024&&y+h<=1024);
}
int main(void){
 assert(!battle_hud_draw_hp(NULL,NULL,0,0,4,2,BATTLE_HUD_PET,1,2,0));
 for(unsigned d=0;d<18;d++)for(unsigned s=0;s<6;s++)for(unsigned side=0;side<3;side++){
  bool expected=d>=1&&d<=16&&s>=1&&s<=4&&side<2;
  assert(battle_hud_draw_hp(rect,NULL,0,0,d,s,side,65535,1,0)==expected);
  assert(battle_hud_draw_hp(rect,NULL,0,0,d,s,side,1,65535,0)==expected);
  assert(battle_hud_draw_hp(rect,NULL,0,0,d,s,side,0,0,0)==expected);
  if(side==0){
   assert(battle_hud_draw_exp(rect,NULL,0,0,d,s,UINT32_MAX-1,UINT32_MAX,0)==expected);
   assert(battle_hud_draw_exp(rect,NULL,0,0,d,s,1,0,0)==expected);
  }
 }
 for(unsigned s=0;s<6;s++)assert(battle_hud_draw_message_box(rect,NULL,0,0,15,5,s,0)==(s>=1&&s<=4));
 assert(!battle_hud_draw_message_box(rect,NULL,0,0,2,5,2,0));
 return 0;
}''')
    executable = Path(tmp)/'safety'
    subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
        '-I',str(root/'firmware/main'),str(root/'firmware/main/battle_hud.c'),str(safety),'-o',str(executable)],check=True)
    subprocess.run([str(executable)],check=True)
    print(json.dumps({'commit':commit,'hpPixelComparisons':count,'expPixelComparisons':exp_count,'messageBoxPixelComparisons':box_count,
        'paletteCases':65536,'sanitizers':'passed','messageTextBoxes':'clear','negativeTextBoxControl':'detected',
        'fourBandComposition':'identical',
        'image':str(output)},indent=2))
