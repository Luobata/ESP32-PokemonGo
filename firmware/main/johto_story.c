#include "johto_story.h"
#include "exp.h"
#include "combat.h"
#include <string.h>
#include <limits.h>
void johto_story_init(johto_story_t *s){memset(s,0,sizeof(*s));s->version=1;}
bool johto_story_valid(const johto_story_t *s){
 if(!s->version){const uint8_t *p=(const void*)s;for(unsigned i=0;i<sizeof(*s);i++)if(p[i])return false;return true;}
 if(s->version!=1||s->forms_seen>>26||s->forms_caught>>26||(s->forms_caught&~s->forms_seen)||s->ruins>15||s->ruin_group>3||s->ruin_step>2||s->rescue_step>3||s->tower_seen>1||s->legend_visits>63||s->forest_visits>3||s->ending_seen>1)return false;
 for(unsigned i=0;i<4;i++)if(s->ruin_misses[i]>5)return false;
 if(s->rescue_step){if(!s->rescue_partner.species_id||s->rescue_partner.species_id==175||s->rescue_partner.species_id>251||s->rescue_partner.level!=35||s->rescue_partner.hp!=100||!combat_individual_valid(&s->rescue_partner))return false;}
 else{const uint8_t *p=(const void*)&s->rescue_partner;for(unsigned i=0;i<sizeof(s->rescue_partner);i++)if(p[i])return false;}
 return true;
}
unsigned johto_rescue_at(const johto_story_t *s){return s->rescues<2?6u*(s->rescues+1):s->rescue_next;}
bool johto_rescue_ready(const johto_story_t *s,const johto_state_t *j){return johto_badges(j)>=2&&j->research[2]>=johto_rescue_at(s);}
bool johto_rescue_begin(johto_story_t *s,const johto_state_t *j,uint32_t seed){
 if(s->rescue_step||!johto_rescue_ready(s,j))return false;
 if(!s->version)s->version=1;
 unsigned id=0;if(s->rescues<2){unsigned n=0;for(unsigned k=0;k<3;k++){unsigned v=152+k*3;if(v!=j->starter&&n++==s->rescues){id=v;break;}}}
 else id=(unsigned[]){172,173,174,236,238,239,240,235}[seed%8];
 s->rescue_seed=seed;s->rescue_step=1;s->rescue_partner=(mon_t){.species_id=id,.level=35,.exp=exp_for_level(35),.hp=100,.intimacy=25,.nickname_idx=255,.flags=seed%32==0};return true;
}
unsigned johto_rescue_answer(const johto_story_t *s){return (s->rescue_seed>>(s->rescue_step*3))%3;}
bool johto_rescue_choose(johto_story_t *s,unsigned choice){if(!s->rescue_step||s->rescue_step>=3||choice!=johto_rescue_answer(s))return false;s->rescue_step++;return true;}
bool johto_rescue_claim(johto_story_t *s,const johto_state_t *j){
 if(s->rescue_step!=3)return false;
 if(s->rescues<UINT16_MAX)s->rescues++;
 s->rescue_next=j->research[2]+3+(s->rescue_seed%4);s->rescue_step=0;memset(&s->rescue_partner,0,sizeof(s->rescue_partner));return true;
}
unsigned johto_ruin_answer(unsigned group,unsigned step){static const uint8_t answers[4][3]={{0,1,2},{2,0,1},{1,2,0},{2,1,0}};return group<4&&step<3?answers[group][step]:3;}
bool johto_ruin_choose(johto_story_t *s,const johto_state_t *j,unsigned group,unsigned choice){
 if(group>=4||johto_badges(j)<(unsigned[]){3,4,6,7}[group]||(s->ruins&(1u<<group)))return false;
 if(!s->version)s->version=1;
 if(s->ruin_group!=group){s->ruin_group=group;s->ruin_step=0;}
 if(choice!=johto_ruin_answer(group,s->ruin_step))return false;
 if(++s->ruin_step==3){s->ruins|=1u<<group;s->ruin_step=0;}return true;
}
unsigned johto_ruin_form(johto_story_t *s,unsigned group,uint32_t roll){
 if(group>=4||!(s->ruins&(1u<<group)))return 26;
 unsigned lo=group*7,hi=group==3?26:lo+7,unseen[7],n=0;
 for(unsigned i=lo;i<hi;i++)if(!(s->forms_caught&(1u<<i)))unseen[n++]=i;
 unsigned form=n&&(s->ruin_misses[group]>=5||roll%4<3)?unseen[(roll/4)%n]:lo+(roll/4)%(hi-lo);
 if(s->forms_caught&(1u<<form)){if(s->ruin_misses[group]<5)s->ruin_misses[group]++;}else s->ruin_misses[group]=0;
 s->forms_seen|=1u<<form;return form;
}
static const uint8_t beast_route[2][3]={{4,2,5},{4,1,7}};
void johto_story_explore(johto_story_t *s,johto_state_t *j,unsigned route){
 if(!s->version)s->version=1;
 if(j->phase==JOHTO_COMPLETE&&route==1)s->forest_visits|=2;
 // Visiting still advances eggs/research elsewhere. Legendary evidence now
 // requires an explicit site + companion action, never repeated free exploration.
}
bool johto_story_legend_ready(const johto_story_t *s,const johto_state_t *j,unsigned id,bool feather){
 if(id>=6||!johto_legend_ready(j,id)||!s->tower_seen)return false;
 if(id==3&&!feather)return false;
 if(id==4&&(j->badges!=255||j->legend_clues[0]!=3||j->legend_clues[1]!=3||j->legend_clues[2]!=3))return false;
 if(id==5&&(j->phase!=JOHTO_COMPLETE||s->forest_visits!=3))return false;
 return !(s->legend_visits&(1u<<id))||(uint64_t)j->explorations>=(uint64_t)s->legend_at[id]+2;
}
const char *johto_story_legend_hint(const johto_story_t *s,const johto_state_t *j,unsigned id,bool feather){
 if(!s->tower_seen)return "四徽章后调查烧焦塔";
 if(id<2&&j->legend_clues[id]<3)return JOHTO_ROUTES[beast_route[id][j->legend_clues[id]]].name;
 if(id==2&&j->legend_clues[2]<3)return j->legend_clues[2]==0?"前往满金原野":j->legend_clues[2]==1?"前往漩涡列岛":"冒险笔记：净水试炼";
 if(id==3&&!feather)return "完成漩涡远征取得银色之羽";
 if(id==3&&j->legend_clues[3]<3)return "继续调查漩涡列岛";
 if(id==4&&j->badges!=255)return "先集齐八枚城都徽章";
 if(id==4&&(j->legend_clues[0]<3||j->legend_clues[1]<3||j->legend_clues[2]<3))return "完成三兽调查 不必捕获";
 if(id==4&&j->legend_clues[4]<3)return "前往铃铛塔调查虹色之羽";
 if(id==5&&j->phase!=JOHTO_COMPLETE)return "完成空木最终考验";
 if(id==5&&!(s->forest_visits&1))return "回访任一关都探索地图";
 if(id==5&&j->legend_clues[5]<3)return "回访桧皮林地调查时空裂隙";
 return johto_story_legend_ready(s,j,id,feather)?"追踪已定位 消耗10体能":"再完成两次城都探索";
}
bool johto_story_final_ready(const johto_story_t *s,const johto_state_t *j,uint16_t defeated,bool feather){return j->phase==JOHTO_COMPLETE||(johto_final_open(j,defeated)&&s->ruins==15&&s->rescues>=2&&feather&&s->tower_seen);}
