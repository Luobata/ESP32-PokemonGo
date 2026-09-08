#!/usr/bin/env python3
"""Record real native firmware frames and mixed audio; isolated preview save only."""
import subprocess, sys, wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'tools/inspector'))
from native import build, Renderer, rgb888
OUT = ROOT/'reports/evidence/capture-animation-2026-09-08'
OUT.mkdir(parents=True, exist_ok=True)
font=ImageFont.truetype('/System/Library/Fonts/PingFang.ttc',26)
exe, version=build()
video=OUT/'capture-demo-silent.mp4'
p=subprocess.Popen(['ffmpeg','-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','720x1008','-r','25','-i','pipe:0','-an','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p',str(video)],stdin=subprocess.PIPE)
audio=bytearray()
for success,frames in ((True,225),(False,200)):
 r=Renderer(exe)
 try:
  r.command('boot 11 25 30 133 4 123 0 0 0')
  for _ in range(5):r.command('key 1 1')
  r.command('key 0 1')
  for _ in range(2):r.command('key 1 1')
  r.command('key 0 1')
  assert not r.inspect()['muted']
  r.audio(11025);r.audio(11025)
  f=r.command('page 4')
  for n in range(frames):
   if n == (37 if success else 30):f=r.command('key 0 1')
   image=Image.new('RGB',(720,1008),'#e9e5db')
   title='捕获成功 · 收球、三次晃动、成功短曲' if success else '捕获失败 · 弹出、反击、再次选择'
   ImageDraw.Draw(image).text((360,23),title,font=font,fill='#30372f',anchor='mm')
   image.paste(Image.frombytes('RGB',(240,320),rgb888(f['pixels'])).resize((720,960),Image.Resampling.NEAREST),(0,48))
   p.stdin.write(image.tobytes());audio.extend(r.audio(882))
   f=r.command('tick 40')
 finally:r.close()
p.stdin.close();assert p.wait()==0
wav=OUT/'capture-demo.wav'
with wave.open(str(wav),'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050);w.writeframes(audio)
subprocess.run(['ffmpeg','-y','-loglevel','error','-i',str(video),'-i',str(wav),'-c:v','copy','-c:a','aac','-b:a','128k','-af','volume=2','-shortest','-movflags','+faststart',str(OUT/'capture-demo.mp4')],check=True)
print(version, OUT/'capture-demo.mp4')
