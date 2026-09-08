#!/usr/bin/env python3
"""Actual capture.c: conditional ball boundaries, master certainty and old rules."""
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
DRIVER = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "capture.h"
int main(void) {
    cap_context_t c={.pet_level=40,.wild_level=20,.wild_speed=99,.wild_weight_hg=999};
    assert(CAP_BALL_COUNT==8);
    assert(cap_ball_factor_1000(CAP_BALL_FAST,&c)==1000);
    c.wild_speed=100;assert(cap_ball_factor_1000(CAP_BALL_FAST,&c)==4000);
    assert(cap_ball_factor_1000(CAP_BALL_HEAVY,&c)==1000);
    c.wild_weight_hg=1000;assert(cap_ball_factor_1000(CAP_BALL_HEAVY,&c)==2000);
    c.wild_weight_hg=1999;assert(cap_ball_factor_1000(CAP_BALL_HEAVY,&c)==2000);
    c.wild_weight_hg=2000;assert(cap_ball_factor_1000(CAP_BALL_HEAVY,&c)==3000);
    assert(cap_ball_factor_1000(CAP_BALL_LEVEL,&c)==2000);
    c.pet_level=39;assert(cap_ball_factor_1000(CAP_BALL_LEVEL,&c)==1500);
    c.pet_level=20;assert(cap_ball_factor_1000(CAP_BALL_LEVEL,&c)==1000);
    c.wild_level=0;assert(cap_ball_factor_1000(CAP_BALL_LEVEL,&c)==1000);
    assert(cap_ball_factor_1000(CAP_BALL_LEVEL,NULL)==1000);
    assert(!strcmp(cap_ball_name((cap_ball_t)-1),"精灵球"));
    assert(!strcmp(cap_ball_name(CAP_BALL_FRIEND),"友友球"));
    unsigned checks=13;
    // Independent expected numbers, before any large grid comparisons.
    c=(cap_context_t){.pet_level=40,.wild_level=20,.wild_speed=100,.wild_weight_hg=2000};
    const unsigned expected[8]={25,37,50,200,99,74,50,25};
    for(unsigned ball=0;ball<8;ball++) {
        assert(cap_window_width_context(45,1024,ball,100,&c)==expected[ball]);checks++;
    }
    for(unsigned rate=0;rate<=255;rate+=3)for(unsigned mood=0;mood<=2048;mood+=256)
    for(unsigned hp=0;hp<=100;hp+=10)for(unsigned t=0;t<=1200;t+=40) {
        cap_result_t r;
        cap_attempt_context(rate,mood,CAP_BALL_MASTER,hp,5,t,17,&c,&r);
        assert(r.caught&&!r.fled&&r.window_w==200&&r.window_start==0&&r.window_end==200);
        checks++;
    }
    for(unsigned ball=0;ball<3;ball++)for(unsigned rate=3;rate<=255;rate+=3)
    for(unsigned hp=0;hp<=100;hp+=10) {
        cap_result_t old,added;
        cap_attempt(rate,1228,ball,hp,4,400,17,&old);
        cap_attempt_context(rate,1228,ball,hp,4,400,17,&c,&added);
        assert(!memcmp(&old,&added,sizeof(old)));checks++;
    }
    printf("PASS special balls: %u checks; eight ball rules; master all pointer phases; original three unchanged\n",checks);
}
'''

def main():
    with tempfile.TemporaryDirectory(prefix='special-balls-') as directory:
        p=Path(directory); (p/'check.c').write_text(DRIVER)
        subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror','-DHOST_BUILD',
            '-fsanitize=address,undefined','-fno-omit-frame-pointer',
            '-I',str(ROOT/'firmware/main'),str(p/'check.c'),str(ROOT/'firmware/main/capture.c'),
            '-lz','-o',str(p/'check')],check=True)
        subprocess.run([str(p/'check')],check=True)

if __name__=='__main__':main()
