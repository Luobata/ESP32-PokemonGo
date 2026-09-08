#!/usr/bin/env python3
"""Cross-system contracts using production world/save and isolated NVS failures."""
import verify_trainer_campaign as h
h.CASES='#include "exploration.c"\n'+h.CASES[:h.CASES.index('static void campaign')]+r'''
static void map_growth(void){
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);
 s_w.pet.intimacy=60*NURT_Q;s_w.pet.stamina=15*NURT_Q;s_w.explore_value=31;world_debug_save();
 failure=4;assert(world_explore().kind==EXPLORE_SAVE_FAILED);failure=0;
 assert(s_w.explore_value==31&&s_party.party[0].explore_value==31&&s_w.pet.stamina==15*NURT_Q);
 assert(world_explore().kind==EXPLORE_ENCOUNTER);
 assert(s_w.explore_value==32&&s_party.party[0].explore_value==32&&s_w.pet.stamina==10*NURT_Q);
 reboot();assert(s_w.explore_value==32&&s_party.party[0].explore_value==32);
 assert(world_evolve_leader(1,2));assert(s_w.species==2&&dex_count_caught(&s_dex)==2);
 achievement_view_t a;world_achievements_snapshot(&a);assert(achievement_progress(&a,9)==1);
 assert(world_achievement_claim(9)==ACH_CLAIM_OK);assert(s_inventory.quantity[ITEM_FIRE_STONE]==1);
 assert(world_achievement_claim(9)==ACH_CLAIM_ALREADY);
 s_w.explore_value=UINT16_MAX;s_w.pet.stamina=10*NURT_Q;world_debug_save();
 assert(world_explore().kind==EXPLORE_CLUE);assert(s_w.explore_value==UINT16_MAX);reboot();assert(s_w.explore_value==UINT16_MAX);
 tests+=7;
}
static void trainer_xp(void){
 seed();assert(world_challenge_begin(0));s_challenge.session.finished=1;s_challenge.session.won=1;s_challenge.session.participated=7;
 unsigned reward=0;
 for(unsigned mood=0;mood<=100;mood++){s_w.pet.mood=mood*NURT_Q;reward=exp_scaled(trainer_reward(&s_challenge),nurture_exp_percent(&s_w.pet));if(reward%3)break;}
 assert(reward%3);world_debug_save();party_t before=s_party;
 failure=4;assert(!world_challenge_settle());failure=0;assert(!memcmp(&s_party,&before,sizeof(before)));
 assert(world_challenge_settle());unsigned sum=0;
 for(unsigned i=0;i<6;i++){unsigned delta=s_party.party[i].exp-before.party[i].exp;if(i<3){assert(delta>=reward/3&&delta<=reward/3+1);sum+=delta;}else assert(!delta);}
 assert(sum==reward);party_t after=s_party;assert(world_challenge_settle());assert(!memcmp(&after,&s_party,sizeof(after)));reboot();assert(!memcmp(&after,&s_party,sizeof(after)));tests+=4;
}
int main(void){assert(assets_init());map_growth();trainer_xp();printf("{\"cases\":%u,\"map_evolution_achievement_item\":true,\"trainer_xp_conserved\":true}\n",tests);}
'''
h.run()
