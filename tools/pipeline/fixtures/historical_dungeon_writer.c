// Synthetic run compiled with published V3 headers; no player data.
#include "dungeon.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(int argc,char **argv){
 assert(argc==2);dungeon_t d={0};d.version=3;d.seed=91273;d.run_id=23;
 d.phase=DUNGEON_FORK;d.node=1;d.count=2;d.base_level=40;d.cards=1u<<3;
 d.battle.defeated=255;d.battle.session.active=1;d.battle.session.trainer=14;d.battle.session.ability=1024;d.battle.session.participated=1;
 for(unsigned i=0;i<2;i++){
  d.ids[i]=i?9:6;d.slots[i]=i;d.members[i]=(mon_t){.species_id=d.ids[i],.level=40,.exp=96000,.flags=i};
  for(unsigned side=0;side<2;side++){
   d.battle.session.sides[side].count=2;
   combat_mon_t *m=&d.battle.session.sides[side].mons[i];m->species=side?(i?34:31):d.ids[i];m->level=40;m->hp=72;m->max_hp=100;m->moves[0]=33;m->pp[0]=20;
  }
 }
 FILE *f=fopen(argv[1],"wb");assert(f);assert(fwrite(&d,1,sizeof(d),f)==sizeof(d));assert(!fclose(f));return 0;
}
