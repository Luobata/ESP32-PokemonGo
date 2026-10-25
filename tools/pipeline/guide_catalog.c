/* Public guide export: call the same catalogs and eligibility rules as firmware. */
#include <stdio.h>
#include <assert.h>
#include "assets.h"
#include "exploration.h"
#include "achievements.h"
#include "trainer.h"
#include "evolution.h"
#ifdef GUIDE_JOHTO
#include "johto_routes.h"
#include "johto_activity.h"
#include "gym_rules.h"
#endif
#ifdef GUIDE_FIELD
#include "field_adventure.h"
#endif

static void string(const char *s,unsigned n){
 putchar('"');for(unsigned i=0;i<n;i++){unsigned char c=s[i];if(c=='"'||c=='\\')putchar('\\');if(c>=32)putchar(c);}putchar('"');
}
#define STR(s) string(s,(unsigned)strlen(s))
#include <string.h>
static void ids(const uint8_t *a,unsigned n){putchar('[');for(unsigned i=0;i<n&&a[i];i++)printf("%s%u",i?",":"",a[i]);putchar(']');}
int main(void){
 assert(assets_init());printf("{\"pokemon\":[");
 for(unsigned id=1;id<=assets_species_count();id++){
  species_t s;assert(assets_species(id,&s));unsigned rarity=0;int route=exploration_habitat(id,&rarity);
#ifdef GUIDE_JOHTO
  if(id>151)rarity=activity_rarity(id);
#endif
  printf("%s{\"id\":%u,\"name\":",id>1?",":"",id);string(s.name_zh,s.name_zh_len);
  printf(",\"type\":[%u,%u],\"rarity\":%u,\"habitat\":%d,\"chapter\":%u,\"catchRate\":%u,\"evolveTo\":%u,\"evolveLevel\":%u,\"trigger\":%u,\"weight\":%u,\"learnset\":[",s.type1,s.type2,rarity,route,exploration_unlock_chapter(id),s.catch_rate,s.evolve_to,s.evolve_level,s.evolve_trigger,s.weight_hg);
  bool found[512]={0};unsigned count=0;
  for(unsigned lv=1;lv<=100;lv++){move_t moves[256];int n=assets_known_moves(id,lv,moves,256);for(int i=0;i<n;i++)if(moves[i].id<512&&!found[moves[i].id]){found[moves[i].id]=true;printf("%s[%u,%u]",count++?",":"",moves[i].id,lv);}}
  printf("]");
#ifdef GUIDE_JOHTO
  evo_option_t options[EVO_OPTION_MAX];unsigned options_count=evo_options(id,s.evolve_trigger,s.evolve_to,s.evolve_level,options);
  printf(",\"evolutions\":[");
  for(unsigned i=0;i<options_count;i++){const evo_option_t *o=&options[i];printf("%s{\"target\":%u,\"item\":%u,\"level\":%u,\"intimacy\":%u,\"badges\":%u,\"training\":",i?",":"",o->target,o->item,o->level,o->intimacy,o->badges);STR(o->training?o->training:"");printf("}");}
  printf("]");
#endif
  printf("}");
 }
 printf("],\"maps\":[");
 for(unsigned map=0;map<EXPLORATION_MAPS;map++){
  const exploration_route_t *r=exploration_route(map);const exploration_region_t *region=exploration_region(map);
  printf("%s{\"id\":%u,\"name\":",map?",":"",map);STR(r->name);printf(",\"description\":");STR(r->description);
  if(region){printf(",\"condition\":");STR(region->condition);printf(",\"levels\":[%u,%u],\"deepMin\":%u,\"item\":%u,\"dungeon\":",region->min_level,region->max_level,exploration_region_level_min(region,true),region->item);STR(region->dungeon);printf(",\"pool\":");ids(region->pool,24);printf(",\"trails\":[");
   for(unsigned j=0;j<3;j++){const exploration_trail_t*t=exploration_region_trail(map,j);printf("%s{\"name\":",j?",":"");STR(t->name);printf(",\"pool\":");ids(t->species,12);printf(",\"rewards\":");ids(region->rewards[j],4);printf("}");}printf("]");
  }
#ifdef GUIDE_VISITORS
  if(region){uint8_t guests[12]={0};unsigned n=exploration_guest_candidates(map,guests);printf(",\"visitors\":");ids(guests,n);}
#endif
  printf("}");
 }
#ifdef GUIDE_JOHTO
 for(unsigned i=0;i<JOHTO_ROUTE_COUNT;i++){
  const johto_route_t *r=&JOHTO_ROUTES[i];printf(",{\"id\":%u,\"johto\":true,\"name\":",EXPLORATION_MAPS+i);STR(r->name);
  printf(",\"description\":");STR(r->activity);printf(",\"condition\":\"城都 %u 徽章\",\"levels\":[%u,%u],\"pool\":",r->badges,r->min_level,r->max_level);ids(r->species,r->count);
  printf(",\"trails\":[");for(unsigned j=0;j<JOHTO_PATH_COUNT;j++){const johto_path_t *t=johto_path(i,j);printf("%s{\"name\":",j?",":"");STR(t->name);printf(",\"pool\":");ids(t->species,4);printf(",\"rewards\":[]}");}printf("]}");
 }
#endif
 printf("],\"items\":[");
 for(unsigned id=0;id<ITEM_COUNT;id++){
  const item_info_t*a=items_info(id);printf("%s{\"id\":%u,\"name\":",id?",":"",id);STR(a->name);printf(",\"description\":");STR(a->description);printf(",\"kind\":%u,\"capacity\":%u,\"evolutions\":[",a->kind,items_capacity(id));
  unsigned count=0;for(unsigned sid=1;sid<=assets_species_count();sid++){nurture_t pet;item_use_result_t result;nurture_init(&pet);if(items_apply(id,sid,100,&pet,&result)==ITEM_USE_OK&&result.species_after!=sid)printf("%s[%u,%u]",count++?",":"",sid,result.species_after);}printf("]}");
 }
 printf("],\"achievements\":[");
 for(unsigned i=0;i<ACHIEVEMENT_COUNT;i++){const achievement_info_t*a=achievement_info(i);printf("%s{\"id\":%u,\"name\":",i?",":"",i);STR(a->name);printf(",\"description\":");STR(a->description);printf(",\"item\":%u,\"quantity\":%u}",a->item,a->quantity);}
 printf("],\"trainers\":[");
 for(unsigned i=0;i<TRAINER_TOTAL;i++){const trainer_info_t*t=trainer_info(i);printf("%s{\"id\":%u,\"name\":",i?",":"",i);STR(t->name);printf(",\"badge\":");STR(t->badge);printf(",\"team\":");ids(t->species,t->count);printf(",\"levels\":");ids(t->levels,t->count);printf("}");}
 printf("],\"activities\":[");
 for(unsigned i=0;i<8;i++){const exploration_activity_t*a=exploration_activity(i);printf("%s{\"name\":",i?",":"");STR(a->name);printf(",\"story\":");STR(a->story);printf(",\"route\":%u,\"level\":%u,\"item\":%u,\"pool\":",a->route,a->level,a->item);ids(a->species,8);printf("}");}
 printf("],\"chapters\":[");
 for(unsigned i=0;i<EXPLORATION_CHAPTERS;i++){const exploration_chapter_t*c=exploration_chapter(i);printf("%s{\"name\":",i?",":"");STR(c->name);printf(",\"condition\":");STR(c->condition);printf("}");}
 printf("],\"moves\":[");unsigned count=0;
 for(unsigned i=1;i<512;i++){move_t m;if(!assets_move(i,&m))continue;printf("%s{\"id\":%u,\"name\":",count++?",":"",i);string(m.name_zh,m.name_zh_len);printf(",\"type\":%u,\"power\":%u,\"accuracy\":%u}",m.type,m.power,m.accuracy);}
 printf("],\"shiny\":[");for(unsigned i=0;i<SHINY_SOURCE_COUNT;i++)printf("%s%u",i?",":"",enc_shiny_denominator(i));printf("]");
#ifdef GUIDE_JOHTO
 printf(",\"johtoGyms\":[");trainer_store_t champion={.defeated=1u<<13};
 for(unsigned i=0;i<9;i++){const trainer_info_t *t=trainer_info_progress(TRAINER_JOHTO_FIRST+i,&champion);printf("%s{\"name\":",i?",":"");STR(t->name);printf(",\"team\":");ids(t->species,t->count);printf(",\"levels\":");ids(t->levels,t->count);printf(",\"rule\":");STR(gym_rules_name(i+1));printf(",\"effect\":");STR(gym_rules_effect(i+1));printf(",\"hint\":");STR(gym_rules_hint(i+1));printf("}");}printf("]");
 printf(",\"researchRewards\":[");for(unsigned i=0;i<JOHTO_REWARD_COUNT;i++){const johto_research_reward_t *r=&JOHTO_REWARDS[i];printf("%s{\"item\":%u,\"route\":%u,\"badges\":%u,\"step\":%u}",i?",":"",19+i,EXPLORATION_MAPS+r->route,r->badges,r->step);}printf("]");
#endif
#ifdef GUIDE_FIELD
 printf(",\"fieldAdventure\":{\"cost\":%u,\"radarCooldownSeconds\":%u,\"mapCooldownSeconds\":%u,\"radarDenominator\":%u,\"mapDenominator\":%u,\"maps\":[",FIELD_COST,FIELD_RADAR_COOLDOWN,FIELD_MAP_COOLDOWN,field_shiny_denominator(FIELD_RADAR),field_shiny_denominator(0));
 for(unsigned i=0;i<FIELD_MAP_COUNT;i++)printf("%s{\"id\":%u,\"badges\":%u}",i?",":"",i,field_map_badges(i));
 printf("]}");
#endif
 printf("}\n");
}
