#!/usr/bin/env python3
"""Record initialization and chaptered gameplay, with the live game mixer per frame.
The first chapters share a fresh save; later chapters are labelled staged growth
fixtures. Never reads or changes a player's device save, and never plays speakers.
"""
from pathlib import Path
import sys,subprocess,json,wave,argparse,hashlib
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'tools/inspector'))
from native import build,Renderer,rgb888
p=argparse.ArgumentParser();p.add_argument('--check-only',action='store_true');p.add_argument('--out',type=Path,default=ROOT/'reports/video/pokewalk-promo-2026-09-09');args=p.parse_args();OUT=args.out;OUT.mkdir(parents=True,exist_ok=True)
FPS=30
scenes=[
 dict(name='opening',title='你好，宝可梦的世界。',sub='全新存档 · 从大木博士的邀请开始',duration=22,boot='0 25 12 74 3 123 0 0 0',events={i*90:['key 0 1'] for i in range(1,8)}),
 dict(name='starter',title='选择你的第一位伙伴。',sub='妙蛙种子 · 小火龙 · 杰尼龟 · 皮卡丘',duration=7,events={30:['key 1 1'],60:['key 1 1'],90:['key 1 1'],150:['key 0 1']}),
 dict(name='idle',title='把冒险，装进口袋。',sub='伙伴已就位，旅程正式开始',duration=3,events={}),
 dict(name='menu',title='一颗按钮，展开冒险。',sub='图鉴 · 队伍 · 道具 · 照料 · 挑战 · 成就',duration=4,setup=['page 11'],events={20:['key 1 1'],40:['key 1 1'],60:['key 1 1'],80:['key 1 1']}),
 dict(name='explore',title='向下一次相遇出发。',sub='成长后的旅程 · 选择路线，消耗体力探索',duration=7,boot='15 25 30 74 3 123 0 0 0',setup=['exploration_fixture 0 12 0 0'],events={30:['key 0 1'],70:['key 1 1'],100:['key 0 1'],140:['key 1 1'],170:['key 0 1']}),
 dict(name='battle',title='相遇，就此开战。',sub='自动出招 · 属性克制 · 像素技能特效',duration=10,boot='3 25 60 130 4 23 0 0 0',events={120:['key 1 1']}),
 dict(name='capture',title='这一刻，抓住它。',sub='投球、晃动，等待新伙伴加入',duration=6,boot='4 25 30 133 4 123 1 0 0',setup=['page 3','tick 6000','page 4'],events={45:['key 0 1']}),
 dict(name='capture-fail',title='失败，也还有机会。',sub='脱出后反击一次，再次选择捕捉或战斗',duration=6,boot='4 25 30 133 4 123 0 0 0',setup=['page 3','tick 6000','page 4'],events={30:['key 0 1']}),
 dict(name='party',title='你的队伍，你的冒险。',sub='选择出战伙伴 · 仓库换入 · 闪光配色',duration=5,boot='12 25 30 74 3 123 0 0 1',setup=['party_add 150 30 80 100 1'],events={30:['key 1 1'],60:['key 1 1'],90:['key 0 3']}),
 dict(name='skills',title='经典招式，随成长学会。',sub='适配伙伴自动解锁机器招式，不遗忘、不设 PP',duration=5,boot='12 9 40 74 3 123 0 0 0',setup=['key 0 1','key 0 3'],events={30:['key 1 1'],60:['key 1 1'],90:['key 1 1']}),
 dict(name='care',title='战斗之外，也要陪伴。',sub='饱食、心情和亲密度，影响经验与稀有相遇',duration=5,boot='5 25 30 74 3 123 0 0 0',setup=['nurture_fixture 75 55 65 70'],events={30:['key 0 1'],70:['key 1 1'],100:['key 0 1']}),
 dict(name='evolve',title='成长，会给你惊喜。',sub='探索与陪伴，让鲤鱼王成为暴鲤龙',duration=5,boot='5 129 20 74 3 123 0 0 0',setup=['care_progress 100 1000']+['key 1 1']*4,events={30:['key 0 1']}),
 dict(name='dex',title='把每一次相遇，收进图鉴。',sub='151 只宝可梦 · 捕获记录 · 正面像素原画',duration=4,boot='6 25 30 74 3 123 0 0 1',events={30:['key 1 1'],60:['key 1 1'],90:['key 1 1']}),
 dict(name='bag',title='为旅程，准备一点惊喜。',sub='精灵球 · 进化石 · 特殊进化机器 · 养成道具',duration=4,boot='10 25 30 74 3 123 0 0 0',setup=['inventory 10 1','inventory 13 1'],events={30:['key 1 1'],60:['key 1 1'],90:['key 1 1']}),
 dict(name='achievements',title='每一份成长，都有回响。',sub='图鉴、进化、徽章成就，兑换旅途补给',duration=4,boot='14 25 30 74 3 123 0 0 1',events={30:['key 0 1'],70:['key 1 1']}),
 dict(name='gym',title='向道馆，发起挑战。',sub='训练家出场 · 多伙伴交锋 · 单侧换宠动画',duration=10,boot='13 9 70 74 3 123 0 0 1',events={30:['key 0 1']}),
 dict(name='league',title='走上联盟的舞台。',sub='成长后的旅程 · 四天王连战，状态持续保留',duration=7,boot='13 6 80 74 3 123 0 0 1',setup=['challenge_unlock 255','page 0','page 13'],events={15:['key 0 1']}),
 dict(name='journal',title='徽章之外，还有新的线索。',sub='更多稀有目标与探索道具，随挑战进度解锁',duration=5,boot='15 25 60 74 3 123 0 0 0',setup=['challenge_unlock 8191','key 0 3'],events={45:['key 1 1'],90:['key 1 1']}),
 dict(name='red',title='与赤红，一决高下。',sub='道馆、联盟之后，挑战白银山的对手',duration=7,boot='13 6 90 74 3 123 0 0 1',setup=['challenge_unlock 8191','page 0','page 13'],events={15:['key 0 1']}),
 dict(name='settings',title='随身，也随心。',sub='音量可调 · 支持静音 · 60 秒自动熄屏',duration=4,boot='11 25 30 74 3 123 0 0 1',setup=['key 1 1']*5+['key 0 1'],events={20:['key 1 1'],40:['key 1 1'],60:['key 1 1']}),
 dict(name='outro',title='下一次相遇，会是谁？',sub='POKEWALK · AI Passport 上的宝可梦同人游戏',duration=3,boot='1 25 30 74 3 123 0 0 1',events={}),
]
DURATION=sum(s['duration'] for s in scenes)
fonts={n:ImageFont.truetype('/System/Library/Fonts/PingFang.ttc',n) for n in [22,24,32,40]}
BG='#f2efe4';INK='#293b31';MUTED='#6e7769';ACCENT='#bfcfaf'
def center(d,y,text,font,color):
 box=d.textbbox((0,0),text,font=font);d.text(((720-(box[2]-box[0]))/2,y),text,font=font,fill=color)
def base(s,index):
 im=Image.new('RGB',(720,1280),BG);d=ImageDraw.Draw(im);d.text((40,32),'POKEWALK',font=fonts[32],fill=INK);d.text((610,40),f'{index+1:02d}/{len(scenes)}',font=fonts[22],fill=MUTED);d.line((40,85,680,85),fill=INK,width=2)
 center(d,108,s['title'],fonts[40],INK);d.rounded_rectangle((30,185,690,1055),radius=20,fill=INK)
 # Two short lines allow all subtitles to remain readable at 720px.
 sub=s['sub'];parts=[sub] if len(sub)<=26 else [sub[:sub.rfind(' · ',0,27)] if ' · ' in sub[:27] else sub[:25],sub[sub.rfind(' · ',0,27)+3:] if ' · ' in sub[:27] else sub[25:]]
 for i,line in enumerate(parts):center(d,1090+i*32,line,fonts[24],INK)
 center(d,1212,'非官方同人项目 · 同源游戏画面 · 成长章节为演示存档',fonts[22],MUTED)
 return im
exe,version=build();log=open(OUT/'encode.log','w');video=clean=None
if not args.check_only:
 def enc(path,size):return subprocess.Popen(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s',size,'-r',str(FPS),'-i','pipe:0','-an','-c:v','libx264','-preset','veryfast','-crf','18','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],stdin=subprocess.PIPE,stderr=log)
 video=enc(OUT/'promo-silent.mp4','720x1280');clean=enc(OUT/'gameplay-silent.mp4','480x640')
manifest={'renderer_build':version,'fps':FPS,'duration':DURATION,'resolution':[720,1280],'fresh_save_opening':True,'later_chapters_staged':True,'audio':'production game mixer sampled synchronously at 22050Hz','scenes':[]};pcm=bytearray();global_frame=0;r=None
try:
 for index,s in enumerate(scenes):
  if 'boot' in s:
   if r:r.close()
   r=Renderer(exe);r.command('boot '+s['boot']);r.command('audio_fixture 0')
  for c in s.get('setup',[]):r.command(c)
  backdrop=base(s,index);start=global_frame/FPS;music=set();pages=set();samples=0;checks=0
  for f in range(s['duration']*FPS):
   for c in s.get('events',{}).get(f,[]):r.command(c)
   frame=r.command(f'tick {int((f+1)*1000/FPS)-int(f*1000/FPS)}');audio=r.audio(735);pcm.extend(audio);samples+=len(audio)//2
   if f%30==0:
    assert r.command('check')['mismatch']==0,(s['name'],f);checks+=1;st=r.inspect();music.add(st['music']);pages.add(st['page'])
   if not args.check_only:
    game=Image.frombytes('RGB',(240,320),rgb888(frame['pixels']));im=backdrop.copy();im.paste(game.resize((630,840),Image.Resampling.NEAREST),(45,200));d=ImageDraw.Draw(im);d.rectangle((40,1180,680,1184),fill=ACCENT);d.rectangle((40,1180,40+int(640*(global_frame+1)/(DURATION*FPS)),1184),fill=INK)
    video.stdin.write(im.tobytes());clean.stdin.write(game.resize((480,640),Image.Resampling.NEAREST).tobytes())
    if f==s['duration']*FPS//2:im.save(OUT/(s['name']+'.jpg'),quality=93)
    if s['name']=='battle' and f==210:im.save(OUT/'pokewalk-cover.jpg',quality=95)
   global_frame+=1
  st=r.inspect();manifest['scenes'].append({'name':s['name'],'start':start,'duration':s['duration'],'pages':sorted(pages),'music_ids':sorted(music),'audio_samples':samples,'ending_page':st['page'],'caught':st['caught'],'evolutions':st['evolutions'],'checks':checks})
  if s['name']=='opening':assert st['page']==9,('opening did not reach starter',st['page'])
  if s['name']=='starter':assert not st['needs_starter'] and st['pet']==25
  if s['name']=='capture':assert st['caught']>=2,'capture scene must succeed'
  if s['name']=='evolve':assert st['evolutions']>=1 and st['pet']==130
  print('recorded',s['name'],st['page'],sorted(music),flush=True)
finally:
 if r:r.close()
 if video:
  for proc in [video,clean]:proc.stdin.close();assert proc.wait()==0
 log.close()
assert len(pcm)==DURATION*22050*2
manifest['audio_sha256']=hashlib.sha256(pcm).hexdigest();manifest['frames']=global_frame
(OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
if not args.check_only:
 with wave.open(str(OUT/'soundtrack.wav'),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050);w.writeframes(pcm)
 for source,target in [('promo-silent.mp4','pokewalk-promo.mp4'),('gameplay-silent.mp4','pokewalk-gameplay-clean.mp4')]:
  subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(OUT/source),'-i',str(OUT/'soundtrack.wav'),'-c:v','copy','-af',f'loudnorm=I=-18:TP=-2:LRA=8,afade=t=in:d=0.2,afade=t=out:st={DURATION-1}:d=1','-c:a','aac','-b:a','128k','-ar','48000','-shortest','-movflags','+faststart',str(OUT/target)],check=True)
print(json.dumps({'duration':DURATION,'scenes':len(scenes),'check_only':args.check_only,'output':str(OUT)}))
