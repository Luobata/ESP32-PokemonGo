#!/usr/bin/env python3
"""Check guide catalog integrity, every generated route, local links and escaping."""
import argparse, hashlib, json, re, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/'tools/save-manager/web/guide'
p=argparse.ArgumentParser();p.add_argument('--check-source',action='store_true');args=p.parse_args()
raw=(WEB/'catalog.js').read_text();catalog=json.loads(raw[raw.index('{'):].rstrip(';\n'))
raw=(WEB/'fieldwork.js').read_text();fieldwork=json.loads(raw[raw.index('{'):].rstrip(';\n'))
assert fieldwork['status']=='released'
assert [s['id'] for s in fieldwork['sites']]==list(range(17))
for site in fieldwork['sites']:
 assert site['types'] and len(site['clues'])==2 and len(site['examples'])>=2
 assert site['legend'] in range(6) and site['routeId'] in range(8) and site['pathId'] in range(3)
 assert all(1<=e['id']<=251 and e['location'] for e in site['examples'])
for edition,d in catalog.items():
 johto=d['features']['johto']; count=251 if johto else 151
 assert [p['id'] for p in d['pokemon']]==list(range(1,count+1))
 assert len(d['items'])==(24 if johto else 19) and len(d['maps'])==(20 if johto else 12) and len(d['achievements'])==(43 if johto else 16)
 assert d['warehouseCapacity']==(753 if johto else 453) and d['saveVersion']==(31 if johto else 23)
 all_ids={p['id'] for p in d['pokemon']};move_ids={m['id'] for m in d['moves']}
 assert {i for m in d['maps'][:4] for i in m['pool']}==set(range(1,152))
 for p in d['pokemon']:
  assert 1<=p['rarity']<=5
  assert all(mid in move_ids and 1<=lv<=100 for mid,lv in p['learnset'])
 for m in d['maps']:
  assert set(m['pool'])<=all_ids
  if 'trails' in m:
   assert len(m['trails'])==3 and all(set(t['pool'])<=set(m['pool']) for t in m['trails'])
   assert len(m['levels'])==2
   if not m.get('johto'):assert m['levels'][0]<=m['deepMin']<=m['levels'][1]
  if d['features']['careEvents'] and 4<=m['id']<12:
   assert len(m['visitors'])>=5 and not set(m['visitors'])&set(m['pool'])
 for i in d['items']:
  assert all(a in all_ids and b in all_ids for a,b in i['evolutions'])
 assert all(a['item'] in range(len(d['items'])) and a['quantity']>0 for a in d['achievements'])
 assert d['shiny']==[64,48,32,16]
 if args.check_source and edition=='release':
  for name,expected in d['sourceHashes'].items():
   assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, 'Stale guide data: '+name
# Run the real guide module with a minimal DOM shell. Browser layout is tested separately.
js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const catalog=JSON.parse(fs.readFileSync(process.argv[2],'utf8').replace(/^export const CATALOG = /,'').replace(/;\s*$/,''));
const fieldwork=JSON.parse(fs.readFileSync(process.argv[4],'utf8').replace(/^export const FIELDWORK_GUIDE = /,'').replace(/;\s*$/,''));
const html=[]; const nodes={};const controls={};
for(const id of ['content','search','navigation','version'])nodes['#'+id]={value:'',innerHTML:'',addEventListener(){},querySelectorAll(){return []},focus(){},scrollIntoView(){}};
const context=vm.createContext({CATALOG:catalog,FIELDWORK_GUIDE:fieldwork,document:{title:'',querySelector(s){return controls[s]||nodes[s]||null}},Image:class{addEventListener(){}},location:{hash:''},window:{addEventListener(){}},console});
const source=fs.readFileSync(process.argv[3],'utf8').replace("import { CATALOG } from './catalog.js';",'').replace("import { FIELDWORK_GUIDE } from './fieldwork.js';",'');vm.runInContext(source,context);
let checks=0;
for(const edition of ['release','previous']){
 vm.runInContext(`data=CATALOG.${edition}`,context);
 for(const section of vm.runInContext('sections.map(s=>s[0])',context)){
  const variants=section==='pokemon'?[null,...Array.from({length:catalog[edition].pokemon.length},(_,i)=>i+1)]:section==='items'?[null,...Array.from({length:catalog[edition].items.length},(_,i)=>i)]:section==='explore'?[null,...Array.from({length:catalog[edition].maps.length},(_,i)=>i)]:section==='fieldwork'?[null,...Array.from({length:17},(_,i)=>i)]:[null];
  for(const id of variants){
   context.location.hash='#'+section+(id===null?'':'/'+id);vm.runInContext('render()',context);const body=nodes['#content'].innerHTML;
   assert(body.includes('<h1>'),`${edition} ${section}/${id} missing heading`);
   assert(!/undefined|NaN|Lv\.null/.test(body),`${edition} ${section}/${id} missing data`);
   if(section==='moves'&&catalog[edition].features.moveSettings)assert(body.includes('至少保留 1 个')&&body.includes('选择自动出招范围'));
   if(section==='party'&&catalog[edition].features.boxRelease)assert(body.includes('直接在仓库放生')&&body.includes('默认取消'));
   if(section==='party'&&catalog[edition].features.expandedWarehouse)assert(body.includes(`${catalog[edition].warehouseCapacity} 格`)&&body.includes('同种宝可梦可以重复捕获'));
   if(section==='save'&&catalog[edition].features.johto)assert(body.includes('V5–V31')&&body.includes('V31 可导出再导入')&&body.includes('重新下载离线工具'));
   else if(section==='save'&&catalog[edition].features.expandedWarehouse)assert(body.includes('V5–V23')&&body.includes('V23 可导出再导入')&&body.includes('重新下载离线工具'));
   else if(section==='save'&&catalog[edition].features.compressedSave)assert(body.includes('V5–V22')&&body.includes('V22 可导出再导入'));
   else if(section==='save'&&catalog[edition].features.moveSettings)assert(body.includes('V5–V21')&&body.includes('V21 可导出再导入'));
   if(section==='items'&&id===null)assert(body.includes('道具手册')&&body.includes('开心饼干'));
   if(section==='items'&&id===0)assert(body.includes('<h1>精灵球</h1>'));
   if(section==='explore'&&id>=4)assert(body.includes('Lv.'+catalog[edition].maps[id].levels[0]));
   if(section==='johto'&&catalog[edition].features.johto)assert(body.includes('捕虫调查')&&body.includes('银色之羽')&&body.includes('任意 4 枚关都徽章'));
   if(section==='pokemon'&&id===175)assert(body.includes('神秘蛋专属伙伴'));
   if(section==='pokemon'&&id===133&&catalog[edition].features.johto)assert(body.includes('晨光训练')&&body.includes('夜行训练'));
   if(section==='fieldwork'){
    assert(!body.includes('尚未发布')&&body.includes('需要安装城都版本固件'));
    assert(!/<details[^>]*\bopen\b/.test(body),'Answers must be hidden until explicitly opened');
    assert.strictEqual((body.match(/<details /g)||[]).length,id===null?17:1);
    if(id!==null)for(const e of fieldwork.sites[id].examples)assert(body.includes(e.name)&&body.includes(e.location));
   }
   for(const match of body.matchAll(/href="(#.*?)"/g)){
    const [page,num]=match[1].slice(1).split('/'); assert(vm.runInContext(`Boolean(pages[${JSON.stringify(page)}])`,context),'Unknown link '+match[1]);
    if(num!==undefined)assert(Number.isInteger(Number(num)));
   }
   checks++;
  }
 }
 for(const [id,value] of [['satiety',100],['mood',100],['bond',100]]){controls['#'+id]={value};controls['#'+id+'-value']={};}
 controls['#care-output']={};controls['#care-detail']={};vm.runInContext('calculators()',context);
 assert(controls['#care-output'].textContent.includes(catalog[edition].features.careEvents?'155%':'130%'));
 for(const k of Object.keys(controls))delete controls[k];
}
controls['#wins']={value:0};controls['#shiny-output']={};vm.runInContext('calculators()',context);assert(controls['#shiny-output'].textContent.includes('2.08%'));
nodes['#search'].value='珊瑚间的光点';vm.runInContext('render()',context);
assert(nodes['#content'].innerHTML.includes('#fieldwork/9')&&!nodes['#content'].innerHTML.includes('灯笼鱼'),'Clue search must not reveal answers');
nodes['#search'].value='<img src=x onerror=alert(1)>';vm.runInContext('render()',context);assert(!nodes['#content'].innerHTML.includes('<img src=x'));
console.log(JSON.stringify({passed:true,pages:checks,editions:2,calculators:true,links:true,escapedSearch:true}));
'''
with tempfile.TemporaryDirectory() as tmp:
 test=Path(tmp)/'guide.cjs';test.write_text(js)
 subprocess.run(['node',str(test),str(WEB/'catalog.js'),str(WEB/'guide.mjs'),str(WEB/'fieldwork.js')],check=True)
for name in ('index.html','guide.css','guide.mjs','catalog.js','fieldwork.js','pokemon.png','battle.png'):
 assert (WEB/name).stat().st_size>0
assert 'href="guide/"' in (WEB.parent/'index.html').read_text()
assert 'href="guide/#updates"' in (WEB.parent/'index.html').read_text()
print(json.dumps({'passed':True,'catalogs':2,'sourceHashes':args.check_source}))
