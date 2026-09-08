#!/usr/bin/env node
// Real production handlers, controlled press/release timing, delayed API replies.
const fs=require('fs'),path=require('path'),assert=require('assert'),crypto=require('crypto');
const {ready,flush}=require('./verify_firmware_clock');
const source=fs.readFileSync(path.join(__dirname,'../inspector/firmware.js'),'utf8');
const requests=h=>h.calls.filter(c=>c.action==='key').map(c=>[c.key,c.event]);
const holds=h=>[...h.timers.values()].filter(t=>t.delay===600);
const releasePointer=(h,key)=>{h.pointer(key,'pointerup');h.pointer(key,'lostpointercapture');h.pointer(key,'click');};
async function paused(code=source){const h=await ready(code);h.toggle();return h;}

async function pointerLong(code=source){
  const h=await paused(code);
  for(const key of [0,1]){
    h.pointer(key,'pointerdown');await flush();
    assert.strictEqual(holds(h).length,1,'real A/B press must arm a 600 ms hold');
    assert.strictEqual(requests(h).length,key,'pointer down must not pre-send a click');
    await h.advanceTimer(600);
    assert.deepStrictEqual(requests(h).at(-1),[key,3],'holding A/B must emit LONG without a dropdown change');
    await h.reply({page:'P10'});
    await h.advanceTimer(600); // No repeat on continued hold.
    releasePointer(h,key);await flush();
    assert.strictEqual(requests(h).length,key+1,'release click must not undo the long action');
    assert.strictEqual(h.timers.size,0);
  }
  return requests(h);
}

async function pointerClicks(){
  const h=await paused();
  for(const key of [0,1,2]){
    h.pointer(key,'pointerdown');releasePointer(h,key);await flush();
    assert.deepStrictEqual(requests(h).at(-1),[key,1]);await h.reply();
    await h.advanceTimer(600);assert.strictEqual(requests(h).length,key+1,'released timer generated a ghost long');
  }
  h.pointer(2,'pointerdown');await h.advanceTimer(600);
  assert.strictEqual(requests(h).length,3,'C must wait for the 1500 ms threshold');
  await h.advanceTimer(1500);
  assert.deepStrictEqual(requests(h).at(-1),[2,3],'C hold must switch the display off');
  await h.reply();releasePointer(h,2);await flush();
  assert.strictEqual(requests(h).length,4,'C release must not wake the display again');
  return requests(h);
}

async function keyboardLong(code=source){
  const h=await paused(code);
  h.keyEvent('keydown','B');h.keyEvent('keydown','B',{repeat:true});
  assert.strictEqual(holds(h).length,1,'keyboard repeat must not restart the hold timer');
  await h.advanceTimer(600);assert.deepStrictEqual(requests(h),[[1,3]]);
  await h.reply({page:'P10'});
  h.keyEvent('keydown','B',{repeat:true});await h.advanceTimer(600);
  h.keyEvent('keyup','B');h.keyEvent('keyup','B');await flush();
  assert.deepStrictEqual(requests(h),[[1,3]],'keyboard release must not click after a long press');
  h.key('b');await flush();assert.deepStrictEqual(requests(h),[[1,3],[1,1]]);await h.reply();
  assert.strictEqual(h.timers.size,0,'all held-key timers must be cleaned up');
}

async function explicitGesture(){
  const h=await paused();
  for(const event of [2,3]){
    h.nodes.gesture.value=String(event);
    h.pointer(1,'pointerdown');assert.strictEqual(holds(h).length,0);
    // Gesture selection is captured at press-down; changing it midway cannot
    // silently change a held gesture into a destructive different action.
    h.nodes.gesture.value='1';releasePointer(h,1);await flush();
    assert.deepStrictEqual(requests(h).at(-1),[1,event]);await h.reply();
    h.nodes.gesture.value=String(event);h.key('a');await flush();
    assert.deepStrictEqual(requests(h).at(-1),[0,event]);await h.reply();
  }
  assert.strictEqual(requests(h).length,4,'dropdown long/double must send exactly once per activation');
}

async function cancelPending(code=source){
  const h=await paused(code);
  for(const event of ['pointercancel','lostpointercapture']){
    h.pointer(1,'pointerdown');h.pointer(1,event);await h.advanceTimer(600);
    releasePointer(h,1);await flush();assert.deepStrictEqual(requests(h),[],`${event} leaked a key`);
  }
  h.keyEvent('keydown','a');h.blur();await h.advanceTimer(600);h.keyEvent('keyup','a');await flush();
  assert.deepStrictEqual(requests(h),[],'window blur leaked a hold');
  h.pointer(1,'pointerdown');h.keyEvent('keydown','a');h.visibility(true);await h.advanceTimer(600);
  h.visibility(false);releasePointer(h,1);h.keyEvent('keyup','a');await flush();
  assert.deepStrictEqual(requests(h),[],'hidden page retained an unfinished hold');
  assert.strictEqual(h.timers.size,0);
  h.key('b');await flush();assert.deepStrictEqual(requests(h),[[1,1]]);await h.reply();
}

async function ignoredInput(){
  const h=await paused();
  h.pointer(1,'pointerdown',{button:2});releasePointer(h,1);
  h.pointer(1,'pointerdown',{isPrimary:false});releasePointer(h,1);
  for(const target of [{tagName:'INPUT'},{tagName:'SELECT'},{tagName:'TEXTAREA'},{tagName:'DIV',isContentEditable:true}]){
    h.keyEvent('keydown','b',{target});h.keyEvent('keyup','b',{target});
  }
  for(const modifier of ['ctrlKey','altKey','metaKey']){
    h.keyEvent('keydown','a',{[modifier]:true});h.keyEvent('keyup','a');
  }
  await h.advanceTimer(600);await flush();assert.deepStrictEqual(requests(h),[]);
}

async function queuedHold(code=source){
  const h=await ready(code);await h.tick();
  h.pointer(1,'pointerdown');await h.advanceTimer(600);releasePointer(h,1);
  h.key('a');h.nodes.gesture.value='3';h.key('b');h.toggle();await flush();
  assert.deepStrictEqual(requests(h),[],'keys must queue behind the in-flight frame');
  await h.reply({session:'after-tick'});
  for(const [key,event,session] of [[1,3,'after-hold'],[0,1,'after-click'],[1,3,'after-explicit']]){
    assert.deepStrictEqual(requests(h).at(-1),[key,event]);await h.reply({session,page:'P10'});
  }
  assert.deepStrictEqual(requests(h),[[1,3],[0,1],[1,3]],'queued hold/release must keep every input exactly once');
  assert.deepStrictEqual(h.calls.filter(c=>c.action==='key').map(c=>c.session),['after-tick','after-hold','after-click']);
  assert.strictEqual(h.maxInFlight,1);assert.strictEqual(h.timers.size,0);
}

async function main(){
  const header=fs.readFileSync(path.join(__dirname,'../../firmware/components/bsp/include/bsp_button.h'),'utf8');
  assert.strictEqual(Number(header.match(/#define BSP_BTN_LONG_PRESS_MS (\d+)/)[1]),600,'web/BSP hold thresholds diverged');
  const cases=[pointerLong,pointerClicks,keyboardLong,explicitGesture,cancelPending,ignoredInput,queuedHold];
  for(const run of cases)await run();
  const mutations=[
    ['click after long release','if(commit&&!held.long)','if(commit)',pointerLong,/release click must not undo/],
    ['native click double dispatch','if(e.detail===0)','if(true)',pointerLong,/release click must not undo/],
    ['missing keyboard hold',"beginKey(`keyboard:${key}`,key);","send('key',{key,event:1});",keyboardLong,/keyboard repeat must not restart/],
    ['cancelled hold fires','heldKeys.delete(id);clearTimeout(held.timer);','/* negative: keep cancelled hold */',cancelPending,/leaked a key/],
  ];
  for(const [name,before,after,run,error] of mutations){
    assert.strictEqual(source.split(before).length,2,`negative ${name} target changed`);
    await assert.rejects(()=>run(source.replace(before,after)),error,`negative ${name} was not detected`);
  }
  const evidence={sourceSha256:crypto.createHash('sha256').update(source).digest('hex'),
    passed:cases.map(run=>run.name),negativeCaught:mutations.map(([name])=>name),
    scope:'actual firmware.js pointer/keyboard handlers in Node VM, controlled hold timers and delayed fetch; browser event delivery is checked separately'};
  const index=process.argv.indexOf('--evidence');
  if(index>=0){fs.mkdirSync(path.dirname(process.argv[index+1]),{recursive:true});fs.writeFileSync(process.argv[index+1],JSON.stringify(evidence,null,2)+'\n');}
  console.log(JSON.stringify(evidence,null,2));
}
if(require.main===module)main().catch(error=>{console.error(error);process.exitCode=1;});
module.exports=main;
