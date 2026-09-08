"""Compile the actual P3 result-rendering branch and exhaust uint16_t EXP.

Runs from the repository root. Includes production headers and measurement code.
The original Git branch is a negative control for the minimum text-gap invariant.
"""
from pathlib import Path
import json
import re
import subprocess
import tempfile

root=Path.cwd()
current=(root/'firmware/main/play_battle.c').read_text()
original=subprocess.check_output(['git','show','HEAD:firmware/main/play_battle.c'],text=True)

def source(page):
    marker='    } else if (s_done) {'
    begin=page.index(marker)+len(marker)
    depth=1
    for token in re.finditer(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|[{}]',page[begin:]):
        if token.group()=='{': depth+=1
        elif token.group()=='}': depth-=1
        if not depth:
            end=begin+token.start()
            break
    else: raise AssertionError('unterminated result branch')
    body=page[begin:end]
    macros='\n'.join(re.findall(r'^#define MSG_[A-Z_]+ .*$',page,re.M))
    return '''#include <stdio.h>
#include <string.h>
#include <assert.h>
#include "battle.h"
#include "render.h"
#include "screen.h"
#define SCR_W SCREEN_W
#define Y(v) (v)
MACROS
#ifndef MSG_X
#define MSG_X 8
#endif
#ifndef MSG_RIGHT
#define MSG_RIGHT (SCREEN_W - 8)
#endif
static struct {int x,y,w;} drawn[4];
static int count;
int render_text_width(const char *s){return render_text_width_sized(s,16);}
int render_text(int x,int y,const char*s,uint16_t c){
 (void)c;int w=render_text_width(s);assert(count<4);drawn[count].x=x;drawn[count].y=y;drawn[count++].w=w;return x+w;
}
int main(void){
 battle_result_t s_res={0};char buf[64];int min_gap=240;
 for(unsigned e=0;e<=65535;e++){
  count=0;s_res.exp=(uint16_t)e;s_res.won=true;
BODY
  assert(count==3);
  for(int i=0;i<count;i++){
   assert(drawn[i].x>=MSG_X&&drawn[i].x+drawn[i].w<=MSG_RIGHT);
   assert(SCREEN_ELEMENT_FITS_BAND(drawn[i].y,16));
  }
  int gap=drawn[2].x-drawn[1].x-drawn[1].w;
  if(gap<min_gap)min_gap=gap;
 }
 printf("{\\"expValues\\":65536,\\"minGap\\":%d}\\n",min_gap);
 return min_gap>=8?0:2;
}
'''.replace('MACROS',macros).replace('BODY',body)

results={}
with tempfile.TemporaryDirectory(prefix='pokemon-result-layout-') as d:
    out=Path(d)
    for tag,page in [('current',current),('original',original)]:
        path=out/(tag+'.c');path.write_text(source(page))
        exe=out/tag
        subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                        '-I',str(root/'firmware/main'),str(path),'-o',str(exe)],check=True)
        run=subprocess.run([str(exe)],capture_output=True,text=True)
        results[tag]=json.loads(run.stdout)
        results[tag]['exitCode']=run.returncode
        assert run.returncode==(0 if tag=='current' else 2),run.stderr
assert results['current']['minGap']==32
assert results['original']['minGap']==0
print(json.dumps(results,indent=2))
