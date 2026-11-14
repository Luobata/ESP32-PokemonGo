#!/usr/bin/env python3
"""Actual production drawing/input: languages, shiny rows and network feedback."""
import json, sys, os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer, build, png
OUT=Path(os.environ.get('POKEWALK_EVIDENCE_DIR',ROOT/'.build/community-feedback-2026-11-14/ui'))
OUT.mkdir(parents=True,exist_ok=True)
exe,version=build();checks=0
def cmd(r,line):
    global checks
    frame=r.command(line)
    assert r.command('check')['mismatch']==0,line
    checks+=1;return frame
def key(r,k,hold=False):return cmd(r,f'key {"ABC".index(k)} {3 if hold else 1}')
def shot(r,name):(OUT/(name+'.png')).write_bytes(png(cmd(r,'check')['pixels']))
def box(frame,x,y,w,h):
    return b''.join(frame['pixels'][((y+row)*240+x)*2:((y+row)*240+x+w)*2] for row in range(h))

r=Renderer(exe)
try:
    cmd(r,'boot 11 130 100 193 4 42 0 0 1 1')
    for _ in range(5):key(r,'B')
    key(r,'C')
    for _ in range(9):key(r,'B')
    assert r.inspect()['menu_view']['option_selected']==9
    before=cmd(r,'check');shot(r,'settings-simplified')
    cmd(r,'save_fail 1');key(r,'C');assert r.inspect()['language']==0;shot(r,'language-save-error')
    key(r,'C');assert r.inspect()['language']==1;assert cmd(r,'check')['pixels']!=before['pixels'];shot(r,'settings-traditional')
    key(r,'B',True);assert not r.inspect()['menu_view']['options']
    key(r,'C');assert r.inspect()['menu_view']['options']
    for _ in range(9):key(r,'B')
    assert r.inspect()['language']==1;key(r,'C');assert r.inspect()['language']==2;shot(r,'settings-english');key(r,'C');assert r.inspect()['language']==3;shot(r,'settings-japanese');key(r,'C');assert r.inspect()['language']==0
    # Wi-Fi association status and all diagnostic labels in both languages.
    for _ in range(3):key(r,'A')
    key(r,'C');key(r,'C')
    for lang in (0,1,2,3):
        cmd(r,f'language {lang}')
        for clients in (0,1,2):cmd(r,f'wifi_status {clients} 0');shot(r,f'wifi-{lang}-{clients}-clients')
    key(r,'C')
    errors=[]
    for reason in (1,2,3):errors.append(cmd(r,f'wifi_status 0 {reason}')['pixels']);shot(r,f'wifi-reason-{reason}')
    assert len(set(errors))==3
finally:r.close()

# Compare ordinary/shiny versions of the same six physical party individuals.
# Badge area remains independent of animated thumbnails and selected-row dirties.
normal=Renderer(exe);shiny=Renderer(exe)
try:
    for r,flag in ((normal,0),(shiny,1)):
        cmd(r,f'boot 12 29 100 193 4 42 0 0 0 {flag}')
        for species in (31,122,149,201,251):cmd(r,f'party_add {species} 100 100 65535 {flag}')
        cmd(r,'page 1');cmd(r,'page 12')  # Refresh the production party snapshot.
        cmd(r,'language 1')
    for row in range(6):
        n=cmd(normal,'check');s=cmd(shiny,'check')
        for i in range(6):assert box(n,168,36+i*36+20,16,16)!=box(s,168,36+i*36+20,16,16),i
        for tick in (80,80,80,80,160,320):
            ns=cmd(normal,f'tick {tick}');ss=cmd(shiny,f'tick {tick}')
            assert box(n,168,36+row*36+20,16,16)==box(ns,168,36+row*36+20,16,16)
            assert box(s,168,36+row*36+20,16,16)==box(ss,168,36+row*36+20,16,16)
        key(normal,'B');key(shiny,'B')
    shot(shiny,'party-shiny-traditional');shot(normal,'party-ordinary-traditional')
    cmd(shiny,'names 1');shot(shiny,'party-shiny-nostalgic-traditional')
finally:normal.close();shiny.close()

pages=[0,1,2,3,4,5,6,9,10,11,12,13,14,15,16,17,18,19,20,21,22]
for lang,page in ((lang,page) for lang in (1,2,3) for page in pages):
    r=Renderer(exe)
    try:
        cmd(r,f'boot {page} 149 60 193 4 42 0 0 1 1')
        cmd(r,f'language {lang}')
        for tick in (16,80,250,500,1000):cmd(r,f'tick {tick}')
        shot(r,f'language-{lang}-P{page}')
    finally:r.close()
# Dynamic battle prompts and the whole capture motion also use translated ink
# bounds; inspect every frame, not only static landing pages.
for lang,page in ((lang,page) for lang in (1,2,3) for page in (3,4)):
    r=Renderer(exe)
    try:
        cmd(r,f'boot {page} 149 60 193 4 42 0 0 1 1');cmd(r,f'language {lang}')
        if page==3:cmd(r,'move_preview 57 0 0 0')
        else:key(r,'C')
        for _ in range(170):cmd(r,'tick 60')
        shot(r,f'language-{lang}-motion-P{page}')
    finally:r.close()
result={'passed':True,'native_build':version,'render_band_checks':checks,'pages':pages,'shiny_party_slots':6,'language_save_failure':True,'network_boundary':'simulated','hardware_tested':False}
(OUT/'checks.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
