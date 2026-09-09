#!/usr/bin/env python3
"""Real core and assets: effect semantics, learned repertoire, AI and version migration."""
import verify_trainer_campaign as h
h.CASES=r'''
static combat_mon_t a,d;static battle_round_t r;static uint32_t rng;
static void pair(void){combat_init(&a,25,60,500);combat_init(&d,143,50,500);memset(&r,0,sizeof(r));rng=123;}
static void hit(unsigned id){memset(&r,0,sizeof(r));r.by_pet=1;combat_turn(&a,&d,1024,&rng,50,id,&r);assert(combat_valid(&a)&&combat_valid(&d));}
static void learned(void){unsigned max=0;
 for(unsigned sid=1;sid<=151;sid++){uint16_t previous[COMBAT_MOVE_CAP],ids[COMBAT_MOVE_CAP];int old=0;
  for(unsigned lv=1;lv<=100;lv++){int n=combat_known_moves(sid,lv,ids,COMBAT_MOVE_CAP);if((unsigned)n>max)max=n;assert(n>=old);
   for(int i=0;i<n;i++){move_t m;assert(combat_move(ids[i],&m)&&m.id==ids[i]);if(i)assert(ids[i]>ids[i-1]);assert(combat_learn_level(sid,ids[i])<=lv);}
   for(int i=0;i<old;i++){bool found=false;for(int j=0;j<n;j++)found|=previous[i]==ids[j];assert(found);}memcpy(previous,ids,n*2);old=n;
  }
 }
 uint16_t ids[COMBAT_MOVE_CAP],evolved[COMBAT_MOVE_CAP];int n=combat_known_moves(25,60,ids,COMBAT_MOVE_CAP),nn=combat_known_moves(26,60,evolved,COMBAT_MOVE_CAP);assert(n>4&&nn>=n);
 for(int i=0;i<n;i++){bool found=false;for(int j=0;j<nn;j++)found|=ids[i]==evolved[j];assert(found);}
 printf("\"max_learned\":%u,",max);tests++;
}
static void effects(void){
 pair();a.hp=100;hit(105);assert(a.hp==350&&d.hp==500&&r.healed==250&&r.self_target&&!r.no_effect);
 pair();d.last_move=53;hit(102);assert(a.mimic_move==53&&!r.damage&&d.hp==500);
 pair();hit(160);assert(a.converted&&!r.damage);
 assert(combat_priority(98)>combat_priority(33)&&combat_priority(68)<combat_priority(33));
 pair();hit(14);assert(a.attack==2&&d.attack==0&&r.self_target&&!r.damage);
 pair();hit(43);assert(d.defense==-1&&a.defense==0&&!r.self_target);
 pair();d.species=1;hit(77);assert(!d.status&&r.no_effect); // Poison immunity.
 pair();hit(86);assert(d.status==3);assert(combat_speed(&d)<battle_effective_stat(30,50));
 pair();d.species=74;hit(86);assert(d.status==0&&r.no_effect);
 pair();hit(98);assert(!d.status); // Not every move of a type invents an ailment.
 pair();hit(49);assert(r.damage==20);pair();hit(82);assert(r.damage==40);pair();hit(69);assert(r.damage==60);
 pair();hit(162);assert(r.damage==250);pair();d.species=92;hit(49);assert(!r.damage&&d.hp==500);
 pair();hit(24);assert(r.hits==2&&r.damage>0);pair();hit(3);assert(r.hits>=2&&r.hits<=5);
 pair();a.hp=100;hit(71);assert(r.healed&&a.hp>100&&d.hp<500);
 pair();hit(38);assert(a.hp<500&&d.hp<500);
 pair();hit(120);assert(a.hp==0);
 pair();hit(76);assert(r.charging&&d.hp==500&&a.charge);hit(76);assert(!r.charging&&d.hp<500&&!a.charge);
 pair();hit(63);assert(a.recharge&&r.damage);unsigned hp=d.hp;hit(33);assert(r.skipped==6&&d.hp==hp&&!a.recharge);
 pair();hit(164);assert(a.hp==375&&a.substitute==125);combat_mon_t tmp=a;a=d;d=tmp;hit(33);assert(d.hp==375&&d.substitute<125);
 pair();a.hp=100;a.status=1;hit(156);assert(a.hp==500&&a.status==4&&a.sleep==2);
 pair();hit(92);assert(d.status==1&&d.toxic==1);tmp=a;a=d;d=tmp;hit(150);unsigned first=500-a.hp;hit(150);assert(500-a.hp>2*first);
 pair();a.species=132;hit(144);assert(a.transform_species==143&&a.hp==500);
 pair();a.hp=200;d.status=0;hit(138);assert(r.no_effect&&d.hp==500&&a.hp==200);
 for(unsigned id=1;id<=250;id++)for(unsigned seed=1;seed<=25;seed++){
  if(!combat_move(id,&(move_t){0}))continue;
  pair();rng=seed;a.hp=250;hit(id);assert(a.hp<=a.max_hp&&d.hp<=d.max_hp&&r.move_id>=1&&combat_move(r.move_id,&(move_t){0}));
 }
 tests++;
}
static void ai(void){bool selected[251]={0};unsigned count=0;
 pair();for(unsigned seed=1;seed<=600;seed++){uint32_t random=seed;uint16_t id=combat_choose(&a,&d,&random);assert(combat_move(id,&(move_t){0}));assert(combat_learn_level(a.species,id)<=a.level);selected[id]=true;}
 for(unsigned i=1;i<=250;i++)count+=selected[i];assert(count>=3);
 combat_mon_t copy=a;uint32_t x=42,y=42;assert(combat_choose(&a,&d,&x)==combat_choose(&copy,&d,&y)&&x==y);
 // Existing PP bytes no longer constrain or spend moves.
 trainer_store_t st={.wild_wins=1};mon_t member={.species_id=25,.level=60,.hp=100};assert(trainer_begin(&st,0,&member,1,1024,7));
 memset(st.session.sides[0].mons[0].pp,0,4);trainer_event_t e;assert(trainer_step(&st,&e));assert(e.attack.move_id&&memcmp(st.session.sides[0].mons[0].pp,(uint8_t[4]){0},4)==0);assert(!trainer_choose_move(&st,0));
 printf("\"ai_distinct_moves\":%u,",count);tests++;
}
static void migration(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);save_t current;assert(save_read(&current));
 for(unsigned v=5;v<=8;v++){
  save_v8_t old={0};memcpy(&old,&current,sizeof(save_v6_t));old.version=v;old.challenge.wild_wins=17;old.challenge.defeated=3;old.achievements=(achievement_store_t){.evolutions=4,.claimed=17};
  old.challenge.session.active=1;old.challenge.session.trainer=2;old.challenge.session.rng=123;old.challenge.session.ability=1024;
  for(unsigned side=0;side<2;side++){trainer_side_v8_t *s=&old.challenge.session.sides[side];s->count=1;s->mons[0]=(trainer_mon_v8_t){.species=25,.level=30,.hp=70,.max_hp=100,.moves={84,98},.pp={0,0},.status=1,.attack=2};}
  disk_len=v==5?sizeof(save_v5_t):v==6?sizeof(save_v6_t):v==7?sizeof(save_v7_t):sizeof(save_v8_t);memcpy(disk,&old,disk_len);
  save_t next;assert(save_read_status(&next)==SAVE_READ_MIGRATED&&next.version==SAVE_VERSION);assert(!memcmp(next.party,old.party,PARTY_BYTES));
  if(v>=7){assert(next.challenge.session.active&&next.challenge.session.sides[0].mons[0].hp==70&&next.challenge.session.sides[0].mons[0].attack==2&&next.challenge.session.rng==123&&next.challenge.defeated==3);}
  if(v==8)assert(next.achievements.evolutions==4&&next.achievements.claimed==17);
  assert(save_write(&next));save_t after;assert(save_read(&after));assert(!memcmp(&next,&after,sizeof(next)));
 }
 tests++;
}
int main(void){assert(assets_init());printf("{");learned();effects();ai();migration();printf("\"cases\":%u,\"moves\":191,\"save_version\":%d,\"save_bytes\":%zu,\"sanitized\":true}\n",tests,SAVE_VERSION,sizeof(save_t));}
'''
# Optional read-only real-device snapshot; never writes back to the hardware.
if __name__ == '__main__':
 import sys,json
 if len(sys.argv)>1:
  path=json.dumps(str(__import__('pathlib').Path(sys.argv[1]).resolve()))
  check=r'''static void device_snapshot(void){
   FILE *fp=fopen(PATH,"rb");assert(fp);disk_len=fread(disk,1,sizeof(disk),fp);fclose(fp);
   assert(disk_len==sizeof(save_v8_t));save_v8_t old;memcpy(&old,disk,sizeof(old));save_t next;
   assert(save_read_status(&next)==SAVE_READ_MIGRATED&&next.version==9);
   assert(!memcmp(next.party,old.party,PARTY_BYTES));
   assert(!memcmp(&next.inventory,&old.inventory,sizeof(next.inventory)));
   assert(!memcmp(&next.achievements,&old.achievements,sizeof(next.achievements)));
   assert(next.species==old.species&&next.level==old.level&&next.exp==old.exp);
   assert(next.challenge.defeated==old.challenge.defeated);tests++;
  }'''.replace('PATH',path)
  h.CASES=h.CASES.replace('int main(void)',check+'\nint main(void)').replace('learned();effects();ai();migration();','learned();effects();ai();migration();device_snapshot();')
 h.run()
