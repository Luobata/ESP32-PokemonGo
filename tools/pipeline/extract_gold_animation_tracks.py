#!/usr/bin/env python3
"""Execute pinned Gold animation machine code offline and export display tracks.

Requires a locally built, hash-matching pokegold.gbc and PyBoy 2.7.0. The ROM is
never included in firmware. Only animation display data is exported. VBlank
waits are replaced by explicit frame stepping; audio calls are suppressed.
The animation command, object, frameset and background routines are unmodified.
"""
import argparse, hashlib, json, re, struct, subprocess
from pathlib import Path
from pyboy import PyBoy
ROOT=Path(__file__).resolve().parents[2]
COMMIT='656583c939d30f920a316177311a502dd222b57c'
ROM_SHA1='d8b8a3600a465308c9953dfa04f0081c05bdcb94'

class Engine:
 def __init__(self,src):
  self.src=src
  palpath='gfx/battle_anims/battle_anims.pal'
  if (src/palpath).read_bytes()!=subprocess.check_output(['git','-C',str(src),'show',COMMIT+':'+palpath]):raise ValueError('Palette differs from pinned Gold source')
  rom=src/'pokegold.gbc' 
  if hashlib.sha1(rom.read_bytes()).hexdigest()!=ROM_SHA1:raise ValueError('Gold ROM does not match the original source build')
  self.syms={m[3]:(int(m[1],16),int(m[2],16)) for m in re.finditer(r'^([0-9a-f]+):([0-9a-f]+) (\S+)$',(src/'pokegold.sym').read_text(),re.M)}
  self.p=PyBoy(str(rom),window='null',sound_emulated=False,log_level='ERROR');self.p.set_emulation_speed(0)
  self.p.memory[0xff50]=1
  for name in ['DelayFrame','BattleAnimDelayFrame','WaitSFX','WaitTop','PlaySFX','PlayCry']:
   if name in self.syms:self.patch(name,[0xc9])
  _,addr=self.syms['Get2bpp'];self.patch('Request2bpp',[0xc3,addr&255,addr>>8])
  self.markers={}
  for i in range(85):
   data=bytes([(i*7+j*13+1)&255 for j in range(16)])
   self.markers[data]=0x8000+i
  self.marker_bytes=list(self.markers)
  self.origins={}
  bank,addr=self.syms['BattleAnimOAMUpdate.loop']
  def origin(context):
   x=(self.read('wBattleAnimTempXCoord')+self.read('wBattleAnimTempXOffset'))&255
   y=(self.read('wBattleAnimTempYCoord')+self.read('wBattleAnimTempYOffset'))&255
   self.origins[self.p.register_file.E]=(x,y)
  self.p.hook_register(bank,addr,origin,None)
  self.dynamic_actor=[False,False]
  def body_load(enabled):
   self.dynamic_actor[self.read('hBattleTurn')]=enabled
  for name,enabled in [('BattleAnimCmd_Transform',True),('BattleAnimCmd_DropSub',True),('BattleAnimCmd_RaiseSub',False),('BattleAnimCmd_MinimizeOpp',False)]:
   bank,addr=self.syms[name];self.p.hook_register(bank,addr,body_load,enabled)
 def patch(self,name,data):
  b,a=self.syms[name];self.p.memory[b,a:a+len(data)]=data
 def write(self,name,value):self.p.memory[self.syms[name][1]]=value
 def read(self,name,count=1):
  a=self.syms[name][1];return self.p.memory[a] if count==1 else bytes(self.p.memory[a:a+count])
 def call(self,name):
  bank,addr=self.syms[name];self.write('hROMBank',bank);self.p.memory[0x2000]=bank
  self.p.memory[0,0x100:0x106]=[0xf3,0xcd,addr&255,addr>>8,0x18,0xfe]
  self.p.register_file.PC=0x100;self.p.register_file.SP=0xdfff
  for _ in range(100):
   self.p.tick(1,False,False)
   if self.p.register_file.PC==0x104:return
  raise RuntimeError(f'{name} did not return: PC={self.p.register_file.PC:04x}')
 def start(self,move,side,param):
  self.dynamic_actor=[False,False]
  m=self.p.memory;m[0xff40]=0;m[0xffff]=0;m[0xff0f]=0;m[0xff70]=1
  m[0xc000:0xe000]=[0]*0x2000;m[0xff80:0xffff]=[0]*0x7f
  m[0xff4f]=0;m[0x8000:0xa000]=[0]*0x2000
  for i,data in enumerate(self.marker_bytes):m[0x9000+i*16:0x9010+i*16]=data
  tilemap=[0x7f]*360
  for x in range(7):
   for y in range(7):tilemap[y*20+12+x]=x*7+y
  for x in range(6):
   for y in range(6):tilemap[(y+6)*20+2+x]=49+x*6+y
  a=self.syms['wTilemap'][1];m[a:a+360]=tilemap
  self.write('hCGB',1);self.write('wFXAnimID',move);self.write('hBattleTurn',side);self.write('wBattleAnimParam',param)
  for n,v in [('wCurPartySpecies',25),('wTempBattleMonSpecies',25),('wTempEnemyMonSpecies',143)]:self.write(n,v)
  # Gold's six effect palettes occupy object slots 2..7. Battler slots are
  # represented symbolically by the runtime's current front/back palettes.
  colors=re.findall(r'RGB\s+(\d+),\s*(\d+),\s*(\d+)',(self.src/'gfx/battle_anims/battle_anims.pal').read_text())
  pal=bytes().join(struct.pack('<H',int(r)|(int(g)<<5)|(int(b)<<10)) for r,g,b in colors)
  gray=struct.pack('<4H',32767,25368,12684,0)
  for n,data in [('wOBPals1',gray*2+pal),('wBGPals1',gray*8)]:
   a=self.syms[n][1];m[a:a+len(data)]=data
  self.call('ClearBattleAnims')
 def step(self):
  self.origins={}
  for n in ['RunBattleAnimCommand','_ExecuteBGEffects','BattleAnim_UpdateOAM_All','BattleAnimRequestPals']:self.call(n)
  return bool(self.read('wBattleAnimFlags')&1)
 def close(self):self.p.stop(save=False)

class Pool:
 def __init__(self):self.values=[];self.ids={}
 def add(self,v):
  if v not in self.ids:self.ids[v]=len(self.values);self.values.append(v)
  return self.ids[v]

def extract(src,out):
 e=Engine(src);e.src=src
 tiles,objects,maps,lines,pals,frames,clips=[Pool() for _ in range(7)]
 rows=json.loads((ROOT/'tools/inspector/move-catalog.json').read_text());lookup=[];coverage=[]
 def tile(data):return e.markers[data] if data in e.markers else tiles.add(data)
 def snapshot():
  vram=bytes(e.p.memory[0x8000:0x9800]);oam=e.read('wShadowOAM',160);sprites=[]
  for i in range(0,160,4):
   y,x,t,flags=oam[i:i+4]
   if y==0 or y>=160 or x==0 or x>=168:continue
   ref=tile(vram[t*16:t*16+16]);ox,oy=e.origins[i]
   ox=x+((ox-x+128)%256-128);oy=y+((oy-y+128)%256-128)
   sprites.append((x,y,ref,flags,ox,oy))
  bg=[]
  for t in e.read('wTilemap',240):
   # The original white tile is outside battler graphics.
   if t==0x7f:bg.append(65535)
   elif t<85 and e.dynamic_actor[1 if t<49 else 0]:bg.append(0x8000+t)
   else:
    a=0x1000+(t if t<128 else t-256)*16
    bg.append(tile(vram[a:a+16]))
  return frames.add((objects.add(tuple(sprites)),maps.add(tuple(bg)),lines.add(e.read('wLYOverridesBackup',96)),
                     pals.add(e.read('wOBPals2',64)),e.read('hSCX'),e.read('hSCY'),e.read('hLCDCPointer'),e.read('wBGP')))
 try:
  for move in rows:
   for side in [0,1]:
    for param in [0,1]:
     e.start(move['id'],side,param);track=[];next_tick=0
     for frame in range(1500):
      done=e.step()
      # Source time is 59.7275 Hz. Firmware samples at 45ms, independently of
      # script waits. Do not stretch every source instruction to 45ms.
      if (frame+1)*100000>next_tick*268774:track.append(snapshot());next_tick+=1
      if done:break
     else:raise RuntimeError(f"nonterminating Gold animation: {move['id']}/{side}/{param}")
     lookup.append((move['id'],side,param,clips.add(tuple(track))))
     coverage.append(dict(move=move['id'],side=side,param=param,source_frames=frame+1,display_frames=len(track)))
   print(move['id'],len(frames.values),len(tiles.values),flush=True)
 finally:e.close()
 out.mkdir(parents=True,exist_ok=True)
 # Fixed-width indexed pools, consumed by the shared C renderer.
 payload=dict(tiles=[v.hex() for v in tiles.values],objects=objects.values,maps=maps.values,lines=[v.hex() for v in lines.values],pals=[v.hex() for v in pals.values],frames=frames.values,clips=clips.values,lookup=lookup)
 (out/'tracks.json').write_text(json.dumps(payload,separators=(',',':')))
 (out/'coverage.json').write_text(json.dumps(dict(source_commit=COMMIT,rom_sha1=ROM_SHA1,cases=coverage,patched=['VBlank waits','audio output','synchronous tile transfers'],unmodified=['animation commands','object motion','framesets','background callbacks'],full_visual_equivalence=False),indent=2)+'\n')
 print({k:len(v.values) for k,v in [('tiles',tiles),('objects',objects),('maps',maps),('lines',lines),('palettes',pals),('frames',frames),('clips',clips)]})

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=Path('/tmp/pokewalk-gold-review'));p.add_argument('--out',type=Path,default=Path('/tmp/pokewalk-gold-tracks'));a=p.parse_args();extract(a.source,a.out)
