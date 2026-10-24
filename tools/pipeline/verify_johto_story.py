#!/usr/bin/env python3
"""Production story transactions, special individuals, full storage and rollback."""
import verify_trainer_campaign as h
from save_history_fixtures import c_cases
h.CASES=c_cases()+r'''
static void seed_story(void){fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);s_challenge.defeated=16383;johto_init(&s_johto);s_johto.phase=JOHTO_ACTIVE;s_johto.starter=152;s_johto.badges=255;s_johto.research[2]=12;s_w.pet.stamina=100*NURT_Q;world_debug_save();}
static void stories(void){
 seed_story();story_request_t q={.op=STORY_RESCUE_BEGIN,.seed=32,.box_slot=BOX_CAPACITY};story_result_t out;
 failure=1;assert(world_story_action(&q,&out)==ACT_SAVE_FAILED&&!s_story.rescue_step);failure=0;
 for(unsigned n=0;n<2;n++){
  assert(world_story_action(&q,&out)==ACT_OK);unsigned expected=n?158:155;assert(s_story.rescue_partner.species_id==expected);johto_story_t before=s_story;
  story_request_t choose={.op=STORY_RESCUE_CHOOSE,.choice=(johto_rescue_answer(&s_story)+1)%3};assert(world_story_action(&choose,&out)==ACT_LOCKED&&!memcmp(&before,&s_story,sizeof(before)));
  for(unsigned step=0;step<2;step++){choose.choice=johto_rescue_answer(&s_story);assert(world_story_action(&choose,&out)==ACT_OK);reboot();assert(s_story.rescue_step==step+2);}
  choose.op=STORY_RESCUE_CLAIM;choose.box_slot=BOX_CAPACITY;assert(world_story_action(&choose,&out)==ACT_OK&&out.partner.species_id==expected);assert(world_story_action(&choose,&out)==ACT_LOCKED);reboot();
 }
 assert(s_story.rescues==2);
 for(unsigned g=0;g<4;g++)for(unsigned step=0;step<3;step++){q=(story_request_t){.op=STORY_RUIN_CHOOSE,.group=g,.choice=johto_ruin_answer(g,step)};assert(world_story_action(&q,&out)==ACT_OK);}
 assert(s_story.ruins==15);
 for(unsigned g=0;g<4;g++){for(unsigned n=0;n<80;n++){unsigned f=johto_ruin_form(&s_story,g,n*977);assert(f>=g*7&&f<(g==3?26:g*7+7));s_story.forms_caught|=1u<<f;}}
 assert(s_story.forms_caught==0x3ffffff);
 q=(story_request_t){.op=STORY_TOWER};assert(world_story_action(&q,&out)==ACT_OK);assert(world_story_action(&q,&out)==ACT_LOCKED);
 for(unsigned r=0;r<8;r++)johto_story_explore(&s_story,&s_johto,r);
 for(unsigned r=0;r<8;r++)johto_story_explore(&s_story,&s_johto,r);
 // Ordinary visits no longer unlock legendary evidence. Continue from a retained old checkpoint.
 assert(!s_johto.legend_clues[0]&&!s_johto.legend_clues[1]&&!s_johto.legend_clues[2]);
 s_johto.legend_clues[0]=s_johto.legend_clues[1]=3;s_johto.legend_clues[2]=2;
 q=(story_request_t){.op=STORY_PURIFY,.choice=1};assert(world_story_action(&q,&out)==ACT_OK&&s_johto.legend_clues[2]==3);
 for(unsigned i=0;i<5;i++){s_johto.legend_clues[i]=3;}s_activities.silver_feather=1;assert(world_johto_final_available());assert(world_challenge_start(TRAINER_JOHTO_FIRST+9)==WORLD_CHALLENGE_LOCKED);
 s_johto.phase=JOHTO_COMPLETE;q=(story_request_t){.op=STORY_FINAL_PRIZE,.choice=0};s_inventory.quantity[ITEM_SUN_STONE]=items_capacity(ITEM_SUN_STONE);assert(world_story_action(&q,&out)==ACT_FULL&&!s_johto.final_reward_claimed);s_inventory.quantity[ITEM_SUN_STONE]--;assert(world_story_action(&q,&out)==ACT_OK&&s_johto.final_reward_claimed);assert(world_story_action(&q,&out)==ACT_LOCKED);reboot();assert(s_johto.final_reward_claimed);
}
static void full_rescue(void){
 seed_story();story_request_t q={.op=STORY_RESCUE_BEGIN,.seed=32,.box_slot=BOX_CAPACITY};story_result_t out;assert(world_story_action(&q,&out)==ACT_OK);
 for(unsigned i=0;i<2;i++){q.op=STORY_RESCUE_CHOOSE;q.choice=johto_rescue_answer(&s_story);assert(world_story_action(&q,&out)==ACT_OK);}
 for(unsigned i=1;i<6;i++){s_party.party[i]=(mon_t){.species_id=25,.level=10,.exp=exp_for_level(10),.hp=100};}s_party.party_count=6;
 for(unsigned i=0;i<BOX_CAPACITY;i++)s_party.box[i]=(mon_t){.species_id=1+i%251,.level=20,.exp=exp_for_level(20),.hp=100,.flags=i%2};
 q.op=STORY_RESCUE_CLAIM;assert(world_story_action(&q,&out)==ACT_FULL&&s_story.rescue_step==3);q.box_slot=752;q.expected=s_party.box[752];q.expected.level++;assert(world_story_action(&q,&out)==ACT_STALE);
 q.expected=s_party.box[752];mon_t neighbor=s_party.box[751];failure=4;assert(world_story_action(&q,&out)==ACT_SAVE_FAILED&&!memcmp(&q.expected,&s_party.box[752],sizeof(mon_t)));failure=0;
 assert(world_story_action(&q,&out)==ACT_OK&&s_party.box[752].species_id==155&&!memcmp(&neighbor,&s_party.box[751],sizeof(mon_t)));reboot();assert(s_party.box[752].species_id==155&&party_total(&s_party)==759);
}
static void specials(void){
 combat_mon_t a,b;mon_t owned={.species_id=235,.level=60,.hp=100};combat_init(&a,235,60,300);combat_init(&b,25,60,300);b.last_move=85;b.last_damage=20;combat_set_individual(&a,&owned);uint32_t rng=7;battle_round_t r={0};assert(combat_choose(&a,&b,&rng)==166);combat_turn(&a,&b,1024,&rng,50,166,&r);assert(!r.no_effect&&a.pp[0]==85);combat_record_sketch(&owned,&a);assert(owned.special.sketch[0]==85&&combat_individual_valid(&owned));combat_reset_volatile(&a);assert(a.pp[0]==85);uint16_t ids[8];assert(combat_individual_moves(&owned,ids,8)==2&&ids[0]==85&&ids[1]==166);owned.special.sketch[1]=85;assert(!combat_individual_valid(&owned));
 for(unsigned form=0;form<26;form++){uint8_t size;assert(assets_front_form(201,form,&size)&&size==56);sprite_asset_t back;assert(assets_back_form(201,form,&back)&&back.w==56);}
 combat_init(&a,201,50,200);combat_init(&b,25,50,500);a.pp[1]=9; // Ground: target electric, super effective.
 combat_turn(&a,&b,1024,&rng,50,237,&r);assert(r.move_type==8&&r.mult==200&&b.hp<500);
 combat_init(&a,202,50,300);combat_init(&b,25,50,300);a.last_damage=25;b.last_move=85;combat_turn(&a,&b,1024,&rng,50,243,&r);assert(b.hp==250&&!r.no_effect);
 combat_init(&a,202,50,300);combat_init(&b,25,50,300);a.last_damage=25;b.last_move=33;combat_turn(&a,&b,1024,&rng,50,243,&r);assert(b.hp==300&&r.no_effect);
}
static void migration(void){for(unsigned i=0;i<sizeof(history)/sizeof(history[0]);i++){static save_t s;assert(save_decode(&s,history[i].data,history[i].size,0)!=SAVE_READ_ERROR);if(history[i].version<29)assert(!s.story.forms_caught&&!s.story.rescues&&!s.story.ending_seen);}}
int main(void){assert(assets_init());stories();full_rescue();specials();migration();printf("story receipts, retry, save failure, all letters, three beasts, special moves, old saves: passed\n");}
'''
h.run()
