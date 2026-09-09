#!/usr/bin/env python3
"""Selected Gen2 mechanics, type boundaries and move learning with real C/assets."""
import verify_trainer_campaign as h
import json
from pathlib import Path
chart=json.loads((Path(__file__).resolve().parents[2]/"data/pokemon_moves/gold_silver_types.json").read_text())["multipliers"]
h.CASES="static const unsigned GOLD_CHART[17][17]={"+",".join("{"+",".join(map(str,r))+"}" for r in chart)+"};\n"+r'''
static battle_round_t turn(unsigned id,combat_mon_t *a,combat_mon_t *d,unsigned seed){battle_round_t r={.by_pet=true};uint32_t rng=seed;combat_turn(a,d,1024,&rng,50,id,&r);assert(combat_valid(a)&&combat_valid(d));return r;}
static void setup(combat_mon_t *a,combat_mon_t *d){combat_init(a,25,60,500);combat_init(d,143,60,500);a->hp=250;}
int main(void){assert(assets_init());
 for(unsigned a=0;a<17;a++)for(unsigned d=0;d<17;d++)assert(battle_effectiveness(a,d,TY_NONE)==GOLD_CHART[a][d]);
 unsigned count=0;for(unsigned id=1;id<=250;id++){move_t m;if(combat_move(id,&m)){count++;assert(m.type<17);}}
 assert(count==191);assert(combat_priority(183)==1&&combat_priority(245)==1);
 assert(battle_effectiveness(TY_GHOST,TY_PSYCHIC,TY_NONE)==200);
 assert(battle_effectiveness(TY_DARK,TY_PSYCHIC,TY_NONE)==200);
 assert(battle_effectiveness(TY_POISON,TY_STEEL,TY_NONE)==0);
 assert(battle_effectiveness(TY_FIGHTING,TY_STEEL,TY_NONE)==200);
 assert(battle_effectiveness(TY_PSYCHIC,TY_DARK,TY_NONE)==0);
 combat_mon_t a,d;battle_round_t r;setup(&a,&d);d.hp=1;r=turn(206,&a,&d,1);assert(!r.missed&&d.hp==1&&r.damage==0);
 setup(&a,&d);a.status=5;r=turn(172,&a,&d,1);assert(!a.status&&!r.skipped);
 setup(&a,&d);r=turn(202,&a,&d,1);assert(r.damage&&r.healed&&a.hp==250+r.healed);
 setup(&a,&d);d.evasion=6;a.accuracy=-6;r=turn(185,&a,&d,1);assert(!r.missed&&r.damage);
 setup(&a,&d);r=turn(204,&a,&d,1);assert(d.attack==-2);
 setup(&a,&d);r=turn(189,&a,&d,1);assert(d.accuracy==-1);
 unsigned steel=0,ancient=0,shadow=0;
 for(unsigned seed=1;seed<200;seed++){
  setup(&a,&d);r=turn(211,&a,&d,seed);steel+=a.defense==1;
  setup(&a,&d);r=turn(246,&a,&d,seed);if(a.attack){assert(a.attack==1&&a.defense==1&&a.special==1&&a.speed==1);ancient++;}
  setup(&a,&d);d.species=65;r=turn(247,&a,&d,seed);assert(r.mult==200);shadow+=d.special==-1;
 }
 assert(steel&&ancient&&shadow);
 setup(&a,&d);d.charge=1;d.charge_move=19;r=turn(239,&a,&d,1);assert(!r.missed&&r.damage);
 setup(&a,&d);r=turn(200,&a,&d,1);assert(a.charge&&a.charge_move==200);r=turn(200,&a,&d,2);assert(!a.charge&&a.confusion);
 setup(&a,&d);d.species=81;r=turn(188,&a,&d,1);assert(r.no_effect&&!r.damage&&!d.status);
 printf("{\"supported\":%u,\"selected_added\":25,\"type_chart\":\"Gold/Silver\",\"mechanics_pass\":true,\"save_bytes\":%zu}\n",count,sizeof(save_t));
}
'''
h.run()
