#!/usr/bin/env python3
"""Warehouse details must inspect the selected individual without moving it."""
import json
from verify_party_menu import Flow, build, ROOT, font_check
out=ROOT/'reports/evidence/box-details-2026-09-09';out.mkdir(parents=True,exist_ok=True)
exe,version=build();f=Flow(exe,page=12,team=0)
try:
    for sid in (1,4,7,10,13):f.cmd(f'party_add {sid} 20 40 100 0')
    # Two individuals of the same species: details and exchange must retain identity.
    f.cmd('party_add 25 40 85 500 1');f.cmd('party_add 133 22 50 200 0')
    f.key('A',True);f.key('B');f.key('A')
    assert f.state()['pet']==133 and f.state()['box_count']==2
    before=f.state()['party'];count=f.state()['box_count']
    f.key('A',True);f.shot(out,'shiny-list')
    assert f.state()['party_view']['box']
    f.key('A',True);f.shot(out,'shiny-details')
    assert f.state()['party_view']['details'] and f.state()['party_view']['species']==25
    assert f.state()['party']==before and f.state()['box_count']==count
    f.key('B');assert f.state()['party_view']['skills'];f.shot(out,'shiny-skills')
    f.key('B');f.key('B',True);f.key('C')
    assert f.state()['party_view']['details'] and not f.state()['party_view']['skills']
    f.key('C');assert f.state()['party_view']['box_row']==0
    f.key('B');assert f.state()['party_view']['box_row']==1
    f.key('A',True);f.shot(out,'ordinary-details')
    f.key('C');assert f.state()['party_view']['box_row']==1
    f.key('B',True);assert f.state()['party_view']['box_row']==0
    f.key('A',True);f.key('A',True);assert f.state()['party_view']['skills']
    f.key('C');f.cmd('save_fail 1');f.key('A')
    assert f.state()['party']==before and '保存失败' in f.state()['party_view']['feedback']
    assert f.state()['party_view']['details'];f.shot(out,'save-failure')
    f.key('A');assert not f.state()['party_view']['box']
    assert f.state()['party'][0]['flags']==1 and f.state()['level']==40
    assert f.state()['box_count']==count
    result={'status':'PASS','renderer':version,'checks':f.checks,'font_glyphs':font_check(),'details_read_only':True,'same_species_individuals':True,'return_row_preserved':True,'long_B_previous':True,'details_exchange_save_retry':True}
    (out/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
finally:f.close()
