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
 r['animation_note']='参照金银脚本：浪面上升、停留、回落（时序适配）' if r['id']==57 else '项目适配动作，尚未逐帧对齐原版' if r['animation']!='属性/状态共用动画' else '属性/状态通用演出，未还原该招原版脚本'
assert len(rows)==191
(ROOT/'tools/inspector/move-catalog.json').write_text(json.dumps(sorted(rows,key=lambda m:m['id']),ensure_ascii=False,indent=2)+'\n')
