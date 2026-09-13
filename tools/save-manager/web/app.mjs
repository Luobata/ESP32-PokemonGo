import {Receiver,envelope,decodeBackup,SIZE} from './backup.mjs';
const $=id=>document.getElementById(id);
let directory,port,reader,writer,heartbeat,session,receiver,connected=false,writeQueue=Promise.resolve(),closing=false;
let selectedImport=null,transfer=null,expectedRestore=null,device=null;
function status(text,error=false){$('status').textContent=text;$('status').classList.toggle('error',error);}
function send(text){const bytes=new TextEncoder().encode(text+'\n');writeQueue=writeQueue.then(()=>writer.write(bytes));return writeQueue;}
function controls(){
 $('connect').disabled=!directory||!!port;$('disconnect').disabled=!port;$('folder').disabled=!!port;
 $('import').disabled=!connected||!selectedImport||!!transfer||!!expectedRestore||!!receiver?.pending;
 $('import-file').disabled=!!transfer||!!receiver?.pending;
}
async function save(q){
  try {
    if(await directory.queryPermission({mode:'readwrite'})!=='granted')throw Error('目录写入授权已失效，请重新连接');
    if(transfer&&(transfer.file.metadata.device_id!==q.device||transfer.file.metadata.firmware!==q.firmware))throw Error('当前设备与待导入文件不匹配');
    status(transfer?'正在保存覆盖前的当前存档…':'校验通过，正在保存文件…');
    const data=await envelope(q);
    const name=`PokeWalk-${transfer?'before-import-':''}${data.created_at.replace(/[:.]/g,'-')}-${crypto.randomUUID()}.pksave`;
    const file=await directory.getFileHandle(name,{create:true});let stream;
    try { stream=await file.createWritable();await stream.write(JSON.stringify(data,null,2)+'\n');await stream.close(); }
    catch(e){if(stream)await stream.abort().catch(()=>{});throw e;}
    if((await (await file.getFile()).text())!==JSON.stringify(data,null,2)+'\n')throw Error('保存后回读校验失败');
    const item=document.createElement('li');item.textContent=name;$('files').prepend(item);
    if(transfer){transfer.id=q.id;transfer.offset=0;transfer.backedUp=true;}
    await send(`!PWBACKUP ACK ${session} ${q.id}`);
    status(transfer?'当前存档已备份，准备传送导入文件…':'备份已保存。请确认设备显示“备份完成”。');
  }catch(e){await send(`!PWBACKUP FAIL ${session} ${q.id}`).catch(()=>{});throw e;}
}
async function nextChunk(id,offset){
  const t=transfer;
  if(!t?.backedUp||id!==t.id||offset!==t.offset||offset>SIZE)throw Error('导入接收状态不匹配');
  if(offset===SIZE){await send(`!PWBACKUP RFIN ${session} ${id}`);status('传送完成，设备正在校验并暂存…');return;}
  const hex=Array.from(t.file.bytes.slice(offset,offset+128),b=>b.toString(16).padStart(2,'0')).join('');
  t.offset+=128;
  await send(`!PWBACKUP RDATA ${session} ${id} ${offset} ${hex}`);
  $('progress').value=t.offset/SIZE;status(`正在导入 ${Math.round(t.offset/SIZE*100)}%`);
}
async function line(text){
  const result=receiver.accept(text);
  if(result?.ready){connected=true;device=result.ready;$('connection').textContent='设备已连接';status(expectedRestore?'已重新连接，等待导入结果…':'可以在设备上备份，或打开「导入存档」后发送文件。');}
  if(result?.offered)status('请在设备上选择「确认覆盖」并按 C；默认选中取消。');
  if(result?.cancelled){transfer=null;status('已取消导入，当前存档未覆盖。');}
  if(result?.progress!==undefined){$('progress').value=result.progress;status(`${transfer?'备份当前存档':'正在接收'} ${Math.round(result.progress*100)}%`);}
  if(result?.complete)await save(result.complete);
  if(result?.upload)await nextChunk(result.upload,0);
  if(result?.next)await nextChunk(result.next.id,result.next.offset);
  if(result?.staged){
    if(!transfer||result.staged!==transfer.file.metadata.crc32)throw Error('设备暂存确认不匹配');
    expectedRestore={crc:result.staged,device:transfer.file.metadata.device_id};transfer=null;connected=false;
    status('文件已暂存，等待设备重启并核对结果；若 USB 断开，请重新连接。');
  }
  if(result?.restored){
    if(expectedRestore&&(expectedRestore.device!==device||expectedRestore.crc!==result.restored.crc))throw Error('重启后的导入结果不匹配');
    status(result.restored.result===1?'设备已确认：存档导入完成。':'导入写入失败，设备已恢复覆盖前的存档。',result.restored.result!==1);expectedRestore=null;
  }
  controls();
}
async function readLoop(){
  const decoder=new TextDecoder();let buffer='';
  try {
    while(true){
      const {value,done}=await reader.read();if(done)break;
      buffer+=decoder.decode(value,{stream:true});let index;
      while((index=buffer.indexOf('\n'))>=0){const text=buffer.slice(0,index).replace(/\r$/,'');buffer=buffer.slice(index+1);await line(text);}
      if(buffer.length>4096)throw Error('串口数据格式异常，请断开后重试');
    }
    if(!closing&&!expectedRestore)throw Error('USB 连接已断开，未确认的操作不算完成');
  }catch(e){if(!closing)status(expectedRestore?'设备正在重启，请重新连接核对结果。':e.message,!expectedRestore);}
  finally{reader.releaseLock();reader=null;transfer=null;await cleanup();}
}
async function cleanup(){
  clearInterval(heartbeat);heartbeat=null;connected=false;device=null;
  if(writer){try{await writeQueue;}catch{}try{writer.releaseLock();}catch{}writer=null;}
  if(port){try{await port.close();}catch{}port=null;}
  $('connection').textContent='已断开';controls();
}
$('folder').onclick=async()=>{try{directory=await showDirectoryPicker({id:'pokewalk-saves',mode:'readwrite'});$('directory').textContent=directory.name;controls();}catch(e){if(e.name!=='AbortError')status(e.message,true);}};
$('connect').onclick=async()=>{
  try {
    closing=false;writeQueue=Promise.resolve();
    port=await navigator.serial.requestPort({filters:[{usbVendorId:0x303a,usbProductId:0x1001}]});controls();
    await port.open({baudRate:115200,bufferSize:65536});
    writer=port.writable.getWriter();reader=port.readable.getReader();
    session=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');receiver=new Receiver(session);
    void readLoop();await send(`!PWBACKUP HELLO ${session}`);status('等待设备响应…');
    heartbeat=setInterval(()=>{send(`!PWBACKUP ${connected?'PING':'HELLO'} ${session}`).catch(e=>{status(e.message,true);void reader?.cancel();});},4000);
  }catch(e){status(e.name==='NotFoundError'?'未选择设备。':e.message,true);if(reader)await reader.cancel();else await cleanup();}
};
$('disconnect').onclick=async()=>{
  closing=true;clearInterval(heartbeat);try{await send(`!PWBACKUP BYE ${session}`);}catch{}
  if(reader)await reader.cancel();else await cleanup();
  status(expectedRestore?'设备已接收导入文件；重新连接核对结果。':'已断开。已保存到目录的备份仍然保留。');
};
$('import-file').onchange=async()=>{
  selectedImport=null;controls();
  try{const file=$('import-file').files[0];if(!file)return;
    if(file.size>45000)throw Error('备份文件过大');selectedImport=await decodeBackup(await file.text());
    $('import-info').textContent=`${file.name} · 校验通过 · 存档 V${selectedImport.metadata.save_version}`;
  }catch(e){$('import-info').textContent=e.message;status(e.message,true);}controls();
};
$('import').onclick=async()=>{
  if(!connected||!selectedImport||transfer)return;
  try {
    const d=selectedImport.metadata;if(d.device_id!==device)throw Error('备份不属于当前设备');
    if(await directory.queryPermission({mode:'readwrite'})!=='granted')throw Error('请重新选择有写入权限的备份目录');
    expectedRestore=null;transfer={file:selectedImport};controls();
    await send(`!PWBACKUP OFFER ${session} ${d.device_id} ${d.firmware} ${d.save_version} ${d.nvs_size} ${d.crc32}`);
    status('等待设备确认导入请求…');
  }catch(e){transfer=null;status(e.message,true);controls();}
};
if(!isSecureContext||!navigator.serial||!window.showDirectoryPicker){$('folder').disabled=true;status('请使用桌面 Chrome / Edge，通过 HTTPS 或 localhost 打开本页。',true);}
