#!/usr/bin/env python3
"""Native warehouse collision, same-species selection and save-retry UI regression."""
import json
from pathlib import Path
from verify_party_menu import Flow, build, ROOT
out=ROOT/'reports/evidence/box-exchange-2026-09-09';out.mkdir(parents=True,exist_ok=True)
exe,version=build();f=Flow(exe,page=12,team=0)
try:
    for sid in (1,4,7,10,13):f.cmd(f'party_add {sid} 20 40 100 0')
    f.cmd('party_add 25 40 85 500 1')
    f.cmd('party_add 133 30 50 200 0')
    assert f.state()['party_count']==6 and f.state()['box_count']==2
    f.key('A',True);f.key('B');f.shot(out,'before-exchange')
    before=f.state()['party'];f.cmd('save_fail 1');f.key('A')
    assert f.state()['party']==before and f.state()['box_count']==2
    assert '保存失败' in f.state()['party_view']['feedback'];f.shot(out,'save-failure')
    f.key('A');assert f.state()['pet']==133 and f.state()['box_count']==2
    assert f.state()['party_count']==6;f.shot(out,'exchanged')
    # There are now two distinct Pikachu in the warehouse; select the shiny one.
    f.key('A',True);f.shot(out,'duplicate-individuals');f.key('A')
    assert f.state()['pet']==25 and f.state()['level']==40 and f.state()['party'][0]['flags']==1
    assert f.state()['box_count']==2;f.shot(out,'shiny-exchanged')
    result={'status':'PASS','renderer':version,'checks':f.checks,'collision_swap':True,'save_retry':True,'distinct_shiny_selection':True}
    (out/'ui.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:f.close()
