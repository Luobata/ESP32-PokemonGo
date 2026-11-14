#!/usr/bin/env python3
"""Check production conversion against pinned full dictionaries and NVS faults."""
import json
import subprocess
import tempfile
from pathlib import Path
from generate_traditional import ROOT, corpus, dictionaries

NVS = '''#include <stdint.h>
typedef int esp_err_t;typedef int nvs_handle_t;
#define ESP_OK 0
#define NVS_READONLY 0
#define NVS_READWRITE 1
int nvs_open(const char*,int,int*);int nvs_get_u8(int,const char*,uint8_t*);
int nvs_set_u8(int,const char*,uint8_t);int nvs_commit(int);void nvs_close(int);
'''
DRIVER = r'''
#include "nvs.h"
#include "language.h"
#include "render.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static int disk=-1,stage,fail,writes;
int nvs_open(const char*n,int mode,int*h){assert(!strcmp(n,"pokewalk"));(void)mode;*h=1;stage=disk;return fail==1?-1:0;}
int nvs_get_u8(int h,const char*k,uint8_t*v){(void)h;assert(!strcmp(k,"language"));if(disk<0||fail==4)return -1;*v=disk;return 0;}
int nvs_set_u8(int h,const char*k,uint8_t v){(void)h;assert(!strcmp(k,"language"));writes++;if(fail==2)return -1;stage=v;return 0;}
int nvs_commit(int h){(void)h;if(fail==3)return -1;disk=stage;return 0;}
void nvs_close(int h){(void)h;}
static char line[65536],input[16384],wanted[16384],copy[16384];
static void decode(const char *hex,char *out){
 while(*hex&&*hex!='\t'&&*hex!='\n'){unsigned byte;assert(sscanf(hex,"%2x",&byte)==1);*out++=byte;hex+=2;}*out=0;
}
int main(void){
 language_settings_init();assert(language_get()==LANGUAGE_ZH_HANS);
 assert(language_settings_set(LANGUAGE_ZH_HANS)&&writes==0);
 assert(!language_settings_set(LANGUAGE_COUNT)&&!language_set_runtime((language_t)-1));
 for(fail=1;fail<=3;fail++){
  assert(!language_settings_set(LANGUAGE_ZH_HANT));assert(language_get()==LANGUAGE_ZH_HANS&&disk==-1);
 }
 fail=0;assert(language_settings_set(LANGUAGE_ZH_HANT));language_set_runtime(LANGUAGE_ZH_HANS);
 language_settings_init();assert(language_get()==LANGUAGE_ZH_HANT&&disk==1);
 for(int invalid=3;invalid<=255;invalid+=252){disk=invalid;language_settings_init();assert(language_get()==LANGUAGE_ZH_HANS);}
 disk=1;fail=4;language_settings_init();assert(language_get()==LANGUAGE_ZH_HANS);
 fail=0;language_settings_init();assert(language_get()==LANGUAGE_ZH_HANT);
 for(fail=1;fail<=3;fail++){assert(!language_settings_set(LANGUAGE_EN));assert(language_get()==LANGUAGE_ZH_HANT&&disk==1);}
 fail=0;assert(language_settings_set(LANGUAGE_EN));language_set_runtime(LANGUAGE_ZH_HANS);
 language_settings_init();assert(language_get()==LANGUAGE_EN&&disk==2);
 language_set_runtime(LANGUAGE_ZH_HANT);
 unsigned count=0,glyphs=0;
 while(fgets(line,sizeof(line),stdin)){
  char *tab=strchr(line,'\t');assert(tab);decode(line,input);decode(tab+1,wanted);
  assert(strlen(input)==strlen(wanted));
  language_set_runtime(LANGUAGE_ZH_HANS);strcpy(copy,input);language_convert_in_place(copy);assert(!strcmp(copy,input));
  language_set_runtime(LANGUAGE_ZH_HANT);strcpy(copy,input);language_convert_in_place(copy);
  if(strcmp(copy,wanted)){fprintf(stderr,"Mismatch: %s => %s expected %s\n",input,copy,wanted);return 1;}
  assert(render_text_width_sized(input,16)==render_text_width_sized(copy,16));
  language_reader_t r=language_reader(input);const char *p=wanted;
  while(*p){uint16_t expected;unsigned bytes=render_utf8_next(p,&expected);assert(language_next(&r)==expected);p+=bytes;
   if(expected>=0x3400&&expected<=0x9fff){const uint8_t *g=language_glyph(expected);assert(g);bool ink=false;for(unsigned i=0;i<32;i++)ink|=g[i]!=0;assert(ink);glyphs++;}
  }
  assert(language_next(&r)==0);count++;
 }
 language_convert_in_place(NULL);assert(!language_glyph('A'));
 printf("{\"passed\":true,\"corpus_strings\":%u,\"glyph_lookups\":%u,\"settings_fault_stages\":4,\"nvs_boundary\":\"simulated\"}\n",count,glyphs);
}
'''

def main():
    chars, phrases = dictionaries()
    groups = {}
    # Independent oracle: use all pinned dictionary entries, not the generated
    # subset or tables imported from the C runtime.
    for src, dst in phrases.items(): groups.setdefault(src[0], []).append((src, dst))
    for entries in groups.values(): entries.sort(key=lambda pair: -len(pair[0]))
    def convert(text):
        out = ''; pos = 0
        while pos < len(text):
            for src, dst in groups.get(text[pos], []):
                if text.startswith(src, pos): out += dst; pos += len(src); break
            else: out += chars.get(text[pos], text[pos]); pos += 1
        return out
    examples = {'尼多后': '尼多后', '发型': '髮型', '头发': '頭髮', '干扰': '干擾',
                '干燥': '乾燥', '繁體中文': '繁體中文', '': '', 'ABC Lv100 HP 123/456': 'ABC Lv100 HP 123/456'}
    rows = {s: convert(s) for s in corpus()}
    for text, expected in examples.items():
        assert convert(text) == expected, (text, convert(text), expected)
        rows[text] = expected
    payload = ''.join(f'{a.encode().hex()}\t{b.encode().hex()}\n' for a, b in rows.items())
    subprocess.run(['python3', str(ROOT/'tools/pipeline/generate_traditional.py'), '--check'], check=True)
    with tempfile.TemporaryDirectory(prefix='pokewalk-language-') as tmp:
        p = Path(tmp); (p/'nvs.h').write_text(NVS); (p/'driver.c').write_text(DRIVER)
        subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',
                        '-I',str(p),'-I',str(ROOT/'firmware/main'), str(p/'driver.c'),
                        str(ROOT/'firmware/main/language.c'),str(ROOT/'firmware/main/language_settings.c'),'-o',str(p/'test')],check=True)
        result = subprocess.run([str(p/'test')],input=payload,text=True,capture_output=True)
        assert result.returncode == 0, result.stdout+result.stderr
        print(result.stdout.strip())

if __name__ == '__main__': main()
