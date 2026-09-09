#!/usr/bin/env python3
"""Inventory source scripts vs adapted firmware presentation; not an equivalence test."""
import argparse,json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('/tmp/pokewalk-gold-review'));a=p.parse_args()
source_commit=subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip()
if source_commit!='656583c939d30f920a316177311a502dd222b57c':
 raise SystemExit('Use the pinned pokegold source commit for this audit')
if subprocess.check_output(['git','-C',str(a.source),'status','--porcelain','--','data/moves/animations.asm'],text=True).strip():
 raise SystemExit('Animation source has local modifications')
s=(a.source/'data/moves/animations.asm').read_text();ptrs=re.findall(r'^\s*dw (BattleAnim_\w+)',s,re.M)[:252]
labels=list(re.finditer(r'^(BattleAnim_\w+):',s,re.M));blocks={m[1]:s[m.end():labels[i+1].start() if i+1<len(labels) else len(s)] for i,m in enumerate(labels)}
rows=json.loads((ROOT/'tools/inspector/move-catalog.json').read_text());report=[]
graphics=json.loads((ROOT/'assets/battle_fx_sources.json').read_text())
for r in rows:
 label=ptrs[r['id']];body=blocks.get(label,'');bg=re.findall(r'anim_bgeffect (\w+)',body)
 report.append(dict(id=r['id'],name=r['name'],original_script=label,original_direct_background_effects=bg,original_calls=re.findall(r'anim_call (\w+)',body),current_animation=r['animation'],alignment='source-informed-adaptation' if r['id']==57 else 'adaptation',full_script_emulation=False))
out=ROOT/'reports/evidence/animation-alignment-2026-09-09';out.mkdir(parents=True,exist_ok=True)
(out/'audit.json').write_text(json.dumps({'source_commit':'656583c939d30f920a316177311a502dd222b57c','graphics_source':graphics['repository'].rsplit('/',1)[-1]+'@'+graphics['commit'],'moves':report,'fully_verified_original_animations':0,'notes':'Direct background commands only; callees not expanded. Asset, timing, palette and layer equivalence are not implied by pixel-consistency tests.'},ensure_ascii=False,indent=2)+'\n')
print({'supported':len(rows),'scripts_with_direct_background_effects':sum(bool(r['original_direct_background_effects']) for r in report),'fully_verified_original_animations':0})
