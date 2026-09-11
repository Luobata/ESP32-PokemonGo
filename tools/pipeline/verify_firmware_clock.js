#!/usr/bin/env node
// Exercise the production UI with delayed responses and a controlled clock.
// C navigation/transition pixels are checked separately by the native gate.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert'),crypto=require('crypto');
const source=fs.readFileSync(path.join(__dirname,'../inspector/firmware.js'),'utf8');
const flush=()=>new Promise(setImmediate);

function harness(code=source,savedNameStyle=null,storageBlocked=false,hash=''){
  const nodes={},keys=[],events={},documentEvents={},calls=[],pending=[],timers=new Map();
  const storage=new Map(savedNameStyle===null?[]:[['pokewalk.nameStyle.v1',savedNameStyle]]);
  let nextTimer=0,inFlight=0,maxInFlight=0,now=0;
  for(const id of ['firmware-canvas','play','page','pet','level','wild','rarity','seed','shiny',
    'reset','step','check','gesture','bands','guides','zoom','screen-wrap','download','status','clock-state','names','team']){
    nodes[id]={value:'0',dataset:{},style:{},disabled:false,attributes:{},reportValidity:()=>true,
      setAttribute(k,v){this.attributes[k]=v;}};
  }
  for(const [k,v] of Object.entries({page:'2',pet:'25',level:'12',wild:'74',rarity:'3',seed:'1',gesture:'1',team:'1'}))nodes[k].value=v;
  for(let i=0;i<3;i++)keys.push({dataset:{key:String(i)},style:{},disabled:false,setPointerCapture(){}});
  const listen=(events,name,fn)=>(events[name]??=[]).push(fn);
  const dispatch=(events,name,event={})=>{for(const fn of events[name]??[])fn(event);};
  nodes['firmware-canvas'].getContext=()=>({putImageData(){}});
  const document={hidden:false,getElementById:id=>nodes[id],querySelector:()=>({clientWidth:600}),
    querySelectorAll:s=>s==='[data-key]'?keys:s==='input[type=number]'?[]:[],
    addEventListener:(name,fn)=>listen(documentEvents,name,fn)};
  vm.runInNewContext(code,{
    performance:{now:()=>now},document,window:{addEventListener:(name,fn)=>listen(events,name,fn)},innerHeight:900,innerWidth:1000,location:{hash},
    localStorage:{getItem(key){if(storageBlocked)throw Error('storage disabled');return storage.get(key)??null;},
      setItem(key,value){if(storageBlocked)throw Error('storage disabled');storage.set(key,value);}},
    setTimeout:(fn,delay)=>{const id=++nextTimer;timers.set(id,{fn,delay});return id;},
    clearTimeout:id=>timers.delete(id),AbortController,ImageData:function(){},
    decodeRGB565BE:()=>new Uint8ClampedArray(240*320*4),
    fetch:async(url,options)=>{
      const request=JSON.parse(options.body);calls.push(request);
      inFlight++;maxInFlight=Math.max(maxInFlight,inFlight);
      return new Promise(resolve=>pending.push({request,resolve}));
    },
  });
  const clockTimers=()=>[...timers].filter(([,timer])=>timer.delay===60);
  return {nodes,keys,calls,pending,timers,clockTimers,storage,
    elapse(ms){now+=ms;},
    get maxInFlight(){return maxInFlight;},
    async reply({session='fixture-session',ms=0,page='P2',mismatch=-1,names='0'}={}){
      const response=pending.shift();assert(response,'expected an in-flight request');inFlight--;
      response.resolve({ok:true,arrayBuffer:async()=>new ArrayBuffer(153600),headers:{get:key=>({
        'X-Preview-Session':session,'X-Preview-Page':page,'X-Preview-Ms':String(ms),
        'X-Preview-Mismatch':String(mismatch),'X-Preview-Version':'clock-probe',
        'X-Preview-Names':names,
      })[key]}});
      await flush();
    },
    async tick(){
      const scheduled=clockTimers();assert.strictEqual(scheduled.length,1,'one automatic clock timer required');
      now+=60;timers.delete(scheduled[0][0]);scheduled[0][1].fn();await flush();
    },
    keyEvent(name,key,extra={}){dispatch(events,name,{repeat:false,target:{tagName:'BODY'},key,preventDefault(){},...extra});},
    // Clock tests use accessible single activation; physical sequences have their own gate.
    key(key){keys['abc'.indexOf(key.toLowerCase())].onclick({detail:0});},
    pointer(key,name,extra={}){keys[key]['on'+name]({button:0,isPrimary:true,pointerId:key+1,detail:1,preventDefault(){},...extra});},
    async advanceTimer(delay){
      const scheduled=[...timers].filter(([,timer])=>timer.delay===delay);
      for(const [id,timer] of scheduled){timers.delete(id);timer.fn();}await flush();
    },
    visibility(hidden){document.hidden=hidden;dispatch(documentEvents,'visibilitychange');},
    blur(){dispatch(events,'blur');},
    toggle(){nodes.play.onclick();},
  };
}

async function ready(code=source){
  const h=harness(code);await flush();
  assert.deepStrictEqual(h.calls.map(c=>c.action),['reset']);
  assert.strictEqual(h.clockTimers().length,0,'clock must wait for the initial scene');
  await h.reply();
  return h;
}

async function defaultClock(code=source){
  const h=await ready(code);
  assert.strictEqual(h.clockTimers().length,1,'default clock must advance without clicking Play');
  assert.strictEqual(h.nodes.play.textContent,'暂停');
  await h.tick();
  assert.deepStrictEqual(h.calls.map(c=>c.action),['reset','tick']);
  assert.strictEqual(h.calls[1].session,'fixture-session');
  assert.strictEqual(h.calls[1].ms,60);
  await h.reply({ms:60});
  await h.tick();await h.reply({ms:120});
  h.toggle();assert.strictEqual(h.clockTimers().length,0);
}

async function inputQueue(){
  const h=await ready();await h.tick();
  for(const key of ['a','b','c'])h.key(key);
  await flush();assert.strictEqual(h.calls.length,2,'keys must wait for the in-flight tick');
  assert(h.keys.every(key=>!key.disabled),'A/B/C must remain usable');
  assert.strictEqual(h.nodes.play.disabled,false);
  h.toggle();assert.strictEqual(h.nodes.play.textContent,'继续运行');
  await h.reply({session:'after-tick',ms:60});
  for(const [index,session,page] of [[0,'after-A','P3'],[1,'after-B','P3'],[2,'after-C','P2']]){
    assert.strictEqual(h.calls.at(-1).key,index);
    assert.strictEqual(h.calls.at(-1).session,index===0?'after-tick':index===1?'after-A':'after-B');
    await h.reply({session,ms:60,page});
  }
  assert.deepStrictEqual(h.calls.map(c=>c.action),['reset','tick','key','key','key']);
  assert.strictEqual(h.maxInFlight,1,'all commands must serialize');
  assert.strictEqual(h.timers.size,0,'paused clock must not append a tick after inputs finish');
}

async function queuedTickCancellation(code=source){
  const h=await ready(code);h.key('a');await flush();
  await h.tick(); // The automatic tick waits behind A's response.
  h.toggle();await h.reply();
  assert.deepStrictEqual(h.calls.map(c=>c.action),['reset','key'],'paused queued tick must expire');
  assert.strictEqual(h.timers.size,0);
}

async function resumedQueuedTick(code=source){
  const h=await ready(code);h.key('a');await flush();await h.tick();
  h.toggle();h.toggle();await h.reply();
  assert.deepStrictEqual(h.calls.map(c=>c.action),['reset','key'],'resumed clock must discard the previous epoch tick');
  assert.strictEqual(h.clockTimers().length,1);
  await h.tick();await h.reply({ms:60});h.toggle();
}

async function rapidResume(code=source){
  const h=await ready(code);await h.tick();
  for(let i=0;i<8;i++){h.toggle();h.toggle();}
  assert.strictEqual(h.clockTimers().length,0,'resuming an active pump must not schedule a second pump');
  await h.reply({ms:60});
  assert.strictEqual(h.clockTimers().length,1,'old pump must hand off to exactly one timer');
  await h.tick();
  for(let i=0;i<8;i++){h.toggle();h.toggle();}
  await h.reply({ms:120});
  assert.strictEqual(h.clockTimers().length,1);
  assert.strictEqual(h.maxInFlight,1);
  h.toggle();
}

async function pausedSceneAndSingleStep(){
  const h=await ready();h.toggle();
  h.nodes.page.value='4';h.nodes.page.onchange();await flush();
  assert.strictEqual(h.calls.at(-1).action,'reset');await h.reply({page:'P4'});
  h.nodes.reset.onclick();await flush();await h.reply({session:'reset-while-paused',page:'P4'});
  assert.strictEqual(h.nodes.play.textContent,'继续运行','scene changes must preserve explicit pause');
  assert.strictEqual(h.clockTimers().length,0);
  h.key('a');await flush();await h.reply({page:'P4'});
  assert.strictEqual(h.clockTimers().length,0,'a key must not override explicit pause');
  h.nodes.step.onclick();h.nodes.check.onclick();await flush();
  assert.strictEqual(h.calls.at(-1).action,'tick');await h.reply({ms:60,page:'P4'});
  assert.strictEqual(h.calls.at(-1).action,'check');await h.reply({ms:60,page:'P4',mismatch:0});
  assert.deepStrictEqual(h.calls.map(c=>c.action),['reset','reset','reset','key','tick','check']);
  assert.strictEqual(h.timers.size,0,'step/check must not restart the clock');
  for(const action of ['step','check']){
    h.toggle();assert.strictEqual(h.clockTimers().length,1);
    h.nodes[action].onclick();await flush();
    assert.strictEqual(h.clockTimers().length,0,`${action} must explicitly pause a running clock`);
    await h.reply({page:'P4'});assert.strictEqual(h.timers.size,0);
  }
}

async function hiddenClock(){
  const h=await ready();h.visibility(true);
  assert.strictEqual(h.clockTimers().length,0);
  assert.strictEqual(h.nodes['clock-state'].dataset.state,'hidden');
  assert.strictEqual(h.nodes.play.textContent,'暂停','visibility must not change user intent');
  h.visibility(false);assert.strictEqual(h.clockTimers().length,1);
  await h.tick();
  for(let i=0;i<8;i++){h.visibility(true);h.visibility(false);}
  assert.strictEqual(h.clockTimers().length,0,'visibility must not duplicate an active pump');
  await h.reply({ms:60});assert.strictEqual(h.clockTimers().length,1);
  h.toggle();h.visibility(true);h.visibility(false);
  assert.strictEqual(h.clockTimers().length,0,'returning to a paused page must stay paused');
  assert.strictEqual(h.nodes['clock-state'].dataset.state,'paused');
}

async function activeSceneChanges(){
  const h=await ready();await h.tick();
  h.nodes.reset.onclick();h.nodes.page.value='3';h.nodes.page.onchange();
  h.key('b');h.toggle();h.toggle();await flush();
  assert.strictEqual(h.calls.length,2,'scene changes and B must queue behind the active tick');
  await h.reply({ms:60});assert.strictEqual(h.calls.at(-1).action,'reset');
  assert.strictEqual(h.clockTimers().length,0);
  await h.reply({session:'new-scene'});assert.strictEqual(h.calls.at(-1).action,'reset');
  assert.strictEqual(h.clockTimers().length,0,'wait for every queued scene change');
  await h.reply({session:'after-page',page:'P3'});
  assert.strictEqual(h.calls.at(-1).action,'key');assert.strictEqual(h.calls.at(-1).session,'after-page');
  await h.reply({page:'P3'});
  assert.strictEqual(h.clockTimers().length,1,'running intent must survive reset/page changes');
  await h.tick();await h.reply({ms:60,page:'P3'});h.toggle();
  assert.deepStrictEqual(h.calls.map(c=>c.action),['reset','tick','reset','reset','key','tick']);
  assert.strictEqual(h.maxInFlight,1);
  assert.strictEqual(h.timers.size,0);
}

async function freshSceneSelection(code=source){
  const h=await ready(code);await h.tick();
  h.nodes.page.value='9';h.nodes.page.onchange();await flush();
  // A stale in-flight page reply must not overwrite the requested scene.
  await h.reply({page:'P2',ms:60});
  assert.strictEqual(h.calls.at(-1).action,'reset','selector must start a fresh fixture');
  assert.strictEqual(h.calls.at(-1).page,9,'in-flight navigation lost the selected scene');
  assert.strictEqual(h.calls.at(-1).pet,25);
  await h.reply({session:'new-starter',page:'P9'});
  h.key('a');await flush();
  assert.strictEqual(h.calls.at(-1).session,'new-starter');
  await h.reply({page:'P1'});h.toggle();
}

async function savedNamePreference(){
  const h=harness(source,'1');await flush();
  assert.strictEqual(h.calls[0].names,1,'saved names must be sent in the first fixture');
  await h.reply({names:'1'});h.toggle();
  h.nodes.page.value='9';h.nodes.page.onchange();await flush();
  assert.strictEqual(h.calls.at(-1).names,1,'a fresh fixture must preserve the name preference');
  await h.reply({page:'P9',names:'1'});
  assert.strictEqual(h.nodes.names.value,'1');
  const reopened=harness(source,h.storage.get('pokewalk.nameStyle.v1'));await flush();
  assert.strictEqual(reopened.calls[0].names,1,'reopening must use the acknowledged preference');
  await reopened.reply({names:'1'});reopened.toggle();
  for(const [saved,blocked] of [['invalid',false],['1',true]]){
    const fallback=harness(source,saved,blocked);await flush();
    assert.strictEqual(fallback.calls[0].names,0,'invalid/unavailable storage must use official names');
    await fallback.reply();fallback.toggle();
  }
}

async function queuedNamePreference(){
  const h=await ready();await h.tick();
  h.nodes.names.value='1';h.nodes.names.onchange();h.toggle();await flush();
  assert.strictEqual(h.calls.length,2,'name switch must wait for the in-flight frame');
  await h.reply({ms:60,names:'0'});
  assert.strictEqual(h.nodes.names.value,'1','stale frame must not overwrite the requested names');
  assert.strictEqual(h.calls.at(-1).action,'names');assert.strictEqual(h.calls.at(-1).style,1);
  await h.reply({ms:60,names:'1'});
  assert.strictEqual(h.nodes.names.value,'1');
  assert.strictEqual(h.storage.get('pokewalk.nameStyle.v1'),'1');
  assert.strictEqual(h.clockTimers().length,0);
  h.nodes.reset.onclick();await flush();
  assert.strictEqual(h.calls.at(-1).names,1);await h.reply({names:'1'});
  assert.strictEqual(h.maxInFlight,1);
}

async function hardwareNamePreference(){
  const h=await ready();h.toggle();h.nodes.gesture.value='3';h.key('a');await flush();
  assert.strictEqual(h.calls.at(-1).event,3);
  await h.reply({page:'P5',names:'1'});
  assert.strictEqual(h.nodes.names.value,'1','hardware long A must update the selector');
  assert.strictEqual(h.storage.get('pokewalk.nameStyle.v1'),'1');
  h.nodes.page.value='3';h.nodes.page.onchange();await flush();
  assert.strictEqual(h.calls.at(-1).names,1);await h.reply({page:'P3',names:'1'});
}

async function bagScene(){
  const h=harness(source,'1',false,'#P10');await flush();
  assert.strictEqual(h.calls[0].page,10,'P10 hash must load the bag fixture');
  assert.strictEqual(h.calls[0].names,1);await h.reply({page:'P10',names:'1'});h.toggle();
  assert.strictEqual(h.nodes.page.value,'10','two-digit page number must survive the response');
  h.nodes.gesture.value='3';h.key('b');await flush();
  assert.strictEqual(h.calls.at(-1).key,1);assert.strictEqual(h.calls.at(-1).event,3);
  await h.reply({page:'P10',names:'1'});
  h.nodes.page.value='5';h.nodes.page.onchange();await flush();
  assert.strictEqual(h.calls.at(-1).page,5);await h.reply({page:'P5',names:'1'});
}

async function delayedClock(){
 const h=await ready();await h.tick();assert.strictEqual(h.calls.at(-1).ms,60);
 h.elapse(180);await h.reply();await h.tick();assert.strictEqual(h.calls.at(-1).ms,240,'request latency must not slow simulation time');
 await h.reply();h.toggle();h.elapse(5000);h.toggle();await h.tick();assert.strictEqual(h.calls.at(-1).ms,60,'paused time must not catch up');
 await h.reply();h.toggle();
}
async function main(){
  const cases=[delayedClock,defaultClock,inputQueue,queuedTickCancellation,resumedQueuedTick,rapidResume,pausedSceneAndSingleStep,hiddenClock,activeSceneChanges,freshSceneSelection,savedNamePreference,queuedNamePreference,hardwareNamePreference,bagScene];
  for(const run of cases)await run();
  const mutations=[
    ['default pause','paused=false','paused=true',defaultClock,/default clock must advance/],
    ['stale queued tick','()=>epoch===clockEpoch&&canRun()','()=>true',queuedTickCancellation,/paused queued tick must expire/],
    ['stale resumed epoch','()=>epoch===clockEpoch&&canRun()','()=>canRun()',resumedQueuedTick,/must discard the previous epoch tick/],
    ['duplicate pump','!canRun()||pumpActive||timer!==null','!canRun()||timer!==null',rapidResume,/must not schedule a second pump/],
    ['stale encounter scene',"$('page').onchange=reset;","$('page').onchange=()=>changeScene('page',{page:Number($('page').value)});",freshSceneSelection,/selector must start a fresh fixture/],
  ];
  for(const [name,before,after,run,error] of mutations){
    assert.strictEqual(source.split(before).length,2,`negative ${name} target changed`);
    await assert.rejects(()=>run(source.replace(before,after)),error,`negative ${name} was not detected`);
  }
  console.log(JSON.stringify({sourceSha256:crypto.createHash('sha256').update(source).digest('hex'),
    passed:cases.map(run=>run.name),negativeCaught:mutations.map(([name])=>name),
    scope:'actual firmware.js in Node VM; delayed fetch, input order, visibility and clock scheduling'},null,2));
}
module.exports=main;
module.exports.harness=harness;
module.exports.ready=ready;
module.exports.flush=flush;
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
