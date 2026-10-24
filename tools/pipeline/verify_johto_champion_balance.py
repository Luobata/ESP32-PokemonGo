#!/usr/bin/env python3
"""Real automatic battles: reproducible matchup coverage, not a player win-rate claim."""
import verify_trainer_campaign as h
h.CASES=r'''
static const uint8_t counters[9][6]={
 {26,135,76,95,82,131},{6,59,18,169,157,227},{68,214,94,197,65,237},
 {197,248,181,149,229,9},{65,196,94,169,80,103},{6,157,9,160,68,171},
 {6,59,68,82,171,131},{131,242,197,230,149,68},{68,248,171,130,242,131}};
static unsigned match(const combat_mon_t *a,const combat_mon_t *b){species_t x,y;assert(assets_species(a->species,&x)&&assets_species(b->species,&y));unsigned attack=battle_effectiveness(x.type1,y.type1,y.type2),second=x.type2==TY_NONE?0:battle_effectiveness(x.type2,y.type1,y.type2);if(second>attack)attack=second;unsigned risk=battle_effectiveness(y.type1,x.type1,x.type2);return (attack+10)*100/(risk+25);}
int main(void){assert(assets_init());
 for(unsigned gym=0;gym<9;gym++)for(unsigned profile=0;profile<7;profile++){
  unsigned wins=0,steps=0,longest=0,switches=0;
  for(unsigned seed=1;seed<=60;seed++){
   mon_t team[6]={0};move_policy_t policies[6]={0};trainer_store_t t={.defeated=16383};const trainer_info_t *info=trainer_info_progress(TRAINER_JOHTO_FIRST+gym,&t);
   unsigned level=info->levels[info->count-1];if(profile==5)level+=5;if(profile==6)level+=10;if(level>100)level=100;
   for(unsigned i=0;i<6;i++){unsigned species=profile>=1&&profile<=3?counters[gym][(i+profile-1)%6]:(unsigned[]){3,6,9,65,143,149}[i];team[i]=(mon_t){.species_id=species,.level=level,.hp=100};if(profile>=1&&profile<=3){for(unsigned id=1;id<=250;id++){move_t m;if(!combat_move(id,&m))continue;bool support=id==73||id==92||id==86||id==105||id==135||id==208||id==115||id==113||id==45||id==204;bool attack=m.power>=60&&m.accuracy>=80&&id!=120&&id!=153&&id!=38&&id!=36&&id!=206;move_policy_set(&policies[i],id,support||attack);}}}
   assert(trainer_begin_filtered(&t,TRAINER_JOHTO_FIRST+gym,team,profile==4?1:6,1024,seed*977,policies));gym_rules_t rules;trainer_rules_begin(&t,&rules,policies);trainer_event_t ev;unsigned n=0,swaps=0,milk=2;
   while(!t.session.finished&&n++<1000){
    trainer_session_t *s=&t.session;
    if(profile==3&&milk&&s->acted==3){combat_mon_t *a=&s->sides[0].mons[s->sides[0].active];if(a->hp&&a->hp*100<a->max_hp*35){unsigned hp=a->hp+items_milk_heal(a->max_hp);a->hp=hp>a->max_hp?a->max_hp:hp;a->status=a->sleep=0;s->next=1;s->acted=1;milk--;}}
    if(profile>=1&&profile<=3&&rules.kind==GYM_DRAGON&&!s->awaiting_replacement&&s->acted==3&&swaps<6){gym_member_t *m=&rules.member[s->sides[1].active];if(!m->broken&&m->hits&&m->player==s->sides[0].active&&rules.round<m->until){for(unsigned i=0;i<6;i++)if(i!=m->player&&s->sides[0].mons[i].hp){if(trainer_switch_rules(&t,i,false,policies,&rules)){swaps++;break;}}}}
    assert(trainer_step_rules(&t,&ev,policies,&rules));assert(trainer_store_valid(&t)&&gym_rules_valid(&rules));
    if(ev.kind==TRAINER_SWITCH_NEEDED){unsigned pick=6,best=0;for(unsigned i=0;i<s->sides[0].count;i++)if(s->sides[0].mons[i].hp){unsigned value=profile>=1&&profile<=3?match(&s->sides[0].mons[i],&s->sides[1].mons[s->sides[1].active]):1;if(pick==6||value>best){pick=i;best=value;}}assert(pick<6&&trainer_switch_rules(&t,pick,true,policies,&rules));}
   }
   assert(t.session.finished&&n<1000);wins+=t.session.won;steps+=n;switches+=rules.switches;if(n>longest)longest=n;
  }
  printf("gym=%u profile=%u wins=%u/60 mean_actions=%u longest=%u enemy_switches=%u\n",gym,profile,wins,steps/60,longest,switches);
 }
 return 0;
}
'''
if __name__=='__main__':h.run()
