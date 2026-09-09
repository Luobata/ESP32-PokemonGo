#!/usr/bin/env python3
"""Pack extracted Gold display tracks into allocation-free indexed C tables."""
import argparse,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--tracks',type=Path,default=Path('/tmp/pokewalk-gold-tracks/tracks.json'));p.add_argument('--check',action='store_true');a=p.parse_args()
r=json.loads(a.tracks.read_text());out=['// Generated from pinned Gold machine-code animation execution. Do not edit.','#pragma once','#include <stdint.h>',
 'typedef struct { uint32_t offset; uint16_t count; } gold_span_t;',
 'typedef struct { uint16_t tile; uint8_t x,y,flags; int8_t dx,dy; } gold_object_t;',
 'typedef struct { uint16_t objects,map,lines,palette; uint8_t scx,scy,lcd,bgp; } gold_frame_t;']
def table(ctype,name,rows,fmt):
 out.append(f'static const {ctype} {name}[] = {{');out.extend(fmt(row)+',' for row in rows);out.append('};')
def plain(row):return '{'+','.join(map(str,row))+'}'
for name,key,n in [('gold_tiles','tiles',16),('gold_lines','lines',96),('gold_palettes','pals',64)]:
 vals=[bytes.fromhex(s) for s in r[key]];out.append(f'static const uint8_t {name}[][ {n} ] = {{');out.extend(plain(v)+',' for v in vals);out.append('};')
out.append('static const uint16_t gold_maps[][240] = {');out.extend(plain(v)+',' for v in r['maps']);out.append('};')
flat=[];spans=[]
for rows in r['objects']:
 spans.append((len(flat),len(rows)));flat.extend(rows)
table('gold_object_t','gold_objects',flat,lambda o:plain([o[2],o[0],o[1],o[3],o[0]-o[4],o[1]-o[5]]));table('gold_span_t','gold_object_spans',spans,plain)
table('gold_frame_t','gold_frames',r['frames'],plain)
flat=[];spans=[]
for rows in r['clips']:spans.append((len(flat),len(rows)));flat.extend(rows)
out.append('static const uint16_t gold_clip_frames[] = {'+','.join(map(str,flat))+'};');table('gold_span_t','gold_clips',spans,plain)
lookup=[[[65535,65535],[65535,65535]] for _ in range(251)]
for move,side,param,clip in r['lookup']:lookup[move][side][param]=clip
out.append('static const uint16_t gold_lookup[251][2][2] = {');out.extend('{'+plain(v[0])+','+plain(v[1])+'},' for v in lookup);out.append('};')
assert max(len(x) for x in r['clips'])+14<=255
header='\n'.join(out)+'\n'
path=ROOT/'firmware/main/gold_fx_data.h'
coverage=json.loads((a.tracks.parent/'coverage.json').read_text())
manifest=dict(source_commit=coverage['source_commit'],rom_sha1=coverage['rom_sha1'],source_rate_hz=59.7275,display_tick_ms=45,
              cases=coverage['cases'],tiles=len(r['tiles']),frames=len(r['frames']),clips=len(r['clips']),
              tracks_sha256=hashlib.sha256(a.tracks.read_bytes()).hexdigest(),header_sha256=hashlib.sha256(header.encode()).hexdigest(),
              full_visual_equivalence=False,notes='ROM not distributed. VBlank waits/audio replaced for offline stepping; portrait mapping and compositing are adaptations. Dynamic battler body reloads use the current species.')
meta=json.dumps(manifest,indent=2)+'\n';mp=ROOT/'assets/gold_fx_sources.json'
if a.check:
 assert path.read_text()==header,'Gold track header is stale'
 assert mp.read_text()==meta,'Gold source manifest is stale'
else:
 path.write_text(header);mp.write_text(meta)
print('packed',len(r['frames']),'frames;',len(r['tiles']),'tiles;',len(flat),'timeline samples')
