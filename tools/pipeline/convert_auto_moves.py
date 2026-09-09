#!/usr/bin/env python3
"""Compile supported Gold/Silver learning routes into automatic growth milestones."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
data=json.loads((ROOT/'data/pokemon_moves/gold_silver.json').read_text());metadata={m['id']:m for m in data['moves']}
SUPPORTED=set(range(1,166))|{m['id'] for m in json.loads((ROOT/'data/pokemon_moves/selected_gen2.json').read_text())}
HM={15:15,19:25,57:25,70:20,148:10,250:20,127:35}
learn=[];ranges=[];report=[]
for p in data['pokemon']:
 records={mid:lv for lv,mid in p['level_up'] if mid in SUPPORTED}
 for mid in p['tm_hm']:
  if mid not in SUPPORTED:continue
  power=metadata[mid]['power'];lv=HM.get(mid,20 if not power else 15 if power<=60 else 25 if power<=90 else 40)
  records[mid]=min(records.get(mid,255),lv)
 for mid in p['egg']:
  if mid in SUPPORTED:records[mid]=min(records.get(mid,255),30)
 rows=sorted((lv,mid) for mid,lv in records.items());ranges.append((len(learn),len(rows)));learn+=rows
 report.append({'species':p['id'],'auto_moves':len(rows),'machine_moves':len(set(p['tm_hm'])&SUPPORTED),'not_implemented':sorted((set(p['tm_hm'])|set(p['egg'])|{m for _,m in p['level_up']})-SUPPORTED)})
text=['// Generated from pinned Gold/Silver factual data by convert_auto_moves.py.','#pragma once','static const uint16_t COMBAT_AUTO_RANGES[151][2] = {'+','.join('{%d,%d}'%r for r in ranges)+'};','static const uint8_t COMBAT_AUTO_LEARN[][2] = {'+','.join('{%d,%d}'%r for r in learn)+'};']
(ROOT/'firmware/main/combat_auto_moves.h').write_text('\n'.join(text)+'\n')
(ROOT/'reports/evidence/gold-silver-2026-09-09/auto-learning.json').write_text(json.dumps({'supported_move_ids':sorted(SUPPORTED),'records':len(learn),'hm_levels':HM,'pokemon':report},indent=2)+'\n')
print('automatic records',len(learn),'supported engine moves',len(SUPPORTED))
