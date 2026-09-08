#!/usr/bin/env python3
"""Real world/save/assets integration, including atomic claims and legacy V7 migration."""
import verify_trainer_campaign as harness
harness.CASES=r'''
static void claims(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 assert(world_achievement_claim(0)==ACH_CLAIM_LOCKED);
 mon_t m={.species_id=1,.level=5,.exp=exp_for_level(5),.hp=100,.flags=1};
 encounter_t e={.species_id=1,.rarity=3,.hp_ratio=100,.is_shiny=true};enc_queue_push(&s_queue,&e);
 assert(world_capture_uid(s_queue.items[0].uid,&m));
 achievement_view_t view;world_achievements_snapshot(&view);assert(view.caught==2&&view.shiny==1);
 uint16_t before=s_inventory.quantity[ITEM_GREAT];
 for(unsigned k=0;k<3;k++){failure=(int[]){1,2,4}[k];assert(world_achievement_claim(0)==ACH_CLAIM_FAILED);assert(!s_achievements.claimed&&s_inventory.quantity[ITEM_GREAT]==before);}
 failure=0;assert(world_achievement_claim(0)==ACH_CLAIM_OK);assert(s_inventory.quantity[ITEM_GREAT]==before+5);
 reboot();assert(world_achievement_claim(0)==ACH_CLAIM_ALREADY&&s_inventory.quantity[ITEM_GREAT]==before+5);
 s_inventory.quantity[ITEM_MOON_STONE]=items_capacity(ITEM_MOON_STONE);assert(world_achievement_claim(7)==ACH_CLAIM_FULL);assert(!(s_achievements.claimed&(1u<<7)));
 s_inventory.quantity[ITEM_MOON_STONE]--;assert(world_achievement_claim(7)==ACH_CLAIM_OK);
 reboot();assert(world_achievement_claim(7)==ACH_CLAIM_ALREADY);
 s_inventory.quantity[ITEM_THUNDER_STONE]=1;item_use_result_t result;
 failure=4;assert(world_item_use(25,ITEM_THUNDER_STONE,&result)==ITEM_USE_SAVE_FAILED);assert(s_w.species==25&&!s_achievements.evolutions);
 failure=0;assert(world_item_use(25,ITEM_THUNDER_STONE,&result)==ITEM_USE_OK);assert(s_w.species==26&&s_achievements.evolutions==1);
 reboot();assert(s_achievements.evolutions==1);assert(world_achievement_claim(9)==ACH_CLAIM_OK);reboot();assert(world_achievement_claim(9)==ACH_CLAIM_ALREADY);
 // Every goal uses capped progress and a stable reward; no partial grants.
 dex_t full;dex_init(&full);for(unsigned id=1;id<=151;id++)dex_mark_caught(&full,id,true);
 achievement_store_t all={.evolutions=5};achievement_view(&view,&all,&full,16383);inventory_t bag={0};
 for(unsigned i=0;i<ACHIEVEMENT_COUNT;i++){memset(&bag,0,sizeof(bag));assert(achievement_progress(&view,i)==achievement_info(i)->target);assert(achievement_claim(&all,&bag,&view,i)==ACH_CLAIM_OK);assert(achievement_claim(&all,&bag,&view,i)==ACH_CLAIM_ALREADY);}
 assert(all.claimed==65535);tests++;
}
static void achievement_legacy(void){
 save_t current;assert(save_read(&current));save_v7_t old={0};memcpy(&old,&current,sizeof(save_v6_t));old.challenge.defeated=255;old.version=7;
 disk_len=sizeof(save_v7_t);memcpy(disk,&old,disk_len);save_t migrated;assert(save_read_status(&migrated)==SAVE_READ_MIGRATED);
 assert(migrated.version==SAVE_VERSION&&migrated.challenge.defeated==255&&!migrated.achievements.claimed&&!migrated.achievements.evolutions);
 assert(!memcmp(current.party,migrated.party,PARTY_BYTES)&&!memcmp(&current.inventory,&migrated.inventory,sizeof(inventory_t)));
 reboot();achievement_view_t v;world_achievements_snapshot(&v);assert(achievement_progress(&v,13)==8&&v.shiny==1);
 assert(world_achievement_claim(13)==ACH_CLAIM_OK);reboot();assert(world_achievement_claim(13)==ACH_CLAIM_ALREADY);assert(!erase_calls);tests++;
}
static void alerts(void){
 fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);alert_count=0;reboot();assert(!alert_count);
 uint8_t made=0;s_last_n=0;spawn_one(50,false,&made);assert(!made&&!alert_count);
 s_last_n=1;memset(s_recs,0,sizeof(s_recs));s_recs[0].rssi=-40;s_recs[0].ssid[0]='x';spawn_one(51,false,&made);
 assert(made==1&&alert_count==1&&alert_rarity==s_queue.items[0].rarity&&alert_shiny==s_queue.items[0].is_shiny);
 world_debug_save();reboot();assert(alert_count==1);tests++;
}
int main(void){assert(assets_init());claims();achievement_legacy();alerts();printf("{\"cases\":%u,\"save_bytes\":%zu,\"claims_atomic\":true,\"v7_preserved\":true,\"sanitized\":true}\n",tests,sizeof(save_t));}
'''
harness.run()
