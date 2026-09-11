#!/usr/bin/env node
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(require('path').join(__dirname,'../inspector/moves.js'),'utf8');
const flush=()=>new Promise(setImmediate);
async function run(code=source){
 let now=0,interval,hold=false,pending;const calls=[],events={},nodes={};
 const node=id=>nodes[id]??=( {value:id==='move'?'57':id==='scope'?'all':id==='search'?'':'0',options:[],classList:{toggle(){}},replaceChildren(...v){this.options=v;this.value=v[0]?.value??'';},getContext:()=>({putImageData(){}})} );
 const catalog=[{id:57,name:'冲浪',type:2}];
 vm.runInNewContext(code,{document:{hidden:false,getElementById:node,addEventListener:(k,f)=>events[k]=f},performance:{now:()=>now},Option:function(t,v){this.value=String(v)},ImageData:function(){},decodeRGB565BE:()=>[],setInterval:f=>interval=f,
 fetch:async(url,o)=>{
  if(!o)return {ok:true,json:async()=>url==='move-catalog.json'?catalog:{moves:[]}};
  const q=JSON.parse(o.body);calls.push(q);
  if(hold)await new Promise(r=>pending=r);
  return {ok:true,arrayBuffer:async()=>new ArrayBuffer(0),headers:{get:k=>({'X-Preview-Animation-Frames':'100','X-Preview-Session':'test','X-Preview-Version':'fixture'})[k]}};
 }});
 await flush();await flush();
 now=45;hold=true;interval();await flush();assert.equal(calls.at(-1).frame,1);
 now=225;interval();await flush();hold=false;pending();await flush();
 now=270;interval();await flush();assert.equal(calls.at(-1).frame,6,'225ms request delay must advance five samples, not one');
 node('play').onclick();now+=5000;node('play').onclick();now+=45;interval();await flush();assert.equal(calls.at(-1).frame,7,'resume must exclude paused time');
 node('restart').onclick();await flush();assert.equal(calls.at(-1).frame,0);now+=45;interval();await flush();assert.equal(calls.at(-1).frame,1);
}
(async()=>{await run();await assert.rejects(()=>run(source.replace('frame=(frame+steps)%frameCount','frame=(frame+1)%frameCount')),/request delay/);console.log(JSON.stringify({passed:true,cases:['slow HTTP catch-up','pause/resume','restart'],negativeCaught:'one-frame-per-response'}));})().catch(e=>{console.error(e);process.exitCode=1});
