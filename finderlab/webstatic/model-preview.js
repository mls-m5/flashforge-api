import {ToolpathView} from './toolpath-view.js';

// Independent input-geometry view: fixed cached-state/model GETs only, never slicing.
const el=id=>document.getElementById(id), text=(id,s)=>{el(id).textContent=s;};
let view,worker,abort,deadline,timer,revision=0,stateRevision=0,token=null;
let identity='',attempted='',enabled=true,polling=false,queued=false,closed=false,preparing=false;
function notifyPreparing(value){
    if(preparing===value)return;preparing=value;
    if(document.dispatchEvent&&typeof CustomEvent!=='undefined')document.dispatchEvent(new CustomEvent('finder-model-preparing',{detail:value}));
}
function clear(message){
    revision++;if(worker)worker.terminate();worker=null;
    notifyPreparing(false);
    if(abort)abort.abort();abort=null;clearTimeout(deadline);
    if(view)view.clear();text('model-message',message);text('model-dimensions','');
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
                const data=event.data.result;view.setModel(data);view.wireframe(el('model-wireframe').checked);
                text('model-message',`${state.name} · original input · ${data.triangles} triangles. ${data.degenerate} zero-area facets in preview; ${skipped} skipped by 3MF import.`);
                text('model-dimensions',`Input dimensions: ${data.dimensions.map(n=>n.toFixed(2)).join(' × ')} mm. Display centered/on-bed only; Orca may arrange differently.`);
                worker.terminate();worker=null;abort=null;clearTimeout(deadline);
            }catch(error){fail(error.message,ticket);}
        };
        worker.postMessage({buffer},[buffer]);
    }catch(error){if(ticket===revision)fail(error.message,ticket);}
}
function fail(message,ticket){if(ticket===revision)clear('Model preview unavailable: '+message+' Slice/Save remain independent.');}
function accept(state){
    const key=state.model&&/^[0-9a-f]{64}$/.test(state.source_sha256||'')?state.source_sha256+':'+state.name:'';
    if(key!==identity){identity=key;attempted='';clear(key?'New source model available.':'Choose an STL/3MF to see input geometry before slicing.');}
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
        const state=await response.json();if(!closed&&!queued&&start===stateRevision)accept(state);
    }catch(error){if(!closed&&!queued&&start===stateRevision){identity='';attempted='';clear(error.message);}}
    finally{polling=false;if(!closed){timer=setTimeout(poll,queued?0:2000);queued=false;}}
}
document.addEventListener('finder-artifact-state',event=>{stateRevision++;accept(event.detail);});
el('model-fit').addEventListener('click',()=>{if(view)view.reset();});
el('model-wireframe').addEventListener('change',()=>{if(view)view.wireframe(el('model-wireframe').checked);});
el('model-reload').addEventListener('click',()=>{identity='';attempted='';token=null;clear('Reloading input geometry…');poll();});
el('model-enabled').addEventListener('change',event=>{enabled=event.target.checked;attempted='';clear(enabled?'Loading input geometry…':'Model preview paused.');if(enabled)poll();});
el('model-canvas').addEventListener('preview-context-lost',()=>{enabled=false;el('model-enabled').checked=false;clear('WebGL context lost. Reload the page to recreate the model view.');});
window.addEventListener('pagehide',()=>{closed=true;enabled=false;clearTimeout(timer);clear('Model view closed.');});
window.addEventListener('pageshow',event=>{if(event.persisted){closed=false;enabled=el('model-enabled').checked;identity='';attempted='';poll();}});
poll();
