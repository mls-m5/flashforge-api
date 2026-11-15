import {ToolpathView} from './toolpath-view.js';
import {normalizeTransform,modelLayout} from './model-transform.js';

const el=id=>document.getElementById(id);
const fields={scale:'plate-scale',x:'plate-x',y:'plate-y',rotate_x:'plate-rotate-x',rotate_y:'plate-rotate-y',rotate_z:'plate-rotate-z'};
let state={},token=null,view=null,revision=0,key='',selected='',published='',loading=false,worker=null,abort=null;
let sources=new Map(),drafts=new Map(),single=null,pointer=null,deadline=null,lastPaint='';
function cancel(){revision++;worker?.terminate();worker=null;abort?.abort();abort=null;clearTimeout(deadline);loading=false;}
function editable(){return state.phase==='model_ready'&&!state.busy&&state.slice_settings==null;}
function fieldsFromDraft(){const t=drafts.get(selected);if(t)for(const [k,id] of Object.entries(fields))el(id).value=String(k==='scale'?t[k]*100:t[k]);}
function list(){
    const select=el('plate-model');select.replaceChildren();
    for(const m of state.models||[]){const option=document.createElement('option');option.value=m.id;option.textContent=m.name;select.append(option);}
    select.value=selected;
}
function draw(){
    if(!state.models||state.models.length<2)return;
    const stamp=JSON.stringify([key,selected,state.phase,state.busy,state.slice_settings!=null,loading,[...drafts],[...sources.keys()]]);
    if(stamp===lastPaint)return;lastPaint=stamp;
    const entries=[],bounds=[];let error='',triangles=0;
    try{
        for(const model of state.models){
            const data=sources.get(model.id);if(!data)throw Error('Loading plate geometry; wait before Slice.');
            triangles+=data.triangles;if(triangles>200000)throw Error('Combined plate exceeds200000 triangles. Remove/simplify a model.');
            const placement=modelLayout(data.positions,drafts.get(model.id));
            entries.push({id:model.id,data,layout:placement});bounds.push(placement.bounds);
            if(!placement.fits)error='A model exceeds the nominal140mm plate/height; move inward or reduce scale.';
        }
        for(let i=0;i<bounds.length;i++)for(let j=i+1;j<bounds.length;j++){
            if(![0,1].some(a=>bounds[i][a][1]+1<=bounds[j][a][0]+1e-6||bounds[j][a][1]+1<=bounds[i][a][0]+1e-6))error='Model XY bounding boxes overlap or have less than1mm gap; move them apart.';
        }
    }catch(e){error=e.message;}
    if(view)view.setPlate(entries,selected);
    el('plate-message').textContent=error||`${state.models.length} models · ${triangles} triangles. Layout draft; explicit Slice only. Selected mesh has a yellow bounds box.`;
    el('plate-fields').disabled=!editable()||loading;
    el('plate-remove').disabled=!editable()||loading;
    el('plate-model').disabled=loading;
    const detail={source_id:state.source_id,source_sha256:state.source_sha256,transform:null,
        plate:state.models.map(m=>({id:m.id,transform:drafts.get(m.id)})),error,locked:state.slice_settings!=null};
    const signature=JSON.stringify(detail);
    if(signature!==published){published=signature;document.dispatchEvent(new CustomEvent('finder-model-transform',{detail}));}
}
async function load(ticket){
    loading=true;draw();
    try{
        if(!view){
            view=new ToolpathView(el('plate-canvas'));view.reset(true);
            const canvas=view.renderer.domElement;
            canvas.addEventListener('pointerdown',e=>{pointer={x:e.clientX,y:e.clientY};});
            canvas.addEventListener('pointerup',e=>{
                if(!pointer||Math.hypot(e.clientX-pointer.x,e.clientY-pointer.y)>5)return;
                const id=view.pickModel(e.clientX,e.clientY);pointer=null;
                if(id){selected=id;list();fieldsFromDraft();draw();}
            });
        }
        for(const model of state.models){
            if(ticket!==revision)return;if(sources.has(model.id))continue;
            abort=new AbortController();
            const response=await fetch('/api/model?model='+encodeURIComponent(model.id),{cache:'no-store',signal:abort.signal,headers:{'X-Finder-Token':token,'If-Match':'"'+model.sha256+'"'}});
            if(!response.ok)throw Error('Model read failed/plate changed: HTTP '+response.status);
            if(response.headers.get('ETag')!=='"'+model.sha256+'"')throw Error('Model identity mismatch');
            const size=Number(response.headers.get('Content-Length'));if(!Number.isInteger(size)||size<1||size>32*1024*1024)throw Error('Plate STL preview limit32MiB per model');
            const buffer=await response.arrayBuffer();if(ticket!==revision)return;
            if(buffer.byteLength!==size)throw Error('Incomplete STL');
            const data=await new Promise((resolve,reject)=>{
                worker=new Worker('/model-worker.js');
                worker.onmessage=e=>e.data.error?reject(Error(e.data.error)):resolve(e.data.result);
                worker.onerror=()=>reject(Error('Plate geometry worker failed'));
                worker.postMessage({buffer},[buffer]);
            });
            if(ticket!==revision)return;
            worker.terminate();worker=null;
            if([...sources.values()].reduce((n,d)=>n+d.triangles,0)+data.triangles>200000)throw Error('Combined plate exceeds200000 triangles; remove/simplify a model');
            sources.set(model.id,data);
        }
    }catch(e){
        if(ticket===revision){worker?.terminate();worker=null;abort?.abort();abort=null;clearTimeout(deadline);loading=false;draw();el('plate-message').textContent=e.message+' Remove/re-add or reload the page to retry. No Slice/Save was sent.';}
        return;
    }
    if(ticket===revision){loading=false;abort=null;clearTimeout(deadline);draw();}
}
function accept(next){
    state=next;const active=state.models?.length>1;
    el('plate-section').hidden=!active;el('single-model-section').hidden=active;
    if(!active){if(key){cancel();key='';sources.clear();drafts.clear();view?.clear();published='';lastPaint='';}return;}
    const identity=state.source_id+':'+state.models.map(m=>m.id+':'+m.sha256).join(',');
    if(key!==identity){
        cancel();key=identity;published='';lastPaint='';
        const ids=new Set(state.models.map(m=>m.id));sources=new Map([...sources].filter(([id])=>ids.has(id)));drafts=new Map([...drafts].filter(([id])=>ids.has(id)));
        for(let i=0;i<state.models.length;i++){
            const m=state.models[i];if(!drafts.has(m.id))drafts.set(m.id,normalizeTransform(i===0&&single?.source_sha256===m.sha256&&single.transform?single.transform:{x:-45+(i%4)*30,y:-20+Math.floor(i/4)*40}));
        }
        if(!ids.has(selected))selected=state.models[0].id;
        list();fieldsFromDraft();
    }
    if(state.plate){for(const item of state.plate)drafts.set(item.id,item.transform);fieldsFromDraft();}
    draw();
    if(token&&!state.busy&&!loading&&state.models.some(m=>!sources.has(m.id))){
        // One attempt per plate identity; do not repeatedly parse malformed input.
        if(attempted!==key){attempted=key;const ticket=revision;deadline=setTimeout(()=>{if(ticket===revision){cancel();draw();el('plate-message').textContent='Plate preview deadline exceeded; reload to retry.';}},45000);load(ticket);}
    }
}
let attempted='';
document.addEventListener('finder-model-transform',e=>{if(!e.detail.plate&&e.detail.transform)single=e.detail;});
document.addEventListener('finder-artifact-state',e=>accept(e.detail));
for(const id of Object.values(fields))el(id).addEventListener('input',()=>{
    if(!editable())return;
    const value={};for(const [k,input] of Object.entries(fields))value[k]=String(el(input).value).trim()&&!el(input).validity?.badInput?Number(el(input).value)/(k==='scale'?100:1):NaN;
    // Keep invalid drafts invalid and block Slice, rather than silently using old values.
    drafts.set(selected,value);draw();
});
el('plate-model').addEventListener('change',()=>{selected=el('plate-model').value;fieldsFromDraft();draw();});
el('plate-center').addEventListener('click',()=>{if(editable()){drafts.set(selected,{...drafts.get(selected),x:0,y:0});fieldsFromDraft();draw();}});
el('plate-fit').addEventListener('click',()=>view?.reset(true));
el('plate-remove').addEventListener('click',()=>{if(editable())document.dispatchEvent(new CustomEvent('finder-remove-model',{detail:{source_id:state.source_id,model_id:selected}}));});
el('plate-canvas').addEventListener('preview-context-lost',()=>{cancel();sources.clear();attempted=key;lastPaint='';draw();el('plate-message').textContent='WebGL context lost. Reload the page before editing this plate.';});
window.addEventListener('pagehide',()=>{cancel();view?.clear();});
window.addEventListener('pageshow',event=>{if(event.persisted){attempted='';lastPaint='';accept(state);}});
fetch('/api/config',{cache:'no-store'}).then(r=>{if(!r.ok)throw Error('Config unavailable');return r.json();}).then(c=>{token=c.token;accept(state);}).catch(e=>{el('plate-message').textContent=e.message;});
