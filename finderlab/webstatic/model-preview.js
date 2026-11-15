import {ToolpathView} from './toolpath-view.js';
import {normalizeTransform,modelLayout} from './model-transform.js';

// Geometry view/draft editor. GET-only; an explicit Slice in app.js commits a draft.
const el=id=>document.getElementById(id), text=(id,s)=>{el(id).textContent=s;};
let view,worker,abort,deadline,timer,revision=0,stateRevision=0,token=null;
let identity='',attempted='',enabled=true,polling=false,queued=false,closed=false,preparing=false;
let currentState={},modelData=null,published='',layoutError='';
const fields={scale:'model-scale',rotate_x:'model-rotate-x',rotate_y:'model-rotate-y',rotate_z:'model-rotate-z',x:'model-x',y:'model-y'};
function setFields(t){for(const [k,id] of Object.entries(fields))el(id).value=String(k==='scale'?t[k]*100:t[k]);}
function readTransform(){
    const t={};for(const [k,id] of Object.entries(fields)){
        if(!String(el(id).value).trim()||el(id).validity?.badInput)throw Error('Fill all transform fields with finite numbers.');
        t[k]=Number(el(id).value)/(k==='scale'?100:1);
    }
    if(!Number.isFinite(t.scale)||t.scale<.01||t.scale>10)throw Error('Scale must be 1–1000%.');
    return normalizeTransform(t);
}
function publish(){
    const editable=currentState.model&&currentState.phase==='model_ready'&&!currentState.busy;
    el('model-manual').disabled=!editable;
    el('model-transform-fields').disabled=!editable||!modelData;
    let transform=null,error='';
    if(el('model-manual').checked){
        try{transform=readTransform();if(!modelData)throw Error('Wait for the model preview or turn manual placement off.');if(layoutError)throw Error(layoutError);}
        catch(e){error=e.message;}
    }
    if(error)text('model-layout-message',error);
    const detail={source_sha256:currentState.source_sha256||'',source_id:currentState.source_id,transform,error,locked:currentState.slice_settings!=null};
    const signature=JSON.stringify(detail);
    if(signature!==published){published=signature;if(document.dispatchEvent&&typeof CustomEvent!=='undefined')document.dispatchEvent(new CustomEvent('finder-model-transform',{detail}));}
}
function paint(){
    layoutError='';
    try{
        if(modelData){
            const manual=el('model-manual').checked;
            const placement=modelLayout(modelData.positions,manual?readTransform():{});
            view.setModelLayout(placement);
            if(manual&&!placement.fits)layoutError='Mesh exceeds the nominal 140 mm plate/height. Reduce scale or move inward.';
            text('model-dimensions',`${manual?'Transformed':'Input'} dimensions: ${placement.dimensions.map(n=>n.toFixed(2)).join(' × ')} mm. ${manual?'XY centre follows controls; Z sits on bed.':'Display centered/on-bed only; Orca may arrange differently.'}`);
        }
    }catch(error){layoutError=error.message;text('model-dimensions','');if(view)view.setModelLayout(null);}
    text('model-layout-message',layoutError||(el('model-manual').checked?'Manual layout selected for explicit Slice; no automatic arrange.':'Automatic Orca arrangement; no geometry edits selected.'));
    publish();
}
function edit(){const was=el('model-manual').checked;el('model-manual').checked=true;paint();if(!was&&view)view.reset(true);}
function notifyPreparing(value){
    if(preparing===value)return;preparing=value;
    if(document.dispatchEvent&&typeof CustomEvent!=='undefined')document.dispatchEvent(new CustomEvent('finder-model-preparing',{detail:value}));
}
function clear(message){
    revision++;if(worker)worker.terminate();worker=null;
    notifyPreparing(false);
    if(abort)abort.abort();abort=null;clearTimeout(deadline);
    if(view)view.clear();modelData=null;text('model-message',message);text('model-dimensions','');publish();
}
async function load(state){
    const ticket=revision,key=identity;attempted=key;
    try{
        if(!view)view=new ToolpathView(el('model-canvas'));
        abort=new AbortController();deadline=setTimeout(()=>{if(ticket===revision)clear('Model preview deadline exceeded; Reload model to retry.');},30000);
        text('model-message','Loading input geometry (3MF may need bounded geometry conversion)…');
        if(/\.3mf$/i.test(state.name))notifyPreparing(true);
        const response=await fetch('/api/model',{cache:'no-store',signal:abort.signal,headers:{'If-Match':'"'+state.source_sha256+'"','X-Finder-Token':token}});
        notifyPreparing(false);
        if(!response.ok){
            let message=`Model unavailable/changed (HTTP ${response.status}).`;
            try{message=(await response.json()).error||message;}catch{}
            throw new Error(message);
        }
        if(response.headers.get('ETag')!=='"'+state.source_sha256+'"')throw new Error('Source identity mismatch.');
        const size=Number(response.headers.get('Content-Length'));
        if(!Number.isInteger(size)||size<1||size>32*1024*1024)throw new Error('Model preview limit is 32 MiB; slicing is independent.');
        const skipped=Number(response.headers.get('X-Skipped-Facets')||0);
        const buffer=await response.arrayBuffer();if(ticket!==revision||identity!==key)return;
        if(buffer.byteLength!==size)throw new Error('Incomplete model geometry response.');
        worker=new Worker('/model-worker.js');
        worker.onerror=()=>fail('Model geometry worker failed.',ticket);
        worker.onmessage=event=>{
            if(ticket!==revision||identity!==key)return;
            if(event.data.error){fail(event.data.error,ticket);return;}
            try{
                const data=event.data.result;modelData=data;view.setModel(data);view.wireframe(el('model-wireframe').checked);
                text('model-message',`${state.name} · original input · ${data.triangles} triangles. ${data.degenerate} zero-area facets in preview; ${skipped} skipped by 3MF import.`);
                text('model-dimensions',`Input dimensions: ${data.dimensions.map(n=>n.toFixed(2)).join(' × ')} mm. Display centered/on-bed only; Orca may arrange differently.`);
                paint();worker.terminate();worker=null;abort=null;clearTimeout(deadline);
            }catch(error){fail(error.message,ticket);}
        };
        worker.postMessage({buffer},[buffer]);
    }catch(error){if(ticket===revision)fail(error.message,ticket);}
}
function fail(message,ticket){if(ticket===revision)clear('Model preview unavailable: '+message+' Slice/Save remain independent.');}
function accept(state){
    const key=state.model&&/^[0-9a-f]{64}$/.test(state.source_sha256||'')?state.source_sha256+':'+(state.source_id||'')+':'+state.name:'';
    currentState=state;
    if(key!==identity){identity=key;attempted='';published='';el('model-manual').checked=false;setFields(normalizeTransform({}));clear(key?'New source model available.':'Choose an STL/3MF to see input geometry before slicing.');}
    // Once Slice starts, all viewers adopt its immutable server snapshot, not another tab's draft.
    if(state.slice_settings!==null&&state.slice_settings!==undefined){
        const before=JSON.stringify([el('model-manual').checked,Object.values(fields).map(id=>el(id).value)]);
        el('model-manual').checked=Boolean(state.model_transform);setFields(normalizeTransform(state.model_transform||{}));
        if(before!==JSON.stringify([el('model-manual').checked,Object.values(fields).map(id=>el(id).value)]))paint();
    }
    publish();
    // Keep the immutable source visible during Slice. Do not request a new conversion while a job is busy.
    if(enabled&&token&&key&&!state.busy&&attempted!==key)load(state);
}
async function poll(){
    clearTimeout(timer);if(closed)return;if(polling){queued=true;return;}
    polling=true;const start=stateRevision;
    try{
        if(!token){
            const response=await fetch('/api/config',{cache:'no-store'});
            if(!response.ok)throw new Error('Cannot read preview capability/token.');
            token=(await response.json()).token;
            if(typeof token!=='string'||!token)throw new Error('No preview token; reload page.');
        }
        const response=await fetch('/api/state',{cache:'no-store'});if(!response.ok)throw new Error('Cannot read model state.');
        const state=await response.json();
        if(!closed&&!queued&&start===stateRevision){
            // Share an authoritative cached observation with the page; it may veto
            // stale/in-flight/uncertain reconciliation. No printer query or action.
            let observation;
            if(document.dispatchEvent&&typeof CustomEvent!=='undefined'){
                observation=new CustomEvent('finder-state-observed',{detail:state,cancelable:true});document.dispatchEvent(observation);
            }
            if(!observation?.defaultPrevented)accept(state);
        }
    }catch(error){if(!closed&&!queued&&start===stateRevision){identity='';attempted='';clear(error.message);}}
    finally{polling=false;if(!closed){timer=setTimeout(poll,queued?0:2000);queued=false;}}
}
document.addEventListener('finder-artifact-state',event=>{stateRevision++;accept(event.detail);});
for(const id of Object.values(fields))el(id).addEventListener('input',edit);
el('model-manual').addEventListener('change',()=>{paint();if(view&&el('model-manual').checked)view.reset(true);});
el('model-center').addEventListener('click',()=>{el('model-x').value='0';el('model-y').value='0';edit();});
el('model-transform-reset').addEventListener('click',()=>{setFields(normalizeTransform({}));el('model-manual').checked=false;paint();});
for(const axis of ['x','y','z'])el('model-turn-'+axis).addEventListener('click',()=>{const field=el('model-rotate-'+axis);field.value=String((Number(field.value)+450)%360);edit();});
el('model-plate').addEventListener('click',()=>{if(view)view.reset(true);});
el('model-fit').addEventListener('click',()=>{if(view)view.reset();});
el('model-wireframe').addEventListener('change',()=>{if(view)view.wireframe(el('model-wireframe').checked);});
el('model-reload').addEventListener('click',()=>{attempted='';token=null;clear('Reloading input geometry…');poll();});
el('model-enabled').addEventListener('change',event=>{enabled=event.target.checked;attempted='';clear(enabled?'Loading input geometry…':'Model preview paused.');if(enabled)poll();});
el('model-canvas').addEventListener('preview-context-lost',()=>{enabled=false;el('model-enabled').checked=false;clear('WebGL context lost. Reload the page to recreate the model view.');});
window.addEventListener('pagehide',()=>{closed=true;enabled=false;clearTimeout(timer);clear('Model view closed.');});
window.addEventListener('pageshow',event=>{if(event.persisted){closed=false;enabled=el('model-enabled').checked;attempted='';poll();}});
poll();
