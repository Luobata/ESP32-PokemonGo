/* Decode the real LCD wire format only; no text, geometry or asset logic here. */
(function(root){
  function decodeRGB565BE(bytes){
    if(bytes.length!==240*320*2) throw new Error('固件像素帧长度不正确');
    const rgba=new Uint8ClampedArray(240*320*4);
    for(let i=0,j=0;i<bytes.length;i+=2,j+=4){
      const v=(bytes[i]<<8)|bytes[i+1],r=(v>>11)&31,g=(v>>5)&63,b=v&31;
      rgba[j]=(r<<3)|(r>>2); rgba[j+1]=(g<<2)|(g>>4); rgba[j+2]=(b<<3)|(b>>2); rgba[j+3]=255;
    }
    return rgba;
  }
  if(typeof module!=='undefined') module.exports=decodeRGB565BE;
  else root.decodeRGB565BE=decodeRGB565BE;
})(globalThis);
