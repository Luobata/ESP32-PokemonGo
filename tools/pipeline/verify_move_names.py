#!/usr/bin/env python3
"""Verify both name styles through the production core, renderer and fixed IDs."""
import contextlib
import io
import json
from pathlib import Path
import struct
import sys

import verify_trainer_campaign as harness
from generate_pokemon_names import generate, OUTPUT, MOVE_DATA

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import build, Renderer, png

OUT = ROOT/'reports/evidence/legacy-move-names-2026-10-07'
OUT.mkdir(parents=True, exist_ok=True)
document = json.loads(MOVE_DATA.read_text())
records = {r['id']: r['name'] for r in document['records']}
catalog = json.loads((ROOT/'tools/inspector/move-catalog.json').read_text())
assert set(records) == {r['id'] for r in catalog} and len(records) == 191
assert OUTPUT.read_text() == generate()
for r in catalog:
    assert r['legacy_name'] == records[r['id']]
# Independent historical anchors catch table swaps (official IDs, not translated labels).
assert {i: records[i] for i in (22, 33, 57, 63, 85, 127, 138, 160, 163)} == {
    22:'鹤鞭',33:'击杀',57:'友泊',63:'饰拳',85:'铅杀',127:'攀瀑',138:'奇妙',160:'全部',163:'神合'}
expected = '\n'.join(f'{{{r["id"]},"{r["name"]}","{r["legacy_name"]}"}},' for r in catalog)
harness.CASES = r'''
#include "pokemon_names.h"
static const struct {uint16_t id;const char *official,*legacy;} names[]={
''' + expected + r'''
};
int main(void){
 assert(assets_init());assert(pokemon_names_get_style()==POKEMON_NAMES_OFFICIAL);
 fresh();assert(world_choose_starter(25)==WORLD_STARTER_OK);
 save_t saved,after;assert(save_read(&saved));
 for(unsigned i=0;i<sizeof(names)/sizeof(names[0]);i++){
  move_t official,legacy,restored,asset;
  assert(pokemon_names_set_style(POKEMON_NAMES_OFFICIAL));assert(combat_move(names[i].id,&official));
  assert(official.name_zh_len==strlen(names[i].official)&&!memcmp(official.name_zh,names[i].official,official.name_zh_len));
  assert(pokemon_names_set_style(POKEMON_NAMES_GS_LEGACY));assert(combat_move(names[i].id,&legacy));
  assert(legacy.name_zh_len==strlen(names[i].legacy)&&!memcmp(legacy.name_zh,names[i].legacy,legacy.name_zh_len));
  assert(assets_move(names[i].id,&asset)&&asset.name_zh==legacy.name_zh);
  assert(official.id==legacy.id&&official.type==legacy.type&&official.power==legacy.power&&official.accuracy==legacy.accuracy&&official.pp==legacy.pp&&official.special==legacy.special);
  assert(pokemon_names_set_style(POKEMON_NAMES_OFFICIAL));assert(combat_move(names[i].id,&restored));
  assert(restored.name_zh==official.name_zh&&!strcmp(legacy.name_zh,names[i].legacy));
  for(unsigned seed=1;seed<=8;seed++){
   combat_mon_t a[2],d[2];battle_round_t r[2];uint32_t rng[2]={seed,seed};
   for(unsigned s=0;s<2;s++){
    pokemon_names_set_style(s);combat_init(&a[s],149,60,500);combat_init(&d[s],143,60,500);memset(&r[s],0,sizeof(r[s]));
    combat_turn(&a[s],&d[s],1024,&rng[s],50,names[i].id,&r[s]);
    move_t m;assert(combat_move(r[s].move_id,&m));assert(m.name_zh_len==r[s].move_zh_len&&!memcmp(m.name_zh,r[s].move_zh,m.name_zh_len));
    r[s].move_zh=NULL;r[s].move_zh_len=0;
   }
   assert(rng[0]==rng[1]&&!memcmp(&a[0],&a[1],sizeof(a[0]))&&!memcmp(&d[0],&d[1],sizeof(d[0]))&&!memcmp(&r[0],&r[1],sizeof(r[0])));
  }
 }
 // No fabricated names for unsupported IDs and no dangling strings after switching.
 uint8_t n=99;assert(!pokemon_move_names_override(0,&n)&&n==0);
 assert(!pokemon_move_names_override(251,&n)&&n==0);assert(!pokemon_move_names_override(65535,&n));
 assert(pokemon_move_names_override(63,NULL));assert(!pokemon_names_set_style(POKEMON_NAMES_STYLE_COUNT));
 uint16_t ids[COMBAT_MOVE_CAP];move_t moves[COMBAT_MOVE_CAP];
 int count=combat_known_moves(151,100,ids,COMBAT_MOVE_CAP);assert(assets_known_moves(151,100,moves,COMBAT_MOVE_CAP)==count);
 for(int i=0;i<count;i++){move_t m;assert(combat_move(ids[i],&m));assert(moves[i].name_zh==m.name_zh);}
 world_debug_save();assert(save_read(&after));assert(!memcmp(&saved,&after,sizeof(saved)));
 printf("{\"moves\":191,\"paired_combat_turns\":1528,\"save_unchanged\":true,\"sanitized\":true}\n");return 0;
}
'''
with contextlib.redirect_stdout(io.StringIO()) as output:
    harness.run()
core = json.loads(output.getvalue())
blob = (ROOT/'assets/font16.bin').read_bytes()
magic,version,size,per,count = struct.unpack_from('<4sHHHI', blob)
assert magic == b'FNT1' and size == 16 and per == 32
codepoints = struct.unpack_from(f'<{count}H', blob, 14)
chars = set(''.join(records.values()))
for c in chars:
    assert ord(c) in codepoints, c
    offset = 14+count*2+codepoints.index(ord(c))*per
    assert any(blob[offset:offset+per]), f'blank {c}'

exe, version = build()
checks = 0
def command(r, text):
    global checks
    f = r.command(text)
    assert not r.command('check')['mismatch'], text
    checks += 1
    return f

def roundtrip(r, y, height, shot):
    before = r.inspect()
    official = command(r,'names 0')
    legacy = command(r,'names 1')
    restored = command(r,'names 0')
    assert official['pixels'] == restored['pixels'], shot
    area = slice(y*480,(y+height)*480)
    assert legacy['pixels'][area] != official['pixels'][area], shot
    after = r.inspect()
    assert {k:v for k,v in before.items() if k!='names'} == {k:v for k,v in after.items() if k!='names'}, shot
    if shot:
        (OUT/(shot+'-legacy.png')).write_bytes(png(legacy['pixels']))
        (OUT/(shot+'-official.png')).write_bytes(png(official['pixels']))

r = Renderer(exe)
try:
    command(r,'boot 3 149 60 130 3 123 0 0 0')
    # Every acceptance move uses actual name text; changing style cannot change stage pixels.
    differing = 0
    for m in catalog:
        command(r,'names 0');official=command(r,f'move_preview {m["id"]} 0 4 1')
        legacy=command(r,'names 1');restored=command(r,'names 0')
        assert official['pixels']==restored['pixels'],m['id']
        different=official['pixels'][274*480:292*480]!=legacy['pixels'][274*480:292*480]
        assert different==(m['name']!=m['legacy_name']),m['id']
        differing+=different
    command(r,'move_preview 63 0 14 1');roundtrip(r,274,18,'hyper-beam')
    command(r,'move_preview 57 0 14 1');roundtrip(r,274,18,'surf')
finally:r.close()
r=Renderer(exe)
try:
    command(r,'boot 1 25 5 74 3 123 0 0 0');command(r,'grant_exp 2400')
    for _ in range(50):
        if r.inspect()['growth']:break
        command(r,'tick 120')
    assert r.inspect()['growth']
    roundtrip(r,204,66,'learned')
finally:r.close()
r=Renderer(exe)
try:
    command(r,'boot 12 149 60 74 3 123 0 0 0')
    for key in ('key 2 1','key 1 1','key 1 1','key 2 1'):
        command(r,key)
    assert r.inspect()['party_view']['skills']
    roundtrip(r,44,216,'learned-list')
finally:r.close()
r=Renderer(exe)
try:
    command(r,'boot 11 149 60 74 3 123 0 0 0')
    for _ in range(5):command(r,'key 1 1')
    command(r,'key 2 1');assert r.inspect()['menu_view']['options']
    command(r,'key 2 1');assert r.inspect()['names']==1
    command(r,'page 3');command(r,'move_preview 63 0 4 1')
    roundtrip(r,274,18,'hardware-setting')
finally:r.close()
r=Renderer(exe)
try:
    command(r,'boot 13 25 20 74 3 123 0 0 0');command(r,'key 2 1')
    for _ in range(250):
        command(r,'tick 45')
        if r.inspect()['challenge']['mode']==3:break
    assert r.inspect()['challenge']['mode']==3, r.inspect()
    roundtrip(r,274,18,'trainer')
finally:r.close()
result={'core':core,'font_characters':len(chars),'build':version,'native_moves':len(catalog),'renamed_moves':differing,'redraw_checks':checks}
(OUT/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
