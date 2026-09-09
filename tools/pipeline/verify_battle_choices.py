#!/usr/bin/env python3
"""Real C page flows for escape, defeat/care and species entrance motion."""
import json
from pathlib import Path
from verify_encounter_lifecycle_preview import Flow, build, png

OUT=Path(__file__).resolve().parents[2]/'reports/evidence/battle-expansion-2026-09-08'

def safe_escape(f):
    f.ready(); before=f.state()
    assert not before['can_leave']
    f.key('C'); assert f.state()['presentation']['phase']=='escaped'
    assert f.active()['escape_attempts']==1 and f.active()['attacks']==0
    for key in 'ABCABC': f.key(key)
    f.until(lambda:f.state()['page']==2,'escape exit')
    assert f.active() is None and f.queued() is None
    assert f.state()['exp']==before['exp'] and f.state()['nurture']==before['nurture']

def failed_escape(f):
    f.ready(); before=f.encounter(); f.key('C')
    assert f.state()['presentation']['phase']=='escape-failed'
    assert f.active()['escape_attempts']==1 and f.active()['retaliation']
    for key in 'ABCABC':
        f.key(key);assert f.active()['attacks']==0 and not f.state()['can_leave']
    f.until(lambda:f.state()['presentation']['phase']=='choice','one retaliation then choice')
    after=f.active()
    assert after['attacks']==1 and after['wild_hp']==before['wild_hp'] and not after['auto_battle']
    f.tick(6000);assert f.active()==after
    f.key('A');assert f.state()['page']==4 and not f.state()['can_leave']
    f.key('C');assert f.state()['page']==3
    f.key('C');assert f.active()['escape_attempts']==2
    assert f.state()['presentation']['phase'] in ('escaped','escape-failed')

def escape_after_move(f):
    f.ready();f.key('B');f.tick();first=f.active()
    assert first['attacks']==1 and not first['finished']
    f.key('C');f.key('C');f.key('C')
    assert f.active()==first and not f.state()['can_leave']
    f.until(lambda:f.active()['escape_attempts']==1,'escape after current move')
    assert f.active()['attacks']==1
    phase=f.state()['presentation']['phase']
    assert phase in ('escaped','escape-failed')
    if phase=='escaped':
        f.until(lambda:f.state()['page']==2,'auto escape success')
        assert f.active() is None
    else:
        f.until(lambda:f.active()['attacks']==2,'failed escape single enemy move')
        assert f.active()['auto_battle'] and not f.active()['retaliation']
        f.until(lambda:f.active()['attacks']==3,'resume chosen auto battle')
        assert f.active()['escape_attempts']==1

def penalty_and_care(f):
    f.ready();before=f.state();f.key('C')
    assert f.state()['presentation']['phase']=='escape-failed'
    f.until(lambda:f.state()['presentation']['phase']=='result','lethal retaliation settlement')
    s=f.state();assert not s['active']['won'] and s['active']['defeat_applied']
    assert s['active']['attacks']==1 and s['exp']>=before['exp']
    expected=dict(before['nurture'],stamina=70,mood=55)
    assert s['nurture']==expected and s['can_leave']
    f.tick(6000);assert f.state()['nurture']==expected and f.state()['exp']==s['exp']
    f.key('A');assert f.state()['page']==5 and f.active() is None
    assert f.state()['nurture']==expected
    f.key('B');f.key('B');f.key('A');f.tick(1200)
    assert f.state()['nurture']['stamina']==70  # Rest is time-only, not an instant refill.
    f.key('B');f.key('B');f.key('B');f.key('A');f.tick(1200)
    assert f.state()['nurture']['mood']==70 and f.state()['nurture']['stamina']==65
    assert f.state()['exp']==s['exp']

def save_failure(f):
    f.ready();before=f.state();f.command('save_fail 1');f.key('C')
    assert f.state()['active'] is None and f.state()['queue']==before['queue']
    assert f.state()['presentation']['phase']=='choice'
    f.tick(6000);assert f.active() is None
    f.key('C');assert f.active()['escape_attempts']==1

def low_condition(f):
    f.command('page 3');f.ready()
    assert f.encounter()['ability_factor']==1024
    f.command('nurture 80 24 24')
    f.key('A');assert f.state()['page']==4 and not f.state()['can_leave']
    f.key('A');assert f.active()['ability_factor']==614

def delayed_battle_condition(f):
    f.ready();assert f.encounter()['ability_factor']==1024
    f.command('nurture 80 24 24');f.key('B')
    assert f.active()['ability_factor']==614

def species_motion(f):
    sampled=[]; hashes=set()
    while f.state()['presentation']['phase']!='choice':
        s=f.state()['presentation']
        if s['phase']=='entrance-motion':
            sampled.append(s['wild_frame']);hashes.add(f.frame['pixels'])
            for key in 'ABC':f.key(key)
            assert f.active() is None and f.queued()['attacks']==0
        f.tick()
        assert f.checks<600
    assert any(sampled) and len(hashes)>1 and f.state()['presentation']['wild_frame']==0
    f.key('A');f.key('C');assert f.state()['presentation']['phase']=='choice'

def main():
    exe,version=build();checks=0;passed=[]
    cases=[('safe escape has no reward or penalty',safe_escape,{}),
           ('failed escape costs exactly one reply then capture remains available',failed_escape,dict(pet=9,level=50,wild=150,rarity=5,seed=4)),
           ('auto escape is processed after current move once',escape_after_move,dict(pet=9,level=100,wild=150,rarity=5,seed=4)),
           ('lethal reply applies one penalty then care restores it',penalty_and_care,dict(pet=11,level=1,wild=150,rarity=5,seed=1)),
           ('escape save failure leaves attempt and encounter intact',save_failure,{}),
           ('low nurture condition affects newly entered battle',low_condition,dict(page=2)),
           ('begin battle refreshes a condition changed while waiting',delayed_battle_condition,{}),
           ('original species frames play once and finish in resting pose',species_motion,dict(wild=149,rarity=5))]
    OUT.mkdir(parents=True,exist_ok=True)
    for label,fn,options in cases:
        f=Flow(exe,**options)
        try:fn(f);passed.append(label)
        except Exception:
            (OUT/'failure.png').write_bytes(png(f.frame['pixels']))
            (OUT/'failure.json').write_text(json.dumps(f.state(),indent=2));raise
        finally:checks+=f.checks;f.close()
    result={'build':version,'status':'PASS','cases':passed,'dirty_full_checks':checks}
    (OUT/'choices.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
