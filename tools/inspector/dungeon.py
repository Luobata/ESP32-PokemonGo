"""Isolated desktop dungeon prototype; never reads or writes device saves."""
import base64
import json
import random
import re
import secrets
import threading
from pathlib import Path
from native import Renderer, build, png, HERE

CARDS = [
 ('烈焰印记','火属性伙伴造成的伤害增加 25%'),('潮汐印记','水属性伙伴造成的伤害增加 25%'),
 ('雷鸣印记','电属性伙伴造成的伤害增加 25%'),('强攻','每场战斗开始时攻击提升一级'),
 ('冥想','每场战斗开始时特攻提升一级'),('坚守','每场战斗开始时防御、特防提升一级'),
 ('疾风','每场战斗开始时速度提升一级'),('会心','每场战斗开始时进入易击中要害状态'),
 ('余温','胜利后存活伙伴恢复 15% 生命'),('营火','营地治疗额外恢复 20% 生命'),
 ('净化','每场战斗开始时清除异常状态'),('接力盾','每只伙伴每场首次主动换入时防御提升一级')]
ROSTER = {3:'妙蛙花',6:'喷火龙',9:'水箭龟',25:'皮卡丘',65:'胡地',143:'卡比兽'}
NODES = ['林间入口','岔路','深林对战','营地','巡护精英','遗迹岔路','最后营地','森林首领']
ROOT = HERE.parent.parent / '.build/dungeon-saves'
LOCK = threading.Lock()
RUNS = {}

class Run:
 def __init__(self, data):
  self.d=data; self.r=None; self.frame=None
 def save(self):
  ROOT.mkdir(parents=True,exist_ok=True)
  path=ROOT/(self.d['id']+'.json'); tmp=path.with_suffix('.tmp')
  tmp.write_text(json.dumps(self.d,ensure_ascii=False));tmp.replace(path)
 def close(self):
  if self.r: self.r.close();self.r=None
 def rng(self, salt): return random.Random(self.d['seed']+self.d['node']*713+salt)
 def draw(self):
  self.d['choices']=self.rng(len(self.d['cards'])*19).sample([i for i in range(12) if i not in self.d['cards']],3)
  self.d['phase']='reward'
 def start(self):
  d=self.d; self.close();self.r=Renderer(build()[0]);self.r.command('boot 13 3 50 74 3 1 0 0 1')
  foes=d.get('foes')
  if not foes:
   table={0:[12,47,17],1:[20,24,28],2:[31,34,62],4:[123,127,114],5:[112,115,128],7:[103,45,149]}
   pool=table[d['node']];foes=pool[:] if d['node']==7 else self.rng(98).sample(pool,2 if d['node']>=2 else 1)
   d['foes']=foes
  hp=[m['hp'] for m in d['party']] if d['party'] else [65535]*3
  statuses=[m['status'] for m in d['party']] if d['party'] else [0]*3
  args=[d['seed']+d['node'],d['node'],sum(1<<i for i in d['cards']),*d['selected'],*hp,*statuses,*(foes+[0]*(3-len(foes))),{0:42,1:43,2:45,4:48,5:48,7:51}[d['node']]]
  self.frame=self.r.command('rogue_setup '+' '.join(map(str,args)))
  if d.get('blob'):
   self.frame=self.r.command('rogue_restore '+d['blob'])
   self.frame=self.r.command('rogue_guards '+str(d.get('guards',0)))
  d['phase']='battle';self.capture()
 def capture(self):
  state=self.r.inspect();d=self.d;c=state['challenge']
  d['blob']=state['rogue_blob'];d['guards']=state['rogue_guards'];d['party']=c['sides'][0]['mons'];d['mode']=c['mode']
  if c['mode']==5 and c['finished']:
   d['blob']=None; d['foes']=None
   if not c['won']:d['phase']='lost';d['log'].append('队伍倒下了。本局结束，已获得的体验奖励保留。')
   else:
    d['wins']+=1;d['xp']+=150+d['node']*40
    if 8 in d['cards']:self.heal(15)
    if d['node']==7:d['phase']='won';d['log'].append('击败森林首领！获得叶之石 ×1。');d['items'].append('叶之石 ×1')
    else:self.draw()
 def heal(self, percent):
  for m in self.d['party']:
   if m['hp']:m['hp']=min(m['max_hp'],m['hp']+max(1,m['max_hp']*percent//100))
 def advance(self):
  d=self.d;d['node']+=1;d['blob']=None;d['foes']=None
  if d['node'] in (1,5):d['phase']='fork'
  elif d['node'] in (3,6):d['phase']='camp'
  else:self.start()
 def act(self,data):
  d=self.d;a=data['action']
  if a=='resume':
   if d['phase']=='battle' and not self.r:self.start()
   return
  if data.get('revision')!=d['revision']:raise ValueError('画面已更新，请重试')
  if a=='tick' and d['phase']=='battle':
   self.frame=self.r.command('tick 60');self.capture()
  elif a=='key' and d['phase']=='battle':
   key=data.get('key');event=data.get('event',1)
   if type(key)!=int or key not in (0,1,2) or event not in (1,3) or (event==3 and key!=1):raise ValueError('按键无效')
   self.frame=self.r.command(f'key {key} {event}');self.capture()
  elif a=='choose' and d['phase']=='reward':
   card=data.get('choice')
   if card not in d['choices']:raise ValueError('强化选项无效')
   d['cards'].append(card);d['log'].append('获得强化：'+CARDS[card][0]);self.advance()
  elif a=='choose' and d['phase']=='fork':
   choice=data.get('choice')
   if choice==0:self.start()
   elif choice==1:
    if d['node']==1:
     for m in d['party']:
      if m['hp']:m['hp']=max(1,m['hp']-max(1,m['max_hp']*12//100))
     d['log'].append('穿过荆棘，存活伙伴损失 12% 生命。');self.draw()
    else:self.heal(15);d['items'].append('树果 ×3');d['log'].append('发现补给，恢复 15% 生命并获得树果。');self.advance()
   else:raise ValueError('路线无效')
  elif a=='choose' and d['phase']=='camp':
   choice=data.get('choice')
   if choice==0:self.heal(25+(20 if 9 in d['cards'] else 0));d['log'].append('营地休息，恢复生命。');self.advance()
   elif choice==1:
    dead=next((m for m in d['party'] if not m['hp']),None)
    if not dead:raise ValueError('没有需要复苏的伙伴')
    dead['hp']=max(1,dead['max_hp']*35//100);dead['status']=0;d['log'].append('一只伙伴复苏，恢复 35% 生命。');self.advance()
   elif choice==2:self.draw()
   else:raise ValueError('营地选项无效')
  elif a=='retire' and d['phase'] not in ('won','lost','retired'):d['phase']='retired';self.close()
  else:raise ValueError('此时不能执行此操作')
  d['revision']+=1;self.save()
 def view(self,audio=False):
  d={k:v for k,v in self.d.items() if k not in ('blob','seed','guards')}
  d['catalog']=[{'id':i,'name':x[0],'description':x[1]} for i,x in enumerate(CARDS)];d['roster']=ROSTER;d['nodes']=NODES
  if self.frame:d['image']=base64.b64encode(png(self.frame['pixels'])).decode()
  if audio and self.r and d['phase']=='battle':d['audio']=base64.b64encode(self.r.audio(1323)).decode()
  return d

def request(data):
 with LOCK:
  if data.get('action')=='new':
   chosen=data.get('selected')
   if not isinstance(chosen,list) or len(chosen)!=3 or any(type(i)!=int or i not in ROSTER for i in chosen) or len(set(chosen))!=3:raise ValueError('请选择三只不同伙伴')
   run=Run(dict(id=secrets.token_hex(16),revision=0,seed=secrets.randbelow(2**30),node=0,phase='battle',selected=chosen,party=[],cards=[],choices=[],wins=0,xp=0,items=[],log=['进入森林秘境。体验队伍等级固定为 50，奖励暂不进入正式存档。'],blob=None))
   run.start();run.save();RUNS[run.d['id']]=run
  else:
   rid=data.get('id','')
   if not isinstance(rid,str) or not re.fullmatch('[0-9a-f]{32}',rid):raise ValueError('未找到体验存档')
   run=RUNS.get(rid)
   if not run:
    path=ROOT/(rid+'.json')
    if not path.exists():raise ValueError('未找到体验存档')
    run=Run(json.loads(path.read_text()));RUNS[rid]=run
   if run.d['phase']=='battle' and not run.r:run.start()
   run.act(data)
  while len(RUNS)>8:
   old=next(iter(RUNS));RUNS.pop(old).close()
  return run.view(bool(data.get('audio')))
