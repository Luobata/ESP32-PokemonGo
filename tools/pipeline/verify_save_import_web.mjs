// Execute the production web import's pre-overwrite backup flow in a DOM/FS seam.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {webcrypto} from 'node:crypto';
import {Receiver,envelope,decodeBackup,SIZE,EXTENDED_SIZE,EXPANDED_SIZE,WAREHOUSE_SIZE,crc32} from '../save-manager/web/backup.mjs';
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
for(const version of [5,16,17,20,21,22]){
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

// Extended STAGE errors remain compatible with old firmware and keep their
// useful diagnosis when production readLoop disconnects after a rejection.
const stageLoop=new (Object.getPrototypeOf(async function(){}).constructor)('Receiver','envelope','decodeBackup','SIZE','detail',source+`
 session='0123456789abcdef0123456789abcdef';receiver=new Receiver(session);device='001122334455';
 transfer={file:{metadata:{crc32:'abcdef01',device_id:device}}};
 reader={async read(){return {done:false,value:new TextEncoder().encode('!PWBACKUP ERROR STAGE'+detail+'\\n')};},releaseLock(){}};
 await readLoop();return {text:$('status').textContent,pending:expectedRestore};
`);
for(const [code,message] of Object.entries({LAYOUT:'分区布局',FLASH:'暂存区写入',NVS:'挂载或关闭',MEMORY:'可用内存不足',READ:'无法读取',VERSION:'实际存档版本不一致',CONTENT:'数据校验未通过',CHECKPOINT:'当前进度保存失败',JOURNAL:'恢复日志'})){
 const rx=new Receiver('session');
 assert.throws(()=>rx.accept(`!PWBACKUP ERROR STAGE ${code}`),new RegExp(message));
 memory.clear();const result=await stageLoop(Receiver,envelope,decodeBackup,SIZE,' '+code);
 assert.match(result.text,new RegExp(`STAGE ${code}`));assert.match(result.text,/原存档未替换/);
 assert.doesNotMatch(result.text,/导入完成|设备正在重启/);assert.equal(result.pending,null);assert.equal(memory.size,0);
}
for(const detail of ['', ' FUTURE_REASON', ' constructor', ' __proto__']){
 const rx=new Receiver('session');
 assert.throws(()=>rx.accept('!PWBACKUP ERROR STAGE'+detail),/存档内容不兼容或暂存失败，原存档未替换/);
}
console.log('detailed stage errors, legacy/unknown fallback and production disconnect handling: passed');

// V23 wire transfer and backup format 2 contain both NVS and the referenced bank.
for(const [length,version] of [[WAREHOUSE_SIZE,28],[WAREHOUSE_SIZE,65535],[EXTENDED_SIZE,23],[EXTENDED_SIZE,24],[EXTENDED_SIZE,65535],[EXPANDED_SIZE,24],[EXPANDED_SIZE,25],[EXPANDED_SIZE,26],[EXPANDED_SIZE,65535]]){
 const payload=Uint8Array.from({length},(_,i)=>(i*37+i/256)&255);
 const hash=crc32(payload),rx=new Receiver('v23');
 rx.accept(`!PWBACKUP BEGIN v23 2 001122334455 ${'a'.repeat(64)} ${version} 36864 ${payload.length} ${hash}`);
 for(let offset=0;offset<payload.length;offset+=128){
  const hex=Buffer.from(payload.slice(offset,offset+128)).toString('hex');
  const result=rx.accept(`!PWBACKUP DATA 2 ${offset} ${hex}`);
  assert.equal(result.progress,(offset+128)/payload.length);
 }
 const q=rx.accept(`!PWBACKUP END 2 ${hash}`).complete;
 const encoded=await envelope(q),decoded=await decodeBackup(JSON.stringify(encoded));
 assert.equal(encoded.format_version,length===WAREHOUSE_SIZE?4:length===EXPANDED_SIZE?3:2);assert.deepEqual(decoded.bytes,payload);
 for(const [field,value] of [['store_offset',0x390000],['store_partition_size',0x10000],['store_record_size',123],['payload_size',SIZE],['format_version',1],['save_version',length===WAREHOUSE_SIZE?27:length===EXPANDED_SIZE?23:22],['sha256','0'.repeat(64)],['crc32','0'.repeat(8)]])
  await assert.rejects(()=>decodeBackup(JSON.stringify({...encoded,[field]:value})));
 let saved='';const fixture={sent:[],directory:{async queryPermission(){return 'granted';},async getFileHandle(){return {async createWritable(){return {async write(text){saved=text;},async close(){}};},async getFile(){return {async text(){return saved;}};}};}}};
 const result=await run(Receiver,envelope,decodeBackup,SIZE,fixture,q,{device_id:q.device,save_version:22});
 assert(result.backedUp);assert.match(fixture.sent[0],/ ACK /);
 assert.deepEqual((await decodeBackup(saved)).bytes,payload);
}
console.log('formats 2/3/4, full 48/56/72 KiB transfer/prebackup, future schemas and partition/digest rejection: passed');
