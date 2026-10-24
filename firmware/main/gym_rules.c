#include "gym_rules.h"
#include "trainer.h"
#include <string.h>
static combat_mon_t *enemy(trainer_session_t *s){return &s->sides[1].mons[s->sides[1].active];}
static unsigned kind(const gym_rules_t *g,const trainer_session_t *s){
 if(!g||!g->version)return GYM_NONE;
 if(g->kind!=GYM_ELM)return g->kind;
 unsigned n=s->sides[1].active;return n<2?GYM_VEIL:n==4?GYM_DRAGON:n==5?GYM_FIST:GYM_NONE;
}
const char *gym_rules_name(unsigned k){static const char *const names[]={"常规对战","暴风领域","虫巢协同","应援阵容","双相幻幕","蓄势重拳","钢铁阵列","寒潮推进","龙阵接力","空木三重试炼","湖泊狂怒"};return k<=GYM_LAKE?names[k]:names[0];}
const char *gym_rules_hint(unsigned k){static const char *const hints[]={"使用伙伴熟悉的招式", "麻痹或降速压制风场", "火或飞行命中拆两层", "中毒灼伤阻止半血恢复", "物理特殊交替破解护幕", "降攻或控制解除蓄势", "两次火水特攻拆除装甲", "火系命中驱散寒潮", "两名伙伴不同属性破阵", "双输出破幕 控制压轴", "降攻或控制平息狂怒"};return k<=GYM_LAKE?hints[k]:hints[0];}
void gym_rules_enter(gym_rules_t *g,trainer_session_t *s){
 if(!g||!g->version||s->sides[1].active>=6)return;
 gym_member_t *m=&g->member[s->sides[1].active];if(m->entered)return;
 m->entered=1;m->player=m->type=255;unsigned k=kind(g,s);
 if(k==GYM_FIST)m->until=g->round+2;
 if(k==GYM_DRAGON)m->until=g->round+3;
 if(g->kind==GYM_ELM){combat_mon_t *e=enemy(s);if(s->sides[1].active==2&&e->speed<6)e->speed++;if(s->sides[1].active==3&&combat_sp_def_stage(e)<6)e->safety.special_defense++;}
}
void gym_rules_begin(gym_rules_t *g,trainer_session_t *s,bool champion){
 memset(g,0,sizeof(*g));
 if(s->trainer==TRAINER_LAKE_BOSS)g->kind=GYM_LAKE;
 else if(champion&&trainer_is_johto(s->trainer))g->kind=s->trainer<TRAINER_JOHTO_FIRST+8?s->trainer-TRAINER_JOHTO_FIRST+1:GYM_ELM;
 if(!g->kind)return;
 g->version=1;if(g->kind==GYM_SWARM)g->stacks=2;if(g->kind==GYM_COLD)g->stacks=1;g->switch_after=3;gym_rules_enter(g,s);
}
bool gym_rules_valid(const gym_rules_t *g){
 if(!g)return false;
 if(!g->version){gym_rules_t zero={0};return !memcmp(g,&zero,sizeof(zero));}
 if(g->version!=1||!g->kind||g->kind>GYM_LAKE||g->round>400||g->pause_until>410||g->switch_after>410||g->stacks>3||g->switches>2)return false;
 for(unsigned i=0;i<6;i++){const gym_member_t *m=&g->member[i];if(m->until>410||m->exposed>410||m->entered>1||m->broken>1||m->hits>2||m->once>1||(m->player>5&&m->player!=255)||(m->type>=BATTLE_TYPE_COUNT&&m->type!=255))return false;}
 return true;
}
unsigned gym_rules_speed(const gym_rules_t *g,unsigned side,unsigned speed){
 if(!g||!g->version)return speed;
 if(g->kind==GYM_WIND&&side==1&&g->round>=g->pause_until)return speed*150/100;
 if(g->kind==GYM_COLD&&side==0)return speed*(100-15*g->stacks)/100;
 return speed;
}
void gym_rules_round(gym_rules_t *g){if(!g||!g->version)return;g->round++;if(g->kind==GYM_COLD&&g->round>=g->pause_until&&!(g->round%2)&&g->stacks<3)g->stacks++;}
static unsigned scale(void *opaque,const combat_mon_t *a,const combat_mon_t *d,const move_t *move,unsigned damage){
 gym_context_t *c=opaque;gym_rules_t *g=c->rules;trainer_session_t *s=c->session;if(!g||!g->version)return damage;
 unsigned k=kind(g,s),i=s->sides[1].active;gym_member_t *m=&g->member[i];unsigned percent=100;
 if(c->side){
  if(k==GYM_WIND&&g->round>=g->pause_until)percent=move->type==TY_FLYING&&gym_rules_speed(g,1,combat_speed(a))>combat_speed(d)?170:140;
  if(k==GYM_SWARM)percent=100+25*g->stacks;
  if(k==GYM_VEIL&&!m->broken)percent=g->kind==GYM_ELM?100:140;
  if(k==GYM_FIST&&!m->broken&&g->kind!=GYM_ELM)percent=130;
  if(k==GYM_CHEER&&i>=(unsigned)(s->sides[1].count-2)){for(unsigned n=0;n+2<s->sides[1].count;n++)if(s->sides[1].mons[n].hp){percent=125;break;}}
  if(k==GYM_FIST&&!m->broken&&!m->once&&g->round>=m->until&&move->type==(g->kind==GYM_ELM?TY_FIRE:TY_FIGHTING))percent=g->kind==GYM_ELM?150:200;
  if(k==GYM_COLD)percent=100+(move->type==TY_ICE?25:10)*g->stacks;
  if(k==GYM_DRAGON&&!m->broken&&g->round<m->until)percent=130;
  if(k==GYM_LAKE&&move->type==TY_WATER){percent=m->broken?100:130;if(m->once&&m->until&&g->round>=m->until)percent+=50;}
 }else{
  if(k==GYM_WIND&&g->round>=g->pause_until){species_t sp;if(assets_species(d->species,&sp)&&battle_effectiveness(move->type,sp.type1,sp.type2)<=100)percent=45;}
  if(k==GYM_SWARM)percent=100-20*g->stacks;
  if(k==GYM_VEIL&&!m->broken)percent=move->special==(i%2)?(g->kind==GYM_ELM?55:30):(g->kind==GYM_ELM?100:70);
  if(k==GYM_FIST&&!m->broken&&g->round<m->until)percent=g->kind==GYM_ELM?60:40;
  if(k==GYM_ARMOR&&!m->broken)percent=move->special?60:30;
  if(k==GYM_COLD&&move->type!=TY_FIRE)percent=100-15*g->stacks;
  if(k==GYM_DRAGON&&!m->broken&&g->round<m->until)percent=50;
  if(k==GYM_LAKE&&!m->broken)percent=50;
  if(m->exposed>g->round)percent=k==GYM_DRAGON?130:125;
 }
 unsigned value=damage*percent/100;return value?value:1;
}
static bool control(unsigned id){return id==45||id==204||id==86||id==78||id==137||id==47||id==79||id==95||id==142;}
static unsigned utility(void *opaque,const combat_mon_t *a,const combat_mon_t *d,const move_t *move,unsigned score){
 (void)a;(void)d;gym_context_t *c=opaque;gym_rules_t *g=c->rules;if(!g||!g->version||c->side)return score;
 unsigned k=kind(g,c->session);gym_member_t *m=&g->member[c->session->sides[1].active];bool breaker=false;
 if(k==GYM_WIND&&g->round>=g->pause_until)breaker=move->id==86||move->id==78||move->id==137||move->id==81||move->id==196||move->id==61||move->id==145;
 if(k==GYM_SWARM&&g->stacks)breaker=move->power&&(move->type==TY_FIRE||move->type==TY_FLYING);
 if(k==GYM_CHEER&&!m->once)breaker=move->id==92||move->id==77||move->id==139;
 if(k==GYM_VEIL&&!m->broken)breaker=move->power&&move->special!=(c->session->sides[1].active%2);
 if((k==GYM_FIST||k==GYM_LAKE)&&!m->broken)breaker=control(move->id);
 if(k==GYM_ARMOR&&!m->broken)breaker=move->power&&move->special&&(move->type==TY_FIRE||move->type==TY_WATER);
 if(k==GYM_COLD&&g->stacks)breaker=move->power&&move->type==TY_FIRE;
 if(k==GYM_DRAGON&&!m->broken&&g->round<m->until)breaker=move->power&&m->player!=c->session->sides[0].active&&m->type!=move->type;
 return breaker?score+80:score;
}
combat_context_t gym_rules_context(gym_context_t *c){return (combat_context_t){.opaque=c,.damage=scale,.utility=utility};}
void gym_rules_after(gym_context_t *c,const battle_round_t *r,unsigned old_sub,int old_attack,int old_speed,unsigned old_status){
 gym_rules_t *g=c->rules;trainer_session_t *s=c->session;if(!g||!g->version)return;
 unsigned k=kind(g,s);gym_member_t *m=&g->member[s->sides[1].active];combat_mon_t *e=enemy(s);
 combat_mon_t *d=&s->sides[c->side^1].mons[s->sides[c->side^1].active];
 bool hit=!r->skipped&&!r->missed&&!r->no_effect&&!r->charging&&(r->damage||d->substitute<old_sub);
 bool controlled=!c->side&&((e->attack<old_attack)||((e->status==3||e->status==4)&&e->status!=old_status));
 if(!c->side){
  if(k==GYM_WIND&&(e->speed<old_speed||(e->status==3&&old_status!=3)))g->pause_until=g->round+4;
  if(k==GYM_SWARM&&hit&&(r->move_type==TY_FIRE||r->move_type==TY_FLYING))g->stacks=g->stacks>2?g->stacks-2:0;
  move_t move;bool special=combat_move(r->move_id,&move)&&move.special;
  if(r->move_id==237)special=r->move_type==TY_FIRE||r->move_type==TY_WATER||r->move_type==TY_GRASS||r->move_type==TY_ELECTRIC||r->move_type==TY_ICE||r->move_type==TY_PSYCHIC||r->move_type==TY_DRAGON||r->move_type==TY_DARK;
  if(k==GYM_VEIL&&!m->broken&&hit&&special!=(s->sides[1].active%2)){m->broken=1;m->exposed=g->round+4;}
  if((k==GYM_FIST||k==GYM_LAKE)&&controlled)m->broken=1;
  if(k==GYM_ARMOR&&!m->broken&&hit&&special&&(r->move_type==TY_FIRE||r->move_type==TY_WATER)&&++m->hits==2){m->broken=1;m->exposed=g->round+4;}
  if(k==GYM_COLD&&hit&&r->move_type==TY_FIRE){g->stacks=g->stacks>2?g->stacks-2:0;g->pause_until=g->round+3;}
  if(k==GYM_DRAGON&&!m->broken&&g->round<m->until&&hit){if(m->hits&&m->player!=s->sides[0].active&&m->type!=r->move_type){m->broken=1;m->exposed=g->round+3;}else if(!m->hits){m->hits=1;m->player=s->sides[0].active;m->type=r->move_type;}}
  if(k==GYM_LAKE&&!m->once&&e->hp&&e->hp*2<e->max_hp){m->once=1;m->until=g->round+1;}
 }else{
  if(k==GYM_SWARM&&hit&&r->move_type==TY_BUG&&g->stacks<3)g->stacks++;
  if(k==GYM_FIST&&!r->skipped&&!r->charging&&g->round>=m->until&&r->move_type==(g->kind==GYM_ELM?TY_FIRE:TY_FIGHTING))m->once=1;
  if(k==GYM_LAKE&&m->until&&g->round>=m->until&&!r->skipped&&!r->charging&&r->move_type==TY_WATER)m->until=0;
 }
 /* Recoil and end-of-action status damage can also cross the half-HP threshold. */
 if(k==GYM_CHEER&&!m->once&&e->hp&&e->hp*2<e->max_hp){m->once=1;if(e->status!=1&&e->status!=2){unsigned hp=e->hp+e->max_hp*30/100;e->hp=hp>e->max_hp?e->max_hp:hp;if(e->defense<6)e->defense++;}}
}
int gym_rules_switch(gym_rules_t *g,const trainer_session_t *s){
 if(!g||!g->version||g->kind==GYM_LAKE||g->switches>=2||g->round<g->switch_after)return -1;
 const trainer_side_t *side=&s->sides[1];const combat_mon_t *e=&side->mons[side->active],*p=&s->sides[0].mons[s->sides[0].active];
 if(e->charge||e->bide||e->trap||e->recharge||!e->hp)return -1;
 species_t es;move_t last;if(!combat_move(p->last_move,&last)||!last.power||!assets_species(e->species,&es))return -1;
 unsigned risk=battle_effectiveness(last.type,es.type1,es.type2);if(risk<200||e->hp*2>e->max_hp)return -1;
 int best=-1;unsigned best_risk=risk;
 for(unsigned i=0;i<side->count;i++){if(i==side->active||!side->mons[i].hp||(g->kind==GYM_ELM&&i/2!=side->active/2))continue;species_t sp;if(!assets_species(side->mons[i].species,&sp))continue;unsigned value=battle_effectiveness(last.type,sp.type1,sp.type2);if(value<best_risk){best=i;best_risk=value;}}
 return best;
}

const char *gym_rules_effect(unsigned k){static const char *const text[]={"标准等级与伤害", "提速50% 非克制减伤55%", "每层增伤25% 减伤20%", "半血回复30% 每只一次", "交替护幕 减伤30%或70%", "蓄势减伤60% 格斗双倍", "物理减伤70% 特殊40%", "每层减速15% 冰伤+25%", "龙鳞三回合 减伤50%", "护幕 雷雨 海天三阶段", "狂怒减伤50% 控制解除"};return k<=GYM_LAKE?text[k]:text[0];}
