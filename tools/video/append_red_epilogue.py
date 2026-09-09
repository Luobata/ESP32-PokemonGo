#!/usr/bin/env python3
"""Append a native-rendered Red battle excerpt to story V2, with game audio."""
from pathlib import Path
import sys, subprocess, json, wave, hashlib, array, math
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/inspector'))
from native import build, Renderer, rgb888
OUT = ROOT / 'reports/video/pokewalk-story-red-2026-09-09'
OUT.mkdir(parents=True, exist_ok=True)
SOURCE = ROOT / 'reports/video/pokewalk-story-transition-2026-09-09/pokewalk-story-v2.mp4'
FPS = 30
INK, PAPER, MUTED = '#293b31', '#f2efe4', '#70796c'
fonts = {n: ImageFont.truetype('/System/Library/Fonts/PingFang.ttc', n, index=2) for n in (22, 24, 32, 38, 52)}
def center(draw, y, text, size, color=INK):
    box = draw.textbbox((0, 0), text, font=fonts[size])
    assert box[2] - box[0] <= 680
    draw.text(((720 - box[2] + box[0]) / 2, y), text, font=fonts[size], fill=color)
def card(title, subtitle):
    im = Image.new('RGB', (720, 1280), INK)
    d = ImageDraw.Draw(im)
    center(d, 65, 'POKEWALK', 32, PAPER)
    d.line((70, 125, 650, 125), fill='#8ba385', width=2)
    center(d, 455, title, 38, PAPER)
    center(d, 555, subtitle, 52, PAPER)
    center(d, 1110, '把伙伴和冒险，带在身边。', 24, '#bdcfb0')
    return im
intro = card('而在旅程的更远处……', '赤红，正在等你。')
ending = card('下一场挑战，等你亲自上场。', 'POKEWALK')
intro.save(OUT / 'chapter-card.png')
bg = Image.new('RGB', (720, 1280), PAPER)
d = ImageDraw.Draw(bg)
d.text((40, 30), 'POKEWALK', font=fonts[32], fill=INK)
d.text((525, 38), '07  赤红', font=fonts[22], fill=MUTED)
d.line((40, 85, 680, 85), fill=INK, width=2)
center(d, 115, '白银山上，与赤红交锋。', 38)
d.rounded_rectangle((30, 185, 690, 1055), radius=20, fill=INK)
center(d, 1090, '通关后挑战演示 · 出场、出宠与技能交锋', 24)
center(d, 1130, '对战节选 · 完整挑战，留给你的旅程', 24)
center(d, 1220, '游戏实录 · 隔离演示存档 · 非官方同人', 22, MUTED)
exe, version = build()
r = Renderer(exe)
frames, pcm, states = [], bytearray(), []
try:
    for command in ['boot 13 6 90 74 3 123 0 0 1', 'audio_fixture 0', 'challenge_unlock 8191', 'page 0', 'page 13']:
        r.command(command)
    # Keep the actual intro, sendouts and seven complete actions. Stop before action 8.
    for f in range(1800):
        if f == 45:
            r.command('key 0 1')
        frame = r.command(f'tick {int((f+1)*1000/FPS)-int(f*1000/FPS)}')
        audio = r.audio(735)
        state = r.inspect()
        if state['challenge']['turns'] >= 8:
            break
        if f % 30 == 0:
            assert r.command('check')['mismatch'] == 0
            states.append({'frame': f, 'music': state['music'], 'challenge': state['challenge']})
        game = Image.frombytes('RGB', (240, 320), rgb888(frame['pixels']))
        im = bg.copy()
        im.paste(game.resize((630, 840), Image.Resampling.NEAREST), (45, 200))
        frames.append(im)
        pcm.extend(audio)
    assert state['challenge']['trainer'] == 13
    assert state['challenge']['turns'] == 8
    assert any(s['challenge']['mode'] == 1 for s in states)
    assert any(s['challenge']['mode'] == 2 for s in states)
    assert len(state['challenge']['sides'][1]['mons']) == 6
finally:
    r.close()
print('Recorded Red:', len(frames)/FPS, 'seconds', flush=True)
for sec in (2, 4, 6, 10, 15, 20, 25):
    if sec*FPS < len(frames):
        frames[sec*FPS].save(OUT / f'red-{sec:02d}.jpg', quality=94)
# The card gives the postgame time jump room to breathe. Recorded actions stay continuous.
lead, tail = 75, 90
enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '720x1280', '-r', '30', '-i', 'pipe:0', '-an', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', str(OUT/'red-silent.mp4')], stdin=subprocess.PIPE)
for i in range(lead):
    enc.stdin.write(intro.tobytes())
for i, im in enumerate(frames):
    if i < 18:
        im = Image.blend(intro, im, (i+1)/18)
    enc.stdin.write(im.tobytes())
for i in range(tail):
    im = Image.blend(frames[-1], ending, min(1, (i+1)/24))
    enc.stdin.write(im.tobytes())
enc.stdin.close()
assert enc.wait() == 0
# Game soundtrack begins as the gameplay fades in; the chapter card follows the previous ending's silence.
samples = array.array('h', pcm)
rms = math.sqrt(sum(x*x for x in samples)/len(samples))
assert rms > 1
sound = b'\0'*(lead*735*2) + pcm + b'\0'*(tail*735*2)
with wave.open(str(OUT/'red-soundtrack.wav'), 'wb') as w:
    w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050); w.writeframes(sound)
duration = (lead+len(frames)+tail)/FPS
excerpt = OUT/'red-epilogue.mp4'
subprocess.run(['ffmpeg','-v','error','-y','-i',str(OUT/'red-silent.mp4'),'-i',str(OUT/'red-soundtrack.wav'),'-c:v','copy','-af',f'loudnorm=I=-18:TP=-2:LRA=8,afade=t=in:st=2.5:d=0.2,afade=t=out:st={(lead+len(frames))/FPS-0.6}:d=0.6','-c:a','aac','-b:a','128k','-ar','48000','-shortest','-movflags','+faststart',str(excerpt)],check=True)
# A short fade out of the former ending leads into the epilogue card.
final = OUT/'pokewalk-story-v3.mp4'
filters = '[0:v]fade=t=out:st=190.033333:d=0.6:color=0x293b31,setpts=PTS-STARTPTS[v0];[0:a]aresample=48000,apad,atrim=duration=190.633333,asetpts=PTS-STARTPTS[a0];[1:v]setpts=PTS-STARTPTS[v1];[1:a]aresample=48000,asetpts=PTS-STARTPTS[a1];[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]'
subprocess.run(['ffmpeg','-v','error','-y','-i',str(SOURCE),'-i',str(excerpt),'-filter_complex',filters,'-map','[v]','-map','[a]','-c:v','libx264','-preset','fast','-crf','18','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-movflags','+faststart',str(final)],check=True)
info = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(final)]))
v = next(s for s in info['streams'] if s['codec_type']=='video')
assert int(v['nb_frames']) == 5719+lead+len(frames)+tail
subprocess.run(['ffmpeg','-v','error','-i',str(final),'-f','null','-'],check=True)
(OUT/'manifest.json').write_text(json.dumps({'status':'PASS','source':str(SOURCE.relative_to(ROOT)),'renderer':version,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'fps':FPS,'duration':float(info['format']['duration']),'frames':int(v['nb_frames']),'red_gameplay_seconds':len(frames)/FPS,'red_epilogue_seconds':duration,'trainer_id':13,'completed_actions':7,'cut_before_action':8,'audio_rms':rms,'audio_source':'synchronous production game mixer','fixture':'isolated postgame demonstration; player saves untouched','states':states,'sha256':hashlib.sha256(final.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
print(final, flush=True)
