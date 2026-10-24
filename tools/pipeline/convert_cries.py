#!/usr/bin/env python3
"""Compile Gold's 38 shared cry programs and all 251 species parameters."""
import argparse,re,subprocess,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=Path('/tmp/pokewalk-gold-review'));p.add_argument('--check',action='store_true');a=p.parse_args()
commit='656583c939d30f920a316177311a502dd222b57c'
manifest=json.loads((ROOT/'assets/cry_sources.json').read_text());assert manifest['commit']==commit
for name,digest in manifest['sha256'].items():assert hashlib.sha256((a.source/name).read_bytes()).hexdigest()==digest
labels={};program=[];scope=''
for raw in (a.source/'audio/cries.asm').read_text().splitlines():
 line=raw.split(';')[0].strip()
 if not line:continue
 if line.endswith(':'):
  name=line[:-1]
  if name.startswith('.'):name=scope+name
  else:scope=name
  labels[name]=len(program)
 else:program.append((scope,line))
rows=re.findall(r'mon_cry\s+CRY_(\w+),\s*(-?\d+),\s*(-?\d+)',(a.source/'data/pokemon/cries.asm').read_text())[:251]
normalize=lambda s:s.replace('_','').lower()
bases=list(dict.fromkeys(normalize(r[0]) for r in rows));assert len(rows)==251
out=[f'// Generated from pret/pokegold@{commit} audio/cries.asm and data/pokemon/cries.asm.']
for i,base in enumerate(bases):
 for ch in (5,6,8):
  matches=[n for n in labels if n.endswith(f'_Ch{ch}') and normalize(n[4:].split('_Ch')[0])==base]
  notes=[];pattern=0;pattern_frame=0;total=0;offset=0
  if matches:
   name=matches[0];pc=labels[name];loops={};stack=[]
   for guard in range(4000):
    scope,line=program[pc];op,*args=line.replace(',',' ').split();current=pc;pc+=1
    def target(label):return labels[scope+label if label.startswith('.') else label]
    if op=='duty_cycle_pattern':
     pattern=sum(int(x)<<(6-2*k) for k,x in enumerate(args));pattern_frame=total
    elif op=='duty_cycle':pattern=int(args[0])*85;pattern_frame=total
    elif op=='pitch_offset':offset=int(args[0])
    elif op=='pitch_sweep':pass # Mono synthesizer keeps the note's initial pitch; documented approximation.
    elif op in ('square_note','noise_note'):
     duration,vol,env,freq=map(int,args);envelope=(vol<<4)|(8-env if env<0 else env)
     notes.append((duration+1,envelope,(freq+offset)&65535,pattern,int(total==pattern_frame)));total+=duration+1
    elif op=='sound_loop':
     assert int(args[0])>0
     loops[current]=loops.get(current,0)+1
     if loops[current]<int(args[0]):pc=target(args[1])
     else:loops.pop(current,None)
    elif op=='sound_call':stack.append(pc);pc=target(args[0])
    elif op=='sound_jump':pc=target(args[0])
    elif op=='sound_ret':
     if stack:pc=stack.pop()
     else:break
    else:raise ValueError((name,op,args))
   else:raise ValueError('unbounded cry')
  out.append(f'static const cry_note_t cry_{i}_{ch}[] = {{'+','.join('{%d,%d,%d,%d,%d}'%n for n in notes)+'};')
out.append('static const cry_score_t cry_scores[] = {')
for i in range(len(bases)):
 out.append('{'+','.join('{cry_%d_%d,sizeof(cry_%d_%d)/sizeof(cry_note_t)}'%(i,ch,i,ch) for ch in (5,6,8))+'},')
out.append('};\nstatic const cry_species_t cry_species[252] = {{0},')
for name,pitch,length in rows:out.append('{%d,%s,%s},'%(bases.index(normalize(name)),pitch,length))
out.append('};')
target=ROOT/'firmware/main/cry_data.h';text='\n'.join(out)+'\n'
if a.check:assert target.read_text()==text
else:target.write_text(text)
print(json.dumps(dict(species=251,bases=len(bases),source=commit,bytes=len(text),verified=True)))
