#!/usr/bin/env python3
"""Replace only the noninteractive Oak/starter handoff with a visible chapter card.
The original audio and total duration remain unchanged. Gameplay outside the
77-frame editorial transition is decoded from the approved complete-flow cut.
"""
from pathlib import Path
import subprocess,json,hashlib
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[2]
source=ROOT/'reports/video/pokewalk-story-complete-2026-09-09/pokewalk-story.mp4'
out=ROOT/'reports/video/pokewalk-story-transition-2026-09-09';out.mkdir(parents=True,exist_ok=True)
start=852;end=929;fps=30;count=end-start
for name,time in [('oak',28.3),('starter',30.9)]:
 subprocess.run(['ffmpeg','-v','error','-y','-ss',str(time),'-i',str(source),'-frames:v','1',str(out/(name+'.png'))],check=True)
card=Image.new('RGB',(720,1280),'#293b31');d=ImageDraw.Draw(card)
def center(y,text,size,color='#f2efe4'):
 font=ImageFont.truetype('/System/Library/Fonts/PingFang.ttc',size,index=2)
 box=d.textbbox((0,0),text,font=font);d.text(((720-box[2]+box[0])/2,y),text,font=font,fill=color)
center(65,'POKEWALK',32);d.line((70,125,650,125),fill='#8ba385',width=2)
center(370,'接下来',30,'#bdcfb0');center(455,'选择你的',52);center(535,'第一位伙伴',52)
d.line((285,650,435,650),fill='#bdcfb0',width=3)
center(710,'妙蛙种子 · 小火龙',28);center(755,'杰尼龟 · 皮卡丘',28)
center(1110,'让冒险，从一位伙伴开始。',28,'#bdcfb0')
card.save(out/'chapter-card.png')
old=Image.open(out/'oak.png').convert('RGB');new=Image.open(out/'starter.png').convert('RGB')
p=subprocess.Popen(['ffmpeg','-v','error','-y','-f','rawvideo','-pix_fmt','rgb24','-s','720x1280','-r','30','-i','pipe:0','-an','-c:v','libx264','-crf','16','-pix_fmt','yuv420p',str(out/'transition-silent.mp4')],stdin=subprocess.PIPE)
for i in range(count):
 if i<18:frame=Image.blend(old,card,(i+1)/18)
 elif i<count-24:frame=card
 else:frame=Image.blend(card,new,(i-(count-24)+1)/24)
 p.stdin.write(frame.tobytes())
p.stdin.close();assert p.wait()==0
# Frame trims avoid imprecise GOP/keyframe seeks. Audio stream is copied verbatim.
filt=f'[0:v]trim=end_frame={start},setpts=PTS-STARTPTS[a];[1:v]setpts=PTS-STARTPTS[b];[0:v]trim=start_frame={end},setpts=PTS-STARTPTS[c];[a][b][c]concat=n=3:v=1:a=0[v]'
final=out/'pokewalk-story-v2.mp4'
subprocess.run(['ffmpeg','-v','error','-y','-i',str(source),'-i',str(out/'transition-silent.mp4'),'-filter_complex',filt,'-map','[v]','-map','0:a:0','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','copy','-movflags','+faststart',str(final)],check=True)
subprocess.run(['ffmpeg','-v','error','-y','-ss','25','-i',str(final),'-t','10','-c:v','libx264','-crf','18','-c:a','aac','-movflags','+faststart',str(out/'oak-to-starter-preview.mp4')],check=True)
info=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(final)]));v=next(x for x in info['streams'] if x['codec_type']=='video');assert int(v['nb_frames'])==5719
subprocess.run(['ffmpeg','-v','error','-i',str(final),'-f','null','-'],check=True)
def audio_hash(path):
 return hashlib.sha256(subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:a:0','-f','s16le','-'])).hexdigest()
audio=audio_hash(source);assert audio==audio_hash(final)
(out/'verification.json').write_text(json.dumps({'status':'PASS','source':str(source.relative_to(ROOT)),'frames':5719,'replacement_start_seconds':start/fps,'replacement_end_seconds':end/fps,'transition_frames':count,'fade_to_card_frames':18,'card_hold_frames':35,'fade_to_starter_frames':24,'audio_identical':True,'audio_pcm_sha256':audio,'final_sha256':hashlib.sha256(final.read_bytes()).hexdigest()},indent=2)+'\n')
print(final)
