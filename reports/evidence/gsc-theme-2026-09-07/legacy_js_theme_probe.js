const fs=require('fs'), vm=require('vm'), assert=require('assert'), cp=require('child_process');
const html=fs.readFileSync('tools/inspector/index.html','utf8');
const payload=JSON.parse(html.match(/const D = (.*);\n/)[1]);
const current=fs.readFileSync('tools/inspector/template.html','utf8');
const old=cp.execFileSync('git',['show','HEAD:tools/inspector/template.html'],{encoding:'utf8'});
// Read current FRNT independently so an older generated payload cannot hide a
// source-size change. The payload supplies only the historical sim fixtures.
const front=fs.readFileSync('assets/gen1_front.bin'), frontSizes={};
assert.equal(front.toString('ascii',0,4),'FRNT');
const segments=front.readUInt16LE(6),frontBase=8+segments*12;
payload.front={};
for(let segment=0;segment<segments;segment++){
  const header=8+segment*12,size=front.readUInt16LE(header),per=front.readUInt16LE(header+2),n=front.readUInt32LE(header+4);
  let at=frontBase+front.readUInt32LE(header+8);assert.equal(per,size*size/4);frontSizes[size]=n;
  for(let i=0;i<n;i++){const sid=front.readUInt16LE(at);at+=2;assert(sid>=1&&sid<=151&&!payload.front[sid]);
    payload.front[sid]=front.subarray(at,at+per).toString('base64');payload.mons[sid-1].fsize=size;at+=per;}
  assert(at<=front.length);
}
assert.equal(Object.keys(payload.front).length,151);
const asset=fs.readFileSync('assets/gen1_back.bin');
assert.equal(asset.toString('ascii',0,4),'BACK');
const actualSize=asset.readUInt16LE(6),stride=asset.readUInt16LE(10),count=asset.readUInt32LE(12);
assert.equal(count,151);assert.equal(stride,actualSize*actualSize/4);assert.equal(asset.length,16+151*stride);
const sources=[{name:'actual assets',size:actualSize,back:Object.fromEntries(Array.from({length:151},(_,i)=>[i+1,asset.subarray(16+i*stride,16+(i+1)*stride).toString('base64')]))}];
for(const size of [32,48]){
  if(size===actualSize)continue;
  const bytes=Buffer.alloc(size*size/4,255);bytes[0]=0x3f;bytes[bytes.length-1]=0xfc;
  sources.push({name:'explicit full-bounds size fixture',size,back:Object.fromEntries(Array.from({length:151},(_,i)=>[i+1,bytes.toString('base64')]))});
}
function load(source,fixture){
  const data=structuredClone(payload);data.meta.backSize=fixture.size;data.back=structuredClone(fixture.back);
  const decoded=[],images=[];
  const canvas=()=>{const c={width:240,height:320};const target={};target.drawImage=(img,...args)=>images.push({sourceSize:img.width,args,smoothing:target.imageSmoothingEnabled});
    const ctx=new Proxy(target,{get:(o,k)=>k in o?o[k]:(...args)=>{},set:(o,k,v)=>(o[k]=v,true)});c.getContext=()=>ctx;return c;};
  const sandbox={ASSETS:data,D:data,console,Math,Number,Uint8Array,decoded,images,
    document:{createElement:canvas,getElementById:canvas,fonts:{load:()=>Promise.resolve([])}},
    b64bytes:s=>new Uint8Array(Buffer.from(s,'base64')),
    drawSprite:(ctx,bytes,size,x,y,scale)=>{assert.equal(bytes.length,size*size/4);decoded.push({size,bytes:bytes.length,scale,x,y});},
    palOf:()=>['#000','#777','#eee'],nameOf:m=>m.zh||m.slug};
  const start=source.indexOf("const cv = document.getElementById('sim-canvas')");
  const end=source.indexOf('\nfunction go(p){',start);assert(start>0&&end>start);
  vm.runInNewContext('const SP=ASSETS.simPages;\n'+source.slice(start,end)+`
    let records=[];
    const originalSpr=spr,originalNN=sprNN;
    spr=function(id,view,x,y,scale){records.push({id,view,x,y,dest:(view==='back'?D.meta.backSize:D.mons[id-1].fsize)*scale,method:'spr'});return originalSpr(id,view,x,y,scale);};
    sprNN=function(id,view,x,y,dest,sil){records.push({id,view,x,y,dest,sil,method:'sprNN'});return originalNN(id,view,x,y,dest,sil);};
    globalThis.api={
      run(page,dir,values={},z='96',alt=false){DIR=dir;st.page=page;P3GSZ=z;P3SKEL=alt?'alt':'std';Object.assign(st[page],values);records=[];decoded.length=0;images.length=0;PAGES[page].render();return structuredResult();},
      pet(id){SP.care.pet.sid=id;},
      dex(state){dexState=()=>state;},
      palette(dir){return DIRS[dir].pal;},
      charge(attacker,id){records=[];decoded.length=0;images.length=0;fxOverlay({charge:true},{attacker,missed:false},0,{x:16,y:112,s:96},{x:120,y:40,s:112},id);return structuredResult();},
      water(dest){records=[];decoded.length=0;images.length=0;sprWater(25,'back',16,112,dest,5);return structuredResult();},
      corrupt(){const saved=D.back[25];D.back[25]=saved.slice(4);try{sprNN(25,'back',0,0,96);}finally{D.back[25]=saved;}},
    };
    function structuredResult(){return {records:records.slice(),decoded:decoded.slice(),images:images.slice()};}
  `,sandbox);
  return sandbox.api;
}
const dirs=['base','A','B','C','G'];
const result={frontSourceSizeCounts:frontSizes,sourceFixtures:[],p1States:0,p3States:0,p5States:0,p6States:0,p6FrontThumbnails:0,chargeCases:0,waterCases:0,negativeControls:[]};
for(const fixture of sources){
  const api=load(current,fixture);result.sourceFixtures.push({name:fixture.name,size:fixture.size,species:151});
  for(const dir of ['base','G']){const p=api.palette(dir);assert.equal(p.field,'#ffffff');assert.equal(p.ink,'#000000');assert.equal(p.dim,'#6b696b');}
  for(let id=1;id<=151;id++)for(const dir of dirs){
    api.pet(id);let r=api.run('P1',dir).records.filter(x=>x.view==='back');assert.equal(r.length,1);assert.equal(r[0].dest,96);result.p1States++;
    r=api.run('P5',dir).records;assert.equal(r.length,1);assert.equal(r[0].view,'front');assert.equal(r[0].dest,payload.mons[id-1].fsize*2);
    assert(r[0].x>=120&&r[0].x+r[0].dest<=232&&r[0].y>=54&&r[0].y+r[0].dest<=166);result.p5States++;
  }
  for(const dir of ['base','A','B','C'])for(const alt of [false,true]){
    const r=api.run('P3',dir,{sc:'win',fi:0},'96',alt).records.find(x=>x.view==='back');assert(r);assert.equal(r.dest,alt?64:dir==='base'?96:64);result.p3States++;
  }
  for(const z of ['48','96']){const r=api.run('P3','G',{sc:'win',fi:0},z).records.find(x=>x.view==='back');assert(r);assert.equal(r.dest,+z);result.p3States++;}
  for(const state of ['unseen','seen','caught','shiny'])for(const dir of dirs)for(let pg=0;pg<8;pg++){
    api.dex(state);const r=api.run('P6',dir,{pg}).records;
    assert.equal(r.length,state==='unseen'?0:Math.min(20,151-pg*20));
    for(const row of r){assert.equal(row.view,'front');assert.equal(row.dest,32);assert.equal(row.method,'sprNN');if(state==='seen')assert(row.sil);result.p6FrontThumbnails++;}result.p6States++;
  }
  for(const attacker of ['pet','wild'])for(const id of [19,74,150]){const r=api.charge(attacker,id).records;assert.equal(r.length,1);assert.equal(r[0].view,attacker==='pet'?'back':'front');assert.equal(r[0].dest,attacker==='pet'?96:112);result.chargeCases++;}
  for(const dest of [48,96]){const r=api.water(dest);assert.equal(r.decoded.length,1);assert.equal(r.decoded[0].size,fixture.size);assert.equal(r.decoded[0].scale,1);assert.equal(r.images[0].sourceSize,fixture.size);assert.equal(r.images[0].args[2],dest);assert.equal(r.images[0].smoothing,false);result.waterCases++;}
  assert.throws(()=>api.corrupt(),/sprite 字节数与源尺寸不符/);
}
const size48=sources.find(x=>x.size===48);const previous=load(old,size48);
const previousBack=previous.run('P1','base').records.find(x=>x.view==='back');assert.equal(previousBack.dest,144);
result.negativeControls=['old P1 back 48 × scale3 grows to 144px','mismatched sprite bytes/size throws instead of drawing'];
result.scope='Actual template functions in Node VM with recording Canvas; source/target dimensions and text palette checks, no browser raster parity claim.';
fs.writeFileSync('reports/evidence/gsc-theme-2026-09-07/legacy-js-check.json',JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result,null,2));
