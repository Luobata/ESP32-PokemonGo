#!/usr/bin/env python3
"""English catalogue coverage, real lookup/printf, names and glyph boundaries."""
import json,re,subprocess,tempfile,textwrap
from pathlib import Path
from generate_english import ROOT, DATA, MAIN, generate

TOKEN=re.compile(r"'[^'\\]*(?:\\.[^'\\]*)*'|\"((?:[^\"\\]|\\.)*)\"|/\*.*?\*/|//[^\n]*",re.S)
DRIVER=r'''
#include "language.h"
#include "pokemon_names.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include <stdint.h>
static char line[16384],source[8192],expected[8192];
static void decode(const char *s,char *o){while(*s&&*s!='\t'&&*s!='\n'){unsigned c;assert(sscanf(s,"%2x",&c)==1);*o++=c;s+=2;}*o=0;}
static void formats(void){
 char got[128],want[128];
 const char raw[6]={0xe9,0x81,0x93,0xe5,0x85,0xb7};
 assert(language_snprintf(got,sizeof(got),"%.*s",6,raw)==5&&!strcmp(got,"Items"));
 for(unsigned cap=0;cap<=sizeof(got);cap++){
  memset(got,0x5a,sizeof(got));memset(want,0x5a,sizeof(want));
  int a=language_snprintf(got,cap,"Lv%03u %+d %lu:%02lu %s %.*s",100u,-123,456ul,7ul,"队伍",6,"道具xxx");
  int b=snprintf(want,cap,"Lv%03u %+d %lu:%02lu %s %s",100u,-123,456ul,7ul,"Party","Items");
  assert(a==b&&!memcmp(got,want,sizeof(got)));
 }
 assert(language_snprintf(got,sizeof(got),"经验 +%u",123u)==8&&!strcmp(got,"EXP +123"));
 assert(language_snprintf(got,sizeof(got),"%s","捕获窗口增至一点五倍")>0&&!strcmp(got,"Catch window x1.5"));
 assert(language_snprintf(NULL,0,"体能%u",100u)==10);
 assert(language_snprintf(got,sizeof(got),"%.*s",-1,"闪光")==5&&!strcmp(got,"Shiny"));
 assert(language_snprintf(got,sizeof(got),"%.3s %c %04x","abcdef",'C',15u)==10&&!strcmp(got,"abc C 000f"));
 assert(language_snprintf(got,sizeof(got),"[%8s][%-8s][%3c]","队伍","x",'C')==25&&!strcmp(got,"[   Party][x       ][  C]"));
 assert(language_snprintf(got,sizeof(got),"%.*u",4,7u)==4&&!strcmp(got,"0007"));
 // Exercise runtime rejection without GCC's printf attribute rejecting the
 // deliberately invalid width at compile time.
 int (*runtime_format)(char*,size_t,const char*,...)=language_snprintf;
 assert(runtime_format(got,sizeof(got),"%999999999999u",7u)==-1);
 assert(language_snprintf(got,sizeof(got),"%*u",4,7u)==-1);
 language_set_runtime(LANGUAGE_ZH_HANS);
 assert(language_snprintf(got,sizeof(got),"经验 +%u",123u)==(int)strlen("经验 +123")&&!strcmp(got,"经验 +123"));
 language_set_runtime(LANGUAGE_EN);
}
int main(void){
 assert(language_set_runtime(LANGUAGE_EN));formats();unsigned count=0;
 while(fgets(line,sizeof(line),stdin)){
  char *tab=strchr(line,'\t');assert(tab);decode(line,source);decode(tab+1,expected);
  const char *translated=language_text(source);assert(!strcmp(translated,expected));
  assert(!strcmp(language_text_n(source,strlen(source)),expected));count++;
 }
 const char *unknown="未定义界面消息";assert(language_text(unknown)==unknown);assert(!language_text(NULL));
 assert(pokemon_names_set_style(POKEMON_NAMES_GS_LEGACY));
 for(unsigned id=1;id<=251;id++){
  uint8_t n;const char *p=pokemon_names_override(id,&n);assert(p&&n==strlen(p)&&n<=16);
  for(const char *s=p;*s;s++)assert((unsigned char)*s<128);
  p=pokemon_move_names_override(id,&n);assert(p&&n==strlen(p)&&n<=16);
 }
 uint8_t n;assert(!strcmp(pokemon_names_override(149,&n),"Dragonite"));
 assert(!strcmp(pokemon_move_names_override(57,&n),"Surf"));
 language_set_runtime(LANGUAGE_ZH_HANS);assert(!strcmp(pokemon_names_override(149,&n),"肥大"));
 language_set_runtime(LANGUAGE_EN);
 for(unsigned c=32;c<127;c++){
  const uint8_t *g=language_glyph(c);assert(g);
  for(unsigned y=0;y<16;y++){unsigned bits=(g[y*2]<<8)|g[y*2+1];assert(!(bits&0xf00f));}
 }
 printf("{\"passed\":true,\"catalogue\":%u,\"species\":251,\"moves\":251,\"printf_sizes\":129,\"ascii_glyphs\":95}\n",count);
}
'''

def main():
    assert (MAIN/'language_english.h').read_text()==generate()
    catalog=json.loads((DATA/'en.json').read_text())
    files=json.loads((DATA/'english_sources.json').read_text())
    missing=[]
    for file in files:
        for match in TOKEN.finditer((MAIN/file).read_text()):
            text=match.group(1)
            if text and re.search('[\u3400-\u9fff]',text) and text not in catalog:missing.append((file,text))
    assert not missing, ('Untranslated display messages',missing)
    # Each complete three-part story page must fit its five English rows.
    for match in re.finditer(r'\b(?:P|S|MON)\([^\n]+\)', (MAIN/'narrative_script.c').read_text()):
        parts=re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"',match.group())
        if len(parts)>=4:
            text=' '.join(catalog[x] for x in parts[-3:] if x)
            assert len(textwrap.wrap(text,26))<=5,('Story page clipped',parts[-3:])
    probes=(MAIN/'johto_routes.c').read_text().split('static const johto_probe_t PROBES')[1].split('const johto_probe_t *johto_probe(')[0]
    for row in probes.splitlines():
        parts=re.findall(r'"([^"\n]+)"',row)
        if len(parts)==8:
            for group,limit,width in ((parts[1:3],3,27),(parts[3:5],4,26),(parts[5:8],5,26)):
                assert len(textwrap.wrap(' '.join(catalog[x] for x in group),width))<=limit,('Fieldwork clipped',group)
    with tempfile.TemporaryDirectory(prefix='pokewalk-english-') as tmp:
        p=Path(tmp);(p/'test.c').write_text(DRIVER)
        command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(MAIN),str(p/'test.c')]
        command += [str(MAIN/f) for f in ('language.c','language_format.c','pokemon_names.c')]+['-o',str(p/'test')]
        subprocess.run(command,check=True)
        payload=''.join(f'{a.encode().hex()}\t{b.encode().hex()}\n' for a,b in catalog.items())
        result=subprocess.run([str(p/'test')],input=payload,text=True,capture_output=True)
        assert result.returncode==0,result.stdout+result.stderr
        print(result.stdout.strip())

if __name__=='__main__':main()
