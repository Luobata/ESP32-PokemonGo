// Owned partner snapshots and run HP are separate; rewards commit with world saves.
#include "dungeon.h"
#include "assets.h"
#include "exp.h"
#include <string.h>
#ifndef HOST_BUILD
#include "nvs.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#define TRACE_STAGE(stage) ESP_LOGI("dungeon","stage=%s phase=%u node=%u run=%lu stack_free=%u",stage,run.phase,run.node,(unsigned long)run.run_id,(unsigned)uxTaskGetStackHighWaterMark(NULL))
#else
#define TRACE_STAGE(stage) ((void)0)
extern bool dungeon_host_commit(const void *data,size_t len);
extern bool dungeon_host_load(void *data,size_t len);
#endif
#define DUNGEON_VERSION 3
const char *const dungeon_nodes[8]={"林间入口","林间岔路","深林对战","营地","巡护精英","遗迹岔路","最后营地","森林首领"};
const char *const dungeon_cards[DUNGEON_CARD_COUNT]={"烈焰印记","潮汐印记","雷鸣印记","强攻","冥想","坚守","疾风","会心","余温","营火","净化","接力盾","弱点追击","接力强攻","乘胜回复"};
const char *const dungeon_desc[DUNGEON_CARD_COUNT]={"火系伙伴伤害增加25%","水系伙伴伤害增加25%","电系伙伴伤害增加25%","开场攻击提升一级","开场特攻提升一级","开场防御特防升一级","开场速度提升一级","开场更易击中要害","胜利存活伙伴回复15%","营地回复额外增加20%","开场清除异常状态","首次主动换入防御升一级","攻击异常对手伤害加25%","主动换入首击伤害加35%","攻击击倒对手回复15%"};
static dungeon_t run;
// Mutations run under the existing LVGL lock (buttons, debug keys and timers).
// Keep the rollback candidate in BSS: esp_timer has only a 3584-byte stack.
// Commit publishes to run only after NVS succeeds. Nested resume starts only
// after the previous candidate is committed, and never retains its contents.
static dungeon_t candidate;
static bool loaded,playing;
static const char *feedback;
const char *dungeon_feedback(void){return feedback;}
static uint32_t rng(dungeon_t *d){uint32_t x=d->seed?d->seed:1;x^=x<<13;x^=x>>17;x^=x<<5;return d->seed=x;}
static bool valid(const dungeon_t *d){
 if(d->version!=DUNGEON_VERSION||d->phase>DUNGEON_ENTRY||d->node>7||d->cards>32767||d->guards>7||d->relay_mask>7||d->pending>1||d->next_phase>DUNGEON_LOST||!items_inventory_valid(&d->earned))return false;
 if(d->phase==DUNGEON_EMPTY)return true;
 if(!d->count)return d->phase==DUNGEON_LOST; // Archived rental run.
 if(d->count>3||!d->base_level||d->base_level>100)return false;
 for(unsigned i=0;i<3;i++)if(d->choices[i]>=DUNGEON_CARD_COUNT)return false;
 for(unsigned i=0;i<d->count;i++){
  if(d->slots[i]>=PARTY_MAX||!d->ids[i]||d->ids[i]>151||d->members[i].species_id!=d->ids[i]||!d->members[i].level||d->members[i].level>100)return false;
  for(unsigned j=0;j<i;j++)if(d->slots[i]==d->slots[j])return false;
 }
 return trainer_store_valid(&d->battle)&&d->battle.session.sides[0].count==d->count;
}
static bool commit(const dungeon_t *d){
 if(!valid(d))return false;
#ifndef HOST_BUILD
 nvs_handle_t h;if(nvs_open("pw_dungeon",NVS_READWRITE,&h)!=ESP_OK)return false;
 esp_err_t e=nvs_set_blob(h,"run_v3",d,sizeof(*d));if(e==ESP_OK)e=nvs_commit(h);nvs_close(h);if(e!=ESP_OK)return false;
#else
 if(!dungeon_host_commit(d,sizeof(*d)))return false;
#endif
 run=*d;return true;
}
void dungeon_load(void){
 if(loaded)return;
 loaded=true;memset(&run,0,sizeof(run));run.version=DUNGEON_VERSION;
#ifndef HOST_BUILD
 nvs_handle_t h;dungeon_t *saved=&candidate;size_t len=sizeof(*saved);
 if(nvs_open("pw_dungeon",NVS_READONLY,&h)==ESP_OK){
  esp_err_t e=nvs_get_blob(h,"run_v3",saved,&len);
  if(e==ESP_OK&&len==sizeof(*saved)&&valid(saved))run=*saved;
  // Legacy rental runs cannot be attached to owned individuals. Keep their
  // history; real inventory/EXP already credited remain in the world save.
  else if(e==ESP_ERR_NVS_NOT_FOUND){
   memset(saved,0,sizeof(*saved));len=sizeof(dungeon_v2_t);
   e=nvs_get_blob(h,"run_v2",saved,&len);
   if(e==ESP_OK&&len==sizeof(dungeon_v2_t)&&saved->version==2&&!saved->pending){saved->version=DUNGEON_VERSION;saved->phase=DUNGEON_LOST;if(valid(saved))run=*saved;}
  }
  nvs_close(h);
 }
#else
 dungeon_t *saved=&candidate;if(dungeon_host_load(saved,sizeof(*saved))&&valid(saved))run=*saved;
#endif
}
const dungeon_t *dungeon_get(void){dungeon_load();return &run;}
bool dungeon_playing(void){return playing;}
void dungeon_set_playing(bool p){playing=p;}
void dungeon_snapshot(trainer_store_t *out,world_party_t *party){
 *out=run.battle;memset(party,0,sizeof(*party));party->count=run.count;
 memcpy(party->members,run.members,run.count*sizeof(mon_t));
}
static void heal(dungeon_t *d,unsigned pct){for(unsigned i=0;i<d->count;i++){combat_mon_t *m=&d->battle.session.sides[0].mons[i];if(m->hp){unsigned n=m->hp+m->max_hp*pct/100;m->hp=n>m->max_hp?m->max_hp:n;}}}
static void draw_cards(dungeon_t *d){
 unsigned pool[DUNGEON_CARD_COUNT],count=0;
 for(unsigned i=0;i<DUNGEON_CARD_COUNT;i++)if(!(d->cards&(1u<<i))){
  bool relevant=i>=3;
  if(i<3)for(unsigned j=0;j<d->count;j++){species_t sp;if(assets_species(d->members[j].species_id,&sp)&&(sp.type1==i+1||sp.type2==i+1))relevant=true;}
  if(relevant)pool[count++]=i;
 }
 for(unsigned i=0;i<3;i++){unsigned index=rng(d)%count;d->choices[i]=pool[index];pool[index]=pool[--count];}
 d->phase=DUNGEON_REWARD;
}
static bool begin_battle(dungeon_t *d,bool fresh){
 uint16_t hp[3],max_hp[3];uint8_t status[3];mon_t party[3];
 if(!fresh){
  world_party_t owned;world_party_snapshot(&owned);
  for(unsigned i=0;i<d->count;i++){if(d->slots[i]>=owned.count)return false;d->members[i]=owned.members[d->slots[i]];d->ids[i]=d->members[i].species_id;}
 }
 for(unsigned i=0;i<d->count;i++){hp[i]=d->battle.session.sides[0].mons[i].hp;max_hp[i]=d->battle.session.sides[0].mons[i].max_hp;status[i]=d->battle.session.sides[0].mons[i].status;party[i]=d->members[i];}
 memset(&d->battle,0,sizeof(d->battle));d->battle.defeated=255;d->guards=0;d->relay_mask=0;
 if(!trainer_begin(&d->battle,14+(d->node==7?2:d->node==4?1:0),party,d->count,1024,rng(d)))return false;
 static const uint8_t foes[8][3]={{12,47,17},{20,24,28},{31,34,62},{0},{123,127,114},{112,115,128},{0},{103,45,149}};
 static const int8_t offsets[8]={-4,-3,-2,0,0,0,0,2};
 int level=d->base_level+offsets[d->node];if(level<2)level=2;if(level>100)level=100;
 unsigned count=d->node==7?3:d->node>=2?2:1,offset=rng(d)%3;
 if(count>d->count)count=d->count;
 trainer_session_t *s=&d->battle.session;s->sides[1].count=count;
 for(unsigned i=0;i<count;i++){unsigned id=foes[d->node][(i+offset)%3];combat_init(&s->sides[1].mons[i],id,level,combat_max_hp(id,level));}
 for(unsigned i=0;i<d->count;i++){
  combat_mon_t *m=&s->sides[0].mons[i];if(!fresh){m->hp=max_hp[i]?(uint32_t)hp[i]*m->max_hp/max_hp[i]:0;if(hp[i]&&!m->hp)m->hp=1;}m->status=fresh||(d->cards&(1u<<10))?0:status[i];if(m->status==4)m->sleep=2;
  m->attack=!!(d->cards&(1u<<3));m->special=!!(d->cards&(1u<<4));m->defense=m->safety.special_defense=!!(d->cards&(1u<<5));m->speed=!!(d->cards&(1u<<6));m->focus=!!(d->cards&(1u<<7));
 }
 unsigned active=0;while(active<d->count&&!s->sides[0].mons[active].hp)active++;if(active==d->count)return false;
 s->sides[0].active=active;s->participated=1u<<active;s->acted=3;d->phase=DUNGEON_BATTLE;return true;
}
bool dungeon_party_locked(void){
 dungeon_load();return run.count&&run.phase!=DUNGEON_EMPTY&&run.phase!=DUNGEON_WON&&run.phase!=DUNGEON_LOST&&!(run.phase==DUNGEON_SETTLEMENT&&!run.pending&&run.next_phase==DUNGEON_WON);
}
unsigned dungeon_recipients(uint32_t id,uint8_t slots[3]){
 dungeon_load();if(!id||id!=run.run_id||!run.count)return 0;
 memcpy(slots,run.slots,run.count);return run.count;
}
bool dungeon_abandon(void){
 if((run.phase==DUNGEON_ENTRY||(run.phase==DUNGEON_SETTLEMENT&&run.pending))&&!dungeon_resume())return false;
 dungeon_t *d=&candidate;*d=run;d->phase=DUNGEON_LOST;return commit(d);
}
bool dungeon_new(const uint8_t slots[3],unsigned count,uint32_t seed){
 dungeon_load();if(!slots||!count||count>3)return false;TRACE_STAGE("entry_begin");
 if((run.phase==DUNGEON_ENTRY||(run.phase==DUNGEON_SETTLEMENT&&run.pending))&&!dungeon_resume())return false;
 if(!world_dungeon_ready())return false;
 world_party_t owned;world_party_snapshot(&owned);
 dungeon_progress_t progress;world_dungeon_progress(&progress);if(progress.run_id==UINT32_MAX)return false;
 dungeon_t *d=&candidate;memset(d,0,sizeof(*d));d->version=DUNGEON_VERSION;d->seed=seed;d->count=count;
 for(unsigned i=0;i<count;i++){
  if(slots[i]>=owned.count)return false;
  for(unsigned j=0;j<i;j++)if(slots[i]==slots[j])return false;
  d->slots[i]=slots[i];d->members[i]=owned.members[slots[i]];d->ids[i]=d->members[i].species_id;
  if(d->members[i].level>d->base_level)d->base_level=d->members[i].level;
 }
 if(!begin_battle(d,true))return false;
 d->run_id=progress.run_id+1;d->phase=DUNGEON_ENTRY;
 if(!commit(d)){TRACE_STAGE("entry_save_failed");return false;}
 TRACE_STAGE("entry_prepared");return dungeon_resume();
}
static bool advance(dungeon_t *d){
 d->node++;if(d->node==1||d->node==5)d->phase=DUNGEON_FORK;
 else if(d->node==3||d->node==6)d->phase=DUNGEON_CAMP;
 else return begin_battle(d,false);
 return true;
}
bool dungeon_choose(unsigned choice){
 dungeon_t *d=&candidate;*d=run;
 if(d->phase==DUNGEON_SETTLEMENT&&choice==0){if(d->pending)return dungeon_resume();d->phase=d->next_phase;if(d->node==5&&d->next_phase==DUNGEON_CAMP)d->node++;}
 else if(d->phase==DUNGEON_REWARD&&choice<3){d->cards|=1u<<d->choices[choice];if(!advance(d))return false;}
 else if(d->phase==DUNGEON_FORK&&choice<2){
  if(!choice){if(!begin_battle(d,false))return false;}
  else if(d->node==1){for(unsigned i=0;i<d->count;i++){combat_mon_t *m=&d->battle.session.sides[0].mons[i];if(m->hp){unsigned n=m->max_hp*12/100;m->hp=m->hp>n?m->hp-n:1;}}draw_cards(d);}
  else{heal(d,15);d->berries+=3;d->next_phase=DUNGEON_CAMP;d->pending=1;d->phase=DUNGEON_SETTLEMENT;memset(&d->receipt,0,sizeof(d->receipt));}
 }else if(d->phase==DUNGEON_CAMP&&choice<3){
  if(choice==2)draw_cards(d);
  else{if(!choice)heal(d,25+((d->cards&(1u<<9))?20:0));else{unsigned i=0;while(i<d->count&&d->battle.session.sides[0].mons[i].hp)i++;if(i==d->count)return false;combat_mon_t *m=&d->battle.session.sides[0].mons[i];m->hp=m->max_hp*35/100;m->status=0;}if(!advance(d))return false;}
 }else return false;
 if(!commit(d))return false;
 return !run.pending||dungeon_resume();
}
bool dungeon_step(trainer_event_t *out){
 feedback=NULL;
 if(run.phase!=DUNGEON_BATTLE)return false;
 dungeon_t *d=&candidate;*d=run;species_t sp;combat_mon_t *m=&d->battle.session.sides[0].mons[d->battle.session.sides[0].active];unsigned boost=0;
 if(assets_species(m->species,&sp))for(unsigned i=0;i<3;i++)if((d->cards&(1u<<i))&&(sp.type1==i+1||sp.type2==i+1))boost=256;
 unsigned slot=d->battle.session.sides[0].active,enemy=d->battle.session.sides[1].active;
 bool pursuit=(d->cards&(1u<<12))&&d->battle.session.sides[1].mons[enemy].status;
 bool relay=(d->cards&(1u<<13))&&(d->relay_mask&(1u<<slot));
 d->battle.session.ability=1024+boost+(pursuit?256:0)+(relay?358:0);
 if(!trainer_step(&d->battle,out))return false;
 bool hit=out->kind==TRAINER_ATTACK&&out->side==0&&!out->attack.missed&&out->attack.damage;
 bool knockout=hit&&out->before_hp[1]&&!d->battle.session.sides[1].mons[enemy].hp&&(d->cards&(1u<<14));
 if(hit&&relay)d->relay_mask&=~(1u<<slot);
 if(knockout){combat_mon_t *a=&d->battle.session.sides[0].mons[slot];if(a->hp){unsigned hp=a->hp+a->max_hp*15/100;a->hp=hp>a->max_hp?a->max_hp:hp;out->attack.pet_hp=a->hp;}}
 if(!commit(d))return false;
 if(hit){if(knockout)feedback="乘胜回复 生命恢复";else if(relay)feedback="接力强攻 伤害增强";else if(pursuit)feedback="弱点追击 伤害增强";else if(boost)feedback="属性印记 伤害增强";}
 return true;
}
bool dungeon_switch(unsigned slot,bool forced){
 feedback=NULL;if(run.phase!=DUNGEON_BATTLE)return false;
 dungeon_t *d=&candidate;*d=run;if(!trainer_switch(&d->battle,slot,forced))return false;
 bool guard=!forced&&(d->cards&(1u<<11))&&!(d->guards&(1u<<slot));
 if(guard){combat_mon_t *m=&d->battle.session.sides[0].mons[slot];if(m->defense<6)m->defense++;d->guards|=1u<<slot;}
 if(!forced&&(d->cards&(1u<<13)))d->relay_mask|=1u<<slot;
 if(!commit(d))return false;
 if(guard)feedback="接力盾 防御提升";else if(!forced&&(d->cards&(1u<<13)))feedback="接力强攻 准备就绪";
 return true;
}
bool dungeon_retire(void){if(run.phase!=DUNGEON_BATTLE)return false;
 dungeon_t *d=&candidate;*d=run;trainer_retire(&d->battle);return commit(d);}
bool dungeon_resume(void){
 if(run.phase==DUNGEON_ENTRY){
  if(!world_dungeon_admit(run.run_id)){TRACE_STAGE("admit_failed");return false;}
  TRACE_STAGE("admitted");
  dungeon_t *d=&candidate;*d=run;d->phase=DUNGEON_BATTLE;bool ok=commit(d);TRACE_STAGE(ok?"entry_ready":"entry_ack_failed");return ok;
 }
 if(run.phase!=DUNGEON_SETTLEMENT||!run.pending)return true;
 dungeon_t *d=&candidate;*d=run;
 if(d->run_id){
  if(!world_dungeon_award(d->run_id,d->node,d->seed,&d->receipt))return false;
  d->xp+=d->receipt.xp;
  for(unsigned i=0;i<ITEM_COUNT;i++)d->earned.quantity[i]+=d->receipt.items.quantity[i];
 }else memset(&d->receipt,0,sizeof(d->receipt));
 d->pending=0;return commit(d);
}
bool dungeon_finish(void){
 if(run.phase==DUNGEON_SETTLEMENT)return dungeon_resume();
 if(run.phase!=DUNGEON_BATTLE||!run.battle.session.finished)return false;
 dungeon_t *d=&candidate;*d=run;memset(&d->receipt,0,sizeof(d->receipt));
 if(!d->battle.session.won)d->phase=DUNGEON_LOST;
 else{
  d->wins++;if(d->cards&(1u<<8))heal(d,15);
  if(d->node==7){d->next_phase=DUNGEON_WON;d->stone=1;}else{draw_cards(d);d->next_phase=DUNGEON_REWARD;}
  d->phase=DUNGEON_SETTLEMENT;d->pending=1;
 }
 if(!commit(d))return false;
 return dungeon_resume();
}
