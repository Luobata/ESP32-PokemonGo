#!/usr/bin/env python3
"""Real refresh planner and world/save transactions, with simulated radio/NVS."""
import argparse,json,subprocess,sys
from pathlib import Path
import verify_world_party as harness
ROOT=harness.ROOT
CASES=r'''
bool assets_species(uint16_t id,species_t *out) {
 if(id<1||id>151)return false;memset(out,0,sizeof(*out));out->id=id;
 out->hp=out->attack=out->defense=out->special=out->speed=36+(id%5)*16;return true;
}
uint32_t assets_species_count(void){return 151;}
bool trainer_store_valid(const trainer_store_t *s){return !s->session.active&&!s->league_active;}
static void ap_set(enc_refresh_ap_t *a,unsigned id) {
 *a=(enc_refresh_ap_t){.bssid={2,3,(id>>16)&255,(id>>8)&255,id&255,6},.rssi=-50,.auth=0,.has_ssid=true};
}
static void unique(const enc_queue_t *q) {
 assert(q->count<=5);
 for(unsigned i=0;i<q->count;i++)for(unsigned j=0;j<i;j++) {
  assert(q->items[i].species_id!=q->items[j].species_id);
  assert(q->items[i].uid!=q->items[j].uid);
 }
}
static void pure_rules(void) {
 enc_refresh_state_t s={0};enc_queue_t q;dex_t d={0};enc_queue_init(&q);
 enc_refresh_ap_t a[64];for(unsigned i=0;i<64;i++)ap_set(a+i,i+1);
 assert(enc_refresh_scan(&s,a,1,false,0,&q,&d,0)==1);
 assert(s.base_started && s.next_base_s==14400);
 for(unsigned i=0;i<20;i++)assert(enc_refresh_scan(&s,a,1,false,0,&q,&d,0)==0);
 s.online_s=3599;assert(enc_refresh_scan(&s,a,1,true,1024,&q,&d,0)==0);
 assert(s.hunt_q10==1024);
 s.online_s=3600;assert(enc_refresh_scan(&s,a,1,true,0,&q,&d,0)==1);unique(&q);
 s.online_s=14400;assert(enc_refresh_scan(&s,a,1,false,0,&q,&d,0)==1);unique(&q);
 // Dense environments: duplicate BSSIDs in a scan cannot bypass cooldown.
 s=(enc_refresh_state_t){0};enc_queue_init(&q);for(unsigned i=1;i<64;i++)a[i]=a[0];
 assert(enc_refresh_scan(&s,a,64,true,4096,&q,&d,1)==1);
 assert(q.items[0].uid!=1 && s.hunt_q10==3072);
 assert(enc_refresh_scan(&s,a,64,true,4096,&q,&d,1)==0 && s.hunt_q10==4096);
 // 4 hunt + 1 base in a fresh scan, five distinct species, all oldest FIFO.
 s=(enc_refresh_state_t){0};enc_queue_init(&q);
 for(unsigned i=0;i<64;i++)ap_set(a+i,i+1);
 assert(enc_refresh_scan(&s,a,64,true,4096,&q,&d,0)==5);unique(&q);
 uint16_t oldest=q.items[0].uid;
 assert(enc_refresh_scan(&s,a,64,true,1024,&q,&d,0)==1);
 assert(!enc_queue_find(&q,oldest));unique(&q);
 // Hard memory bound does not evict still-cooling APs to bypass cooldown.
 s=(enc_refresh_state_t){.base_started=1,.next_base_s=14400};enc_queue_init(&q);
 for(unsigned i=0;i<64;i++) {
  ap_set(a,i+1);assert(enc_refresh_scan(&s,a,1,true,1024,&q,&d,0)==1);
 }
 ap_set(a,999);assert(enc_refresh_scan(&s,a,1,true,1024,&q,&d,0)==0);
 s.online_s=3600;assert(enc_refresh_scan(&s,a,1,true,0,&q,&d,0)==1);assert(enc_refresh_valid(&s));
 // Long sequence, ordinary open APs: each 8 exploration encounters includes
 // >=4 stars, each 30 includes 5; never assumes office encryption/weak RSSI.
 s=(enc_refresh_state_t){.base_started=1,.next_base_s=UINT32_MAX};enc_queue_init(&q);
 unsigned rare=0,elite=0,max_rare=0,max_elite=0;
 for(unsigned i=0;i<2000;i++) {
  s.online_s=i*120;ap_set(a,i+1);
  assert(enc_refresh_scan(&s,a,1,true,1024,&q,&d,0)==1);
  uint8_t r=q.items[q.count-1].rarity;
  rare++;elite++;if(rare>max_rare)max_rare=rare;if(elite>max_elite)max_elite=elite;
  if(r>=4)rare=0;if(r==5)elite=0;
  assert(rare<8 && elite<30 && enc_refresh_valid(&s));unique(&q);
 }
 assert(s.discoveries==2000 && max_rare<=8 && max_elite<=30);
 assert(enc_rarity_from_ap(-50,8,true,false)==1);
 for(unsigned i=0;i<5;i++)assert(enc_rarity_from_ap(-50,(unsigned[]){5,10,14,15,16}[i],true,false)==2);
 tests+=10;
}
static void radio(unsigned id) {
 enc_refresh_ap_t ap;ap_set(&ap,id);s_last_n=1;memset(s_recs,0,sizeof(s_recs));
 memcpy(s_recs[0].bssid,ap.bssid,6);s_recs[0].rssi=-50;s_recs[0].ssid[0]='x';
}
static void concurrent_seen(void) {extra_commit_hook=NULL;world_mark_seen(150,true);}
static void transactions(void) {
 fresh();radio(1);assert(refresh_from_scan(false,0)==0);assert(world_choose_starter(25)==WORLD_STARTER_OK);
 unsigned notices=alert_count;assert(refresh_from_scan(false,0)==1&&alert_count==notices);
 assert(s_queue.count==0&&s_exploration.energy==4);enc_refresh_state_t kept=s_refresh;
 reboot();radio(1);assert(refresh_from_scan(false,0)==0&&s_refresh.serial==kept.serial&&s_exploration.energy==4);
 radio(2);assert(refresh_from_scan(true,512)==0);world_debug_save();reboot();assert(s_refresh.hunt_q10==512);
 assert(refresh_from_scan(true,512)==1&&s_refresh.hunt_q10==0&&s_exploration.energy==5);
 for(int f=1;f<=4;f++){if(f==3)continue;radio(100+f);enc_refresh_state_t old=s_refresh;exploration_state_t x=s_exploration;
  failure=f;assert(refresh_from_scan(true,1024)==0);failure=0;
  assert(!memcmp(&old,&s_refresh,sizeof(old))&&!memcmp(&x,&s_exploration,sizeof(x))&&alert_count==notices);
 }
 tests+=5;
}

static void migrations(const char *real) {
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);save_t current;assert(save_read(&current));
 for(unsigned version=5;version<=9;version++) {
  memset(disk,0,sizeof(disk));
  if(version==5){save_v5_t old={0};memcpy(&old,&current,sizeof(old));old.version=5;memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);}
  if(version==6){save_v6_t old=current.v6;old.version=6;memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);}
  if(version==7){save_v7_t old={0};old.v6=current.v6;old.version=7;memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);}
  if(version==8){save_v8_t old={0};old.v6=current.v6;old.version=8;memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);}
  if(version==9){save_v9_t old=current.v9;old.version=9;memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);}
  save_t migrated;assert(save_read_status(&migrated)==SAVE_READ_MIGRATED);
  assert(migrated.version==SAVE_VERSION && !memcmp(migrated.party,current.party,PARTY_BYTES));
  assert(migrated.refresh.base_started && enc_refresh_valid(&migrated.refresh));
  assert(save_write(&migrated));assert(save_read_status(&migrated)==SAVE_READ_OK);
 }
 if(real) {
  FILE *f=fopen(real,"rb");assert(f);save_v9_t old;assert(fread(&old,1,sizeof(old),f)==sizeof(old));assert(fgetc(f)==EOF);fclose(f);
  assert(old.version==9);memcpy(disk,&old,sizeof(old));disk_len=sizeof(old);
  save_t migrated;assert(save_read_status(&migrated)==SAVE_READ_MIGRATED);
  assert(!memcmp(migrated.party,old.party,PARTY_BYTES));assert(!memcmp(&migrated.dex,&old.dex,sizeof(old.dex)));
  assert(!memcmp(&migrated.inventory,&old.inventory,sizeof(old.inventory)));
  assert(!memcmp(&migrated.challenge,&old.challenge,sizeof(old.challenge)));
  assert(!memcmp(&migrated.achievements,&old.achievements,sizeof(old.achievements)));
  assert(migrated.exp==old.exp&&migrated.level==old.level&&migrated.species==old.species);
  assert(save_write(&migrated));reboot();radio(1);assert(refresh_from_scan(false,0)==0);
 }
 tests+=6;
}
int main(void) {
 pure_rules();transactions();migrations(REAL_SAVE);
 printf("{\"cases\":%u,\"sequence_encounters\":2000,\"save_version\":%d,\"save_bytes\":%zu,\"erase_calls\":%u}\n",tests,SAVE_VERSION,sizeof(save_t),erase_calls);
 return 0;
}
'''
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--save',type=Path);args=ap.parse_args()
 harness.CASES=CASES.replace('REAL_SAVE',json.dumps(str(args.save.resolve())) if args.save else 'NULL')
 try:report=harness.run(ROOT)
 except subprocess.CalledProcessError as e:print(e.stdout,e.stderr);raise
 report['real_v9_tested']=bool(args.save)
 out=ROOT/'reports/evidence/routes-v11-2026-09-08';out.mkdir(parents=True,exist_ok=True)
 (out/'legacy-refresh-verification.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
