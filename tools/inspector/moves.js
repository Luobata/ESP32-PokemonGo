/* No browser-drawn effects: only RGB565 frames from the production C renderer. */
(async function(){
 const $=id=>document.getElementById(id),canvas=$('canvas'),ctx=canvas.getContext('2d');
 const types='一般 火 水 电 草 冰 格斗 毒 地面 飞行 超能 虫 岩石 幽灵 龙 恶 钢'.split(' ');
 let catalog=[],session=null,frame=0,playing=true,busy=false,timer=null,queue=Promise.resolve();
 function enqueue(fn){queue=queue.then(fn).catch(e=>{playing=false;$('play').textContent='播放';$('status').textContent=e.message;});return queue;}
 async function request(action,args={}){
  const res=await fetch('/api/firmware',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({session,action,...args})});
  if(!res.ok)throw new Error((await res.json()).error||'预览失败');
  session=res.headers.get('X-Preview-Session');ctx.putImageData(new ImageData(decodeRGB565BE(new Uint8Array(await res.arrayBuffer())),240,320),0,0);
  $('status').textContent='同源构建 '+res.headers.get('X-Preview-Version');
 }
 function selected(){return catalog.find(m=>m.id===Number($('move').value));}
 async function render(){if(!session||!selected())return;await request('move_preview',{move:selected().id,side:Number($('side').value),mode:Number($('mode').value),frame});$('frame').value=frame;$('frame-label').textContent=frame+' / 35';}
 function info(){const m=selected();$('meta').textContent=m?`${types[m.type]} · 威力 ${m.power||'—'} · 命中 ${m.accuracy===255?'必中':m.accuracy+'%'}\n动画：${m.animation==='属性/状态共用动画'?m.animation:'招式指定动作'}${m.new?' · 本批新增':''}`:'无匹配招式';}
 function filter(){const old=$('move').value,q=$('search').value.trim();const rows=catalog.filter(m=>($('scope').value!=='new'||m.new)&&(!q||m.name.includes(q)||String(m.id).includes(q)));$('move').replaceChildren(...rows.map(m=>new Option(`${m.id} · ${m.name}`,m.id)));if(rows.some(m=>String(m.id)===old))$('move').value=old;$('count').textContent=`(${rows.length})`;info();frame=0;enqueue(render);}
 async function load(){await request('reset',{page:3,pet:Number($('pet').value),wild:Number($('wild').value),level:60,rarity:3,seed:123,team:0});frame=0;await render();}
 $('move').onchange=()=>{info();frame=0;enqueue(render);};$('search').oninput=filter;$('scope').onchange=filter;
 for(const id of ['side','mode'])$(id).onchange=()=>{frame=0;enqueue(render);};
 $('load').onclick=()=>enqueue(load);
 for(const [id,dir] of [['prev',-1],['next',1]])$(id).onclick=()=>{const s=$('move');if(!s.options.length)return;s.selectedIndex=(s.selectedIndex+dir+s.options.length)%s.options.length;s.onchange();};
 $('play').onclick=()=>{playing=!playing;$('play').textContent=playing?'暂停':'播放';$('play').classList.toggle('active',playing);};
 $('restart').onclick=()=>{frame=0;enqueue(render);};$('step').onclick=()=>{playing=false;$('play').textContent='播放';frame=(frame+1)%36;enqueue(render);};
 $('frame').oninput=()=>{playing=false;$('play').textContent='播放';frame=Number($('frame').value);enqueue(render);};
 $('save').onclick=()=>{const a=document.createElement('a');a.download=`move-${$('move').value}-side${$('side').value}-frame${frame}.png`;a.href=canvas.toDataURL();a.click();};
 try{const res=await fetch('move-catalog.json');if(!res.ok)throw Error('无法载入招式表');catalog=await res.json();filter();await enqueue(load);}catch(e){$('status').textContent=e.message;}
 timer=setInterval(()=>{if(!playing||busy||document.hidden||!session)return;busy=true;enqueue(async()=>{frame=(frame+1)%36;await render();}).finally(()=>busy=false);},90);
})();
