#!/usr/bin/env python3
"""Production party C: 759 distinct individuals, policies, holes and legacy codec.

The former S14 Python mirror deduplicates by species and is a historical model;
current hardware/preview both use this C implementation. The 1886-byte codec is
retained only for old-layout migration. V23 persistence is tested by the save gates.
An alternate party.c path can be supplied for mutation/negative testing.
"""
from pathlib import Path
import subprocess,sys,tempfile
ROOT=Path(__file__).resolve().parents[2]
SOURCE=r'''
#include "party.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static party_t party,before,decoded;
int main(void){
 _Static_assert(BOX_SPECIES==251 && BOX_CAPACITY==753 && PARTY_MAX==6,"capacity");
 _Static_assert(MON_BYTES==12 && LEGACY_PARTY_BYTES==1886,"immutable old codec");
 party_init(&party);assert(party_total(&party)==0&&!party_leader(&party));
 assert(!party_receive(NULL,NULL));mon_t invalid={.species_id=252};assert(!party_receive(&party,&invalid));
 for(unsigned i=0;i<759;i++){
  mon_t m={.species_id=25,.level=(uint8_t)(1+i%100),.hp=99,.intimacy=77,.flags=i%2,.exp=1000+i,.nickname_idx=255,.explore_value=65535};
  assert(party_receive(&party,&m));
  const mon_t *got=i<6?&party.party[i]:&party.box[i-6];assert(!memcmp(got,&m,sizeof(m)));
  assert(party_total(&party)==i+1);move_policy_set(&party.policies[i],33+i%100,false);
 }
 before=party;mon_t shiny={.species_id=25,.level=100,.flags=1,.exp=999999};
 assert(!party_can_receive(&party,25)&&!party_receive(&party,&shiny)&&!memcmp(&party,&before,sizeof(party)));
 const unsigned boundaries[]={0,150,151,255,256,452,648,752};
 for(unsigned j=0;j<sizeof(boundaries)/sizeof(boundaries[0]);j++){
  unsigned at=boundaries[j];party=before;
  assert(party_exchange_at(&party,5,at));
  assert(!memcmp(&party.party[5],&before.box[at],sizeof(mon_t)));
  assert(!memcmp(&party.policies[5],&before.policies[6+at],sizeof(move_policy_t)));
  assert(party_exchange_at(&party,5,at)&&!memcmp(&party,&before,sizeof(party)));
  memset(&party.box[at],0,sizeof(mon_t));assert(party_can_receive(&party,25));
  assert(party_receive(&party,&shiny)&&!memcmp(&party.box[at],&shiny,sizeof(mon_t)));
  move_policy_t all={0};assert(!memcmp(&party.policies[6+at],&all,sizeof(all)));
  assert(party_total(&party)==759);
 }
 party=before;assert(!party_exchange_at(&party,6,0)&&!party_exchange_at(&party,0,753));
 assert(!party_set_leader(&party,0)&&!party_set_leader(&party,6));assert(!memcmp(&party,&before,sizeof(party)));
 assert(party_set_leader(&party,5));assert(!memcmp(&party.party[0],&before.party[5],sizeof(mon_t)));
 assert(!memcmp(&party.policies[0],&before.policies[5],sizeof(move_policy_t)));
 for(unsigned i=1;i<6;i++){assert(!memcmp(&party.party[i],&before.party[i-1],sizeof(mon_t)));assert(!memcmp(&party.policies[i],&before.policies[i-1],sizeof(move_policy_t)));}
 assert(!memcmp(party.box,before.box,sizeof(party.box)));
 // Exact historical field encoding, with upper slots explicitly absent from the old format.
 uint8_t wire[1886],again[1886];party_serialize(&party,wire);assert(wire[0]==6&&wire[1]==151);
 const uint8_t expected[]={25,6,99,77,255,255,255,1,0xed,3,0,0};assert(!memcmp(wire+2,expected,12));
 assert(party_deserialize(&decoded,wire,sizeof(wire)));assert(party_total(&decoded)==157);
 for(unsigned i=151;i<753;i++)assert(!decoded.box[i].species_id);
 for(unsigned i=0;i<759;i++)for(unsigned j=0;j<MOVE_POLICY_BYTES;j++)assert(!decoded.policies[i].disabled[j]);
 party_serialize(&decoded,again);assert(!memcmp(wire,again,sizeof(wire)));
 before=decoded;assert(!party_deserialize(&decoded,wire,sizeof(wire)-1)&&!memcmp(&before,&decoded,sizeof(decoded)));
 mon_t a={.level=5,.exp=100},b={.level=4,.exp=900};assert(party_better(&a,&b));b.flags=1;assert(party_better(&b,&a));
 puts("753 independent warehouse slots + 6 party, duplicate capture, full rejection, 256+ indices, individual policies, reorder, holes and exact legacy encoding: passed");
}
'''
with tempfile.TemporaryDirectory() as folder:
 p=Path(folder);(p/'test.c').write_text(SOURCE)
 party=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'firmware/main/party.c'
 subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I',str(ROOT/'firmware/main'),str(p/'test.c'),str(party),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
