#!/usr/bin/env python3
"""Exercise native combat, persisted continuation, route choices and one-shot rewards."""
import copy
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'inspector'))
import dungeon

def simulate(seed):
 with patch.object(dungeon.secrets,'randbelow',return_value=seed):
  data=dungeon.request({'action':'new','selected':[6,9,143]})
 r=dungeon.RUNS[data['id']]
 r.frame=r.r.command('tick 5000');r.capture();r.save()
 before=copy.deepcopy(r.d);r.close();r.start()
 assert r.d['blob']==before['blob'] and r.d['party']==before['party']
 try:r.act({'action':'tick','revision':-1});raise AssertionError('stale input accepted')
 except ValueError:pass
 visited=set()
 for _ in range(1200):
  d=r.d;visited.add(d['phase'])
  if d['phase']=='battle':
   r.frame=r.r.command('tick 1500');r.capture()
   if d['mode']==4:
    r.r.command('key 1 1');r.frame=r.r.command('key 2 1');r.capture()
  elif d['phase']=='reward':
   cards=list(d['choices']);old=len(d['cards']);rev=d['revision']
   r.act({'action':'choose','choice':cards[0],'revision':rev})
   assert len(d['cards'])==old+1
   try:r.act({'action':'choose','choice':cards[0],'revision':rev});raise AssertionError('duplicate reward')
   except ValueError:pass
  elif d['phase']=='fork':r.act({'action':'choose','choice':1,'revision':d['revision']})
  elif d['phase']=='camp':r.act({'action':'choose','choice':0,'revision':d['revision']})
  else:break
 assert d['phase'] in ('won','lost'),d
 result={'seed':seed,'result':d['phase'],'node':d['node']+1,'wins':d['wins'],'phases':sorted(visited)}
 r.close();return result

with tempfile.TemporaryDirectory() as temp:
 dungeon.ROOT=Path(temp)
 results=[simulate(i) for i in (1,2,3)]
 assert any(r['result']=='won' for r in results),results
 assert all(p in set().union(*(set(r['phases']) for r in results)) for p in ('fork','camp','reward','battle'))
 print(results)
 print('PASS: native runs, snapshot resume, stale revision, duplicate reward protection')
