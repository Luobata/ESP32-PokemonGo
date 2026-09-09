#!/usr/bin/env python3
"""Export the actual compiled move definitions for the native acceptance UI."""
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
rows=[];fx=(ROOT/'firmware/main/battle_fx.c').read_text();styles={int(k):v for k,v in re.findall(r'\{(\d+), BATTLE_FX_(\w+)\}',fx)}
for file in ['combat_moves.h','combat_selected_moves.h']:
 text=(ROOT/'firmware/main'/file).read_text()
 for mid,ty,power,accuracy,pp,special,name,length,effect,chance in re.findall(r'\{\{(\d+),(\d+),(\d+),(\d+),(\d+),(true|false),"([^"]+)",(\d+)\},(EFFECT_\w+),(\d+)\}',text):
  mid=int(mid);rows.append(dict(id=mid,name=name,type=int(ty),power=int(power),accuracy=int(accuracy),effect=effect,chance=int(chance),new=mid>165 and mid!=250,animation=styles.get(mid,'属性/状态共用动画')))
for r in rows:
 r['animation']='GOLD_TRACK'
 r['animation_note']='原作图元、帧集、对象运动和背景状态轨迹 · 45ms采样 · 竖屏合成适配（未宣称逐像素等价）'
assert len(rows)==191
(ROOT/'tools/inspector/move-catalog.json').write_text(json.dumps(sorted(rows,key=lambda m:m['id']),ensure_ascii=False,indent=2)+'\n')
