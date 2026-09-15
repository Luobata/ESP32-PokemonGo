#!/usr/bin/env python3
"""Real world/save/dungeon code with independent fault-injectable NVS boundaries."""
import verify_trainer_campaign as harness
harness.REAL_DUNGEON = True
harness.CASES = r'''
#include "dungeon.c"
static unsigned char run_disk[sizeof(dungeon_t)];
static size_t run_len;
static int run_fail_after=-1;
bool dungeon_host_commit(const void *data,size_t len){
 if(run_fail_after==0){run_fail_after=-1;return false;}if(run_fail_after>0)run_fail_after--;
 assert(len==sizeof(dungeon_t));memcpy(run_disk,data,len);run_len=len;return true;
}
bool dungeon_host_load(void *data,size_t len){if(len!=run_len)return false;memcpy(data,run_disk,len);return true;}
static const uint8_t chosen[3]={1,2,3};
static void setup(void){fresh();assert(world_choose_starter(1)==WORLD_STARTER_OK);s_w.pet.stamina=100*NURT_Q;s_party.party_count=4;for(unsigned i=1;i<4;i++)s_party.party[i]=(mon_t){.species_id=(uint8_t[]){1,6,9,143}[i],.level=50,.exp=exp_for_level(50)};world_debug_save();loaded=false;run_len=0;run_fail_after=-1;dungeon_load();}
static void restart(void){reboot();loaded=false;memset(&run,0,sizeof(run));dungeon_load();}
static void win(unsigned node){dungeon_t d=run;d.node=node;d.phase=DUNGEON_BATTLE;d.battle.session.finished=1;d.battle.session.won=1;for(unsigned i=0;i<d.battle.session.sides[1].count;i++)d.battle.session.sides[1].mons[i].hp=0;assert(commit(&d));}
static void admission(void){
 setup();run_fail_after=0;assert(!dungeon_new(chosen,3,1));assert(s_w.pet.stamina==100*NURT_Q&&s_dungeon.run_id==0);
 failure=4;assert(!dungeon_new(chosen,3,1));assert(s_w.pet.stamina==100*NURT_Q&&s_dungeon.run_id==0);failure=0;
 assert(dungeon_resume());assert(s_w.pet.stamina==80*NURT_Q&&run.phase==DUNGEON_BATTLE);
 assert(world_dungeon_admit(1));assert(s_w.pet.stamina==80*NURT_Q);tests++;
 setup();run_fail_after=1;assert(!dungeon_new(chosen,3,2));assert(run.phase==DUNGEON_ENTRY&&s_dungeon.run_id==1&&s_w.pet.stamina==80*NURT_Q);
 restart();assert(dungeon_resume());assert(s_w.pet.stamina==80*NURT_Q&&run.phase==DUNGEON_BATTLE);tests++;
 setup();s_w.pet.stamina=19*NURT_Q;assert(!dungeon_new(chosen,3,2));assert(s_dungeon.run_id==0&&s_w.pet.stamina==19*NURT_Q);tests++;
}
static void receipts(void){
 setup();assert(dungeon_new(chosen,3,11));win(0);party_t before=s_party;
 failure=4;assert(!dungeon_finish());assert(run.pending&&run.phase==DUNGEON_SETTLEMENT&&!memcmp(&before,&s_party,sizeof(before)));failure=0;
 assert(dungeon_resume());assert(run.xp>0&&!run.pending);before=s_party;uint32_t xp=run.xp;inventory_t inv=s_inventory;
 restart();assert(dungeon_resume());assert(!memcmp(&before,&s_party,sizeof(before))&&run.xp==xp&&!memcmp(&inv,&s_inventory,sizeof(inv)));tests++;
 // Failure after WORLD reward commit but before RUN receipt acknowledgement.
 setup();assert(dungeon_new(chosen,3,13));win(4);run_fail_after=1;assert(!dungeon_finish());assert(run.pending&&s_dungeon.elite_seen);
 before=s_party;inv=s_inventory;dungeon_receipt_t paid=s_dungeon.receipt;
 restart();assert(dungeon_resume());assert(!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&inv,&s_inventory,sizeof(inv)));assert(run.xp==paid.xp&&run.receipt.first_elite);tests++;
 assert(dungeon_choose(0)); // display -> upgrade
 assert(dungeon_choose(0)); // upgrade -> fork
 assert(dungeon_choose(1)); // supplies -> receipt -> camp
 assert(run.phase==DUNGEON_SETTLEMENT&&run.node==5);assert(dungeon_choose(0));assert(run.phase==DUNGEON_CAMP&&run.node==6);tests++;
 // Winning the optional node also keeps the last camp.
 win(5);assert(dungeon_finish());assert(dungeon_choose(0));assert(run.phase==DUNGEON_REWARD&&run.node==5);assert(dungeon_choose(0));assert(run.phase==DUNGEON_CAMP&&run.node==6);tests++;
 win(7);assert(dungeon_finish());assert(run.receipt.first_clear&&s_dungeon.clears==1&&run.receipt.items.quantity[ITEM_LEAF_STONE]==1);
 before=s_party;inv=s_inventory;restart();assert(dungeon_resume());assert(s_dungeon.clears==1&&!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&inv,&s_inventory,sizeof(inv)));tests++;
 assert(dungeon_new(chosen,3,17));win(7);assert(dungeon_finish());assert(!run.receipt.first_clear&&s_dungeon.clears==2);tests++;
 // Previously earned rewards survive retirement; no consolation farming.
 assert(dungeon_new(chosen,3,19));win(0);assert(dungeon_finish());assert(dungeon_choose(0));assert(dungeon_choose(0));assert(dungeon_choose(0));before=s_party;inv=s_inventory;xp=run.xp;
 assert(dungeon_retire());assert(dungeon_finish());assert(run.phase==DUNGEON_LOST&&run.xp==xp&&!memcmp(&before,&s_party,sizeof(before))&&!memcmp(&inv,&s_inventory,sizeof(inv)));tests++;
}
static void migration(void){
 setup();save_t saved;assert(save_read_status(&saved)==SAVE_READ_OK);saved.version=14;saved.exploration.research_flags=3;
 memcpy(disk,&saved,sizeof(save_v14_t));disk_len=sizeof(save_v14_t);save_t next;assert(save_read_status(&next)==SAVE_READ_MIGRATED);
 assert(next.version==SAVE_VERSION&&next.exploration.research_flags==3&&next.dungeon.run_id==0);assert(!memcmp(next.party,saved.party,PARTY_BYTES));tests++;
 saved.version=15;memcpy(disk,&saved,sizeof(save_v14_t));assert(save_read_status(&next)==SAVE_READ_ERROR);tests++;
}
static void rewards(void){
 dungeon_progress_t p={0};dungeon_receipt_t r;dungeon_reward_plan(4,1,&p,&r);assert(r.first_elite&&r.items.quantity[ITEM_BERRY]==3&&r.items.quantity[ITEM_GREAT]==2&&r.items.quantity[ITEM_MILK]==1);
 dungeon_reward_plan(7,1,&p,&r);assert(r.first_clear&&r.items.quantity[ITEM_ULTRA]==2&&r.items.quantity[ITEM_LEAF_STONE]==1);
 p.clears=2;dungeon_reward_plan(7,1,&p,&r);assert(!r.first_clear&&r.items.quantity[ITEM_LINK_MACHINE]>=1);
 p.clears=9;dungeon_reward_plan(7,1,&p,&r);assert(r.items.quantity[ITEM_GROWTH_MACHINE]==1);tests++;
 setup();assert(dungeon_new(chosen,3,20));for(unsigned i=0;i<ITEM_COUNT;i++)s_inventory.quantity[i]=items_capacity(i);world_debug_save();win(7);assert(dungeon_finish());assert(run.receipt.full);for(unsigned i=0;i<ITEM_COUNT;i++)assert(!run.receipt.items.quantity[i]);tests++;
}
static void combos(void){
 setup();assert(dungeon_new(chosen,3,123));dungeon_t base=run;
 base.battle.session.next=0;base.battle.session.acted=0;base.battle.session.planned[0]=33;base.battle.session.sides[1].mons[0].status=2;
 trainer_event_t plain,pursuit,relay;run=base;assert(dungeon_step(&plain));assert(plain.attack.damage>0);
 run=base;run.cards=1u<<12;assert(dungeon_step(&pursuit));assert(pursuit.attack.damage>plain.attack.damage&&dungeon_feedback());
 run=base;run.cards=1u<<13;run.relay_mask=1;assert(dungeon_step(&relay));assert(relay.attack.damage>plain.attack.damage&&!run.relay_mask);tests++;
 run=base;run.cards=(1u<<11)|(1u<<13);run_fail_after=0;assert(!dungeon_switch(1,false));assert(!run.guards&&!run.relay_mask);
 assert(dungeon_switch(1,false));assert(run.guards==2&&run.relay_mask==2&&run.battle.session.sides[0].mons[1].defense==1);tests++;
 run=base;run.cards=1u<<14;run.battle.session.sides[0].mons[0].hp=80;run.battle.session.sides[1].mons[0].hp=1;
 assert(dungeon_step(&relay));assert(run.battle.session.sides[0].mons[0].hp>80&&relay.attack.pet_hp==run.battle.session.sides[0].mons[0].hp);tests++;
}

static void owned_partners(void){
 setup();uint8_t slots[3]={2,1,0};
 // Two distinct individuals of the same species, including a shiny partner.
 s_party.party[1]=(mon_t){.species_id=1,.level=16,.exp=exp_for_level(16)};
 s_party.party[2]=s_party.party[1];s_party.party[2].flags=1;world_debug_save();
 assert(dungeon_new(slots,2,123));assert(run.count==2&&run.ids[0]==1&&run.ids[1]==1);
 assert(run.members[0].flags&1);assert(run.battle.session.sides[0].mons[0].level==16);
 assert(run.battle.session.sides[1].mons[0].level==12);
 trainer_store_t battle;world_party_t view;dungeon_snapshot(&battle,&view);
 assert(view.count==2&&view.members[0].flags==1&&view.members[1].flags==0);tests++;
 world_party_snapshot(&view);assert(view.switch_locked);
 assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_BUSY);
 mon_t incoming={.species_id=25,.level=5,.exp=exp_for_level(5)};s_party.box[0]=incoming;
 assert(world_box_exchange(1,&view.members[1],&incoming)==WORLD_SWITCH_BUSY);
 restart();world_party_snapshot(&view);assert(view.switch_locked&&run.count==2&&run.slots[0]==2);tests++;
 party_t before=s_party;win(0);assert(dungeon_finish());
 assert(s_party.party[1].exp>before.party[1].exp&&s_party.party[2].exp>before.party[2].exp);
 assert(!memcmp(&before.party[0],&s_party.party[0],sizeof(mon_t)));
 assert(!memcmp(&before.party[3],&s_party.party[3],sizeof(mon_t)));
 assert(dungeon_abandon());world_party_snapshot(&view);assert(!view.switch_locked);
 assert(world_set_leader(1,&view.members[1],NULL)==WORLD_SWITCH_OK);tests++;
 // One owned starter can enter. No phantom team slots, level 50 rentals or fees on bad selection.
 setup();slots[0]=0;slots[1]=0;int32_t stamina=s_w.pet.stamina;
 assert(!dungeon_new(slots,0,1)&&!dungeon_new(slots,2,1));assert(s_w.pet.stamina==stamina);
 slots[0]=5;assert(!dungeon_new(slots,1,1));assert(s_w.pet.stamina==stamina);
 slots[0]=0;assert(dungeon_new(slots,1,1));assert(run.count==1&&run.members[0].species_id==1&&run.members[0].level==s_party.party[0].level);
 assert(run.battle.session.sides[0].count==1);run.node=7;assert(begin_battle(&run,false));assert(run.battle.session.sides[1].count==1);tests++;
 // Growth/evolution affect the next encounter, while the original difficulty stays fixed.
 run.battle.session.sides[0].mons[0].hp=1;unsigned baseline=run.base_level;
 s_party.party[0].species_id=2;s_w.species=2;s_party.party[0].level=s_w.level=20;s_party.party[0].exp=s_w.exp=exp_for_level(20);
 run.node=2;assert(begin_battle(&run,false));assert(run.ids[0]==2&&run.members[0].level==20&&run.base_level==baseline&&run.battle.session.sides[0].mons[0].hp>0);tests++;
 // Ending a run never unlocks team changes before a pending receipt is safely committed.
 win(0);failure=4;assert(!dungeon_finish());assert(!dungeon_abandon()&&dungeon_party_locked());failure=0;
 assert(dungeon_abandon()&&!dungeon_party_locked());tests++;
}
static void abandon_then_exchange(void){
 setup();assert(dungeon_new(chosen,3,21));
 mon_t incoming={.species_id=25,.level=40,.exp=exp_for_level(40),.flags=1};s_party.box[0]=incoming;world_debug_save();
 win(4);failure=4;assert(!dungeon_finish());failure=0;
 world_party_t before,after;world_party_snapshot(&before);
 // Save the earned reward, but fail to acknowledge it in the dungeon record.
 run_fail_after=0;assert(!dungeon_abandon());assert(dungeon_party_locked());
 party_t paid=s_party;inventory_t items=s_inventory;int32_t stamina=s_w.pet.stamina;
 assert(paid.party[chosen[0]].exp>before.members[chosen[0]].exp);
 restart();assert(dungeon_abandon());world_party_snapshot(&after);
 assert(!after.switch_locked&&!memcmp(&paid,&s_party,sizeof(paid))&&!memcmp(&items,&s_inventory,sizeof(items)));
 // The pre-confirmation member is stale after settlement; refreshed EXP must be used.
 assert(world_box_exchange(chosen[0],&before.members[chosen[0]],&incoming)==WORLD_SWITCH_STALE);
 assert(world_box_exchange(chosen[0],&after.members[chosen[0]],&incoming)==WORLD_SWITCH_OK);
 assert(s_party.party[chosen[0]].flags&1);
 int box=party_box_match(&s_party,&after.members[chosen[0]]);assert(box>=0);
 restart();assert(!dungeon_party_locked()&&s_party.party[chosen[0]].flags&1);
 assert(party_box_match(&s_party,&after.members[chosen[0]])>=0);
 assert(!memcmp(&items,&s_inventory,sizeof(items))&&s_w.pet.stamina==stamina);tests++;
}
int main(void){assert(assets_init());abandon_then_exchange();owned_partners();combos();admission();receipts();migration();rewards();printf("{\"cases\":%u,\"save_bytes\":%zu,\"sanitized\":true}\n",tests,sizeof(save_t));return 0;}
'''
if __name__=='__main__':harness.run()
