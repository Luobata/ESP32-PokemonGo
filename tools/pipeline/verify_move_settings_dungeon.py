#!/usr/bin/env python3
"""Reserved party slots, forced replacements and reboot preserve dungeon policies."""
import verify_dungeon_rewards as base
h=base.harness
h.CASES=h.CASES[:h.CASES.index('int main(')]+r'''
int main(void){
 assert(assets_init());setup();unsigned keep[3]={53,57,34};world_party_t p;world_party_snapshot(&p);
 for(unsigned j=0;j<3;j++){
  mon_t m=p.members[chosen[j]];uint16_t ids[COMBAT_MOVE_CAP];int n=combat_known_moves(m.species_id,m.level,ids,COMBAT_MOVE_CAP);
  assert(combat_learn_level(m.species_id,keep[j])<=m.level);
  for(int i=0;i<n;i++)if(ids[i]!=keep[j])assert(world_move_set(chosen[j],&m,ids[i],false)==WORLD_SWITCH_OK);
 }
 assert(dungeon_new(chosen,3,123));assert(world_move_set(1,&p.members[1],53,false)==WORLD_SWITCH_BUSY);
 run.battle.session.sides[0].mons[0].hp=0;assert(commit(&run));trainer_event_t e;
 assert(dungeon_step(&e)&&e.kind==TRAINER_SWITCH_NEEDED);assert(dungeon_switch(1,true));
 assert(run.battle.session.planned[0]==57||run.battle.session.planned[0]==165);
 restart();assert(run.slots[1]==2&&!move_policy_allows(&s_party.policies[2],33));
 unsigned attacks=0;
 for(unsigned i=0;i<600&&!run.battle.session.finished;i++){
  assert(dungeon_step(&e));if(e.kind==TRAINER_SWITCH_NEEDED){bool ok=false;for(unsigned j=0;j<3;j++)if(dungeon_switch(j,true)){ok=true;break;}assert(ok);}
  if(e.kind==TRAINER_ATTACK&&e.side==0){unsigned slot=run.battle.session.sides[0].active;assert(e.attack.move_id==keep[slot]||e.attack.move_id==165||!e.attack.move_id);attacks++;}
 }
 assert(run.battle.session.finished&&attacks>0);printf("{\"passed\":true,\"player_attacks\":%u,\"reserved_slot_mapping\":true,\"forced_switch\":true,\"reboot\":true}\n",attacks);
 return 0;
}
'''
if __name__=='__main__':h.run()
