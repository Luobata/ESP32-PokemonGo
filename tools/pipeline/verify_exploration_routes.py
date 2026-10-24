#!/usr/bin/env python3
"""Production C route/credit/save transactions; ASan + UBSan + real V10 migration."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import verify_world_party as harness
ROOT=harness.ROOT
def history_array(version):
 manifest=json.loads((ROOT/'tools/pipeline/fixtures/save_history/manifest.json').read_text())
 record=next(f for f in manifest['fixtures'] if f['version']==version)
 data=(ROOT/'tools/pipeline/fixtures/save_history'/record['file']).read_bytes()
 assert len(data)==record['size'] and hashlib.sha256(data).hexdigest()==record['sha256']
 return f'static const unsigned char fixed_v{version}[]={{'+','.join(map(str,data))+'};\n'

CASES=r'''
bool assets_species(uint16_t id,species_t *out){if(id<1||id>151)return false;memset(out,0,sizeof(*out));out->id=id;out->hp=out->attack=out->defense=out->special=out->speed=40;return true;}
uint32_t assets_species_count(void){return 151;}
bool trainer_store_valid(const trainer_store_t *s){return !s->session.active&&!s->league_active;}
static unsigned tests;
static void radio(unsigned id){s_last_n=1;memset(s_recs,0,sizeof(s_recs));s_recs[0].bssid[0]=2;s_recs[0].bssid[4]=id>>8;s_recs[0].bssid[5]=id;s_recs[0].rssi=-50;s_recs[0].ssid[0]='x';}
static void core(void){
 for(unsigned route=0;route<4;route++){
  exploration_state_t x;exploration_init(&x);x.route=route;x.energy=24;
  enc_refresh_state_t r={0};enc_queue_t q;enc_queue_init(&q);dex_t d;dex_init(&d);
  for(unsigned step=0;step<7;step++){
   exploration_event_t e=exploration_step(&x,&r,&q,&d,1);
   assert(e.kind==(step==6?EXPLORE_TARGET:step%2?EXPLORE_CLUE:EXPLORE_ENCOUNTER));
   assert(x.energy==24&&x.steps==step+1);
   if(e.species){assert(e.uid!=1&&dex_is_seen(&d,e.species));enc_queue_init(&q);}
   if(step==5)assert(x.clues[route]==3);
   if(step==6){unsigned native;assert(exploration_habitat(e.species,&native)>=0);assert(e.species==exploration_route(route)->target&&e.rarity==native&&!x.clues[route]);}
  }
 }
 // A pending target cannot block exploration; it remains a separate individual.
 exploration_state_t x={.energy=1,.clues={3}};enc_refresh_state_t r={0};enc_queue_t q;enc_queue_init(&q);dex_t d;dex_init(&d);
 encounter_t e={.species_id=25,.rarity=2,.hp_ratio=100};enc_queue_push(&q,&e);
 encounter_t old=q.items[0];exploration_event_t again=exploration_step(&x,&r,&q,&d,0);
 assert(again.kind==EXPLORE_TARGET&&again.species==25&&again.uid!=old.uid&&q.count==2&&!memcmp(&old,&q.items[0],sizeof(old))&&!x.clues[0]);
 x.energy=0;x.clues[0]=3;enc_queue_init(&q);assert(exploration_step(&x,&r,&q,&d,0).kind==EXPLORE_TARGET && x.energy==0);
 // Long play: clues never consume rarity pity; route changes do not reset it.
 unsigned rare=0,elite=0,seen[152]={0},monsters=0;
 exploration_init(&x);memset(&r,0,sizeof(r));
 for(unsigned i=0;i<20000;i++){
  x.energy=24;x.route=(i/100)%4;enc_queue_init(&q);
  unsigned a=r.since_rare,b=r.since_elite;
  exploration_event_t out=exploration_step(&x,&r,&q,&d,0);
  if(out.kind==EXPLORE_CLUE){assert(a==r.since_rare&&b==r.since_elite);continue;}
  assert(out.kind==EXPLORE_ENCOUNTER||out.kind==EXPLORE_TARGET);monsters++;seen[out.species]++;
  if(out.kind!=EXPLORE_TARGET){rare++;elite++;}assert(rare<=8&&elite<=30);if(out.rarity>=4)rare=0;if(out.rarity==5)elite=0;
  assert(enc_refresh_valid(&r)&&exploration_valid(&x));
 }
 for(unsigned i=1;i<=151;i++)assert(seen[i]);assert(monsters>10000);
 // Preserve five-slot FIFO, including when a clue precedes an eviction.
 enc_queue_init(&q);for(unsigned i=0;i<5;i++){e.species_id=140+i;enc_queue_push(&q,&e);}uint16_t first=q.items[0].uid;
 x=(exploration_state_t){.energy=2};r=(enc_refresh_state_t){0};assert(exploration_step(&x,&r,&q,&d,0).kind==EXPLORE_ENCOUNTER);
 assert(q.count==5&&!enc_queue_find(&q,first));
 tests+=10;
}
static void credits(void){
 fresh();radio(1);assert(refresh_from_scan(false,0)==0);assert(world_choose_starter(25)==WORLD_STARTER_OK);
 assert(s_exploration.energy==0);unsigned notices=alert_count;
 assert(refresh_from_scan(false,0)==0&&s_queue.count==0&&alert_count==notices);
 s_exploration.energy=24;s_refresh.hunt_q10=4096;world_debug_save();reboot();radio(1);
 assert(refresh_from_scan(false,0)==0&&s_exploration.energy==24&&s_refresh.hunt_q10==0);
 reboot();assert(s_refresh.hunt_q10==0&&s_exploration.energy==24);
 unsigned discoveries=s_refresh.discoveries;radio(2);failure=4;
 assert(refresh_from_scan(true,512)==0&&s_refresh.discoveries==discoveries);failure=0;
 assert(refresh_from_scan(true,512)==1&&s_refresh.discoveries==discoveries+1&&s_exploration.energy==24);
 reboot();assert(s_refresh.discoveries==discoveries+1&&s_exploration.energy==24);
 for(unsigned i=0;i<100;i++){radio(i+3);assert(refresh_from_scan(false,4096)==0);}
 assert(s_refresh.discoveries==discoveries+1&&s_refresh.hunt_q10==0&&s_queue.count==0);
 tests+=8;
}
static void supply_loop(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);radio(1);
 s_exploration.energy=24;s_refresh.hunt_q10=4096;world_debug_save();
 for(int f=1;f<=4;f++){if(f==3)continue;failure=f;
  assert(refresh_from_scan(false,0)==0&&s_refresh.hunt_q10==4096);failure=0;
 }
 assert(refresh_from_scan(false,0)==0&&s_refresh.hunt_q10==0);
 s_exploration.energy=23;world_debug_save();
 for(unsigned i=0;i<10;i++){radio(i+1);assert(refresh_from_scan(false,0)==0&&s_exploration.energy==23);}
 reboot();assert(s_exploration.energy==23&&s_refresh.hunt_q10==0&&s_queue.count==0);tests+=8;
}
static void concurrent_seen(void){extra_commit_hook=NULL;world_mark_seen(150,true);}
static void transactions(void){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 for(int f=1;f<=4;f++){if(f==3)continue;
  exploration_state_t x=s_exploration;enc_queue_t q=s_queue;dex_t d=s_dex;enc_refresh_state_t r=s_refresh;
  failure=f;assert(world_explore().kind==EXPLORE_SAVE_FAILED);failure=0;
  assert(!memcmp(&x,&s_exploration,sizeof(x))&&!memcmp(&q,&s_queue,sizeof(q))&&!memcmp(&d,&s_dex,sizeof(d))&&!memcmp(&r,&s_refresh,sizeof(r)));
 }
 exploration_event_t e=world_explore();assert(e.kind==EXPLORE_ENCOUNTER&&s_exploration.energy==0);uint16_t uid=e.uid;
 reboot();assert(s_exploration.energy==0&&enc_queue_find(&s_queue,uid));
 failure=4;assert(world_exploration_select(2)==EXPLORE_SAVE_FAILED&&s_exploration.route==0);failure=0;
 assert(world_exploration_select(2)==EXPLORE_NONE);reboot();assert(s_exploration.route==2);
 assert(world_exploration_select(0)==EXPLORE_NONE);
 extra_commit_hook=concurrent_seen;e=world_explore();assert(e.kind==EXPLORE_CLUE&&s_exploration.clues[0]==1&&s_exploration.energy==0&&dex_is_seen(&s_dex,150));
 world_debug_save();reboot();assert(dex_is_seen(&s_dex,150)&&s_exploration.clues[0]==1&&s_exploration.energy==0);
 battle_session_t session={.initialized=true,.started=true,.pet_species=25,.wild_species=s_queue.items[0].species_id,.pet_level=5,.wild_level=5};assert(world_battle_set_uid(uid,&session));assert(world_explore().kind==EXPLORE_BUSY&&world_exploration_select(1)==EXPLORE_BUSY);world_end_active_encounter();
 s_challenge.session.active=true;assert(world_explore().kind==EXPLORE_BUSY);s_challenge.session.active=false;
 tests+=8;
}
static void migration(const char *path){
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);save_v10_t old;assert(sizeof(old)==sizeof(fixed_v10));memcpy(&old,fixed_v10,sizeof(old));
 if(path){FILE*f=fopen(path,"rb");assert(f);assert(fread(&old,1,sizeof(old),f)==sizeof(old));assert(fgetc(f)==EOF);fclose(f);assert(old.version==10);}
 // This route harness stubs active trainer validation; test a copy with no campaign.
 // The unmodified historical bytes are covered by verify_save_import_compatibility.
 old.challenge=(trainer_store_t){0};
 memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);
 save_t next;assert(save_read_status(&next)==SAVE_READ_MIGRATED&&next.version==SAVE_VERSION);
 assert(next.species==old.species&&next.level==old.level&&next.exp==old.exp);
 assert(!memcmp(&next.pet,&old.pet,sizeof(old.pet))&&!memcmp(&next.refresh,&old.refresh,sizeof(old.refresh)));
 enc_queue_t queue=old.queue;for(unsigned i=0;i<ENC_QUEUE_CAP;i++){queue.items[i].level=0;queue.items[i].activity=0;}
 assert(!memcmp(&next.queue,&queue,sizeof(queue)));
 party_t decoded;assert(save_validate_world(&next,&decoded));
 assert(decoded.party_count==old.party[0]);
 assert(next.exploration.energy==0&&next.exploration.steps==0);assert(save_write(&next));
 next.exploration.energy=1;next.exploration.clues[2]=2;assert(save_write(&next));
 assert(save_read_status(&next)==SAVE_READ_OK&&next.exploration.energy==1&&next.exploration.clues[2]==2);
 // Malformed route state is rejected without erase or new-game overwrite.
 next.exploration.route=4;memcpy(disk,&next,sizeof(next));disk_len=sizeof(next);assert(save_read_status(&next)==SAVE_READ_ERROR);
 assert(!erase_calls);tests+=4;
}
int main(void){core();credits();supply_loop();transactions();migration(REAL_SAVE);printf("{\"cases\":%u,\"sequence_steps\":20000,\"species_reachable\":151,\"save_version\":%u,\"save_bytes\":%zu,\"erase_calls\":%u}\n",tests,SAVE_VERSION,sizeof(save_t),erase_calls);return 0;}
'''
def main():
 p=argparse.ArgumentParser();p.add_argument('--save',type=Path);a=p.parse_args()
 harness.CASES=history_array(10)+CASES.replace('REAL_SAVE',json.dumps(str(a.save.resolve())) if a.save else 'NULL')
 try:r=harness.run(ROOT)
 except subprocess.CalledProcessError as e:print(e.stdout,e.stderr);raise
 r.update(real_v10_tested=bool(a.save),sanitizers=['ASan','UBSan'])
 out=ROOT/'reports/evidence/routes-v11-2026-09-08';out.mkdir(parents=True,exist_ok=True)
 (out/'world-verification.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
if __name__=='__main__':main()
