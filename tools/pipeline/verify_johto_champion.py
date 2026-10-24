#!/usr/bin/env python3
"""Production champion rules and save transactions; never touches a device save."""
import verify_trainer_campaign as h
from save_history_fixtures import c_cases
h.CASES=c_cases()+r'''
static void seed_champion(bool red){fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_challenge.defeated=red?16383:255;johto_init(&s_johto);s_johto.phase=JOHTO_ACTIVE;s_johto.starter=152;s_johto.badges=255;s_w.pet.stamina=100*NURT_Q;world_debug_save();}
static void automatic(void){
 seed_champion(false);assert(world_challenge_start(TRAINER_JOHTO_FIRST)==WORLD_CHALLENGE_OK);assert(s_challenge.session.sides[1].count==3&&s_challenge.session.sides[1].mons[2].level==42&&!s_endgame.battle.kind);
 s_challenge.session.finished=s_challenge.session.won=1;assert(world_challenge_settle());assert(!s_endgame.champion_gyms&&s_johto.badges==255);
 s_challenge.defeated|=1u<<13;s_w.pet.stamina=100*NURT_Q;
 for(unsigned gym=0;gym<8;gym++){
  s_w.pet.stamina=100*NURT_Q;unsigned id=TRAINER_JOHTO_FIRST+gym;const trainer_info_t *info=trainer_info_progress(id,&s_challenge);
  assert(world_challenge_start(id)==WORLD_CHALLENGE_OK);assert(s_endgame.battle.kind==gym+1);
  assert(s_challenge.session.sides[1].count==info->count);for(unsigned i=0;i<info->count;i++)assert(s_challenge.session.sides[1].mons[i].level==info->levels[i]);
  endgame_t before=s_endgame;reboot();assert(!memcmp(&before,&s_endgame,sizeof(before)));
  s_challenge.session.finished=s_challenge.session.won=1;failure=4;assert(!world_challenge_settle()&&s_endgame.champion_gyms==((1u<<gym)-1));failure=0;
  assert(world_challenge_settle());assert(s_endgame.champion_gyms==((1u<<(gym+1))-1));assert(world_challenge_settle());reboot();
 }
 achievement_view_t view;world_achievements_snapshot(&view);for(unsigned i=32;i<=40;i++)assert(achievement_progress(&view,i)==achievement_info(i)->target);
 s_inventory.quantity[ITEM_FAST]=items_capacity(ITEM_FAST);assert(world_achievement_claim(32)==ACH_CLAIM_FULL&&!s_endgame.claimed);s_inventory.quantity[ITEM_FAST]=0;
 failure=4;assert(world_achievement_claim(32)==ACH_CLAIM_FAILED&&!s_endgame.claimed);failure=0;
 assert(world_achievement_claim(32)==ACH_CLAIM_OK&&s_endgame.claimed==1);assert(world_achievement_claim(32)==ACH_CLAIM_ALREADY);reboot();assert(s_endgame.claimed==1);
 const trainer_info_t *elm=trainer_info_progress(TRAINER_JOHTO_FIRST+8,&s_challenge);assert(elm->count==6&&elm->species[2]==243&&elm->species[3]==245&&elm->species[4]==249&&elm->species[5]==250&&elm->levels[5]==100);
 // Completed legacy chapters retain access; each legendary rematch uses the same locked phases.
 s_johto.phase=JOHTO_COMPLETE;
 for(unsigned id=TRAINER_JOHTO_FIRST+8;id<TRAINER_LAKE_GUARD;id++){
  s_w.pet.stamina=100*NURT_Q;assert(world_challenge_start(id)==WORLD_CHALLENGE_OK&&s_endgame.battle.kind==GYM_ELM);
  for(unsigned i=0;i<6;i++){assert(s_challenge.session.sides[1].mons[i].species==elm->species[i]);assert(s_challenge.session.sides[1].mons[i].level==elm->levels[i]);}
  s_challenge.session.finished=s_challenge.session.won=1;failure=4;assert(!world_challenge_settle());failure=0;assert(world_challenge_settle()&&s_endgame.champion_elm);reboot();assert(s_endgame.champion_elm);
 }
 assert(world_achievement_claim(41)==ACH_CLAIM_OK);assert(world_achievement_claim(41)==ACH_CLAIM_ALREADY);

}
static trainer_store_t duel;static gym_rules_t rules;
static void setup(unsigned k){memset(&duel,0,sizeof(duel));duel.session.sides[0].count=duel.session.sides[1].count=6;for(unsigned i=0;i<6;i++){combat_init(&duel.session.sides[0].mons[i],143,80,500);combat_init(&duel.session.sides[1].mons[i],241,80,500);}memset(&rules,0,sizeof(rules));rules.version=1;rules.kind=k;gym_rules_enter(&rules,&duel.session);}
static combat_mon_t *dm(unsigned side){return &duel.session.sides[side].mons[duel.session.sides[side].active];}
static unsigned damage(unsigned side,unsigned move,bool use_rules){
 combat_mon_t a=*dm(side),d=*dm(side^1);battle_round_t r={0};uint32_t rng=22;gym_context_t c={&rules,&duel.session,side};combat_context_t ctx=gym_rules_context(&c);combat_turn_context(&a,&d,1024,&rng,50,move,&r,NULL,use_rules?&ctx:NULL);assert(!r.missed&&!r.no_effect);return r.damage;
}
static void event(unsigned side,unsigned move,unsigned damage_value,int old_attack,int old_speed,unsigned old_status){move_t m;assert(combat_move(move,&m));battle_round_t r={.move_id=move,.move_type=m.type,.damage=damage_value};gym_context_t ctx={&rules,&duel.session,side};gym_rules_after(&ctx,&r,0,old_attack,old_speed,old_status);assert(gym_rules_valid(&rules));}
static void mechanics(void){
 setup(GYM_WIND);assert(gym_rules_speed(&rules,1,100)==150);dm(1)->status=3;event(0,86,0,0,0,0);assert(rules.pause_until==4&&gym_rules_speed(&rules,1,100)==100);for(unsigned i=0;i<4;i++)gym_rules_round(&rules);assert(gym_rules_speed(&rules,1,100)==150);
 setup(GYM_SWARM);for(unsigned i=0;i<5;i++)event(1,41,1,0,0,0);assert(rules.stacks==3);assert(damage(0,33,true)<damage(0,33,false));event(0,53,1,0,0,0);assert(rules.stacks==1);battle_round_t miss={.move_id=53,.move_type=TY_FIRE,.missed=1};gym_context_t ctx={&rules,&duel.session,0};gym_rules_after(&ctx,&miss,0,0,0,0);assert(rules.stacks==1);
 setup(GYM_CHEER);dm(1)->hp=dm(1)->max_hp/3;unsigned low=dm(1)->hp;event(0,33,1,0,0,0);assert(rules.member[0].once&&dm(1)->hp>low);dm(1)->hp=low;event(0,33,1,0,0,0);assert(dm(1)->hp==low);setup(GYM_CHEER);dm(1)->status=1;dm(1)->hp=20;event(0,33,1,0,0,1);assert(dm(1)->hp==20&&rules.member[0].once);
 setup(GYM_CHEER);dm(1)->hp=20;event(1,36,1,0,0,0);assert(rules.member[0].once&&dm(1)->hp>20);setup(GYM_CHEER);dm(1)->hp=0;event(1,36,1,0,0,0);assert(!rules.member[0].once&&!dm(1)->hp);
 setup(GYM_VEIL);assert(damage(0,33,true)<damage(0,33,false));event(0,94,1,0,0,0);assert(rules.member[0].broken&&damage(0,33,true)>damage(0,33,false));gym_rules_t before=rules;gym_rules_enter(&rules,&duel.session);assert(!memcmp(&before,&rules,sizeof(rules)));
 setup(GYM_FIST);assert(damage(0,33,true)<damage(0,33,false));rules.round=2;assert(damage(1,2,true)>damage(1,2,false));dm(1)->attack=-1;event(0,45,0,0,0,0);assert(rules.member[0].broken&&damage(1,2,true)==damage(1,2,false));
 setup(GYM_ARMOR);assert(damage(0,33,true)<damage(0,33,false));assert(damage(0,94,true)<damage(0,94,false));event(0,53,1,0,0,0);event(0,57,1,0,0,0);assert(rules.member[0].broken&&damage(0,33,true)>damage(0,33,false));
 setup(GYM_COLD);for(unsigned i=0;i<6;i++)gym_rules_round(&rules);assert(rules.stacks==3&&gym_rules_speed(&rules,0,100)==55);event(0,53,1,0,0,0);assert(rules.stacks==1&&rules.pause_until==9);
 setup(GYM_DRAGON);assert(damage(0,33,true)<damage(0,33,false));event(0,33,1,0,0,0);event(0,53,1,0,0,0);assert(!rules.member[0].broken);duel.session.sides[0].active=1;event(0,33,1,0,0,0);assert(!rules.member[0].broken);event(0,53,1,0,0,0);assert(rules.member[0].broken);setup(GYM_DRAGON);rules.round=3;assert(damage(0,33,true)==damage(0,33,false));
 // Fixed damage, reflection and disabled moves retain their original semantics.
 setup(GYM_ARMOR);assert(damage(0,69,true)==damage(0,69,false));move_policy_t policy={0};for(unsigned id=1;id<=251;id++)move_policy_set(&policy,id,false);ctx=(gym_context_t){&rules,&duel.session,0};combat_context_t modifiers=gym_rules_context(&ctx);uint32_t rng=23;assert(combat_choose_context(dm(0),dm(1),&rng,&policy,&modifiers)==165);
 setup(GYM_ELM);for(unsigned i=0;i<6;i++){duel.session.sides[1].active=i;gym_rules_enter(&rules,&duel.session);}assert(duel.session.sides[1].mons[2].speed==1&&combat_sp_def_stage(&duel.session.sides[1].mons[3])==1);before=rules;gym_rules_enter(&rules,&duel.session);assert(!memcmp(&before,&rules,sizeof(rules)));
 setup(GYM_ARMOR);dm(1)->species=208;dm(1)->hp=20;dm(0)->last_move=57;duel.session.sides[1].mons[1].species=130;rules.round=3;rules.switch_after=3;assert(gym_rules_switch(&rules,&duel.session)==1);rules.switches=2;assert(gym_rules_switch(&rules,&duel.session)==-1);
}
static void lake(void){
 seed_champion(true);story_request_t q={.op=STORY_LAKE_BEGIN,.box_slot=BOX_CAPACITY};story_result_t out;
 s_johto.badges=15;assert(world_story_action(&q,&out)==ACT_LOCKED);s_johto.badges=31;s_w.pet.stamina=9*NURT_Q;assert(world_story_action(&q,&out)==ACT_STAMINA);s_w.pet.stamina=100*NURT_Q;
 failure=4;assert(world_story_action(&q,&out)==ACT_SAVE_FAILED&&!s_endgame.lake_stage&&s_w.pet.stamina==100*NURT_Q);failure=0;
 assert(world_story_action(&q,&out)==ACT_OK&&s_endgame.lake_level==85&&s_w.pet.stamina==90*NURT_Q);assert(world_story_action(&q,&out)==ACT_LOCKED);reboot();
 q.op=STORY_LAKE_CLUE;assert(world_story_action(&q,&out)==ACT_OK);
 uint32_t chain=s_exploration_wins;int32_t stamina=s_w.pet.stamina;
 assert(world_challenge_start(TRAINER_LAKE_GUARD)==WORLD_CHALLENGE_OK&&s_w.pet.stamina==stamina);assert(s_challenge.session.sides[1].mons[0].level==80);assert(world_challenge_retire());assert(world_challenge_settle());assert(s_endgame.lake_stage==LAKE_FACILITY);
 assert(world_challenge_start(TRAINER_LAKE_GUARD)==WORLD_CHALLENGE_OK);s_challenge.session.finished=s_challenge.session.won=1;assert(world_challenge_settle());assert(s_endgame.lake_stage==LAKE_GUARD_DONE);assert(world_challenge_start(TRAINER_LAKE_GUARD)==WORLD_CHALLENGE_LOCKED);
 q.op=STORY_LAKE_SWITCH;q.choice=0;assert(world_story_action(&q,&out)==ACT_LOCKED);q.choice=1;assert(world_story_action(&q,&out)==ACT_OK);
 assert(world_challenge_start(TRAINER_LAKE_BOSS)==WORLD_CHALLENGE_OK&&s_endgame.battle.kind==GYM_LAKE);assert(s_challenge.session.sides[1].mons[0].species==130&&s_challenge.session.sides[1].mons[0].level==85);
 s_challenge.session.finished=s_challenge.session.won=1;assert(world_challenge_settle());reboot();assert(s_endgame.lake_stage==LAKE_CALM&&s_exploration_wins==chain);
 for(unsigned i=1;i<6;i++)s_party.party[i]=(mon_t){.species_id=25,.level=10,.exp=exp_for_level(10),.hp=100};s_party.party_count=6;
 for(unsigned i=0;i<BOX_CAPACITY;i++){s_party.box[i]=(mon_t){.species_id=1+i%251,.level=20,.exp=exp_for_level(20),.hp=100,.flags=i%2};for(unsigned b=0;b<32;b++)s_party.policies[6+i].disabled[b]=(i*17+b*73)&255;s_party.policies[6+i].disabled[31]&=7;}
 q.op=STORY_LAKE_CLAIM;q.box_slot=BOX_CAPACITY;assert(world_story_action(&q,&out)==ACT_FULL&&s_endgame.lake_stage==LAKE_CALM);q.box_slot=752;q.expected=s_party.box[752];q.expected.level++;assert(world_story_action(&q,&out)==ACT_STALE);
 q.expected=s_party.box[752];mon_t neighbor=s_party.box[751];failure=4;assert(world_story_action(&q,&out)==ACT_SAVE_FAILED&&!memcmp(&q.expected,&s_party.box[752],sizeof(mon_t)));failure=0;
 assert(world_story_action(&q,&out)==ACT_OK&&out.partner.flags==1&&s_endgame.lake_stage==LAKE_RECEIVED);assert(s_party.box[752].species_id==130&&s_party.box[752].level==85&&s_party.box[752].flags==1);assert(!memcmp(&neighbor,&s_party.box[751],sizeof(mon_t)));assert(dex_is_caught(&s_dex,130));move_policy_t empty={0};assert(!memcmp(&empty,&s_party.policies[758],sizeof(empty)));assert(world_story_action(&q,&out)==ACT_LOCKED);reboot();assert(s_endgame.lake_stage==LAKE_RECEIVED&&party_total(&s_party)==759);assert(world_achievement_claim(42)==ACH_CLAIM_OK);assert(world_achievement_claim(42)==ACH_CLAIM_ALREADY);
 seed_champion(false);q=(story_request_t){.op=STORY_LAKE_BEGIN};assert(world_story_action(&q,&out)==ACT_OK&&s_endgame.lake_level==65);s_challenge.defeated|=1u<<13;world_debug_save();reboot();assert(s_endgame.lake_level==65);
}
static void legacy_active(void){
 static save_v29_t old;static save_t loaded;for(unsigned i=0;i<sizeof(history)/sizeof(history[0]);i++)if(history[i].version==29)memcpy(&old,history[i].data,sizeof(old));
 old.challenge=(trainer_store_t){.defeated=255};mon_t player={.species_id=25,.level=80,.hp=100};assert(trainer_begin(&old.challenge,TRAINER_JOHTO_FIRST,&player,1,1024,9));old.challenge.defeated=16383;
 assert(save_decode(&loaded,&old,sizeof(old),0)==SAVE_READ_MIGRATED);assert(!loaded.endgame.battle.kind&&!memcmp(&loaded.challenge,&old.challenge,sizeof(old.challenge)));assert(loaded.challenge.session.sides[1].mons[2].level==42);
 gym_rules_t before=loaded.endgame.battle;trainer_event_t ev;assert(trainer_step_rules(&loaded.challenge,&ev,NULL,&loaded.endgame.battle));assert(!memcmp(&before,&loaded.endgame.battle,sizeof(before)));
}
static void invalid_endgame(void){
 seed_champion(true);static save_t candidate,decoded;assert(save_read(&candidate));candidate.endgame.version=1;
 candidate.endgame.claimed=1;assert(save_decode(&decoded,&candidate,sizeof(candidate),0)==SAVE_READ_ERROR);
 candidate.endgame.claimed=0;candidate.endgame.version=2;assert(save_decode(&decoded,&candidate,sizeof(candidate),0)==SAVE_READ_ERROR);
 memset(&candidate.endgame,0,sizeof(candidate.endgame));candidate.endgame.champion_gyms=1;assert(save_decode(&decoded,&candidate,sizeof(candidate),0)==SAVE_READ_ERROR);
 candidate.endgame=(endgame_t){.version=1,.lake_stage=LAKE_CALM,.lake_level=85,.lake_partner={.species_id=130,.level=85,.flags=1,.hp=100,.exp=exp_for_level(85)}};
 assert(save_decode(&decoded,&candidate,sizeof(candidate),0)==SAVE_READ_OK);candidate.endgame.lake_partner.flags=0;assert(save_decode(&decoded,&candidate,sizeof(candidate),0)==SAVE_READ_ERROR);
 candidate.endgame=(endgame_t){.version=1,.battle={.version=1,.kind=GYM_ELM}};assert(save_decode(&decoded,&candidate,sizeof(candidate),0)==SAVE_READ_ERROR);
}
static void historical(void){for(unsigned i=0;i<sizeof(history)/sizeof(history[0]);i++){static save_t s;assert(save_decode(&s,history[i].data,history[i].size,0)!=SAVE_READ_ERROR);endgame_t zero={0};assert(!memcmp(&s.endgame,&zero,sizeof(zero)));assert(save_validate_world(&s,&s.members));}}
int main(void){assert(assets_init());automatic();mechanics();lake();historical();legacy_active();invalid_endgame();assert(!erase_calls);printf("automatic levels, 8 gym rules, limited switching, champion receipts, lake retries/full box/rollback, V5-V30: passed (%zu bytes)\n",sizeof(save_t));}
'''
h.run()
