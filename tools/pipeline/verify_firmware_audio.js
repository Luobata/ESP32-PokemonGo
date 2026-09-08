// Web Audio is mocked: this test never opens an output device.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
(async()=>{
const nodes={'audio-toggle':{setAttribute(){}},'audio-state':{},'firmware-canvas':{dataset:{session:'one',screenOff:'false'}},'clock-state':{dataset:{state:'running'}}};
let created=0,requests=0,started=0,stopped=0,callback,resolveFetch;
const listeners={},timers=new Map();let id=0;
class AudioContext {constructor(){created++;this.currentTime=0;this.destination={};}async resume(){}async suspend(){}async close(){}createBuffer(){return {duration:.16,getChannelData:()=>new Float32Array(3528)}}createBufferSource(){return {connect(){},start(){started++},stop(){stopped++}}}}
const document={hidden:false,getElementById:k=>nodes[k],addEventListener:(k,v)=>listeners[k]=v};
const ctx={document,window:{addEventListener:(k,v)=>listeners[k]=v},AudioContext,AbortController,DataView,Float32Array,Set,setTimeout:(fn,ms)=>{timers.set(++id,{fn,ms});return id},clearTimeout:id=>timers.delete(id),fetch:()=>{requests++;return new Promise(r=>resolveFetch=r)}};
vm.runInNewContext(fs.readFileSync(require('path').join(__dirname,'../inspector/firmware-audio.js'),'utf8'),ctx);
const flush=async()=>{for(let i=0;i<5;i++)await Promise.resolve()};
async function pump(){const entry=[...timers].find(([i,x])=>x.ms===40);assert(entry);timers.delete(entry[0]);entry[1].fn();await flush()}
async function reply(){resolveFetch({ok:true,arrayBuffer:async()=>new ArrayBuffer(7056)});await flush()}
assert.strictEqual(created,0);assert.strictEqual(requests,0);
await nodes['audio-toggle'].onclick();assert.strictEqual(created,1);await pump();assert.strictEqual(requests,1);await reply();assert.strictEqual(started,1);
// Hidden page stops buffered audio, and never fetches more PCM until visible.
document.hidden=true;listeners.visibilitychange();assert.strictEqual(stopped,1);await pump();assert.strictEqual(requests,1);
document.hidden=false;listeners.visibilitychange();await pump();nodes['firmware-canvas'].dataset.session='two';await reply();assert.strictEqual(started,1);
await pump();await reply();assert.strictEqual(started,2);
nodes['firmware-canvas'].dataset.screenOff='true';await pump();assert.strictEqual(stopped,2);
nodes['firmware-canvas'].dataset.screenOff='false';await pump();await nodes['audio-toggle'].onclick();await reply();assert.strictEqual(started,2);
assert.strictEqual(nodes['audio-toggle'].textContent,'开启试听');console.log(JSON.stringify({opt_in:true,hidden_mute:true,sleep_mute:true,stale_session_dropped:true,disabled_response_dropped:true,real_audio_devices:0}));
})().catch(e=>{console.error(e);process.exitCode=1});
