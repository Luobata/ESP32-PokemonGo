#!/usr/bin/env python3
"""Gym receipts, supply floor and generation-II damage consistency regressions."""
import verify_trainer_campaign as h
h.CASES=r'''
static void supplies(void){
 unsigned balls=0;
 for(unsigned seed=1;seed<=10000;seed++){item_loot_t x=items_roll_loot(1,seed);assert(x.item_id<ITEM_COUNT&&x.quantity);if(x.item_id==ITEM_POKE)balls+=x.quantity;}
 assert(balls>=10000);printf("balls per common win: %.3f\n",balls/10000.0);
 inventory_t bag={0};trainer_store_t st={0};st.session.active=st.session.finished=st.session.won=1;
 trainer_grant_items(&st,&bag);assert(bag.quantity[ITEM_POKE]==5&&bag.quantity[ITEM_BERRY]==3&&bag.quantity[ITEM_MILK]==2&&bag.quantity[ITEM_MOON_STONE]==1);
 trainer_settle(&st);inventory_t before=bag;trainer_grant_items(&st,&bag);assert(!memcmp(&bag,&before,sizeof(bag)));
 st.session.active=1;trainer_grant_items(&st,&bag);assert(bag.quantity[ITEM_MILK]==3&&bag.quantity[ITEM_POKE]==7&&bag.quantity[ITEM_MOON_STONE]==1);
 tests++;
}
static void damage(void){
 for(unsigned seed=1;seed<200;seed++){
  combat_mon_t a,b;combat_init(&a,25,50,10000);combat_init(&b,143,50,10000);
  battle_round_t normal={0},burn={0};uint32_t x=seed;
  combat_turn(&a,&b,1024,&x,50,33,&normal);
  combat_init(&a,25,50,10000);combat_init(&b,143,50,10000);a.status=2;x=seed;
  combat_turn(&a,&b,1024,&x,50,33,&burn);
  if(normal.critical){if(normal.damage!=burn.damage)printf("critical seed %u damage %u burn %u crit2 %u\n",seed,normal.damage,burn.damage,burn.critical);assert(normal.damage==burn.damage);}else assert(burn.damage<=normal.damage);
  // Conversion to Normal cannot add STAB to typeless Struggle.
  memset(&normal,0,sizeof(normal));memset(&burn,0,sizeof(burn));
  combat_init(&a,25,50,10000);combat_init(&b,143,50,10000);x=seed;combat_turn(&a,&b,1024,&x,50,165,&normal);
  combat_init(&a,25,50,10000);combat_init(&b,143,50,10000);a.converted=1;a.converted_type=TY_NORMAL;x=seed;combat_turn(&a,&b,1024,&x,50,165,&burn);if(normal.damage!=burn.damage)printf("struggle seed %u damage %u converted %u\n",seed,normal.damage,burn.damage);assert(normal.damage==burn.damage);
 }
 // Production wild mode must use the same damage scale as the shared trainer core.
 battle_session_t w;assert(battle_session_init(&w,25,50,143,50,1024,123));
 combat_mon_t a=w.fighters[0],b=w.fighters[1];uint32_t rng=w.rng;
 uint16_t pa=combat_choose(&a,&b,&rng),pb=combat_choose(&b,&a,&rng);(void)pb;
 battle_round_t expected={0},actual={0};combat_turn(&a,&b,1024,&rng,50,pa,&expected);
 assert(battle_session_step(&w,&actual)&&actual.by_pet);assert(actual.damage==expected.damage);
 tests++;
}
int main(void){assert(assets_init());supplies();damage();printf("{\"status\":\"PASS\",\"groups\":%u}\n",tests);}
'''
if __name__=='__main__':h.run()
