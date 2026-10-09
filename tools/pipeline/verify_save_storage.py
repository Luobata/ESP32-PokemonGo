#!/usr/bin/env python3
"""Exercise the production V22 codec, bounds and corruption under sanitizers."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = r'''
#include "save_storage.h"
#include <assert.h>
#include <stdio.h>
static uint8_t raw[7792], encoded[7900], decoded[7792], corrupt[7900];
static uint32_t rng=1;
static uint8_t next(void){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;return (uint8_t)rng;}
int main(void){
 for(unsigned pattern=0;pattern<200;pattern++){
  for(size_t i=0;i<sizeof(raw);i++)raw[i]=pattern==0?0:pattern==1?255:pattern==2?i%2:next()%(pattern+1)?0:next();
  save_put16(raw,SAVE_STORAGE_VERSION);
  size_t n=save_storage_encode(encoded,sizeof(encoded),raw,sizeof(raw));assert(n);
  assert(save_storage_decode(decoded,sizeof(decoded),encoded,n)&&!memcmp(raw,decoded,sizeof(raw)));
  for(size_t len=0;len<n;len++)assert(!save_storage_decode(decoded,sizeof(decoded),encoded,len));
  assert(!save_storage_decode(decoded,sizeof(decoded),encoded,n+1));
  for(size_t i=0;i<n;i++){
   memcpy(corrupt,encoded,n);corrupt[i]^=1;
   assert(!save_storage_decode(decoded,sizeof(decoded),corrupt,n));
  }
  assert(!save_storage_encode(corrupt,n-1,raw,sizeof(raw)));
  assert(!save_storage_decode(decoded,sizeof(decoded)-1,encoded,n));
  assert(!save_storage_decode(decoded,0,encoded,n));
  assert(!save_storage_decode(decoded,1,encoded,n));
 }
 assert(!save_storage_encode(NULL,0,raw,sizeof(raw)));
 assert(!save_storage_decode(NULL,sizeof(decoded),encoded,sizeof(encoded)));
 puts("V22 codec: sparse/dense/random bytes, every truncation/bit corruption, length and capacity boundaries passed");
}
'''

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='pokewalk-save-codec-') as d:
        p = Path(d)
        (p/'test.c').write_text(SOURCE)
        subprocess.run(['cc', '-std=c11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
                        '-fsanitize=address,undefined', '-I', str(ROOT/'firmware/main'),
                        str(p/'test.c'), '-o', str(p/'test')], check=True)
        subprocess.run([str(p/'test')], check=True)
