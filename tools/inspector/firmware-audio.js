// Explicit opt-in only. Stream the actual C music/SFX mixer, not a second synth.
(()=>{
 const button=document.getElementById('audio-toggle'),status=document.getElementById('audio-state');
 const canvas=document.getElementById('firmware-canvas'),clock=document.getElementById('clock-state');
 let context=null,enabled=false,epoch=0,timer=null,next=0,lastSession=null;
 const sources=new Set();
 function stopScheduled(){for(const s of sources){try{s.stop();}catch{}}sources.clear();next=0;}
 function running(){return enabled&&!document.hidden&&clock.dataset.state==='running'&&canvas.dataset.screenOff!=='true';}
 function schedule(){clearTimeout(timer);timer=setTimeout(pump,40);}
 let inFlight=false;
 async function pump(){
  if(!enabled)return;
  if(!running()){stopScheduled();schedule();return;}
  if(inFlight||!canvas.dataset.session){schedule();return;}
  if(lastSession!==canvas.dataset.session){stopScheduled();lastSession=canvas.dataset.session;}
  if(next>context.currentTime+0.25){schedule();return;}
  inFlight=true;const token=epoch,session=lastSession;
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),10000);
  try{
   const response=await fetch('/api/firmware',{method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},body:JSON.stringify({session,action:'audio',samples:3528})});
   if(!response.ok)throw new Error('试听连接中断');
   const bytes=await response.arrayBuffer();
   if(token!==epoch||!running()||session!==canvas.dataset.session)return;
   if(bytes.byteLength!==7056)throw new Error('试听数据不完整');
   const data=new DataView(bytes),buffer=context.createBuffer(1,3528,22050),channel=buffer.getChannelData(0);
   for(let i=0;i<3528;i++)channel[i]=data.getInt16(i*2,true)/32768;
   const source=context.createBufferSource();source.buffer=buffer;source.connect(context.destination);
   next=Math.max(next,context.currentTime+0.04);source.start(next);next+=buffer.duration;
   sources.add(source);source.onended=()=>sources.delete(source);
  }catch(error){if(token===epoch){enabled=false;epoch++;stopScheduled();button.textContent='重试试听';button.setAttribute('aria-pressed','false');status.textContent=error.message;}}
  finally{clearTimeout(timeout);inFlight=false;if(enabled)schedule();}
 }
 button.onclick=async()=>{
  if(enabled){enabled=false;epoch++;clearTimeout(timer);stopScheduled();if(context)await context.suspend();}
  else{
   try{context??=new AudioContext();await context.resume();enabled=true;epoch++;schedule();}
   catch{status.textContent='浏览器无法开启试听';return;}
  }
  button.textContent=enabled?'关闭试听':'开启试听';button.setAttribute('aria-pressed',String(enabled));
  status.textContent=enabled?'试听已开启；如无声，请关闭游戏内静音':'浏览器试听默认关闭；游戏静音在「选项」切换';
 };
 document.addEventListener('visibilitychange',()=>{epoch++;stopScheduled();});
 window.addEventListener('pagehide',()=>{enabled=false;epoch++;clearTimeout(timer);stopScheduled();context?.close();});
})();
