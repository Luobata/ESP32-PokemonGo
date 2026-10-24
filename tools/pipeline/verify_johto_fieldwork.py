#!/usr/bin/env python3
"""Real save/world fieldwork transactions, rejected preparations and old progress."""
import verify_trainer_campaign as h
from save_history_fixtures import c_cases
import json
from pathlib import Path
guide_raw=(Path(__file__).resolve().parents[2]/'tools/save-manager/web/guide/fieldwork.js').read_text()
guide=json.loads(guide_raw[guide_raw.index('{'):].rstrip(';\n'))
examples=[(s['id'],e['id'],e['routeId'],e['pathId']) for s in guide['sites'] for e in s['examples']]
h.CASES=c_cases()+'\nstatic const unsigned guide_examples[][4]={'+','.join('{'+','.join(map(str,row))+'}' for row in examples)+'};\n'+r'''
static save_t before,after;
static void guide_helpers(void){
 for(unsigned i=0;i<sizeof(guide_examples)/sizeof(*guide_examples);i++){
  const unsigned *e=guide_examples[i];mon_t m={.species_id=e[1],.hp=100};
  assert(johto_probe_member(e[0],&m));const johto_path_t *p=johto_path(e[2],e[3]);assert(p);
  bool found=false;for(unsigned k=0;k<4;k++)found|=p->species[k]==e[1];assert(found);
 }
}
static void ready(unsigned id){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);party_init(&s_party);
 for(unsigned i=0;i<6;i++){mon_t m={.species_id=(unsigned[]){25,28,6,3,65,130}[i],.level=60,.hp=100,.exp=exp_for_level(60)};assert(party_receive(&s_party,&m));}
 s_w.species=25;s_w.level=60;s_w.exp=exp_for_level(60);s_w.pet.stamina=100*NURT_Q;
 johto_init(&s_johto);johto_story_init(&s_story);const johto_probe_t *p=johto_probe(id);assert(p);
 s_johto.phase=p->legend==5?JOHTO_COMPLETE:JOHTO_ACTIVE;s_johto.starter=152;s_johto.badges=255;
 for(unsigned i=0;i<6;i++)s_johto.legend_clues[i]=3;s_johto.legend_clues[p->legend]=p->step;
 s_story.tower_seen=1;s_story.forest_visits=3;s_activities.silver_feather=1;
 assert(johto_receive_egg(&s_johto,123));world_debug_save();assert(save_read(&before));
}
static unsigned helper(unsigned id,bool match){for(unsigned i=0;i<s_party.party_count;i++)if(johto_probe_member(id,&s_party.party[i])==match)return i;assert(!"fixture missing helper");return 0;}
static void unchanged(void){world_debug_save();assert(save_read(&after));assert(!memcmp(&before,&after,sizeof(before)));}
static void all_sites(void){
 for(unsigned id=0;id<JOHTO_PROBE_COUNT;id++){
  ready(id);const johto_probe_t *p=johto_probe(id);unsigned slot=helper(id,true),wrong=helper(id,false);mon_t actor=s_party.party[slot];
  assert(johto_probe_available(&s_johto,&s_story,true,id));
  assert(johto_probe_next(&s_johto,&s_story,true,p->route,p->legend)==id);
  assert(world_johto_investigate(id,(p->path+1)%3,slot,&actor)==WORLD_JOHTO_WRONG_PATH);unchanged();
  assert(world_johto_investigate(id,p->path,wrong,&s_party.party[wrong])==WORLD_JOHTO_WRONG_PARTNER);unchanged();
  mon_t stale=actor;stale.exp++;assert(world_johto_investigate(id,p->path,slot,&stale)==WORLD_JOHTO_LOCKED);unchanged();
  assert(world_johto_investigate(id,p->path,PARTY_MAX,&actor)==WORLD_JOHTO_LOCKED);unchanged();
  // Every accepted type allows multiple actual species, including secondary types.
  unsigned compatible=0;for(unsigned sp=1;sp<=251;sp++){mon_t m={.species_id=sp,.hp=100};compatible+=johto_probe_member(id,&m);}assert(compatible>=2);
  for(unsigned f=0;f<3;f++){
   failure=(unsigned[]){1,2,4}[f];assert(world_johto_investigate(id,p->path,slot,&actor)==WORLD_JOHTO_SAVE_FAILED);failure=0;unchanged();reboot();
  }
  assert(world_johto_investigate(id,p->path,slot,&actor)==WORLD_JOHTO_OK);reboot();assert(save_read(&after));
  assert(after.johto.legend_clues[p->legend]==p->step+1&&after.johto.research[p->route]==1&&after.johto.explorations==1&&after.johto.egg_steps==1);
  assert(after.pet.stamina==before.pet.stamina-NURT_EXPLORE_COST);assert(!memcmp(&after.members,&before.members,sizeof(after.members))&&!memcmp(&after.queue,&before.queue,sizeof(after.queue))&&!memcmp(&after.inventory,&before.inventory,sizeof(after.inventory)));
  before=after;assert(world_johto_investigate(id,p->path,slot,&actor)==WORLD_JOHTO_LOCKED);unchanged();
 }
}
static void gates(void){
 ready(0);const johto_probe_t *p=johto_probe(0);mon_t actor=s_party.party[0];
 s_w.pet.stamina=NURT_EXPLORE_COST-1;assert(world_johto_investigate(0,p->path,0,&actor)==WORLD_JOHTO_NO_STAMINA);assert(!s_johto.legend_clues[0]);
 s_w.pet.stamina=100*NURT_Q;s_story.tower_seen=0;assert(world_johto_investigate(0,p->path,0,&actor)==WORLD_JOHTO_LOCKED);
 s_story.tower_seen=1;s_johto.badges=7;assert(world_johto_investigate(0,p->path,0,&actor)==WORLD_JOHTO_LOCKED);
 ready(8);s_activities.silver_feather=0;assert(!johto_probe_available(&s_johto,&s_story,false,8));
 ready(11);s_johto.legend_clues[2]=2;assert(!johto_probe_available(&s_johto,&s_story,true,11));
 ready(14);s_story.forest_visits=2;assert(!johto_probe_available(&s_johto,&s_story,true,14));
 ready(0);s_activities.run.kind=ACT_BUG;assert(world_johto_investigate(0,0,0,&actor)==WORLD_JOHTO_BUSY);
 ready(0);s_challenge.session.active=1;assert(world_johto_investigate(0,0,0,&actor)==WORLD_JOHTO_BUSY);
 ready(0);s_johto.last_action=UINT32_MAX;assert(world_johto_investigate(0,0,0,&actor)==WORLD_JOHTO_LOCKED);
}
static void no_spamming(void){
 ready(0);memset(s_johto.legend_clues,0,6);
 for(unsigned i=0;i<32;i++){s_w.pet.stamina=100*NURT_Q;johto_search_t out;assert(world_johto_search(i%8,i%3,&out)==WORLD_JOHTO_OK);for(unsigned k=0;k<6;k++)assert(!s_johto.legend_clues[k]);}
 encounter_t out;s_w.pet.stamina=100*NURT_Q;assert(world_johto_explore(4,&out)==WORLD_JOHTO_OK&&!s_johto.legend_clues[0]);
 assert(s_johto.explorations==33&&s_johto.egg_status==JOHTO_EGG_READY);
}
static void old_progress(void){
 for(unsigned i=0;i<sizeof(history)/sizeof(*history);i++){assert(save_decode(&after,history[i].data,history[i].size,0)!=SAVE_READ_ERROR);history_assert(&after,history[i].version);}
 ready(0);s_johto.legend_clues[0]=3;world_debug_save();reboot();assert(johto_story_legend_ready(&s_story,&s_johto,0,true));
 encounter_t e;assert(world_johto_legend(0,&e)==WORLD_JOHTO_OK&&e.species_id==243);
 // A previously completed step stays completed even with an unsuitable party.
 ready(1);assert(s_johto.legend_clues[0]==1&&!johto_probe_available(&s_johto,&s_story,true,0));
}
int main(void){assert(assets_init());guide_helpers();all_sites();gates();no_spamming();old_progress();puts("17 field sites: real save/world commit, wrong route/partner, stale identity, resource gates, I/O rollback/reboot, no click grinding, V5-V31 retained; guide examples match production types and encounter pools");}
'''
if __name__=='__main__':h.run()
