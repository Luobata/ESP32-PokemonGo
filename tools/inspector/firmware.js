/* UI sends input to C and displays returned LCD bytes. It never draws a page. */
(function(){
  const $=id=>document.getElementById(id),canvas=$('firmware-canvas'),ctx=canvas.getContext('2d');
  let session=null,paused=false,timer=null,pumpActive=false,clockEpoch=0,sceneChanges=0,lastPage='P3',requests=Promise.resolve();
  const namePreferenceKey='pokewalk.nameStyle.v1';
  let nameStyle=0,nameRequest=0;
  try{const saved=localStorage.getItem(namePreferenceKey);if(saved==='0'||saved==='1')nameStyle=Number(saved);}catch{}
  $('names').value=String(nameStyle);
  const canRun=()=>!paused&&!document.hidden&&sceneChanges===0&&session!==null;
  function clockStatus(){
    $('play').textContent=paused?'继续运行':'暂停';
    const state=paused?'paused':document.hidden?'hidden':sceneChanges||!session?'loading':'running';
    const labels={paused:'已暂停 · 按键仍可输入，转场与动画需继续运行或单步推进',hidden:'后台暂停 · 返回页面后继续运行',loading:'正在载入场景…',running:'实时运行 · 转场与动画自动继续'};
    if($('clock-state').dataset.state!==state){$('clock-state').dataset.state=state;$('clock-state').textContent=labels[state];}
  }
  function suspendClock(){clockEpoch++;clearTimeout(timer);timer=null;clockStatus();}
  function scheduleClock(){
    clockStatus();
    if(!canRun()||pumpActive||timer!==null)return;
    timer=setTimeout(()=>{timer=null;pump();},60);
  }
  function pauseClock(){paused=true;suspendClock();}
  function send(action,args={},guard=null){
    // Preserve A/B/C while a tick is in flight. Each input sees the session and
    // state returned by its predecessor; playback never disables the controls.
    const next=requests.then(()=>guard&&!guard()?false:perform(action,args));requests=next;return next;
  }
  async function perform(action,args){
    const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),20000);
    $('status').setAttribute('aria-busy','true');
    if(action==='reset')$('reset').disabled=true;
    try{
      const response=await fetch('/api/firmware',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({session,action,...args})});
      if(!response.ok){let error;try{error=(await response.json()).error;}catch{}throw new Error(error||'请通过 tools/inspector/server.py 启动固件同源预览');}
      const bytes=new Uint8Array(await response.arrayBuffer());
      const rgba=decodeRGB565BE(bytes);
      ctx.putImageData(new ImageData(rgba,240,320),0,0);
      session=response.headers.get('X-Preview-Session');lastPage=response.headers.get('X-Preview-Page');
      $('page').value=lastPage.slice(1);
      const selectedNames=response.headers.get('X-Preview-Names');
      if(selectedNames==='0'||selectedNames==='1'){
        nameStyle=Number(selectedNames);
        if(nameRequest===0)$('names').value=selectedNames;
        try{localStorage.setItem(namePreferenceKey,selectedNames);}catch{}
      }
      const mismatch=Number(response.headers.get('X-Preview-Mismatch'));
      const ms=response.headers.get('X-Preview-Ms'),version=response.headers.get('X-Preview-Version');
      const screenOff=response.headers.get('X-Preview-Screen-Off')==='1';
      $('status').className='status'+(mismatch>0?' error':'');
      $('status').textContent=(screenOff?'已熄屏 · 按 A / B / C 亮屏 · ':'')+`${lastPage} · ${ms} ms · 构建 ${version}`+(mismatch>=0?` · 横带重绘差异 ${mismatch} 像素`:'');
      canvas.dataset.session=session;
      canvas.dataset.music=response.headers.get('X-Preview-Music')||'0';
      canvas.dataset.ms=ms;canvas.dataset.page=lastPage;canvas.dataset.version=version;
      canvas.dataset.screenOff=String(screenOff);
      return true;
    }catch(error){pauseClock();$('status').className='status error';$('status').textContent=error.message;return false;}
    finally{clearTimeout(timeout);$('reset').disabled=false;$('status').setAttribute('aria-busy','false');}
  }
  async function changeScene(action,args){
    sceneChanges++;suspendClock();
    try{return await send(action,args);}
    finally{sceneChanges--;scheduleClock();}
  }
  async function reset(){
    if(![...document.querySelectorAll('input[type=number]')].every(e=>e.reportValidity()))return;
    await changeScene('reset',Object.fromEntries(['page','pet','level','wild','rarity','seed'].map(k=>[k,Number($(k).value)]).concat([['shiny',$('shiny').checked?1:0],['names',Number($('names').value)],['team',Number($('team').value)]])));
  }
  $('reset').onclick=reset;
  $('names').onchange=async()=>{
    const style=Number($('names').value);nameRequest++;
    try{await changeScene('names',{style});}
    finally{if(--nameRequest===0)$('names').value=String(nameStyle);}
  };
  // The inspector's selector loads a scene. In-game A/B/C navigation preserves
  // state; choosing a preview after a consumed encounter must not reuse its uid.
  $('page').onchange=reset;
  $('step').onclick=()=>{pauseClock();return send('tick',{ms:60});};
  $('check').onclick=()=>{pauseClock();return send('check');};
  async function pump(){
    if(!canRun()||pumpActive)return;
    pumpActive=true;
    const epoch=clockEpoch;
    // Only automatic ticks may expire in the queue. A pause, hidden tab or
    // scene change invalidates old ticks without dropping any user input.
    try{await send('tick',{ms:60},()=>epoch===clockEpoch&&canRun());}
    finally{pumpActive=false;scheduleClock();}
  }
  $('play').onclick=()=>{paused=!paused;suspendClock();scheduleClock();};
  // Match BSP: A/B 600 ms, C 1500 ms (plus hardware ADC debounce).
  // A completed hold owns its release: the browser's following click must not
  // send a second event and undo B's "previous item" selection.
  const longPressMs=600,heldKeys=new Map();
  function beginKey(id,key){
    if(heldKeys.has(id)||document.hidden)return;
    const held={key,event:Number($('gesture').value),long:false,timer:null};
    heldKeys.set(id,held);
    if(held.event===1)held.timer=setTimeout(()=>{
      if(heldKeys.get(id)!==held)return;
      held.long=true;held.timer=null;
      send('key',{key,event:3});
    },key===2?1500:longPressMs);
  }
  function endKey(id,commit){
    const held=heldKeys.get(id);if(!held)return;
    heldKeys.delete(id);clearTimeout(held.timer);
    if(commit&&!held.long)send('key',{key:held.key,event:held.event});
  }
  function cancelKeys(){for(const id of heldKeys.keys())endKey(id,false);}
  document.querySelectorAll('[data-key]').forEach(b=>{
    const key=Number(b.dataset.key);
    b.style.touchAction='none';
    b.onpointerdown=e=>{
      if(e.button!==0||e.isPrimary===false)return;
      b.setPointerCapture(e.pointerId);beginKey(`pointer:${e.pointerId}`,key);
    };
    b.onpointerup=e=>endKey(`pointer:${e.pointerId}`,true);
    b.onpointercancel=e=>endKey(`pointer:${e.pointerId}`,false);
    b.onlostpointercapture=e=>endKey(`pointer:${e.pointerId}`,false);
    b.oncontextmenu=e=>e.preventDefault();
    // Enter/Space and accessibility activation have no preceding pointer pair.
    b.onclick=e=>{if(e.detail===0)send('key',{key,event:Number($('gesture').value)});};
  });
  window.addEventListener('keydown',e=>{
    if(e.repeat||e.ctrlKey||e.altKey||e.metaKey||e.target.isContentEditable||['INPUT','SELECT','TEXTAREA'].includes(e.target.tagName))return;
    const key='abc'.indexOf(e.key.toLowerCase());
    if(key>=0){e.preventDefault();beginKey(`keyboard:${key}`,key);}
  });
  window.addEventListener('keyup',e=>{
    const key='abc'.indexOf(e.key.toLowerCase());
    if(key>=0)endKey(`keyboard:${key}`,true);
  });
  window.addEventListener('blur',cancelKeys);
  document.addEventListener('visibilitychange',()=>{if(document.hidden)cancelKeys();});
  $('bands').onchange=()=>{$('guides').style.display=$('bands').checked?'block':'none';};
  function zoom(){const wanted=Number($('zoom').value)||Math.min(2,Math.max(1,Math.floor((innerHeight-280)/320)));const available=document.querySelector('.stage').clientWidth-34;const scale=Math.min(wanted,Math.max(1,Math.floor(available/240)));$('screen-wrap').style.width=(240*scale)+'px';$('screen-wrap').style.height=(320*scale)+'px';}
  $('zoom').onchange=zoom;window.addEventListener('resize',zoom);zoom();
  $('download').onclick=()=>{const a=document.createElement('a');a.download=`firmware-${lastPage}-${canvas.dataset.ms}ms.png`;a.href=canvas.toDataURL('image/png');a.click();};
  const hash=location.hash.match(/^#P([0-6]|9|1[0-2])$/);if(hash)$('page').value=hash[1];
  document.addEventListener('visibilitychange',()=>{suspendClock();scheduleClock();});
  reset();
})();
