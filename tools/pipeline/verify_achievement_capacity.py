#!/usr/bin/env python3
"""Production world/save: full and partial achievement rewards never block claims."""
import verify_trainer_campaign as harness
harness.CASES = r'''
static void capped_claims(void) {
 for(unsigned id=0;id<ACHIEVEMENT_COUNT;id++){
  for(unsigned room=0;room<=achievement_info(id)->quantity;room++){
   fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
   for(unsigned sid=1;sid<=151;sid++)dex_mark_caught(&s_dex,sid,true);
   s_achievements.evolutions=5;s_challenge.defeated=16383;
   unsigned item=achievement_info(id)->item,cap=items_capacity(item);
   s_inventory.quantity[item]=cap-room;
   inventory_t before=s_inventory;uint16_t claimed=s_achievements.claimed;
   for(unsigned k=0;k<3;k++){
    failure=(int[]){1,2,4}[k];assert(world_achievement_claim(id)==ACH_CLAIM_FAILED);
    assert(s_achievements.claimed==claimed&&!memcmp(&before,&s_inventory,sizeof(before)));
   }
   failure=0;
   achievement_claim_t expected=room<achievement_info(id)->quantity?ACH_CLAIM_CAPPED:ACH_CLAIM_OK;
   assert(world_achievement_claim(id)==expected);
   assert(s_inventory.quantity[item]==cap&&(s_achievements.claimed&(1u<<id)));
   for(unsigned other=0;other<ITEM_COUNT;other++)if(other!=item)assert(s_inventory.quantity[other]==before.quantity[other]);
   reboot();assert(world_achievement_claim(id)==ACH_CLAIM_ALREADY);
   assert(s_inventory.quantity[item]==cap);tests++;
  }
 }
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 assert(world_achievement_claim(0)==ACH_CLAIM_LOCKED);assert(!s_achievements.claimed);
 assert(world_achievement_claim(ACHIEVEMENT_COUNT)==ACH_CLAIM_LOCKED);
}
int main(void){assert(assets_init());capped_claims();printf("{\"cases\":%u,\"all_achievements_full_and_partial\":true,\"save_failures_atomic\":true,\"repeat_claim_blocked\":true}\n",tests);}
'''
harness.run()
