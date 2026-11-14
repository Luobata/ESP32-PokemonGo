#!/usr/bin/env python3
"""Actual Japanese lookup/names/UTF-8 bounds plus complete story layout budgets."""
import json,re,subprocess,tempfile
from pathlib import Path
from generate_japanese import ROOT,DATA,MAIN,generate,glyph_codes
from verify_english import TOKEN

def width(text):return sum(8 if ord(c)<128 else 16 for c in text)
def rows(parts,limit):
    # Independent CJK layout budget. Punctuation stays with its preceding glyph.
    text=''.join(parts);clusters=[]
    for c in text:
        if c in '、。！？）」』ー…ぁぃぅぇぉっゃゅょゎゕゖァィゥェォッャュョヮヵヶ\u3099\u309a' and clusters:clusters[-1]+=c
        else:clusters.append(c)
    n=1;used=0
    for cluster in clusters:
        w=width(cluster)
        if used+w>limit:n+=1;used=0
        used+=w
    return n

DRIVER=r'''
#include "language.h"
#include "pokemon_names.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static char line[16384],source[8192],expected[8192];
static void decode(const char*s,char*o){while(*s&&*s!='\t'&&*s!='\n'){unsigned c;assert(sscanf(s,"%2x",&c)==1);*o++=c;s+=2;}*o=0;}
static void utf8(const char *p){while(*p){unsigned char c=*p++;unsigned n=c<128?0:c>=0xc2&&c<0xe0?1:c>=0xe0&&c<0xf0?2:99;assert(n!=99);while(n--){assert((*p&0xc0)==0x80);p++;}}}
int main(void){
 language_set_runtime(LANGUAGE_JA);unsigned count=0;
 while(fgets(line,sizeof(line),stdin)){
  char*tab=strchr(line,'\t');assert(tab);decode(line,source);decode(tab+1,expected);
  assert(!strcmp(language_text(source),expected));assert(!strcmp(language_text_n(source,strlen(source)),expected));
  if(strncmp(source,"name:",5)) {char copy[4096];int n=language_snprintf(copy,sizeof(copy),"%s",source);assert(n==(int)strlen(expected)&&!strcmp(copy,expected));}
  count++;
 }
 char out[128];const char raw[6]={0xe9,0x81,0x93,0xe5,0x85,0xb7};
 assert(language_snprintf(out,sizeof(out),"%.*s",6,raw)==6&&!strcmp(out,"道具"));
 for(unsigned cap=0;cap<=sizeof(out);cap++) {
  memset(out,0x5a,sizeof(out));int n=language_snprintf(out,cap,"経験値+%u %s %.*s",123u,"队伍",6,raw);
  assert(n==(int)strlen("経験値+123 手持ち 道具"));if(cap)utf8(out);
  for(unsigned i=cap;i<sizeof(out);i++)assert(out[i]==0x5a);
 }
 assert(pokemon_names_set_style(POKEMON_NAMES_GS_LEGACY));uint8_t n;
 assert(!strcmp(pokemon_names_override(149,&n),"カイリュー"));
 assert(!strcmp(pokemon_move_names_override(57,&n),"なみのり"));
 for(unsigned i=1;i<=251;i++){
  const char*p=pokemon_names_override(i,&n);assert(p&&n==strlen(p));utf8(p);
  p=pokemon_move_names_override(i,&n);assert(p&&n==strlen(p));utf8(p);
 }
 assert(!language_species_name(0)&&!language_species_name(252));
 assert(!language_move_name(0)&&!language_move_name(252));
 const char*unknown="未定義のメッセージ";assert(language_text(unknown)==unknown);assert(!language_text(NULL));
 language_set_runtime(LANGUAGE_ZH_HANS);assert(!strcmp(pokemon_names_override(149,&n),"肥大"));
 language_set_runtime(LANGUAGE_JA);
 for(unsigned cp=0;cp<65536;cp++){const uint8_t*g=language_glyph(cp);if(g&&cp!=32){bool ink=false;for(int i=0;i<32;i++)ink|=g[i]!=0;assert(ink);}}
 printf("{\"passed\":true,\"catalogue\":%u,\"species\":251,\"moves\":251,\"utf8_buffer_sizes\":129}\n",count);
}
'''

def main():
    assert (MAIN/'language_japanese.h').read_text()==generate()
    ja=json.loads((DATA/'ja.json').read_text());en=json.loads((DATA/'en.json').read_text());assert set(ja)==set(en)
    missing=[]
    for file in json.loads((DATA/'english_sources.json').read_text()):
        for m in TOKEN.finditer((MAIN/file).read_text()):
            s=m.group(1)
            if s and re.search('[\u3400-\u9fff]',s) and s not in ja:missing.append((file,s))
    assert not missing,missing
    for source in ('出战','养成效果可查看当前加成','按C调节屏幕亮度'):
        assert width(ja[source])<=(32 if source=='出战' else 216),(source,ja[source])
    for source,target in ja.items():
        if source.startswith(('A上 B下','A/B选择','A/B翻页')):assert width(target)<=224,('footer clipped',source,target,width(target))
    for m in re.finditer(r'\b(?:P|S|MON)\([^\n]+\)',(MAIN/'narrative_script.c').read_text()):
        parts=re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"',m.group())
        if len(parts)>=4:assert rows([ja[x] for x in parts[-3:] if x],208)<=5,('Story clipped',parts[-3:])
    for m in re.finditer(r'\{((?:"[^"]+",?)+)\},"([^"]+)",3',(MAIN/'narrative_script.c').read_text()):
        assert rows([ja[m[2]]],208)<=2,('Inference hint clipped',m[2])
        for choice in re.findall(r'"([^"]+)"',m[1]):assert width(ja[choice])<=182,('Inference choice clipped',choice)
    probes=(MAIN/'johto_routes.c').read_text().split('static const johto_probe_t PROBES')[1].split('const johto_probe_t *johto_probe(')[0]
    for line in probes.splitlines():
        parts=re.findall(r'"([^"\n]+)"',line)
        if len(parts)==8:
            for group,limit,w in ((parts[1:3],3,216),(parts[3:5],4,208),(parts[5:8],5,208)):
                assert rows([ja[x] for x in group],w)<=limit,('Fieldwork clipped',group)
    for source in re.findall(r'"([^"\n]+)"',(MAIN/'opening.c').read_text()):
        if source in ja:assert width(ja[source])<=224,('Opening line clipped',source,ja[source])
    descriptions=(MAIN/'combat.c').read_text().split('const char *combat_description')[1].split('const char *combat_feedback')[0]
    for source in re.findall(r'"([^"]+)"',descriptions):
        assert width(ja[source])<=208,('Move description overlaps its feedback',source,ja[source])
    glyphset=set(glyph_codes())
    names=json.loads((DATA/'japanese_names.json').read_text())
    assert all(len(name.encode())<64 for name in names['moves']), 'Move label buffer'
    assert all(ord(c)<128 or ord(c) in glyphset for s in [*ja.values(),*names['pokemon'],*names['moves']] for c in s)
    # Device-hosted setup form has a fixed 1700 B buffer, including the AP token.
    for source,target in ja.items():
        if source.startswith('<!doctype'):assert len(target.replace('%s','12345678').replace('%%','%').encode())<1700
    with tempfile.TemporaryDirectory(prefix='pokewalk-japanese-') as tmp:
        p=Path(tmp);(p/'test.c').write_text(DRIVER)
        command=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(MAIN),str(p/'test.c')]
        command += [str(MAIN/f) for f in ('language.c','language_format.c','pokemon_names.c')]+['-o',str(p/'test')]
        subprocess.run(command,check=True)
        payload=''.join(f'{a.encode().hex()}\t{b.encode().hex()}\n' for a,b in ja.items())
        result=subprocess.run([str(p/'test')],input=payload,text=True,capture_output=True)
        assert result.returncode==0,result.stdout+result.stderr
        print(result.stdout.strip())

if __name__=='__main__':main()
