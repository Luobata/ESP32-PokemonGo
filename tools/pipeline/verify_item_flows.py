#!/usr/bin/env python3
"""Actual C P3/P4: inventory consumption, special balls and award/save retries."""
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer, build, png
from verify_capture_flow import Flow

OUT=ROOT/'reports/evidence/items-2026-09-08'

class Capture:
    def __init__(self,exe,ball,wild=143):
        self.r=Renderer(exe);self.checks=0
        self.command(f'boot 4 25 12 {wild} 5 7 0')
        for i in range(8):self.command(f'inventory {i} {int(i==ball)}')
        self.command('page 4')
    def command(self,c):
        self.frame=self.r.command(c)
        assert self.r.command('check')['mismatch']==0,c
        self.checks+=1;return self.frame
    def state(self):return self.r.inspect()
    def close(self):self.r.close()
    def image(self,name): (OUT/name).write_bytes(png(self.frame['pixels']))

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    exe,version=build();results=[];checks=0
    for ball in range(8):
        f=Capture(exe,ball)
        try:
            # Master succeeds even at the edge; all others at the bar center.
            if ball!=3:f.command('tick 300')
            f.command('key 0 1')
            s=f.state()
            assert s['inventory'][ball]==0 and s['party_count']==2 and s['active'] is None
            caught=next(m for m in s['party'] if m['species']==143)
            assert caught['intimacy']==(40 if ball==7 else 0)
            assert caught['level']==45 and caught['exp']==5*45**3//2, 'capture lost the EXP floor of its wild level'
            for _ in range(3): f.command('key 0 1')
            f.command('tick 40')
            assert f.state()['inventory'][ball]==0 and f.state()['party_count']==2
            results.append(f'ball {ball}: one spent, one catch, intimacy correct')
        finally:checks+=f.checks;f.close()

    f=Capture(exe,3)
    try:
        before=f.state();f.command('save_fail 1');f.command('key 0 1')
        assert f.state()==before,'first write failure published inventory/session changes'
        f.image('ball-first-save-failed.png')
        f.command('key 0 1');assert f.state()['party_count']==2 and f.state()['inventory'][3]==0
        results.append('first throw save failure spends nothing; A retry succeeds')
    finally:checks+=f.checks;f.close()

    f=Capture(exe,3)
    try:
        f.command('save_fail_after 1');f.command('key 0 1');pending=f.state()
        assert pending['inventory'][3]==0 and pending['party_count']==1 and pending['active']
        assert pending['page']==4 and not pending['can_leave']
        f.image('caught-result-save-failed.png')
        for c in ['key 1 1','key 2 1','tick 2400']:
            f.command(c);assert f.state()==pending,'pending successful catch became a miss or escaped'
        f.command('key 0 1');s=f.state()
        assert s['inventory'][3]==0 and s['party_count']==2 and s['active'] is None
        f.image('caught-result-save-retried.png')
        results.append('second catch write failure keeps hit; retry adds mon without another ball')
    finally:checks+=f.checks;f.close()

    # Real battles obtain awards from the real learning table and move resolver.
    awards=[]
    for rarity,wild,item,quantity in [(1,5,0,2),(2,5,1,1),(3,1,2,1),(4,1,5,1),(5,1,4,1)]:
        f=Flow(exe,pet=149,level=100,wild=wild,rarity=rarity,seed=7)
        try:
            before=f.state()['inventory'];f.victory();s=f.state();b=f.encounter()
            assert b['loot_checked']
            assert (b['loot_item'],b['loot_qty'])==(item,quantity)
            (OUT/f'victory-loot-{rarity}.png').write_bytes(png(f.command('check')['pixels']))
            delta=[y-x for x,y in zip(before,s['inventory'])]
            assert sum(v>0 for v in delta)<=1 and sum(delta)==b['loot_qty']
            assert b['loot_item']!=3 or rarity==5
            after=s['inventory'];f.key('A');f.key('C');f.command('page 3')
            assert f.encounter()['loot_checked'] and f.state()['inventory']==after
            awards.append({'rarity':rarity,'item':b['loot_item'],'quantity':b['loot_qty']})
            results.append(f'rarity {rarity}: actual victory settles drop exactly once')
        finally:checks+=f.checks;f.close()

    f=Flow(exe,pet=149,level=100,wild=1,rarity=5,seed=7)
    try:
        before=f.state()['inventory'];f.key('B');f.command('save_fail 1')
        f.until(lambda:f.phase()=='result','loot retry result')
        pending=f.state();assert not f.encounter()['loot_checked'] and not pending['can_leave']
        for key in 'BCBC':f.key(key);assert f.state()==pending
        f.key('A');assert f.encounter()['loot_checked'] and f.state()['can_leave']
        after=f.state()['inventory'];assert sum(after)-sum(before)==f.encounter()['loot_qty']
        f.key('A');f.key('C');assert f.state()['inventory']==after
        results.append('loot write failure locks result; A retry awards once')
    finally:checks+=f.checks;f.close()

    for full in (False,True):
        f=Flow(exe,pet=149,level=100,wild=1 if full else 19,rarity=5,seed=7)
        try:
            if full:f.command('inventory 4 20')
            before=f.state()['inventory'];f.victory();b=f.encounter()
            assert f.state()['inventory']==before and b['loot_checked'] and b['loot_qty']==0
            assert b['loot_full']==full and b['loot_item']==(4 if full else 255)
            results.append('full stock consumes roll without overflow' if full else 'victory may give no drop')
        finally:checks+=f.checks;f.close()

    f=Flow(exe,pet=11,level=1,wild=150,rarity=5,seed=1)
    try:
        before=f.state()['inventory'];f.key('B')
        f.until(lambda:f.phase()=='result','loss')
        assert not f.encounter()['won'] and not f.encounter()['loot_checked']
        assert f.state()['inventory']==before
        results.append('defeat gives no item award')
    finally:checks+=f.checks;f.close()

    f=Flow(exe,pet=149,level=100,wild=1,rarity=5,seed=7)
    try:
        f.victory()
        for i in range(8):f.command(f'inventory {i} {int(i==3)}')
        f.key('A');f.command('save_fail_after 1');f.key('A');pending=f.state()
        assert pending['page']==4 and not pending['can_leave']
        assert f.encounter()['capture_used'] and pending['inventory'][3]==0
        for key in 'BCBC':f.key(key);assert f.state()==pending
        f.tick(2400);assert f.state()==pending,'final successful throw became an escape while awaiting save'
        f.key('A');assert f.state()['party_count']==2 and f.state()['inventory'][3]==0
        results.append('victory final capture save retry keeps hit and locks menu exit')
    finally:checks+=f.checks;f.close()
    result={'status':'PASS','build':version,'cases':results,'awards':awards,'dirty_full_checks':checks,
            'scope':'actual C pages/rules/assets; host world/NVS fixture, storage verified separately'}
    (OUT/'capture-loot-flows.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
