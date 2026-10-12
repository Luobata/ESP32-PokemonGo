export const SIZE = 24576;
export const EXTENDED_SIZE = 49152;
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
    if(p[1]==='ERROR'){
      if(p[2]==='STAGE'){
        const reasons={LAYOUT:'设备分区布局不支持导入',FLASH:'存档暂存区写入失败',
          NVS:'暂存存档无法挂载或关闭',MEMORY:'设备可用内存不足，请重启设备后重试',
          READ:'无法读取备份中的游戏存档',VERSION:'备份声明版本与实际存档版本不一致',
          CONTENT:'存档数据校验未通过，请保留原备份',CHECKPOINT:'设备当前进度保存失败',
          JOURNAL:'导入恢复日志写入或校验失败'};
        const detail=Object.hasOwn(reasons,p[3])?reasons[p[3]]:null;
        throw Error(detail?`${detail}（STAGE ${p[3]}），原存档未替换`:'存档内容不兼容或暂存失败，原存档未替换');
      }
      throw Error(({TIMEOUT:'操作超时，当前存档未覆盖，请重新连接',SNAPSHOT:'当前存档备份失败，未开始导入',OPEN_IMPORT:'请先在设备打开「选项 → 导入存档」',BUSY:'设备正在进行另一项操作',INCOMPATIBLE:'备份不属于此设备或存档版本不兼容；请更新设备固件',MEMORY:'设备内存不足，请稍后重试',CHECKSUM:'导入校验失败，原存档未替换',SEQUENCE:'导入数据顺序错误'})[p[2]]||'设备拒绝导入');
    }
    if(p[1]==='OFFERED'&&p.length===2)return {offered:true};
    if(p[1]==='CANCELLED'&&p.length===2)return {cancelled:true};
    if(p[1]==='UPLOAD'&&p.length===3&&/^[0-9]+$/.test(p[2]))return {upload:p[2]};
    if(p[1]==='NEXT'&&p.length===4&&/^[0-9]+$/.test(p[2])&&/^[0-9]+$/.test(p[3]))return {next:{id:p[2],offset:Number(p[3])}};
    if(p[1]==='STAGED'&&p.length===3&&/^[a-f0-9]{8}$/.test(p[2]))return {staged:p[2]};
    if(p[1]==='RESTORED'&&p.length===5&&p[2]===this.session&&/^[123]$/.test(p[3])&&/^[a-f0-9]{8}$/.test(p[4]))return {restored:{result:Number(p[3]),crc:p[4]}};
    if(p[1]==='BEGIN') {
      if(p.length!==10||p[2]!==this.session||this.pending) throw Error('备份开始信息无效');
      const [, , , id, device, firmware, version, address, size, crc]=p;
      if(!/^[1-9][0-9]{0,9}$/.test(id)||!(/^[a-f0-9]{12}$/.test(device))||
         !/^[a-f0-9]{64}$/.test(firmware)||(!/^[1-9][0-9]{0,4}$/.test(version)||!validSaveVersion(Number(version)))||address!=='36864'||!([SIZE,EXTENDED_SIZE].includes(Number(size)))||!(/^[a-f0-9]{8}$/.test(crc))) throw Error('设备或备份协议不支持');
      this.pending={id,device,firmware,version:Number(version),crc,bytes:new Uint8Array(Number(size)),offset:0};
      return {progress:0};
    }
    const q=this.pending;
    if(!q) return null;
    if(p[1]==='DATA') {
      if(p.length!==5||p[2]!==q.id||p[3]!==String(q.offset)||!(/^[a-f0-9]{256}$/.test(p[4]))||q.offset+128>q.bytes.length) throw Error('备份数据缺失或顺序错误');
      for(let i=0;i<128;i++) q.bytes[q.offset+i]=parseInt(p[4].slice(i*2,i*2+2),16);
      q.offset+=128;return {progress:q.offset/q.bytes.length};
    }
    if(p[1]==='END') {
      if(p.length!==4||p[2]!==q.id||p[3]!==q.crc||q.offset!==q.bytes.length||crc32(q.bytes)!==q.crc) throw Error('备份完整性校验失败');
      this.pending=null;return {complete:q};
    }
    throw Error('未知备份消息');
  }
}
export async function envelope(q, cryptoAPI=globalThis.crypto) {
  const digest=await cryptoAPI.subtle.digest('SHA-256',q.bytes);
  return {format:'pokewalk-nvs-backup',format_version:q.bytes.length===EXTENDED_SIZE?2:1,created_at:new Date().toISOString(),
    chip:'esp32c3',device_id:q.device,firmware:q.firmware,save_version:q.version,
    nvs_offset:36864,nvs_size:SIZE,crc32:q.crc,
    ...(q.bytes.length===EXTENDED_SIZE?{payload_size:EXTENDED_SIZE,store_offset:0x380000,store_partition_size:0x20000,store_record_size:SIZE}:{}),
    sha256:Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join(''),
    payload_base64:btoa(String.fromCharCode(...q.bytes))};
}

export async function decodeBackup(text,cryptoAPI=globalThis.crypto) {
  if(typeof text!=='string'||text.length>90000)throw Error('备份文件过大或无效');
  const d=JSON.parse(text);
  if(d.format!=='pokewalk-nvs-backup'||![1,2].includes(d.format_version)||d.chip!=='esp32c3'||!validSaveVersion(d.save_version)||d.nvs_offset!==36864||d.nvs_size!==SIZE||
     !/^[a-f0-9]{12}$/.test(d.device_id)||!/^[a-f0-9]{64}$/.test(d.firmware)||!/^[a-f0-9]{64}$/.test(d.sha256)||!/^[a-f0-9]{8}$/.test(d.crc32)||
     typeof d.payload_base64!=='string'||!/^[A-Za-z0-9+/=]+$/.test(d.payload_base64))throw Error('备份格式或版本不支持');
  const extended=d.format_version===2;
  if(extended&&(d.save_version<23||d.payload_size!==EXTENDED_SIZE||d.store_offset!==0x380000||d.store_partition_size!==0x20000||d.store_record_size!==SIZE))throw Error('扩展存档分区布局不支持');
  const bytes=Uint8Array.from(atob(d.payload_base64),c=>c.charCodeAt(0));
  if(bytes.length!==(extended?EXTENDED_SIZE:SIZE)||crc32(bytes)!==d.crc32)throw Error('备份长度或 CRC 校验失败');
  const digest=await cryptoAPI.subtle.digest('SHA-256',bytes);
  const sha=Array.from(new Uint8Array(digest),b=>b.toString(16).padStart(2,'0')).join('');
  if(sha!==d.sha256)throw Error('备份 SHA-256 校验失败');
  return {metadata:d,bytes};
}
