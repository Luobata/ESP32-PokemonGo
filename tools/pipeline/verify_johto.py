#!/usr/bin/env python3
"""Exercise the chapter core and verify Gen I assets against a fixed baseline.

Live world transactions and save migration are checked by verify_johto_save.py.
"""
from pathlib import Path
import argparse, json, subprocess, tempfile, struct, re
from verify_battle_layout import read_fronts

ROOT=Path(__file__).resolve().parents[2]
BASELINE='67a4a25749463d50750c9448ff9d5217d1379094'
def baseline(path):
    return subprocess.check_output(['git','show',f'{BASELINE}:{path}'],cwd=ROOT)
DRIVER=r'''
#include "johto.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static johto_state_t s, before, loaded;
static unsigned action;
static void explore(unsigned route,unsigned count){
 for(unsigned i=0;i<count;i++){
  assert(johto_explore(&s,route,++action,true));assert(johto_valid(&s));
  before=s;assert(!johto_explore(&s,route,action,true));assert(!memcmp(&s,&before,sizeof s));
  memcpy(&loaded,&s,sizeof s);assert(johto_valid(&loaded));s=loaded;
 }
}
int main(void){
 const unsigned old[]={0,7,15,255,8191,16383};
 for(unsigned i=0;i<sizeof old/sizeof old[0];i++){
  johto_init(&s);assert(johto_valid(&s));
  assert(johto_offer(&s,old[i])==(i>=2));
  before=s;assert(!johto_offer(&s,old[i]));assert(!memcmp(&s,&before,sizeof s));
  assert(!s.badges&&!s.starter&&!s.explorations);
 }
 assert(johto_depart(&s));assert(!johto_depart(&s));
 before=s;assert(!johto_choose_starter(&s,25));assert(!memcmp(&s,&before,sizeof s));
 assert(johto_choose_starter(&s,152));assert(!johto_choose_starter(&s,155));
 assert(!johto_gym_open(&s,1));assert(!johto_gym_win(&s,1));
 before=s;assert(!johto_explore(&s,0,1,false));assert(!memcmp(&s,&before,sizeof s));
 assert(!johto_explore(&s,1,1,true));assert(!johto_receive_egg(&s,0));
 assert(johto_gym_win(&s,0));assert(johto_receive_egg(&s,256));
 assert(johto_egg_shiny(&s));before=s;assert(!johto_receive_egg(&s,17));assert(!memcmp(&s,&before,sizeof s));
 explore(0,11);assert(s.egg_status==JOHTO_EGG_INCUBATING&&!johto_hatch(&s,true));
 explore(1,1);assert(s.egg_status==JOHTO_EGG_READY);
 before=s;assert(!johto_hatch(&s,false));assert(!memcmp(&s,&before,sizeof s));
 assert(johto_hatch(&s,true));assert(s.eggs_hatched==1);assert(!johto_hatch(&s,true));
 assert(!johto_receive_egg(&s,99));explore(1,12);assert(johto_receive_egg(&s,99));
 assert(!johto_egg_shiny(&s));
 for(unsigned gym=1;gym<8;gym++){
  assert(johto_gym_open(&s,gym));assert(johto_gym_win(&s,gym));assert(!johto_gym_win(&s,gym));
  assert(johto_badges(&s)==gym+1);
 }
 assert(!johto_final_open(&s,16383));explore(4,3);explore(2,3);explore(6,3);explore(7,3);
 // Story transactions own clue progression; the core checks readiness only.
 for(unsigned i=0;i<5;i++)s.legend_clues[i]=3;
 for(unsigned i=0;i<5;i++)assert(johto_legend_ready(&s,i));
 assert(!johto_legend_ready(&s,5));assert(!johto_final_open(&s,8191));
 assert(johto_final_open(&s,16383));assert(johto_final_win(&s,16383));assert(!johto_final_win(&s,16383));
 assert(johto_claim_final(&s));assert(!johto_claim_final(&s));assert(johto_final_open(&s,16383));
 explore(1,3);s.legend_clues[5]=3;assert(johto_legend_ready(&s,5));assert(johto_valid(&s));
 for(unsigned r=0;r<8;r++)for(unsigned lv=1;lv<=100;lv++)for(unsigned roll=0;roll<5;roll++){
  unsigned got=johto_route_level(r,lv,roll);assert(got>=JOHTO_ROUTES[r].min_level&&got<=JOHTO_ROUTES[r].max_level);
 }
 assert(!johto_route_level(8,40,0));
 loaded=s;loaded.version=2;assert(!johto_valid(&loaded));loaded=s;loaded.badges=0x82;assert(!johto_valid(&loaded));
 loaded=s;loaded.egg_steps=13;assert(!johto_valid(&loaded));loaded=s;loaded.reserved=1;assert(!johto_valid(&loaded));
 puts("{\"state_bytes\":48,\"routes\":[");
 for(unsigned r=0;r<8;r++){
  const johto_route_t *p=&JOHTO_ROUTES[r];assert(p->count<=12);
  printf("%s{\"id\":%u,\"name\":\"%s\",\"activity\":\"%s\",\"badges\":%u,\"levels\":[%u,%u],\"species\":[",r?",":"",r,p->name,p->activity,p->badges,p->min_level,p->max_level);
  for(unsigned i=0;i<p->count;i++){assert(p->species[i]>=152&&p->species[i]<=248&&p->species[i]!=175&&p->species[i]!=176);printf("%s%u",i?",":"",p->species[i]);}
  printf("]}");
 }
 puts("],\"trainers\":[");
 for(unsigned i=0;i<9;i++){
  const johto_trainer_t *t=&JOHTO_TRAINERS[i];
  printf("%s{\"name\":\"%s\",\"badge\":\"%s\",\"opening\":\"%s\",\"ending\":\"%s\",\"team\":[",i?",":"",t->name,t->badge,t->opening,t->ending);
  for(unsigned j=0;j<t->count;j++)printf("%s[%u,%u]",j?",":"",t->species[j],t->levels[j]);
  printf("]}");
 }
 puts("]}");
}
'''

def verify(assets:Path, output:Path|None=None):
    with tempfile.TemporaryDirectory(prefix='johto-chapter-') as temp:
        p=Path(temp);(p/'test.c').write_text(DRIVER)
        subprocess.run(['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror',
                        '-fsanitize=address,undefined','-I',str(ROOT/'firmware/main'),
                        str(p/'test.c'),str(ROOT/'firmware/main/johto.c'),'-o',str(p/'test')],check=True)
        result=json.loads(subprocess.check_output([str(p/'test')],text=True))
    rows=json.loads((assets/'johto_catalog.json').read_text())['pokemon']
    assert len(rows)==251 and [r['id'] for r in rows]==list(range(1,252))
    original=baseline('assets/gen1.bin');candidate=(assets/'gen1.bin').read_bytes()
    assert struct.unpack_from('<I',candidate,8)[0]==251
    assert original[16:16+151*32]==candidate[16:16+151*32], 'existing species records changed'
    old_pool=original[16+151*32:];new_pool=candidate[16+251*32:]
    assert new_pool.startswith(old_pool), 'existing names/offsets changed'
    old_front=read_fronts(baseline('assets/gen1_front.bin'))
    new_front=read_fronts((assets/'gen1_front.bin').read_bytes(),251)
    assert all(old_front[sid]==new_front[sid] for sid in range(1,152))
    assert baseline('assets/gen1_back.bin')[16:]==(assets/'gen1_back.bin').read_bytes()[16:16+151*576]
    stats=[list(map(int,m.split(','))) for m in re.findall(r'\{([0-9,]+)\}',(ROOT/'firmware/main/combat_gen2_stats.h').read_text())]
    assert stats==[r['stats'] for r in rows[:151]], 'original six-stat values changed'
    assert rows[200]['level_up']==[[1,237]] and rows[234]['level_up']==[[1+i*10,166] for i in range(10)]
    for r in rows:
        assert all(0<value<256 for value in r['stats'])
        assert all(1<=level<=100 and 1<=move<=251 for level,move in r['level_up'])
        assert all(1<=move<=251 for move in r['tm_hm'])
        assert all(1<=e['target']<=251 for e in r['evolutions'])
    # Acquisition graph; transaction tests separately verify rewards and full-box paths.
    sources={i:'existing Kanto acquisition' for i in range(1,152)}
    for route in result['routes']:
        for sid in route['species']:
            if sid!=201:sources.setdefault(sid,route['name'])
    for sid in (152,155,158):sources[sid]='starter choice / first two Goldenrod rescues'
    sources[175]='Togepi-only egg'
    sources[201]='four ruins investigations, 26 forms'
    for sid in (172,173,174,236,238,239,240,235):sources.setdefault(sid,'repeat Goldenrod rescues')
    for sid in (243,244,245,249,250,251):sources[sid]='dedicated repeatable investigation'
    changed=True
    while changed:
        changed=False
        for row in rows:
            if row['id'] not in sources:continue
            for evo in row['evolutions']:
                if evo['target'] not in sources:
                    sources[evo['target']]=f'evolution from {row["id"]} ({evo["method"]})';changed=True
    assert len(sources)==251,sorted(set(range(1,252))-sources.keys())
    result.update({'status':'PASS','scope':'isolated chapter core, not live world persistence',
                   'acquisition_plan':sources,'pending_special_mechanics':[]})
    if output:output.parent.mkdir(parents=True,exist_ok=True);output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print('PASS: old progress gates, 8 gyms, 4000 level bounds, locked egg, full-box retry, duplicate actions and final reward; acquisition reachability 251/251')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--assets',type=Path,required=True);p.add_argument('--report',type=Path)
    a=p.parse_args();verify(a.assets,a.report)
