#!/usr/bin/env python3
"""Check guide catalog integrity, every generated route, local links and escaping."""
import argparse, hashlib, json, re, subprocess, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
WEB=ROOT/'tools/save-manager/web/guide'
p=argparse.ArgumentParser();p.add_argument('--check-source',action='store_true');args=p.parse_args()
raw=(WEB/'catalog.js').read_text();catalog=json.loads(raw[raw.index('{'):].rstrip(';\n'))
for edition,d in catalog.items():
 assert [p['id'] for p in d['pokemon']]==list(range(1,152))
 assert len(d['items'])==19 and len(d['maps'])==12 and len(d['achievements'])==16
 all_ids={p['id'] for p in d['pokemon']};move_ids={m['id'] for m in d['moves']}
 assert {i for m in d['maps'][:4] for i in m['pool']}==all_ids
 for p in d['pokemon']:
  assert all(mid in move_ids and 1<=lv<=100 for mid,lv in p['learnset'])
 for m in d['maps']:
  assert set(m['pool'])<=all_ids
  if 'trails' in m:
   assert len(m['trails'])==3 and all(set(t['pool'])<=set(m['pool']) for t in m['trails'])
   assert len(m['levels'])==2 and m['levels'][0]<=m['deepMin']<=m['levels'][1]
  if d['features']['careEvents'] and m['id']>=4:
   assert len(m['visitors'])>=5 and not set(m['visitors'])&set(m['pool'])
 for i in d['items']:
  assert all(a in all_ids and b in all_ids for a,b in i['evolutions'])
 assert all(a['item'] in range(19) and a['quantity']>0 for a in d['achievements'])
 assert d['shiny']==[64,48,32,16]
 if args.check_source and edition=='release':
  for name,expected in d['sourceHashes'].items():
   assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==expected, 'Stale guide data: '+name
# Run the real guide module with a minimal DOM shell. Browser layout is tested separately.
js=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const catalog=JSON.parse(fs.readFileSync(process.argv[2],'utf8').replace(/^export const CATALOG = /,'').replace(/;\s*$/,''));
const html=[]; const nodes={};const controls={};
for(const id of ['content','search','navigation','version'])nodes['#'+id]={value:'',innerHTML:'',addEventListener(){},querySelectorAll(){return []},focus(){},scrollIntoView(){}};
const context=vm.createContext({CATALOG:catalog,document:{title:'',querySelector(s){return controls[s]||nodes[s]||null}},Image:class{addEventListener(){}},location:{hash:''},window:{addEventListener(){}},console});
const source=fs.readFileSync(process.argv[3],'utf8').replace("import { CATALOG } from './catalog.js';",'');vm.runInContext(source,context);
let checks=0;
for(const edition of ['release','previous']){
 vm.runInContext(`data=CATALOG.${edition}`,context);
 for(const section of vm.runInContext('sections.map(s=>s[0])',context)){
  const variants=section==='pokemon'?[null,...Array.from({length:151},(_,i)=>i+1)]:section==='items'?[null,...Array.from({length:19},(_,i)=>i)]:section==='explore'?[null,...Array.from({length:12},(_,i)=>i)]:[null];
  for(const id of variants){
   context.location.hash='#'+section+(id===null?'':'/'+id);vm.runInContext('render()',context);const body=nodes['#content'].innerHTML;
   assert(body.includes('<h1>'),`${edition} ${section}/${id} missing heading`);
   assert(!/undefined|NaN|Lv\.null/.test(body),`${edition} ${section}/${id} missing data`);
   if(section==='moves'&&catalog[edition].features.moveSettings)assert(body.includes('至少保留 1 个')&&body.includes('选择自动出招范围'));
   if(section==='party'&&catalog[edition].features.boxRelease)assert(body.includes('直接在仓库放生')&&body.includes('默认取消'));
   if(section==='save'&&catalog[edition].features.compressedSave)assert(body.includes('V5–V22')&&body.includes('V22 可导出再导入'));
   else if(section==='save'&&catalog[edition].features.moveSettings)assert(body.includes('V5–V21')&&body.includes('V21 可导出再导入'));
   if(section==='items'&&id===null)assert(body.includes('道具手册')&&body.includes('开心饼干'));
   if(section==='items'&&id===0)assert(body.includes('<h1>精灵球</h1>'));
   if(section==='explore'&&id>=4)assert(body.includes('Lv.'+catalog[edition].maps[id].levels[0]));
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
nodes['#search'].value='<img src=x onerror=alert(1)>';vm.runInContext('render()',context);assert(!nodes['#content'].innerHTML.includes('<img src=x'));
console.log(JSON.stringify({passed:true,pages:checks,editions:2,calculators:true,links:true,escapedSearch:true}));
'''
with tempfile.TemporaryDirectory() as tmp:
 test=Path(tmp)/'guide.cjs';test.write_text(js)
 subprocess.run(['node',str(test),str(WEB/'catalog.js'),str(WEB/'guide.mjs')],check=True)
for name in ('index.html','guide.css','guide.mjs','catalog.js','pokemon.png','battle.png'):
 assert (WEB/name).stat().st_size>0
assert 'href="guide/"' in (WEB.parent/'index.html').read_text()
assert 'href="guide/#updates"' in (WEB.parent/'index.html').read_text()
print(json.dumps({'passed':True,'catalogs':2,'sourceHashes':args.check_source}))
