#!/usr/bin/env python3
"""Production V27 activity transactions, NVS rollback, migration and resumability."""
import verify_trainer_campaign as h
from save_history_fixtures import c_cases
h.CASES=c_cases()+r'''
static activity_result_data_t event;
static activity_request_t q;
static activity_result_t act(unsigned op,unsigned value){q=(activity_request_t){.op=op,.choice=value,.box_slot=BOX_CAPACITY,.elapsed=300};return world_activity_action(&q,&event);}
static void setup(unsigned level){fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_johto.phase=JOHTO_ACTIVE;s_johto.starter=152;s_johto.badges=255;
 for(unsigned i=0;i<3;i++){s_party.party[i]=(mon_t){.species_id=(unsigned[]){145,154,248}[i],.level=level,.exp=exp_for_level(level),.hp=100,.intimacy=80};}s_party.party_count=3;s_w.species=145;s_w.level=level;s_w.exp=exp_for_level(level);s_w.pet.stamina=100*NURT_Q;s_exploration_wins=100;
 for(unsigned i=0;i<ITEM_COUNT;i++)s_inventory.quantity[i]=items_capacity(i);world_debug_save();}
static activity_result_t start(unsigned kind,unsigned seed){q=(activity_request_t){.op=ACTION_BEGIN,.choice=kind,.slots={0,1,2},.count=kind==ACT_BUG?1:3,.seed=seed};return world_activity_action(&q,&event);}
static void histories(void){static save_t s;for(unsigned i=0;i<sizeof(history)/sizeof(*history);i++){memcpy(&s,history[i].data,history[i].size);assert(save_decode(&s,&s,history[i].size,0)!=SAVE_READ_ERROR);history_assert(&s,history[i].version);assert(!s.activities.run.kind&&!s.activities.bug_completed&&!s.activities.sea_clears);}}
static void bug_cases(void){
 setup(60);s_johto.badges=1;assert(start(ACT_BUG,19)==ACT_LOCKED);s_johto.badges=255;
 failure=4;assert(start(ACT_BUG,19)==ACT_SAVE_FAILED&&!s_activities.run.kind&&s_w.pet.stamina==100*NURT_Q);failure=0;
 assert(start(ACT_BUG,19)==ACT_OK&&s_w.pet.stamina==90*NURT_Q);reboot();assert(s_activities.run.kind==ACT_BUG&&s_exploration_wins==100);
 assert(start(ACT_BUG,1)==ACT_BUSY);assert(world_set_leader(1,&s_party.party[1],NULL)==WORLD_SWITCH_BUSY);
 for(unsigned i=0;i<6;i++){
  assert(act(ACTION_SURVEY,i%3)==ACT_OK);mon_t found=s_activities.run.found;reboot();assert(!memcmp(&found,&s_activities.run.found,sizeof(found)));
  if(i<3){s_inventory.quantity[ITEM_MASTER]=1;world_debug_save();unsigned balls=s_inventory.quantity[ITEM_MASTER];failure=4;activity_result_t got=act(ACTION_THROW,ITEM_MASTER);assert(got==ACT_SAVE_FAILED&&s_inventory.quantity[ITEM_MASTER]==balls);failure=0;
   assert(act(ACTION_THROW,ITEM_MASTER)==ACT_OK&&event.capture.caught&&s_activities.run.attempts==i+1);reboot();assert(s_activities.run.phase==ACT_COMPARE);assert(act(ACTION_KEEP,1)==ACT_OK);
  }else {assert(act(ACTION_THROW,ITEM_MASTER)==ACT_LOCKED);assert(act(ACTION_SKIP,0)==ACT_OK);}
 }
 assert(s_activities.run.phase==ACT_SETTLE&&activity_score(&s_activities.run)>=50);mon_t won=s_activities.run.candidate;
 while(s_party.party_count<6){mon_t m={.species_id=25,.level=10,.hp=100};assert(party_receive(&s_party,&m));}
 for(unsigned i=0;i<BOX_CAPACITY;i++)s_party.box[i]=(mon_t){.species_id=1+i%251,.level=10,.exp=exp_for_level(10),.hp=100,.flags=i%2};world_debug_save();
 assert(act(ACTION_SETTLE,0)==ACT_FULL);reboot();assert(!memcmp(&won,&s_activities.run.candidate,sizeof(won)));
 q=(activity_request_t){.op=ACTION_SETTLE,.box_slot=452,.expected=s_party.box[452]};mon_t sibling=s_party.box[451];q.expected.level++;assert(world_activity_action(&q,&event)==ACT_STALE);q.expected=s_party.box[452];
 failure=4;assert(world_activity_action(&q,&event)==ACT_SAVE_FAILED&&s_party.box[452].species_id!=won.species_id);failure=0;
 assert(world_activity_action(&q,&event)==ACT_OK);assert(!memcmp(&won,&s_party.box[452],sizeof(won))&&!memcmp(&sibling,&s_party.box[451],sizeof(sibling)));
 assert(s_activities.pending.quantity[ITEM_SUN_STONE]==1&&s_activities.bug_first_silver);reboot();assert(!s_activities.run.kind&&s_exploration_wins==100);assert(act(ACTION_SETTLE,0)==ACT_LOCKED);
 s_inventory.quantity[ITEM_SUN_STONE]--;assert(act(ACTION_CLAIM,0)==ACT_OK&&!s_activities.pending.quantity[ITEM_SUN_STONE]);
}
static void win_battle(void){
 // Deterministic reward/transaction probe; difficulty has a separate simulation.
 for(unsigned i=0;i<s_activities.run.battle.session.sides[1].count;i++)s_activities.run.battle.session.sides[1].mons[i].hp=1;
 for(unsigned n=0;n<1000&&!s_activities.run.battle.session.finished;n++){
  assert(act(ACTION_STEP,0)==ACT_OK);
  if(event.event.kind==TRAINER_SWITCH_NEEDED){bool ok=false;for(unsigned i=0;i<3;i++){q=(activity_request_t){.op=ACTION_SWITCH,.choice=i,.hard=1};if(world_activity_action(&q,&event)==ACT_OK){ok=true;break;}}assert(ok);}
 }
 assert(s_activities.run.battle.session.finished&&s_activities.run.battle.session.won);assert(act(ACTION_BATTLE_END,0)==ACT_OK);
}
static void sea(void){
 setup(95);assert(start(ACT_SEA,81)==ACT_OK&&s_w.pet.stamina==80*NURT_Q);unsigned fixed=s_activities.run.base_level;assert(fixed==70);
 win_battle();win_battle();assert(s_activities.run.phase==ACT_CAMP&&s_activities.run.node==3);assert(act(ACTION_CAMP,0)==ACT_OK);uint32_t before=s_w.exp;
 failure=4;assert(act(ACTION_BANK,0)==ACT_SAVE_FAILED&&s_w.exp==before&&!s_activities.run.banked);failure=0;
 assert(act(ACTION_BANK,0)==ACT_OK&&s_w.exp>before);uint32_t credited=s_w.exp;reboot();assert(s_activities.run.banked&&s_w.exp==credited);assert(act(ACTION_BANK,0)==ACT_LOCKED&&s_w.exp==credited);
 assert(act(ACTION_CONTINUE,1)==ACT_OK);assert(act(ACTION_PATH,1)==ACT_OK);assert(s_activities.run.base_level==fixed);win_battle();assert(act(ACTION_CAMP,1)==ACT_OK);win_battle();assert(s_activities.run.won&&s_activities.run.phase==ACT_SETTLE);
 mon_t target=s_activities.run.found;reboot();assert(!memcmp(&target,&s_activities.run.found,sizeof(target)));assert(act(ACTION_SETTLE,0)==ACT_OK&&s_activities.sea_clears==1&&s_activities.silver_feather);
 assert(s_activities.pending.quantity[ITEM_DRAGON_SCALE]==1&&s_activities.pending.quantity[ITEM_METAL_COAT]==1);assert(s_queue.items[s_queue.count-1].species_id==target.species_id&&s_exploration_wins==100);assert(act(ACTION_SETTLE,0)==ACT_LOCKED);
 setup(95);assert(start(ACT_SEA,82)==ACT_OK);win_battle();win_battle();assert(act(ACTION_CAMP,0)==ACT_OK);assert(act(ACTION_BANK,0)==ACT_OK);credited=s_w.exp;
 assert(act(ACTION_CONTINUE,1)==ACT_OK);assert(act(ACTION_PATH,0)==ACT_OK);assert(act(ACTION_RETIRE,0)==ACT_OK);assert(act(ACTION_SETTLE,0)==ACT_OK&&s_w.exp==credited&&!s_activities.sea_clears&&s_exploration_wins==100);
 setup(95);assert(start(ACT_SEA,83)==ACT_OK);win_battle();win_battle();assert(act(ACTION_CAMP,0)==ACT_OK);assert(act(ACTION_BANK,0)==ACT_OK);assert(act(ACTION_CONTINUE,0)==ACT_OK);assert(act(ACTION_SETTLE,0)==ACT_OK&&!s_activities.sea_clears);
 assert(!erase_calls);
}
static void variants(void){
 for(unsigned kind=ACT_ICE;kind<=ACT_TOWER;kind++){
  setup(95);s_johto.badges=(1u<<(kind==ACT_ICE?4:6))-1;assert(start(kind,178)==ACT_LOCKED);s_johto.badges=255;
  assert(start(kind,178)==ACT_OK&&s_w.pet.stamina==80*NURT_Q);win_battle();win_battle();assert(act(ACTION_CAMP,1)==ACT_OK);assert(act(ACTION_BANK,0)==ACT_OK);reboot();
  assert(act(ACTION_CONTINUE,1)==ACT_OK);assert(act(ACTION_PATH,0)==ACT_OK);win_battle();assert(act(ACTION_CAMP,0)==ACT_OK);win_battle();mon_t reward=s_activities.run.found;assert(reward.species_id>151);
  unsigned item=kind==ACT_ICE?ITEM_METAL_COAT:ITEM_KINGS_ROCK;assert(act(ACTION_SETTLE,0)==ACT_OK);assert(s_activities.pending.quantity[item]==1&&!s_activities.silver_feather&&!s_activities.sea_clears);assert(s_queue.items[s_queue.count-1].species_id==reward.species_id);reboot();assert(act(ACTION_SETTLE,0)==ACT_LOCKED);
 }
}
static void boundaries(void){
 setup(60);assert(start(ACT_BUG,19)==ACT_OK);
 activity_store_t broken=s_activities;broken.run.phase=ACT_COMPARE;assert(!activity_valid(&broken));broken=s_activities;broken.run.count=3;assert(!activity_valid(&broken));broken=s_activities;broken.run.observed=32767;assert(!activity_valid(&broken));
 collect_save_locked(&s_save_buf);s_save_buf.members.party[0].species_id=25;assert(!save_validate_world(&s_save_buf,&s_save_buf.members));
 assert(act(ACTION_END_SURVEY,0)==ACT_OK);assert(act(ACTION_SETTLE,0)==ACT_OK&&!s_activities.bug_completed);
 for(unsigned seed=100;s_activities.bug_completed<3&&seed<110;seed++){
  s_w.pet.stamina=100*NURT_Q;assert(start(ACT_BUG,seed)==ACT_OK);
  for(unsigned i=0;i<6;i++){assert(act(ACTION_SURVEY,i%3)==ACT_OK);assert(act(ACTION_SKIP,0)==ACT_OK);}
  assert(act(ACTION_SETTLE,0)==ACT_OK);reboot();
 }
 assert(s_activities.bug_completed==3&&s_activities.bug_choices==1);
 failure=4;assert(act(ACTION_PRIZE,1)==ACT_SAVE_FAILED&&s_activities.bug_choices==1);failure=0;
 assert(act(ACTION_PRIZE,1)==ACT_OK&&!s_activities.bug_choices&&s_activities.pending.quantity[ITEM_KINGS_ROCK]==1);reboot();assert(act(ACTION_PRIZE,0)==ACT_LOCKED);
 setup(1);assert(start(ACT_SEA,991)==ACT_OK&&s_activities.run.base_level==55);
 for(unsigned n=0;n<1000&&!s_activities.run.battle.session.finished;n++){
  assert(act(ACTION_STEP,0)==ACT_OK);
  if(event.event.kind==TRAINER_SWITCH_NEEDED)for(unsigned i=0;i<3;i++){q=(activity_request_t){.op=ACTION_SWITCH,.choice=i,.hard=1};if(world_activity_action(&q,&event)==ACT_OK)break;}
 }
 assert(s_activities.run.battle.session.finished&&!s_activities.run.battle.session.won);
 assert(act(ACTION_BATTLE_END,0)==ACT_OK&&!s_activities.run.xp);assert(act(ACTION_SETTLE,0)==ACT_OK&&!s_activities.sea_clears&&s_exploration_wins==100);
}
int main(void){assert(assets_init());histories();bug_cases();sea();variants();boundaries();puts("V27 historical migrations, bug six nodes/three balls/full box, exact-slot replacement, sea relay/deep/retreat, persisted RNG, save failures and chain isolation passed");}
'''
if __name__=='__main__':h.run()
