#!/usr/bin/env python3
"""Export public guide catalogs from actual C rules and checked-in pixel assets."""
import argparse,base64,hashlib,json,os,re,subprocess,sys,tempfile,struct,zlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/inspector'))
from build import load_data,load_front,load_palettes,load_back

def catalog(root):
 with tempfile.TemporaryDirectory() as d:
  p=Path(d);(p/'esp_log.h').write_text('#define ESP_LOGE(...)\n#define ESP_LOGI(...)\n#define ESP_LOGW(...)\n')
  assembly=[]
  for name in ('gen1.bin','gen1_front.bin','gen1_back.bin','palettes.bin','font16.bin','moves.bin','ui.bin'):
   symbol='_binary_'+name.replace('.','_');assembly += ['.balign 4',f'.global {symbol}_start',f'.global {symbol}_end',f'{symbol}_start:',f'.incbin "{root/"assets"/name}"',f'{symbol}_end:']
  (p/'assets.S').write_text('\n'.join(assembly)+'\n')
  source=root/'firmware/main';development='exploration_visitors(' in (source/'exploration.c').read_text()
  files=['assets.c','pokemon_names.c','exploration.c','items.c','encounter.c','nurture.c','party.c','trainer.c','combat.c','battle.c','exp.c','evolution.c','achievements.c']
  command=['cc','-std=gnu11','-DHOST_BUILD','-O1','-ffunction-sections','-fdata-sections','-I',str(source),'-I',str(p),str(ROOT/'tools/pipeline/guide_catalog.c'),str(p/'assets.S')]+[str(source/f) for f in files]+['-lz',('-Wl,-dead_strip' if sys.platform=='darwin' else '-Wl,--gc-sections'),'-o',str(p/'catalog')]
  if development:command.insert(1,'-DGUIDE_VISITORS')
  result=subprocess.run(command,capture_output=True,text=True);assert result.returncode==0,result.stderr
  result=subprocess.run([str(p/'catalog')],capture_output=True,text=True);assert result.returncode==0,result.stderr
  data=json.loads(result.stdout)
  pools=json.loads(re.search(r'POOLS\[4\]\[5\]\[16\]=\s*(\{.*?\});',(source/'exploration.c').read_text(),re.S).group(1).replace('{','[').replace('}',']'))
  for i in range(4):data['maps'][i]['pool']=sum(pools[i],[])
  data['cards']=list(zip(*[re.findall(r'"([^"]+)"',re.search(r'dungeon_'+key+r'\[DUNGEON_CARD_COUNT\]=\{(.*?)\};',(source/'dungeon.c').read_text(),re.S).group(1)) for key in ('cards','desc')]))
  data['features']={'careEvents':development,'shinyEntry':(source/'shiny_entry.c').exists(),'nostalgicMoves':'pokemon_move_names_override' in (source/'pokemon_names.c').read_text(),'moveSettings':(source/'move_policy.h').exists(),'boxRelease':'world_box_release' in (source/'world.c').read_text()}
  data['sourceHashes']={str(f.relative_to(root)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(source.glob('*')) if f.suffix in ('.c','.h')}
  assert len(data['pokemon'])==151 and len(data['items'])==19 and len(data['achievements'])==16
  return data

def atlas(root,out):
 mons=load_data(root/'assets/gen1.bin');front=load_front(root/'assets/gen1_front.bin')[0];pals=load_palettes(root/'assets/palettes.bin')
 # Dimensions are encoded in the byte count; sheets contain actual front art.
 size=64;width=16*size;height=10*size;rows=[bytearray(width*4) for _ in range(height)]
 for mon in mons:
  raw=base64.b64decode(front[mon['id']]);side=int((len(raw)*4)**.5);palette=pals['normal'][mon['pal']]
  ox=(mon['id']-1)%16*size+(size-side)//2;oy=(mon['id']-1)//16*size+(size-side)//2
  for y in range(side):
   for x in range(side):
    value=(raw[(y*side+x)//4]>>(6-2*(x%4)))&3
    if value!=3:rows[oy+y][(ox+x)*4:(ox+x)*4+4]=bytes.fromhex(palette[value][1:])+b'\xff'
 def chunk(kind,body):return struct.pack('>I',len(body))+kind+body+struct.pack('>I',zlib.crc32(kind+body))
 data=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b''.join(b'\0'+r for r in rows),9))+chunk(b'IEND',b'')
 (out/'pokemon.png').write_bytes(data)

def version_catalog(ref,version):
 with tempfile.TemporaryDirectory() as d:
  archive=subprocess.run(['git','archive',ref,'firmware/main','assets'],cwd=ROOT,capture_output=True,check=True).stdout
  subprocess.run(['tar','-x','-C',d],input=archive,check=True);data=catalog(Path(d))
 data['sourceRef']=subprocess.check_output(['git','rev-parse',ref],cwd=ROOT,text=True).strip()
 data['version']=version
 return data

def main():
 p=argparse.ArgumentParser();p.add_argument('--release-ref',default='4b614e7c8c90529f261fc9ca729774807b6f29e3');p.add_argument('--previous-ref',default='af22e73947c5a2b4693ea89fd671995c2a1159d9')
 p.add_argument('--release-version',default='2026.10.07 · 招式设置与仓库管理');p.add_argument('--previous-version',default='2026.10.07 · 闪光出场与怀旧译名');a=p.parse_args()
 out=ROOT/'tools/save-manager/web/guide';out.mkdir(parents=True,exist_ok=True)
 release=version_catalog(a.release_ref,a.release_version);previous=version_catalog(a.previous_ref,a.previous_version)
 (out/'catalog.js').write_text('export const CATALOG = '+json.dumps({'release':release,'previous':previous},ensure_ascii=False,separators=(',',':'))+';\n')
 atlas(ROOT,out);print(json.dumps({'pokemon':151,'maps':len(release['maps']),'moves':len(release['moves']),'items':19,'achievements':16,'release':release['sourceRef']}))
if __name__=='__main__':main()
