// Desktop-only dungeon prototype bridge. Never linked into the device firmware.
static unsigned rogue_cards,rogue_guards;
static bool rogue_enabled;
static bool rogue_setup(const char *line){
 unsigned seed,node,cards,ids[3],hp[3],status[3],foes[3],level;
 if(sscanf(line,"%*s %u %u %u %u %u %u %u %u %u %u %u %u %u %u %u %u",&seed,&node,&cards,&ids[0],&ids[1],&ids[2],&hp[0],&hp[1],&hp[2],&status[0],&status[1],&status[2],&foes[0],&foes[1],&foes[2],&level)!=16)return false;
 if(node>7||cards>4095||level<1||level>100)return false;
 for(unsigned i=0;i<3;i++)if(ids[i]<1||ids[i]>151||foes[i]>151||status[i]>5||hp[i]>65535)return false;
 if(!foes[0]||(!foes[1]&&foes[2]))return false;
 nav_exit_current();rogue_enabled=true;rogue_cards=cards;rogue_guards=0;
 memset(&challenge,0,sizeof(challenge));challenge.defeated=255;
 party.party_count=3;
 for(unsigned i=0;i<3;i++)party.party[i]=(mon_t){.species_id=ids[i],.level=50,.exp=exp_for_level(50)};
 world.species=ids[0];world.level=50;world.exp=party.party[0].exp;
 world.pet.stamina=100*NURT_Q;world.pet.satiety=world.pet.mood=80*NURT_Q;
 inventory.quantity[ITEM_MILK]=0;
 if(!trainer_begin(&challenge,14+(node==7?2:node==4?1:0),party.party,3,1024,seed))return false;
 trainer_session_t *s=&challenge.session;
 s->sides[1].count=0;
 for(unsigned i=0;i<3;i++){
  combat_mon_t *m=&s->sides[0].mons[i];m->hp=hp[i]==65535?m->max_hp:hp[i]>m->max_hp?m->max_hp:hp[i];m->status=(cards&(1u<<10))?0:status[i];if(m->status==4)m->sleep=2;
  m->attack=!!(cards&(1u<<3));m->special=!!(cards&(1u<<4));
  m->defense=!!(cards&(1u<<5));m->safety.special_defense=!!(cards&(1u<<5));
  m->speed=!!(cards&(1u<<6));m->focus=!!(cards&(1u<<7));
  if(foes[i]){combat_init(&s->sides[1].mons[i],foes[i],level,combat_max_hp(foes[i],level));s->sides[1].count++;}
 }
 unsigned active=0;while(active<3&&!s->sides[0].mons[active].hp)active++;if(active==3)return false;
 s->sides[0].active=active;s->participated=1u<<active;s->acted=3;
 nav_go(PAGE_TRAINER);return true;
}
static bool rogue_restore(const char *hex){
 size_t len=sizeof(challenge);if(strlen(hex)!=len*2)return false;
 trainer_store_t candidate;unsigned char *bytes=(unsigned char*)&candidate;
 for(size_t i=0;i<len;i++){char pair[3]={hex[i*2],hex[i*2+1],0};char *end;unsigned n=strtoul(pair,&end,16);if(*end)return false;bytes[i]=n;}
 if(!trainer_store_valid(&candidate)||candidate.session.sides[0].count!=3)return false;
 challenge=candidate;nav_go(PAGE_TRAINER);return true;
}
static void rogue_state(void){
 printf(",\"rogue_blob\":\"");if(rogue_enabled)for(size_t i=0;i<sizeof(challenge);i++)printf("%02x",((unsigned char*)&challenge)[i]);printf("\",\"rogue_guards\":%u",rogue_guards);
}
static void rogue_before_step(trainer_store_t *st){
 if(!rogue_enabled)return;
 const combat_mon_t *m=&st->session.sides[0].mons[st->session.sides[0].active];species_t sp;unsigned boost=0;
 if(assets_species(m->species,&sp))for(unsigned i=0;i<3;i++)if((rogue_cards&(1u<<i))&&(sp.type1==i+1||sp.type2==i+1))boost=256;
 st->session.ability=1024+boost;
}
static void rogue_after_switch(trainer_store_t *st,unsigned slot){
 if(rogue_enabled&&(rogue_cards&(1u<<11))&&!(rogue_guards&(1u<<slot))){
  combat_mon_t *m=&st->session.sides[0].mons[slot];if(m->defense<6)m->defense++;rogue_guards|=1u<<slot;
 }
}
