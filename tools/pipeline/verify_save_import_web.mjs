// Execute the production web import's pre-overwrite backup flow in a DOM/FS seam.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {Receiver,envelope,decodeBackup,SIZE,crc32} from '../save-manager/web/backup.mjs';
const nodes=new Map();
globalThis.document={getElementById(id){if(!nodes.has(id))nodes.set(id,{classList:{toggle(){}},prepend(){}});return nodes.get(id);},createElement(){return {};}};
globalThis.window={showDirectoryPicker(){}};
globalThis.isSecureContext=true;
Object.defineProperty(globalThis,'navigator',{value:{serial:{}},configurable:true});
Object.defineProperty(globalThis,'crypto',{value:webcrypto,configurable:true});
const source=readFileSync(new URL('../save-manager/web/app.mjs',import.meta.url),'utf8').replace(/^import[^\n]*\n/,'');
const run=new (Object.getPrototypeOf(async function(){}).constructor)('Receiver','envelope','decodeBackup','SIZE','fixture','q','metadata',source+`
 directory=fixture.directory;writer={write:async bytes=>fixture.sent.push(new TextDecoder().decode(bytes))};
 session='0123456789abcdef0123456789abcdef';transfer={file:{metadata}};
 await save(q);return transfer;
`);
const bytes=new Uint8Array(SIZE);const current={id:'1',device:'001122334455',firmware:'2'.repeat(64),version:17,crc:crc32(bytes),bytes};
for(const version of [5,16,17]){
 let saved='';const fixture={sent:[],directory:{async queryPermission(){return 'granted';},async getFileHandle(){return {async createWritable(){return {async write(text){saved=text;},async close(){},async abort(){}};},async getFile(){return {async text(){return saved;}};}};}}};
 const transfer=await run(Receiver,envelope,decodeBackup,SIZE,fixture,current,{device_id:current.device,firmware:'1'.repeat(64),save_version:version});
 assert(transfer.backedUp);assert.equal(fixture.sent.length,1);assert.match(fixture.sent[0],/ ACK .* 1/);
 const file=await decodeBackup(saved);assert.equal(file.metadata.firmware,current.firmware);assert.equal(file.metadata.save_version,17);
}
for(const fail of ['device','permission','write','readback']){
 let saved='';let created=false;
 const fixture={sent:[],directory:{async queryPermission(){return fail==='permission'?'denied':'granted';},async getFileHandle(){created=true;return {async createWritable(){return {async write(text){if(fail==='write')throw Error('disk full');saved=text;},async close(){},async abort(){}};},async getFile(){return {async text(){return fail==='readback'?'corrupt':saved;}};}};}}};
 await assert.rejects(()=>run(Receiver,envelope,decodeBackup,SIZE,fixture,current,{device_id:fail==='device'?'f'.repeat(12):current.device,firmware:'1'.repeat(64),save_version:17}));
 assert.equal(fixture.sent.length,1);assert.match(fixture.sent[0],/ FAIL .* 1/);
 if(fail==='device'||fail==='permission')assert(!created);
}
console.log('web cross-build prebackup ACK, current metadata, wrong-device/write/permission/readback rejection: passed');

// Exercise production receipt handling, not just its parser or prebackup helper.
const receipts=new (Object.getPrototypeOf(async function(){}).constructor)('Receiver','envelope','decodeBackup','SIZE','scenario',source+`
 session='0123456789abcdef0123456789abcdef';receiver=new Receiver(session);
 await line('!PWBACKUP READY '+session+' 001122334455');
 if(scenario==='historical'){
   await line('!PWBACKUP RESTORED '+session+' 1 abcdef01');
   return $('status').textContent;
 }
 if(scenario!=='reload'){
   transfer={file:{metadata:{crc32:'abcdef01',device_id:'001122334455'}}};
   await line('!PWBACKUP STAGED abcdef01');
 }
 if(scenario==='staged')return expectedRestore;
 if(scenario==='mismatch')await line('!PWBACKUP RESTORED '+session+' 1 12345678');
 else if(scenario==='wrong-device'){
   await line('!PWBACKUP READY '+session+' ffffffffffff');
   await line('!PWBACKUP RESTORED '+session+' 1 abcdef01');
 }else await line('!PWBACKUP RESTORED '+session+' '+(scenario==='rollback'?2:scenario==='load-error'?3:1)+' abcdef01');
 return {text:$('status').textContent,pending:expectedRestore};
`);
const memory=new Map();globalThis.sessionStorage={getItem:k=>memory.get(k)||null,setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
const invoke=scenario=>receipts(Receiver,envelope,decodeBackup,SIZE,scenario);
assert.doesNotMatch(await invoke('historical'),/导入完成/);
for(const scenario of ['success','rollback','load-error']){
 memory.clear();const result=await invoke(scenario);assert.equal(result.pending,null);
 assert.match(result.text,scenario==='success'?/导入完成/:scenario==='rollback'?/已恢复覆盖前/:/读档失败/);
 if(scenario!=='success')assert.doesNotMatch(result.text,/导入完成/);
}
for(const scenario of ['mismatch','wrong-device']){
 memory.clear();await assert.rejects(()=>invoke(scenario),/不匹配/);assert(memory.size);
}
memory.clear();await invoke('staged');assert(memory.size);
assert.match((await invoke('reload')).text,/导入完成/);assert.equal(memory.size,0);
assert.doesNotMatch(await invoke('historical'),/导入完成/);
console.log('production web receipt correlation, stale receipts, mismatch, rollback, load failure and reload: passed');
const loop=new (Object.getPrototypeOf(async function(){}).constructor)('Receiver','envelope','decodeBackup','SIZE',source+`
 session='0123456789abcdef0123456789abcdef';receiver=new Receiver(session);device='001122334455';
 rememberRestore({crc:'abcdef01',device});
 reader={async read(){return {done:false,value:new TextEncoder().encode('!PWBACKUP RESTORED '+session+' 1 12345678\\n')};},releaseLock(){}};
 await readLoop();return $('status').textContent;
`);
memory.clear();
const error=await loop(Receiver,envelope,decodeBackup,SIZE);
assert.match(error,/不匹配/);assert.match(error,/尚未确认/);assert.doesNotMatch(error,/设备正在重启/);
console.log('production read loop preserves mismatched-restore error across disconnect: passed');
