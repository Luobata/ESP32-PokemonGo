#!/usr/bin/env python3
"""Complete story cut, with the full opening handoff and uninterrupted battles."""
from pathlib import Path
from collections import deque
import sys,json,subprocess,argparse,wave,array,math,hashlib
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import Renderer,build,rgb888
ap=argparse.ArgumentParser();ap.add_argument('--check-only',action='store_true');ap.add_argument('--out',type=Path,default=ROOT/'reports/video/pokewalk-story-complete-2026-09-09');args=ap.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
FPS=30
scenes=[
 dict(name='opening',act=1,title='故事，从一个邀请开始。',sub='大木博士正在等你。',duration=60,boot='0 25 12 74 3 123 0 0 0',opening=True),
 dict(name='starter',act=1,title='皮卡丘，就决定是你了。',sub='选好第一位伙伴，我们出发。',duration=10,events={90:['key 1 1'],150:['key 1 1'],210:['key 1 1'],270:['key 0 1']}),
 dict(name='depart',act=2,title='森林里，会遇见谁？',sub='带上精灵球，去附近探索。',duration=3,events={45:['page 15']}),
 dict(name='explore',act=2,title='草丛里，传来了动静。',sub='第一次探索，发现了新的伙伴。',duration=4,setup=['exploration_fixture 0 3 0 0'],events={30:['key 0 1']}),
 dict(name='meet',act=2,title='原来是尼多娜。',sub='试着邀请它，加入我们的冒险。',duration=30,until_choice=True,events={0:['key 0 1']}),
 dict(name='capture',act=2,title='看准时机，投出精灵球。',sub='等它安静下来……我们成功了！',duration=8,setup=['key 0 1'],events={45:['key 0 1']}),
 dict(name='party',act=3,title='从今天起，我们一起走。',sub='刚刚捕获的尼多娜，已经加入队伍。',duration=4,setup=['key 0 1','tick 100','page 1','page 12'],events={30:['key 1 1']}),
 dict(name='care',act=3,title='冒险之后，也要好好休息。',sub='照料伙伴，为下一次出发做好准备。',duration=5,setup=['page 5'],events={30:['key 0 1'],90:['key 1 1']}),
 dict(name='growth',act=3,title='许多次冒险之后……',sub='成长演示：还是这两位伙伴，已经更强了。',duration=4,boot='12 25 35 74 3 123 0 0 0',setup=['party_add 30 35 60 500 0']),
 dict(name='skills',act=3,title='新的本领，也慢慢学会了。',sub='招式随成长解锁，不必反复遗忘和替换。',duration=4,setup=['key 0 1','key 0 3'],events={45:['key 1 1']}),
 dict(name='partner',act=4,title='尼多娜，这次交给你。',sub='换一位伙伴上场，向第一枚徽章出发。',duration=4,setup=['page 1','page 12'],events={15:['key 1 1'],45:['key 0 1'],75:['key 0 1']}),
 dict(name='gym',act=4,title='一起赢下，第一场道馆战。',sub='完整道馆战 · 每一次出招，都走向同一个结果。',duration=18,setup=['page 13','key 0 1'],battle=True),
 dict(name='victory',act=4,title='第一枚徽章，属于我们。',sub='胜利经验也分享给了没有上场的皮卡丘。',duration=6),
 dict(name='unlock',act=5,title='这枚徽章，打开了新的旅程。',sub='新的探索情报：森林深处出现了飞天螳螂。',duration=6,setup=['key 0 1','page 15','key 0 3']),
 dict(name='tracking',act=5,title='这一次，我们有了目标。',sub='从图鉴找到栖息地，再沿着线索追踪。',duration=5,setup=['page 6']+['key 1 1']*6+['key 0 1','key 1 1','key 1 1'],events={90:['key 0 1']}),
 dict(name='clues',act=5,title='一步一步，离它越来越近。',sub='三段线索，把我们带到森林更深处。',duration=17,setup=['exploration_fixture 0 24 0 0'],events={15:['key 0 1'],45:['key 1 1'],60:['key 0 1'],150:['key 0 1'],180:['key 1 1'],195:['key 0 1'],285:['key 0 1'],315:['key 1 1'],330:['key 0 1'],420:['key 0 1']}),
 dict(name='target',act=5,title='找到你了，飞天螳螂。',sub='下一位伙伴，正在等待我们的邀请。',duration=4),
 dict(name='second_meet',act=6,title='飞天螳螂，一起走吧。',sub='循着线索找到你，也想邀请你成为伙伴。',duration=30,until_choice=True,events={0:['key 0 1']}),
 dict(name='second_capture',act=6,title='再一次，投出邀请。',sub='看准时机，等待新伙伴回应。',duration=8,setup=['key 0 1'],events={45:['key 0 1']}),
 dict(name='new_party',act=6,title='这一次，我们有了三位伙伴。',sub='从第一枚徽章，到下一次相遇，旅程还在继续。',duration=6,setup=['key 0 1','tick 100','page 1','page 12'],events={30:['key 1 1'],75:['key 1 1']}),
 dict(name='outro',act=6,title='你的下一次相遇，会是谁？',sub='PokeWalk · 把伙伴和冒险，带在身边。',duration=5,setup=['page 1']),
]
DURATION=sum(s['duration'] for s in scenes);ACTS=['初遇','出发','成长','挑战','新旅程','同行']
fonts={n:ImageFont.truetype('/System/Library/Fonts/PingFang.ttc',n,index=2) for n in (22,24,32,38)}
for s in scenes:
 for c in s['title']+s['sub']:
  if not c.isspace():assert fonts[24].getmask(c).getbbox(),c
BG='#f2efe4';INK='#293b31';MUTED='#70796c'
def center(d,y,text,font,color=INK):
 box=d.textbbox((0,0),text,font=font);assert box[2]-box[0]<=680,text
 d.text(((720-box[2]+box[0])/2,y),text,font=font,fill=color)
def backdrop(s):
 im=Image.new('RGB',(720,1280),BG);d=ImageDraw.Draw(im)
 d.text((40,30),'POKEWALK',font=fonts[32],fill=INK);d.text((525,38),f"{s['act']:02d}  {ACTS[s['act']-1]}",font=fonts[22],fill=MUTED)
 d.line((40,85,680,85),fill=INK,width=2);center(d,115,s['title'],fonts[38]);d.rounded_rectangle((30,185,690,1055),radius=20,fill=INK)
 text=s['sub'];lines=[text] if fonts[24].getlength(text)<=640 else [text[:text.index(' · ')],text[text.index(' · ')+3:]] if ' · ' in text else [text[:24],text[24:]]
 for i,line in enumerate(lines):center(d,1090+i*34,line,fonts[24])
 center(d,1220,'游戏实录 · 成长段为演示存档 · 非官方同人',fonts[22],MUTED)
 return im
exe,version=build();r=None;pcm=bytearray();previous=None;previous_game=None;previous_music=None;global_frame=0;boundaries=[];manifest={'renderer':version,'duration':DURATION,'fps':FPS,'fresh_opening':True,'growth_time_jumps_labelled':True,'scenes':[]}
video=clean=None
if not args.check_only:
 def encoder(file,size):return subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',size,'-r','30','-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(out/file)],stdin=subprocess.PIPE)
 video=encoder('story-silent.mp4','720x1280');clean=encoder('gameplay-silent.mp4','480x640')
try:
 for s in scenes:
  if 'boot' in s:
   if r:r.close()
   r=Renderer(exe);r.command('boot '+s['boot']);r.command('audio_fixture 0')
  for c in s.get('setup',[]):r.command(c)
  begin=r.inspect();frames=[];checks=0;source_frames=0;reading=0;ready_hold=0
  for f in range(5400 if s.get('battle') else 1800 if s.get('opening') else s['duration']*FPS):
   for c in s.get('events',{}).get(f,[]):r.command(c)
   frame=r.command(f'tick {int((f+1)*1000/FPS)-int(f*1000/FPS)}');audio=r.audio(735)
   if f%30==0:assert r.command('check')['mismatch']==0,(s['name'],f);checks+=1
   sample=(frame['pixels'],audio,r.inspect()['music'] if f%30==0 else None,f)
   source_frames=f+1
   frames.append(sample)
   if s.get('battle') and f%3==0 and r.inspect()['challenge']['mode']==5:
    assert r.inspect()['challenge']['won'];break
   if s.get('until_choice'):
    status=r.inspect()
    if (status.get('presentation') or {}).get('phase')=='choice':
     ready_hold+=1
     if ready_hold>=45:break
    else:ready_hold=0
   if s.get('opening'):
    status=r.inspect()
    if status['page']==0 and not status['display']['busy']:
     reading+=1
     if reading>=60:r.command('key 0 1');reading=0
    else:reading=0
    if status['page']==9 and not status['display']['busy']:
     ready_hold+=1
     if ready_hold>=45:break
  if s.get('until_choice'):assert ready_hold>=45
  if s.get('opening'):assert r.inspect()['page']==9 and ready_hold>=45
  if s.get('battle'):assert r.inspect()['challenge']['mode']==5
  s['duration']=len(frames)/FPS
  end=r.inspect()
  if s['name']=='starter':assert end['pet']==25 and not end['needs_starter']
  if s['name']=='explore':assert end['queue'][-1]['species']==30
  if s['name']=='capture':assert end['caught']==2 and end['party'][1]['species']==30 and end['inventory'][0]==begin['inventory'][0]-1
  if s['name']=='partner':assert end['pet']==30 and end['party'][1]['species']==25
  if s['name']=='gym':assert end['challenge']['defeated']==1 and end['party'][1]['exp']>begin['party'][1]['exp']
  if s['name']=='clues':assert end['queue'][-1]['species']==123
  if s['name']=='second_capture':assert end['caught']==3 and end['party'][2]['species']==123 and end['inventory'][0]==begin['inventory'][0]-1
  bg=backdrop(s);start=global_frame/FPS;chunk=bytearray();jump_at=[]
  for f,(pixels,audio,music,source_f) in enumerate(frames):
   jump=f and source_f!=frames[f-1][3]+1
   if f==0 or jump:
    fade_from=previous;game_from=previous_game;fade_start=f;jump_at.append(source_f/FPS)
    if jump or 'boot' in s or begin['music']!=previous_music:boundaries.append((global_frame,len(pcm)//2))
   pcm.extend(audio);chunk.extend(audio)
   if not args.check_only:
    game=Image.frombytes('RGB',(240,320),rgb888(pixels));im=bg.copy();im.paste(game.resize((630,840),Image.Resampling.NEAREST),(45,200));d=ImageDraw.Draw(im)
    for i in range(6):d.rectangle((40+i*108,1185,138+i*108,1189),fill=INK if i<s['act'] else '#c2ceba')
    raw=game.resize((480,640),Image.Resampling.NEAREST)
    if fade_from is not None and f-fade_start<9:
     alpha=(f-fade_start+1)/9;im=Image.blend(fade_from,im,alpha);raw=Image.blend(game_from,raw,alpha)
    video.stdin.write(im.tobytes());clean.stdin.write(raw.tobytes());previous=im;previous_game=raw
    if f==len(frames)//2 or (s['name'] in ('gym','clues','capture') and f==len(frames)-15):im.save(out/f"{s['name']}-{f:03d}.jpg",quality=94)
   global_frame+=1
  values=array.array('h',chunk);rms=math.sqrt(sum(x*x for x in values)/len(values));assert rms>1,(s['name'],'silent soundtrack')
  manifest['scenes'].append({'name':s['name'],'act':s['act'],'start':start,'duration':s['duration'],'source_seconds':source_frames/FPS,'source_cuts':jump_at,'complete_source':True,'checks':checks,'rms':round(rms,2),'music_ids':sorted({x[2] for x in frames if x[2] is not None}),'party_before':begin['party'],'party_after':end['party'],'defeated':end['challenge']['defeated'],'exploration':end['exploration']})
  previous_music=end['music']
  print('recorded',s['name'],'source',round(source_frames/FPS,2),'output',s['duration'],flush=True)
finally:
 if r:r.close()
 if video:
  for enc in (video,clean):enc.stdin.close();assert enc.wait()==0
DURATION=global_frame/FPS;manifest['duration']=DURATION
assert len(pcm)==global_frame*735*2
manifest['frames']=global_frame;manifest['source_commit']=subprocess.check_output(['git','rev-parse','HEAD'],text=True,cwd=ROOT).strip();manifest['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
# Short ramps on editorial boundaries soften scene changes without replacing game music.
samples=array.array('h',pcm);ramp=2205
for _,at in boundaries:
 for i in range(ramp):
  if at+i<len(samples):samples[at+i]=int(samples[at+i]*i/ramp)
  if at-i-1>=0:samples[at-i-1]=int(samples[at-i-1]*i/ramp)
manifest['audio_sha256']=hashlib.sha256(samples.tobytes()).hexdigest();(out/('check-manifest.json' if args.check_only else 'manifest.json')).write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
if not args.check_only:
 with wave.open(str(out/'soundtrack.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050);w.writeframes(samples.tobytes())
 for src,dst in [('story-silent.mp4','pokewalk-story.mp4'),('gameplay-silent.mp4','pokewalk-story-clean.mp4')]:
  subprocess.run(['ffmpeg','-v','error','-y','-i',str(out/src),'-i',str(out/'soundtrack.wav'),'-c:v','copy','-af',f'loudnorm=I=-18:TP=-2:LRA=8,afade=t=out:st={DURATION-1}:d=1','-c:a','aac','-b:a','128k','-ar','48000','-shortest','-movflags','+faststart',str(out/dst)],check=True)
print(json.dumps({'duration':DURATION,'frames':global_frame,'output':str(out)}))
