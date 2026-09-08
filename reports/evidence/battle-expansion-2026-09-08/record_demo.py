"""Record native production C pages for the delivered game flows."""
from pathlib import Path
import sys
import json
from PIL import Image, ImageDraw

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'tools/pipeline'))
from verify_encounter_lifecycle_preview import Flow, build
from native import rgb888

OUT=Path(__file__).resolve().parent
exe,version=build()
checks=0
stories={}
states={}

def snap(f): return Image.frombytes('RGB',(240,320),rgb888(f.frame['pixels']))

f=Flow(exe,pet=149,wild=149,rarity=5)
try:
    f.command('names 1')
    frames=[snap(f)]
    while f.state()['presentation']['phase']!='choice':
        f.tick();frames.append(snap(f));assert len(frames)<120
    stories['feida-entry']=frames
    states['feida-ready']=f.state()
finally:checks+=f.checks;f.close()

f=Flow(exe,pet=9,level=30,wild=150,rarity=5,seed=4)
try:
    f.ready();frames=[snap(f)];f.key('C');frames.append(snap(f))
    while f.state()['presentation']['phase']!='choice':
        f.tick();frames.append(snap(f));assert len(frames)<120
    assert f.active()['attacks']==1
    stories['escape-failed']=frames
    states['choice-after-escape-failed']=f.state()
finally:checks+=f.checks;f.close()

f=Flow(exe,pet=11,level=1,wild=150,rarity=5,seed=1)
try:
    f.ready();f.key('C');frames=[snap(f)]
    while f.state()['presentation']['phase']!='result':
        f.tick();frames.append(snap(f));assert len(frames)<120
    stories['defeat-penalty']=frames
    states['defeat']=f.state()
    f.key('A');snap(f).save(OUT/'care-before.png')
    f.key('B');f.key('B');f.key('A');f.tick(1200)
    f.key('B');f.key('B');f.key('A');f.tick(1200)
    snap(f).save(OUT/'care-recovered.png');states['care-recovered']=f.state()
finally:checks+=f.checks;f.close()

sheet=Image.new('RGB',(1024,1068),'#eeede6');draw=ImageDraw.Draw(sheet)
for row,(name,frames) in enumerate(stories.items()):
    duration=[60]*len(frames);duration[-1]=1500
    frames[0].save(OUT/f'{name}.gif',save_all=True,append_images=frames[1:],duration=duration,loop=0,disposal=2)
    frames[-1].save(OUT/f'{name}-end.png')
    samples=(0,12 if len(frames)>12 else 1,len(frames)//2,len(frames)-1)
    for col,index in enumerate(samples):
        x,y=col*256+8,row*356+28
        sheet.paste(frames[index],(x,y));draw.text((x,y-19),f'{name} / frame {index}',fill='#29302b')
sheet.save(OUT/'demo-contact-sheet.png')
result={'build':version,'dirty_full_checks':checks,'frames':{name:len(fs) for name,fs in stories.items()},'states':states}
(OUT/'demo.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='states'}))
