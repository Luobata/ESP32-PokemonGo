#!/usr/bin/env python3
"""Compile and verify the Crystal-style escape threshold and action transaction."""
from pathlib import Path
import subprocess
import tempfile

MAIN = Path(__file__).resolve().parents[2] / 'firmware/main'
DRIVER = r'''
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "battle_escape.h"
bool assets_species(uint16_t id,species_t *out) {
    if(id<1||id>2)return false;memset(out,0,sizeof(*out));
    out->speed=id==1?50:100;return true;
}
uint16_t battle_effective_stat(uint8_t value,uint8_t level) {(void)level;return value;}
int main(void) {
    assert(battle_escape_chance(50,100,0)==65);
    assert(battle_escape_chance(50,100,1)==95);
    assert(battle_escape_chance(30,247,0)==16);
    assert(battle_escape_chance(100,100,0)==256);
    assert(battle_escape_chance(101,100,0)==256);
    assert(battle_escape_chance(0,3,0)==256);
    assert(battle_escape_chance(1,65535,255)==256);
    unsigned cases=7;
    for(unsigned pet=1;pet<512;pet+=7)for(unsigned wild=4;wild<1024;wild+=13) {
        uint16_t previous=0;
        for(unsigned attempt=0;attempt<12;attempt++) {
            uint16_t n=battle_escape_chance(pet,wild,attempt);
            assert(n>=1&&n<=256&&n>=previous);previous=n;cases++;
        }
        assert(previous==256); // Repeated failed attempts cannot wrap forever.
    }
    unsigned wins=0,losses=0;
    for(unsigned seed=1;seed<=1024;seed++) {
        battle_session_t s={.initialized=true,.pet_species=1,.wild_species=2,
                            .pet_hp=40,.wild_hp=80,.rng=seed};
        battle_escape_result_t out;
        assert(battle_escape_try(&s,&out));
        assert(out.chance==65&&s.escape_attempts==1&&s.started);
        assert(s.pet_hp==40&&s.wild_hp==80&&!s.finished&&!s.reward_settled&&!s.auto_battle);
        if(out.escaped) {wins++;assert(!s.retaliation_pending&&!s.escape_retaliation);}
        else {
            losses++;assert(s.retaliation_pending&&s.escape_retaliation);
            battle_session_t old=s;assert(!battle_escape_try(&s,&out));
            assert(!memcmp(&old,&s,sizeof(s))); // Can't skip the obligatory attack.
        }
        cases++;
    }
    assert(wins==260&&losses==764); // All 256 byte outcomes occur four times.
    battle_session_t s={.initialized=true,.pet_species=1,.wild_species=2,.pet_hp=1,
                        .wild_hp=1,.escape_attempts=255,.rng=17,.auto_battle=true};
    battle_escape_result_t out;assert(battle_escape_try(&s,&out));
    assert(out.escaped&&out.chance==256&&s.escape_attempts==255&&s.auto_battle&&s.rng==17);
    s.finished=true;battle_session_t old=s;assert(!battle_escape_try(&s,&out));
    assert(!memcmp(&old,&s,sizeof(s)));
    printf("PASS escape: %u threshold/action cases; %u/1024 low-speed successes\n",cases+2,wins);
}
'''

def main():
    with tempfile.TemporaryDirectory(prefix='escape-verify-') as directory:
        p=Path(directory); (p/'probe.c').write_text(DRIVER)
        subprocess.run(['cc','-std=c11','-O1','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','-fno-omit-frame-pointer',
                        '-I',str(MAIN),str(p/'probe.c'),str(MAIN/'battle_escape.c'),
                        '-o',str(p/'probe')],check=True)
        subprocess.run([str(p/'probe')],check=True)

if __name__=='__main__':main()
