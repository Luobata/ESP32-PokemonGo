export const SIZE = 24576;
// save_version describes opaque game data, not the backup protocol. Preserve
// future uint16 schema versions without teaching this tool the game's layout.
// Import eligibility still belongs to the device/firmware compatibility checks.
export function validSaveVersion(version) {
  return Number.isInteger(version) && version >= 1 && version <= 0xffff;
}
export function crc32(bytes) {
  let c = 0xffffffff;
  for (const b of bytes) { c ^= b; for(let i=0;i<8;i++) c=(c>>>1)^((c&1)?0xedb88320:0); }
  return ((c^0xffffffff)>>>0).toString(16).padStart(8,'0');
}
export class Receiver {
  constructor(session) { this.session=session; this.pending=null; }
  accept(line) {
    if(!line.startsWith('!PWBACKUP ')) return null;
    const p=line.trim().split(/\s+/);
    if(p[1]==='READY') return p.length===4&&p[2]===this.session?{ready:p[3]}:null;
    if(p[1]==='ERROR')throw Error(({TIMEOUT:'操作超时，当前存档未覆盖，请重新连接',SNAPSHOT:'当前存档备份失败，未开始导入',OPEN_IMPORT:'请先在设备打开「选项 → 导入存档」',BUSY:'设备正在进行另一项操作',INCOMPATIBLE:'备份不属于此设备或固件构建不兼容',MEMORY:'设备内存不足，请稍后重试',CHECKSUM:'导入校验失败，原存档未替换',STAGE:'暂存失败，原存档未替换',SEQUENCE:'导入数据顺序错误'})[p[2]]||'设备拒绝导入');
    if(p[1]==='OFFERED'&&p.length===2)return {offered:true};
    if(p[1]==='CANCELLED'&&p.length===2)return {cancelled:true};
    if(p[1]==='UPLOAD'&&p.length===3&&/^[0-9]+$/.test(p[2]))return {upload:p[2]};
    if(p[1]==='NEXT'&&p.length===4&&/^[0-9]+$/.test(p[2])&&/^[0-9]+$/.test(p[3]))return {next:{id:p[2],offset:Number(p[3])}};
    if(p[1]==='STAGED'&&p.length===3&&/^[a-f0-9]{8}$/.test(p[2]))return {staged:p[2]};
    if(p[1]==='RESTORED'&&p.length===5&&p[2]===this.session&&/^[12]$/.test(p[3])&&/^[a-f0-9]{8}$/.test(p[4]))return {restored:{result:Number(p[3]),crc:p[4]}};
    if(p[1]==='BEGIN') {
      if(p.length!==10||p[2]!==this.session||this.pending) throw Error('备份开始信息无效');
      const [, , , id, device, firmware, version, address, size, crc]=p;
      if(!/^[1-9][0-9]{0,9}$/.test(id)||!(/^[a-f0-9]{12}$/.test(device))||
         !/^[a-f0-9]{64}$/.test(firmware)||(!/^[1-9][0-9]{0,4}$/.test(version)||!validSaveVersion(Number(version)))||address!=='36864'||size!=='24576'||!(/^[a-f0-9]{8}$/.test(crc))) throw Error('设备或备份协议不支持');
      this.pending={id,device,firmware,version:Number(version),crc,bytes:new Uint8Array(SIZE),offset:0};
      return {progress:0};
    }
    const q=this.pending;
    if(!q) return null;
    if(p[1]==='DATA') {
      if(p.length!==5||p[2]!==q.id||p[3]!==String(q.offset)||!(/^[a-f0-9]{256}$/.test(p[4]))||q.offset+128>SIZE) throw Error('备份数据缺失或顺序错误');
      for(let i=0;i<128;i++) q.bytes[q.offset+i]=parseInt(p[4].slice(i*2,i*2+2),16);
      q.offset+=128;return {progress:q.offset/SIZE};
    }
    if(p[1]==='END') {
      if(p.length!==4||p[2]!==q.id||p[3]!==q.crc||q.offset!==SIZE||crc32(q.bytes)!==q.crc) throw Error('备份完整性校验失败');
      this.pending=null;return {complete:q};
    }
    throw Error('未知备份消息');
  }
}
export async function envelope(q, cryptoAPI=globalThis.crypto) {
  const digest=await cryptoAPI.subtle.digest('SHA-256',q.bytes);
  return {format:'pokewalk-nvs-backup',format_version:1,created_at:new Date().toISOString(),
    chip:'esp32c3',device_id:q.device,firmware:q.firmware,save_version:q.version,
    nvs_offset:36864,nvs_size:SIZE,crc32:q.crc,
    sha256:Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join(''),
    payload_base64:btoa(String.fromCharCode(...q.bytes))};
}

export async function decodeBackup(text,cryptoAPI=globalThis.crypto) {
  if(typeof text!=='string'||text.length>45000)throw Error('备份文件过大或无效');
  const d=JSON.parse(text);
  if(d.format!=='pokewalk-nvs-backup'||d.format_version!==1||d.chip!=='esp32c3'||!validSaveVersion(d.save_version)||d.nvs_offset!==36864||d.nvs_size!==SIZE||
     !/^[a-f0-9]{12}$/.test(d.device_id)||!/^[a-f0-9]{64}$/.test(d.firmware)||!/^[a-f0-9]{64}$/.test(d.sha256)||!/^[a-f0-9]{8}$/.test(d.crc32)||
     typeof d.payload_base64!=='string'||!/^[A-Za-z0-9+/=]+$/.test(d.payload_base64))throw Error('备份格式或版本不支持');
  const bytes=Uint8Array.from(atob(d.payload_base64),c=>c.charCodeAt(0));
  if(bytes.length!==SIZE||crc32(bytes)!==d.crc32)throw Error('备份长度或 CRC 校验失败');
  const digest=await cryptoAPI.subtle.digest('SHA-256',bytes);
  const sha=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
  if(sha!==d.sha256)throw Error('备份 SHA-256 校验失败');
  return {metadata:d,bytes};
}
