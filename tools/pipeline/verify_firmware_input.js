#!/usr/bin/env node
// Execute production browser handlers, preserving the complete hardware gesture.
const fs=require('fs'),path=require('path'),assert=require('assert');
const {ready,flush}=require('./verify_firmware_clock');
const source=fs.readFileSync(path.join(__dirname,'../inspector/firmware.js'),'utf8');
const keys=h=>h.calls.filter(c=>c.action==='key').map(c=>[c.key,c.event]);
async function drain(h){await flush();while(h.pending.length)await h.reply();}
async function paused(code=source){const h=await ready(code);h.toggle();return h;}
async function clicks(){
 const h=await paused();
 for(let key=0;key<3;key++){
  h.pointer(key,'pointerdown');await drain(h);
  assert.deepStrictEqual(keys(h).at(-1),[key,0],'PRESS must arrive before release (instant throw)');
  h.pointer(key,'pointerup');h.pointer(key,'lostpointercapture');h.pointer(key,'click');await drain(h);
  assert.deepStrictEqual(keys(h).slice(-4),[[key,0],[key,4],[key,1],[key,5]],'one complete click gesture');
 }
 await h.advanceTimer(600);await h.advanceTimer(1500);await drain(h);
 assert.strictEqual(keys(h).length,12,'released timers cannot create ghost holds');
}
async function returnHold(code=source){
 const h=await paused(code);
 h.pointer(1,'pointerdown');await drain(h);
 await h.advanceTimer(600);await drain(h);
 assert.deepStrictEqual(keys(h),[[1,0],[1,3]]);
 await h.advanceTimer(600);h.pointer(1,'pointerup');h.pointer(1,'click');await drain(h);
 assert.deepStrictEqual(keys(h),[[1,0],[1,3],[1,4],[1,5]],'long return must not also select next row');
}
async function keyboard(){
 const h=await paused();
 for(const [name,key] of [['ArrowUp',0],['ArrowDown',1],['Enter',2]]){
  h.keyEvent('keydown',name);h.keyEvent('keydown',name,{repeat:true});await drain(h);
  h.keyEvent('keyup',name);await drain(h);
  assert.deepStrictEqual(keys(h).slice(-4),[[key,0],[key,4],[key,1],[key,5]]);
 }
 h.keyEvent('keydown','ArrowDown');await drain(h);await h.advanceTimer(600);await drain(h);
 h.keyEvent('keyup','ArrowDown');await drain(h);
 assert.deepStrictEqual(keys(h).slice(-4),[[1,0],[1,3],[1,4],[1,5]]);
 h.keyEvent('keydown','c');await drain(h);await h.advanceTimer(1500);await drain(h);
 h.keyEvent('keyup','c');await drain(h);
 assert.deepStrictEqual(keys(h).slice(-4),[[2,0],[2,3],[2,4],[2,5]],'existing long-confirm screen-off remains available');
}
async function cancellation(){
 const h=await paused();
 for(const cause of ['pointercancel','lostpointercapture']){
  h.pointer(1,'pointerdown');await drain(h);h.pointer(1,cause);await drain(h);
  await h.advanceTimer(600);await drain(h);
  assert.deepStrictEqual(keys(h).slice(-3),[[1,0],[1,4],[1,5]],'cancel must release hardware state without navigation');
 }
 h.keyEvent('keydown','ArrowDown');await drain(h);h.blur();await drain(h);
 await h.advanceTimer(600);await drain(h);
 assert.deepStrictEqual(keys(h).slice(-3),[[1,0],[1,4],[1,5]]);
 h.pointer(1,'pointerdown');await drain(h);h.visibility(true);await drain(h);
 assert.deepStrictEqual(keys(h).slice(-3),[[1,0],[1,4],[1,5]]);
 assert.strictEqual(h.timers.size,0);
}
async function queue(){
 const h=await ready();await h.tick();
 h.pointer(1,'pointerdown');await h.advanceTimer(600);h.pointer(1,'pointerup');h.toggle();
 await flush();assert.deepStrictEqual(keys(h),[]);
 await h.reply({session:'after-tick'});await drain(h);
 assert.deepStrictEqual(keys(h),[[1,0],[1,3],[1,4],[1,5]]);
 assert.strictEqual(h.maxInFlight,1,'all lifecycle events must serialize with rendering');
}
async function explicitAndIgnored(){
 const h=await paused();
 for(const event of [2,3]){
  h.nodes.gesture.value=String(event);h.pointer(1,'pointerdown');h.pointer(1,'pointerup');await drain(h);
  assert.deepStrictEqual(keys(h).at(-1),[1,event]);
 }
 const before=keys(h).length;
 for(const target of [{tagName:'INPUT'},{tagName:'SELECT'},{tagName:'TEXTAREA'},{tagName:'DIV',isContentEditable:true}]){
  h.keyEvent('keydown','ArrowDown',{target});h.keyEvent('keyup','ArrowDown',{target});
 }
 h.pointer(1,'pointerdown',{button:2});h.pointer(1,'pointerup');await drain(h);
 assert.strictEqual(keys(h).length,before);
}
async function main(){
 const cases=[clicks,returnHold,keyboard,cancellation,queue,explicitAndIgnored];
 for(const test of cases)await test();
 assert(source.includes('if(commit&&!held.long)'));
 await assert.rejects(()=>returnHold(source.replace('if(commit&&!held.long)','if(commit)')),/long return/);
 const result={passed:cases.map(f=>f.name),negativeCaught:['click after long return'],scope:'production firmware.js, complete PRESS/RELEASE/CLICK/LONG/END events and queued responses'};
 const i=process.argv.indexOf('--evidence');if(i>=0){fs.mkdirSync(path.dirname(process.argv[i+1]),{recursive:true});fs.writeFileSync(process.argv[i+1],JSON.stringify(result,null,2)+'\n');}
 console.log(JSON.stringify(result));
}
if(require.main===module)main().catch(e=>{console.error(e);process.exitCode=1;});
module.exports=main;
