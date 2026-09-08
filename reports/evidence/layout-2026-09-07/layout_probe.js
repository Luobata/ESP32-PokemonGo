// Node VM check of the actual JS page renderers. No browser/glyph raster claim.
// Run from repository root after build.py --assets assets --out /tmp/pokemon-layout-20260907/index.html.
const fs=require('fs'), vm=require('vm'), assert=require('assert'), cp=require('child_process');
const built=fs.readFileSync(process.argv[2]||'/tmp/pokemon-layout-20260907/index.html','utf8');
const payload=JSON.parse(built.match(/const D = (.*);\n/)[1]);
const current=fs.readFileSync('tools/inspector/template.html','utf8');
const original=cp.execFileSync('git',['show','HEAD:tools/inspector/template.html'],{encoding:'utf8'});
const context=()=>new Proxy({}, {get:(o,k)=>k in o?o[k]:(...args)=>{},set:(o,k,v)=>(o[k]=v,true)});
function load(source){
  const canvas=()=>({width:240,height:320,getContext:()=>context()});
  const sandbox={ASSETS:structuredClone(payload),D:null,console,Uint8Array,Math,Number,
    document:{createElement:canvas,getElementById:canvas,fonts:{load:()=>Promise.resolve([])}},
    b64bytes:s=>new Uint8Array(Buffer.from(s,'base64')),drawSprite:()=>{},palOf:()=>['#000','#777','#eee'],
    nameOf:m=>m.zh||m.slug};
  sandbox.D=sandbox.ASSETS;
  const start=source.indexOf("const cv = document.getElementById('sim-canvas')");
  const end=source.indexOf('\nfunction go(p){',start);
  assert(start>0&&end>start);
  vm.runInNewContext('const SP=ASSETS.simPages;\n'+source.slice(start,end)+`
    let records=[];
    const origText=text, origHp=gscHpBar, origExp=gscExpBar, origBar=bar, origBarD=barD, origSpr=spr;
    text=function(s,x,y,c){records.push({kind:'text',s,x,y,w:textW(s),h:16});return origText(s,x,y,c);};
    gscHpBar=function(x,y,p,side){records.push({kind:'hp',side,x,y,w:108,h:12});return origHp(x,y,p,side);};
    gscExpBar=function(x,y,p,f){records.push({kind:'exp',x,y,w:96,h:12});return origExp(x,y,p,f);};
    bar=function(x,y,w,h,...rest){records.push({kind:'bar',x,y,w,h});return origBar(x,y,w,h,...rest);};
    barD=function(x,y,w,h,...rest){records.push({kind:'bar',x,y,w,h});return origBarD(x,y,w,h,...rest);};
    spr=function(id,view,x,y,scale){records.push({kind:'sprite',id,view,x,y,scale});return origSpr(id,view,x,y,scale);};
    globalThis.api={
      run(page,dir,values={}){DIR=dir;st.page=page;Object.assign(st[page],values);records=[];PAGES[page].render();return records;},
      length(sc){return P3_timeline(sc).length;},
      shake(r,ph){return p3Shake(r,ph);},
      axisLabel(value){SP.care.axisNames[3]=value;},
      width(s){return textW(s);},
      palette(){return DIRS.base.pal;},
      hint(page){return SP.hints[page].line;},
      worstWild(){const sc=SP.battle.scenarios[1];D.mons[sc.wildSid-1].zh='多刺菊石兽';sc.wildLevel=100;
        sc.rounds.forEach(r=>{r.move='尖刺加农炮';r.damage=65535;});},
      stubs:SP.stubs,
    };
  `,sandbox);
  return sandbox.api;
}
const now=load(current), old=load(original), result={frames:0,pageStates:0};
const overlaps=(a,b)=>a.x<b.x+b.w&&b.x<a.x+a.w&&a.y<b.y+b.h&&b.y<a.y+a.h;
const texts=r=>r.filter(x=>x.kind==='text');
function checkBounds(rows,tag,bands=false){
  for(const r of rows){assert(r.x>=0&&r.y>=0&&r.x+r.w<=240&&r.y+r.h<=320,tag+': outside screen '+JSON.stringify(r));
    if(bands)assert(Math.floor(r.y/80)===Math.floor((r.y+r.h-1)/80),tag+': text crosses band '+JSON.stringify(r));}
}
function noTextOverlap(rows,tag){for(let i=0;i<rows.length;i++)for(let j=i+1;j<rows.length;j++)
  assert(!overlaps(rows[i],rows[j]),tag+': overlapping text '+JSON.stringify([rows[i],rows[j]]));}
for(const page of ['P0','P1','P2','P4','P5','P6','P7','P8'])for(const dir of ['base','G']){
  const r=now.run(page,dir);checkBounds(texts(r),page+'/'+dir);noTextOverlap(texts(r),page+'/'+dir);result.pageStates++;
}
for(const sc of ['win','lose'])for(const dir of ['base','G'])for(let fi=0;fi<now.length(sc);fi++){
  const rows=now.run('P3',dir,{sc,fi});checkBounds(texts(rows),'P3/'+dir+'/'+sc+'/'+fi,dir==='G');
  noTextOverlap(texts(rows),'P3/'+dir+'/'+sc+'/'+fi);result.frames++;
  if(dir==='G'){
    const hp=rows.find(r=>r.kind==='hp'&&r.side==='pet'), ex=rows.find(r=>r.kind==='exp');
    const number=rows.find(r=>r.kind==='text'&&/^\d+\/\d+$/.test(r.s));
    assert(hp.x+hp.w===number.x+number.w);
    if(ex)assert(hp.x+hp.w===ex.x+ex.w);
  }
}
// Worst supported strings exercise layout without selecting only the two short sample names.
now.worstWild();
for(let fi=0;fi<now.length('lose');fi++){
  const rows=texts(now.run('P3','G',{sc:'lose',fi}));checkBounds(rows,'P3/max strings',true);noTextOverlap(rows,'P3/max strings');
}
for(const dir of ['base','G']){
  now.axisLabel('今日行程'); const rows=now.run('P1',dir);
  const label=rows.find(r=>r.kind==='text'&&r.s==='今日行程');
  const bar=rows.filter(r=>r.kind==='bar')[3];assert(bar.x-label.x-label.w===8);
}
checkBounds(texts(now.run('P1','G')),'P1/G dynamic labels',true);
for(const [page,values] of [['P0',{done:true,skipped:true}],['P7',{}],['P8',{}]]){
  const rows=texts(now.run(page,'base',values));for(const r of rows)assert(r.x+r.w/2===120);
}
const capture=now.run('P4','G');assert(capture.find(r=>r.kind==='text'&&r.s===payload.mons[18].zh));
assert(capture.find(r=>r.kind==='sprite').id===19);
assert(now.width('é×')===32&&now.width('AB')===16);
assert(now.palette().field==='#ffff84');
assert(now.shake({attacker:'pet',missed:false},0)[0]!==0);
assert(now.shake({attacker:'wild',missed:false},0)[1]!==0);
assert(now.shake({attacker:'pet',missed:true},0).every(v=>v===0));
// Negative controls: read the original source independently, require the former defects to fail.
let oldBandFailure=false;try{checkBounds(texts(old.run('P3','G',{sc:'win',fi:0})),'old P3/G',true);}catch(e){oldBandFailure=true;}
assert(oldBandFailure);
const oldEnd=texts(old.run('P3','base',{sc:'lose',fi:old.length('lose')-1}));
assert(oldEnd.some((a,i)=>oldEnd.some((b,j)=>i!==j&&overlaps(a,b))));
assert(old.shake({attacker:'pet',missed:false},0)[0]===0);
const oldCapture=old.run('P4','G');assert(!oldCapture.find(r=>r.kind==='text'&&r.s===payload.mons[18].zh));
result.negativeControls=['old G text crosses band','old base result overlays round text','old shake is zero','old capture species mismatch'];
result.scope='actual JS layout and text-advance functions with a recording Canvas context; not browser or glyph pixels';
console.log(JSON.stringify(result,null,2));
