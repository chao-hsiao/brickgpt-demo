const $=id=>document.getElementById(id);
const canvas=$('canvas'),ctx=canvas.getContext('2d');
let bricks=[],visible=0,current=null,currentId=null,yaw=-.72,elevation=.63,zoom=1,drag=null,rotating=false,playTimer=null,runIndex=[];
const colors=['#d5ed82','#c0db6c','#9fbf62','#7fa858','#608e55','#477655'];
let generationEnabled=false;
$('generate').disabled=true;
async function loadRuntime(){try{const c=await json('/api/config');generationEnabled=c.generation_enabled;$('runtimeMode').textContent=generationEnabled?'● Local · '+c.device:'● Saved-output replay';$('generate').textContent=generationEnabled?'Generate locally ↗':'Replay-only mode';$('generate').title=generationEnabled?'Run the official model locally':'Install the model and restart to enable generation';$('generate').disabled=!generationEnabled||!!(current&&!['complete','failed'].includes(current.status));}catch(e){$('generate').disabled=true;$('record').textContent=e.message;}}
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function resize(){let r=canvas.getBoundingClientRect(),d=devicePixelRatio||1;canvas.width=r.width*d;canvas.height=r.height*d;draw();}
new ResizeObserver(resize).observe(canvas);
function draw(){
 const d=devicePixelRatio||1,w=canvas.width/d,h=canvas.height/d;ctx.setTransform(d,0,0,d,0,0);ctx.clearRect(0,0,w,h);
 if(!bricks.length)return;
 const lo=[Infinity,Infinity,Infinity],hi=[-Infinity,-Infinity,-Infinity];
 for(const b of bricks){lo[0]=Math.min(lo[0],b.x);lo[1]=Math.min(lo[1],b.y);lo[2]=Math.min(lo[2],b.z*1.2);hi[0]=Math.max(hi[0],b.x+b.h);hi[1]=Math.max(hi[1],b.y+b.w);hi[2]=Math.max(hi[2],(b.z+1)*1.2);}
 const center=lo.map((v,i)=>(v+hi[i])/2),extent=Math.max(hi[0]-lo[0],hi[1]-lo[1],hi[2]-lo[2],5),scale=Math.min(w,h)*.68/extent*zoom;
 function project(p){let x=p[0]-center[0],y=p[1]-center[1],z=p[2]-center[2],xx=x*Math.cos(yaw)-y*Math.sin(yaw),yy=x*Math.sin(yaw)+y*Math.cos(yaw);return [w*.5+xx*scale,h*.51+(yy*Math.sin(elevation)-z*Math.cos(elevation))*scale,yy*Math.cos(elevation)+z*Math.sin(elevation)];}
 ctx.strokeStyle='rgba(159,183,154,.12)';ctx.lineWidth=.7;
 let reach=Math.max(20,Math.ceil(extent*1.5));for(let v=-reach;v<=reach;v+=2){for(const pair of [[[center[0]+v,center[1]-reach,0],[center[0]+v,center[1]+reach,0]],[[center[0]-reach,center[1]+v,0],[center[0]+reach,center[1]+v,0]]]){let a=project(pair[0]),b=project(pair[1]);ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.stroke();}}
 const faceDefs=[[[4,5,6,7],[0,0,1],1],[[0,3,2,1],[0,0,-1],.45],[[1,2,6,5],[1,0,0],.75],[[0,4,7,3],[-1,0,0],.63],[[2,3,7,6],[0,1,0],.83],[[0,1,5,4],[0,-1,0],.67]],faces=[];
 for(const b of bricks.slice(0,visible)){
  const x=b.x+.025,y=b.y+.025,z=b.z*1.2+.025,X=b.x+b.h-.025,Y=b.y+b.w-.025,Z=(b.z+1)*1.2-.025;
  const verts=[[x,y,z],[X,y,z],[X,Y,z],[x,Y,z],[x,y,Z],[X,y,Z],[X,Y,Z],[x,Y,Z]].map(project);
  for(const [indices,n,shade]of faceDefs){const facing=(n[0]*Math.sin(yaw)+n[1]*Math.cos(yaw))*Math.cos(elevation)+n[2]*Math.sin(elevation);if(facing<=0)continue;const pts=indices.map(i=>verts[i]);faces.push({pts,depth:pts.reduce((s,p)=>s+p[2],0)/4,color:colors[b.z%colors.length],shade});}
 }
 faces.sort((a,b)=>a.depth-b.depth);
 for(const f of faces){ctx.beginPath();f.pts.forEach((p,i)=>i?ctx.lineTo(p[0],p[1]):ctx.moveTo(p[0],p[1]));ctx.closePath();const c=f.color.slice(1).match(/../g).map(v=>Math.round(parseInt(v,16)*f.shade));ctx.fillStyle=`rgb(${c.join(',')})`;ctx.fill();ctx.strokeStyle='rgba(21,36,20,.45)';ctx.lineWidth=.6;ctx.stroke();}
}
canvas.onpointerdown=e=>{drag={x:e.clientX,y:e.clientY,yaw,elevation};canvas.setPointerCapture(e.pointerId);};
canvas.onpointermove=e=>{if(!drag)return;yaw=drag.yaw+(e.clientX-drag.x)*.008;elevation=Math.max(.15,Math.min(1.35,drag.elevation+(e.clientY-drag.y)*.006));draw();};
canvas.onpointerup=()=>drag=null;canvas.onpointercancel=()=>drag=null;
canvas.addEventListener('wheel',e=>{e.preventDefault();zoom=Math.max(.4,Math.min(3,zoom*Math.exp(-e.deltaY*.001)));draw();},{passive:false});
function setVisible(n){visible=n;$('timeline').value=n;$('count').textContent=`${n} / ${bricks.length}`;draw();}
$('timeline').oninput=e=>{stopPlay();setVisible(Number(e.target.value));};
function stopPlay(){clearInterval(playTimer);playTimer=null;$('play').textContent='▶ Replay assembly';}
$('play').onclick=()=>{if(playTimer){stopPlay();return;}setVisible(0);$('play').textContent='Ⅱ Pause replay';playTimer=setInterval(()=>{setVisible(Math.min(visible+1,bricks.length));if(visible>=bricks.length)stopPlay();},Math.max(70,7000/Math.max(bricks.length,1)));};
$('rotate').onclick=()=>{rotating=!rotating;$('rotate').textContent=rotating?'Ⅱ Stop rotation':'↻ Rotate';};
let lastFrame=0;function frame(t){if(rotating&&t-lastFrame>35){yaw+=.008;draw();lastFrame=t;}requestAnimationFrame(frame);}requestAnimationFrame(frame);
async function json(url,options){const r=await fetch(url,options),d=await r.json();if(!r.ok)throw Error(d.error||`HTTP ${r.status}`);return d;}
function paint(d){
 current=d;const done=d.status==='complete',active=!['complete','failed'].includes(d.status);bricks=d.bricks||d.progress?.bricks||[];
 $('baseModel').textContent=d.models?.[0]?.repo||'meta-llama/Llama-3.2-1B-Instruct';
 $('adapterModel').textContent=d.models?.[1]?.repo||'AvaLovelace/BrickGPT';
 $('modelContext').textContent=done?'Model used for this saved run.':d.status==='failed'?'Configured model for this failed run.':d.status==='loading_model'?'Loading model for this run…':'Generating with this model…';
 $('runTitle').textContent=d.prompt;$('sourceBadge').textContent=done?'Saved genuine model output':d.status==='failed'?'Run failed':d.status==='loading_model'?'Loading official weights':'Live generation';
 $('sourceBadge').style.borderColor=done?'#667a44':'#6b6646';$('empty').hidden=bricks.length>0;
 $('empty').textContent=d.status==='failed'?`${d.error_type}: ${d.error_message||'See experiment log'}`:'Model is working. Decoded bricks will appear as they are accepted.';
 $('timeline').max=bricks.length;$('play').disabled=!bricks.length;
 if(!playTimer)setVisible(bricks.length);
 $('metricBricks').textContent=d.brick_count??bricks.length;
 $('metricTime').textContent=d.generation_seconds?`${d.generation_seconds.toFixed(1)} s`:(d.progress?.seconds?`${Math.round(d.progress.seconds)} s…`:'—');
 $('metricValid').textContent=done?(d.valid_geometry?'PASS':'FAIL'):'—';$('metricConnected').textContent=done?(d.connected_to_ground?'PASS':'FAIL'):'—';
 $('record').textContent=`Seed ${d.seed} · ${d.config?.device||'MPS'} · ${d.parameter_dtype||'weights loading'}${done?` · ${Object.values(d.rejection_reasons||{}).reduce((a,b)=>a+b,0)} rejections · ${d.regenerations} rollbacks · EOS ${d.model_eos_observed?'observed':'not observed'}`:''}`;
 $('physics').textContent=d.force_stability==='passed'?'Post-generation static force check passed. Inference still used connectivity fallback.':d.force_stability==='failed'?'Static force check FAILED. This structure is not certified stable.':'Full force stability NOT CERTIFIED — restricted Gurobi license. Ground connectivity is a different check.';
 const files=done?[['TXT','bricks.txt'],['LDR','bricks.ldr'],['JSON','result.json'],...(d.assets?.mesh?[['GLB',d.assets.mesh]]:[]),...(d.assets?.video?[['MP4',d.assets.video]]:[])]:[];
 $('downloads').innerHTML=files.map(([label,file])=>`<a href="/downloads/${encodeURIComponent(d.run_id)}/${file}">${label} ↓</a>`).join('');
 $('generate').disabled=active||!generationEnabled;draw();
}
async function select(id){currentId=id;stopPlay();await update();drawList();}
function drawList(){$('runs').innerHTML=runIndex.length?runIndex.map(d=>`<button class="run ${d.run_id===currentId?'selected':''}" data-id="${esc(d.run_id)}"><strong>${esc(d.prompt)}</strong><span>${esc(d.status)} · seed ${d.seed}${d.brick_count?' · '+d.brick_count+' bricks':''}</span></button>`).join(''):'<p class="hint">No model output yet. Start with Generate locally.</p>';document.querySelectorAll('.run').forEach(b=>b.onclick=()=>select(b.dataset.id));}
async function refresh(){try{runIndex=await json('/api/runs');drawList();if(!currentId&&runIndex.length){const good=runIndex.find(r=>r.status==='complete')||runIndex[0];await select(good.run_id);}}catch(e){$('record').textContent=e.message;}}
async function update(){if(!currentId)return;try{paint(await json('/api/runs/'+encodeURIComponent(currentId)));}catch(e){$('record').textContent=e.message;}}
$('refresh').onclick=refresh;document.querySelectorAll('.preset').forEach(b=>b.onclick=()=>{$('prompt').value=b.dataset.prompt;});
$('generate').onclick=async()=>{try{$('generate').disabled=true;const d=await json('/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:$('prompt').value,seed:Number($('seed').value)})});currentId=d.run_id;$('runTitle').textContent='Starting model…';$('sourceBadge').textContent='Starting live run';setTimeout(refresh,1200);}catch(e){$('record').textContent=e.message;$('generate').disabled=false;}};
loadRuntime();refresh();setInterval(async()=>{await refresh();if(currentId&&(current?.run_id!==currentId||!['complete','failed'].includes(current?.status)||(runIndex.find(r=>r.run_id===currentId)?.assets&&!current?.assets)))await update();},2500);
