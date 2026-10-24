'use strict';
const $=id=>document.getElementById(id);
const types=['一般','火','水','电','草','冰','格斗','毒','地面','飞行','超能力','虫','岩石','幽灵','龙','恶','钢'];
let data,selected=152,isShiny=false,isBack=false,started=0,loadedId=0,front=null,back=null,animation=0,routeFilter=null,requestId=0;
const ctx=$('sprite').getContext('2d');ctx.imageSmoothingEnabled=false;
const image=src=>new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('素材载入失败：'+src));i.src=src;});
function text(tag,value,className){const e=document.createElement(tag);e.textContent=value;if(className)e.className=className;return e;}
function renderList(){
 const query=$('search').value.trim().toLowerCase();
 const rows=data.pokemon.filter(p=>(p.id>151||$('kanto').checked)&&(!routeFilter||routeFilter.includes(p.id))&&(!query||String(p.id).includes(query)||p.name_zh.includes(query)||p.slug.includes(query)));
 $('count').textContent=`${rows.length} 位伙伴${routeFilter?' · 当前路线':''}`;
 $('species-list').replaceChildren(...rows.map(p=>{const b=document.createElement('button');b.type='button';b.setAttribute('role','option');b.setAttribute('aria-selected',String(p.id===selected));b.append(text('span',String(p.id).padStart(3,'0')),text('b',p.name_zh));b.onclick=()=>select(p.id);return b;}));
 if(!rows.length)$('species-list').append(text('p','没有匹配的伙伴'));
}
function sourceName(id){
 if(id===175)return '获取计划：第一枚城都徽章后的神秘蛋委托，仅有效探索推进孵化。';
 if([243,244,245,249,250,251].includes(id))return '获取计划：独立传说调查，完成后可反复挑战；不放进普通随机池。';
 if([152,155,158].includes(id))return '获取计划：抵达城都时选择；另外两位通过后续研究获得。';
 const routes=data.chapter.routes.filter(r=>r.species.includes(id));
 if(routes.length)return '获取计划：'+routes.map(r=>`${r.name}（Lv.${r.levels.join('–')}）`).join('、');
 const parent=data.pokemon.find(p=>p.evolutions.some(e=>e.target===id));
 return parent?'获取计划：由'+parent.name_zh+'进化；完整进化条件与道具尚待正式接入。':'第一世代现有获取途径保留。';
}
async function select(id){
 const request=++requestId;
 selected=id;loadedId=0;cancelAnimationFrame(animation);renderList();
 const p=data.pokemon.find(p=>p.id===id);$('number').textContent='No. '+String(id).padStart(3,'0');$('name').textContent=p.name_zh;$('types').textContent=[...new Set(p.types)].map(v=>types[v]).join(' / ');
 $('stats').replaceChildren(...['HP','攻击','防御','速度','特攻','特防'].map((n,i)=>{const e=text('span',n);e.append(text('b',p.stats[i]));return e;}));
 $('acquisition').textContent=sourceName(id);
 $('mechanic').textContent=({201:'未知图腾：当前为 A 形态素材；其他形态与觉醒力量机制待接入。',202:'果然翁：素材已验证；反击型 AI 与镜面反射待专门实现。',235:'图图犬：素材已验证；写生与个体招式记录待专门实现。'})[id]||`已提取原版 ${p.level_up.length} 条升级招式、${p.tm_hm.length} 条 TM/HM 资格；开发版仅开放现有战斗引擎已实现的招式，其余机制待补齐。`;
 ctx.fillStyle='white';ctx.fillRect(0,0,224,224);
 try{
  const imgs=await Promise.all([image(`johto-assets/${id}.png`),image(`johto-assets/back-${id}-${Number(isShiny)}.png`)]);
  if(request!==requestId)return;[front,back]=imgs;loadedId=id;started=performance.now();animation=requestAnimationFrame(draw);
 }catch(error){if(request===requestId)$('mechanic').textContent=error.message;}
}
function draw(now){
 if(loadedId!==selected)return;
 const motion=data.timing[selected];const tick=Math.floor((now-started)*60/1000);const frame=tick<motion.ticks.length?motion.ticks[tick]:0;
 ctx.fillStyle='white';ctx.fillRect(0,0,224,224);
 const size=isBack?96:motion.size*2,offset=Math.floor((224-size)/2);
 if(isBack)ctx.drawImage(back,0,0,size,size,offset,offset,size,size);
 else ctx.drawImage(front,isShiny?112:0,frame*112,size,size,offset,offset,size,size);
 $('pose-label').textContent=(isShiny?'闪光':'普通')+' / '+(isBack?'背面':tick<motion.ticks.length?'出场动作':'正面');
 if(!isBack&&tick<=motion.ticks.length)animation=requestAnimationFrame(draw);
}
function renderRoutes(){
 const badges=Number($('badges').value);
 $('routes').replaceChildren(...data.chapter.routes.map(r=>{const e=document.createElement('div');e.className='route-row'+(r.badges>badges?' locked':'');const title=text('div','');title.append(text('strong',r.name),text('small',r.activity));const button=text('button',r.badges>badges?`${r.badges} 枚徽章后开放`:'查看伙伴计划');button.onclick=()=>{routeFilter=r.species;$('search').value='';renderList();select(r.species[0]);$('partners').scrollIntoView({behavior:'smooth'});};e.append(text('span',String(r.id+1).padStart(2,'0')),title,text('span','Lv. '+r.levels.join('–')),button);return e;}));
}
async function main(){
 try{const r=await fetch('johto-assets/catalog.json');if(!r.ok)throw new Error('请先运行 python3 tools/pipeline/build_johto_preview.py --src <固定版本的 pokecrystal 目录>');data=await r.json();
 $('content').hidden=false;$('load-status').hidden=true;renderList();renderRoutes();await select(152);
 $('pending').replaceChildren(...data.pending.map(v=>text('li',v)));
 const boss=data.chapter.trainers[8];$('final-team').replaceChildren(...boss.team.map(([id,lv])=>{const e=document.createElement('div');e.className='final-mon';const art=document.createElement('div');art.className='final-art';art.style.backgroundImage=`url(johto-assets/${id}.png)`;e.append(art,text('b',data.pokemon[id-1].name_zh),text('small','Lv. '+lv));return e;}));
 }catch(error){$('load-status').textContent='预览暂未就绪。\n'+error.message;}
}
$('search').oninput=()=>{routeFilter=null;renderList();};$('kanto').onchange=()=>{routeFilter=null;renderList();};$('badges').onchange=renderRoutes;
$('replay').onclick=()=>{isBack=false;$('back').setAttribute('aria-pressed','false');$('back').textContent='查看背面';started=performance.now();cancelAnimationFrame(animation);animation=requestAnimationFrame(draw);};
$('shiny').onclick=()=>{isShiny=!isShiny;$('shiny').setAttribute('aria-pressed',String(isShiny));$('shiny').textContent=isShiny?'闪光配色':'普通配色';select(selected);};
$('back').onclick=()=>{isBack=!isBack;$('back').setAttribute('aria-pressed',String(isBack));$('back').textContent=isBack?'查看正面':'查看背面';cancelAnimationFrame(animation);draw(performance.now());};
main();
