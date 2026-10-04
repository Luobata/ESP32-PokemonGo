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
