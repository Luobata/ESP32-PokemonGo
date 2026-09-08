#!/usr/bin/env python3
"""Audit original Gold/Silver learnability for National Dex 1..151 (not just moves 1..165)."""
import argparse,re,json,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def parse(root):
 constants=re.findall(r'^\s*const ([A-Z0-9_]+)',(root/'constants/move_constants.asm').read_text(),re.M)[:252];moves={n:i for i,n in enumerate(constants)}
 mons=['NONE']+re.findall(r'^\s*const ([A-Z0-9_]+)',(root/'constants/pokemon_constants.asm').read_text(),re.M)[:251];species={n:i for i,n in enumerate(mons)}
 ptrs=re.findall(r'^\s*dw (\w+)',(root/'data/pokemon/evos_attacks_pointers.asm').read_text(),re.M)
 text=(root/'data/pokemon/evos_attacks.asm').read_text();blocks={m.group(1):m.group(2) for m in re.finditer(r'^(\w+):\s*\n(.*?)(?=^\w+:|\Z)',text,re.M|re.S)}
 levels={};parents={}
 for sid,ptr in enumerate(ptrs,1):
  block=blocks[ptr];levels[sid]=[(int(l),moves[m]) for l,m in re.findall(r'\bdb (\d+), ([A-Z0-9_]+)',block) if m in moves]
  for target in re.findall(r'^\s*db EVOLVE_[^\n]*, ([A-Z0-9_]+)',block,re.M):parents[species[target]]=sid
 eptrs=re.findall(r'^\s*dw (\w+)',(root/'data/pokemon/egg_move_pointers.asm').read_text(),re.M)
 eggtext=(root/'data/pokemon/egg_moves.asm').read_text();eblocks={m.group(1):m.group(2) for m in re.finditer(r'^(\w+):\s*\n(.*?)(?=^\w+:|\Z)',eggtext,re.M|re.S)}
 eggs={sid:[moves[m] for m in re.findall(r'^\s*db ([A-Z0-9_]+)',eblocks.get(ptr,''),re.M) if m in moves] for sid,ptr in enumerate(eptrs,1)}
 tm={};paths=re.findall(r'INCLUDE "([^"]+)"',(root/'data/pokemon/base_stats.asm').read_text())
 for sid,path in enumerate(paths,1):
  t=(root/path).read_text();match=re.search(r'^\s*tmhm\s+([^;\n]+)',t,re.M);tm[sid]=[moves[m.strip()] for m in match[1].split(',') if m.strip()] if match else []
 entries=[]
 for sid in range(1,152):
  line=[];at=sid
  while at and at not in line:line.append(at);at=parents.get(at)
  l={};e=set();t=set()
  for ancestor in line:
   for lv,mid in levels[ancestor]:l[mid]=min(l.get(mid,255),lv)
   e.update(eggs.get(ancestor,[]));t.update(tm.get(ancestor,[]))
  entries.append({'id':sid,'name':mons[sid],'lineage':line,'level_up':sorted([[lv,mid] for mid,lv in l.items()]),'tm_hm':sorted(t),'egg':sorted(e)})
 meta=[]
 for i,line in enumerate(re.findall(r'^\s*move\s+([^\n]+)',(root/'data/moves/moves.asm').read_text(),re.M),1):
  r=[x.strip() for x in line.split(';')[0].split(',')];meta.append({'id':i,'name':constants[i],'effect':r[1],'power':int(r[2]),'type':r[3],'accuracy':int(r[4])})
 return entries,meta

def main():
 p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('/tmp/pokewalk-gold-review'));a=p.parse_args();entries,meta=parse(a.source)
 commit=subprocess.check_output(['git','-C',str(a.source),'rev-parse','HEAD'],text=True).strip()
 data={'source':'https://github.com/pret/pokegold','commit':commit,'scope':'Gold/Silver level-up, TM/HM and egg moves, including ancestors outside Dex 1..151. Excludes tradeback/event-only moves and Crystal tutors.','pokemon':entries,'moves':meta}
 path=ROOT/'data/pokemon_moves/gold_silver.json';path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
 learned=set();by_method={k:set() for k in ('level_up','tm_hm','egg')}
 for m in entries:
  by_method['level_up'].update(x[1] for x in m['level_up']);by_method['tm_hm'].update(m['tm_hm']);by_method['egg'].update(m['egg'])
 for s in by_method.values():learned.update(s)
 missing=sorted(learned-set(range(1,166)))
 report={'species':151,'original_moves':len(meta),'learnable_unique':len(learned),'unique_by_method':{k:len(v) for k,v in by_method.items()},'missing_engine_moves':len(missing),'missing':[{**meta[i-1]} for i in missing],'source_commit':commit}
 out=ROOT/'reports/evidence/gold-silver-2026-09-09';out.mkdir(parents=True,exist_ok=True);(out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps({k:v for k,v in report.items() if k!='missing'}));print('missing effects',sorted({meta[i-1]['effect'] for i in missing}))
if __name__=='__main__':main()
