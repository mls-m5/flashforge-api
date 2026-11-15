// Input-model controller only; mocked HTTP/worker/renderer, no GPU or native slicer.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),handlers={},requests=[],workers=[],views=[],timers=new Map(),preparing=[],drafts=[];
let state={phase:'model_ready',model:true,busy:false,name:'part.3mf',source_sha256:'a'.repeat(64),sha256:'a'.repeat(64),artifact:false},timerId=0,fail=false;
function el(id){if(!elements.has(id))elements.set(id,{checked:id==='model-enabled',textContent:'',addEventListener(k,f){this[k]=f;}});return elements.get(id);}
class View{constructor(){views.push(this);this.clears=0;}clear(){this.clears++;}setModel(data){this.data=data;}setModelLayout(layout){this.layout=layout;}wireframe(v){this.wire=v;}reset(){this.resetCalled=true;}}
class Worker{constructor(url){assert.equal(url,'/model-worker.js');workers.push(this);}postMessage(value){this.input=value;}terminate(){this.terminated=true;}}
const context={document:{getElementById:el,addEventListener:(k,f)=>handlers[k]=f,dispatchEvent:e=>{if(e.type==='finder-model-preparing')preparing.push(e.detail);if(e.type==='finder-model-transform')drafts.push(e.detail);}},CustomEvent:class{constructor(type,init){this.type=type;this.detail=init.detail;}}, window:{addEventListener(){}},ToolpathView:View,Worker,AbortController,
 setTimeout(fn,ms){timers.set(++timerId,{fn,ms});return timerId;},clearTimeout(id){timers.delete(id);},
 async fetch(url,options={}){requests.push({url,options});assert(!options.method||options.method==='GET');if(fail)throw Error('synthetic HTTP failure');
  if(url==='/api/config')return{ok:true,json:async()=>({token:'test-model-token'})};
  if(url==='/api/state')return{ok:true,json:async()=>({...state})};
  assert.equal(url,'/api/model');assert.equal(options.headers['X-Finder-Token'],'test-model-token');assert.equal(options.headers['If-Match'],'"'+state.source_sha256+'"');
  return{ok:true,headers:{get:k=>k==='ETag'?'"'+state.source_sha256+'"':k==='X-Skipped-Facets'?'2':'10'},arrayBuffer:async()=>new ArrayBuffer(10)};
 }};
const flush=()=>new Promise(r=>setImmediate(r));
const result={triangles:1,degenerate:0,dimensions:[10,20,30],positions:new Float32Array([0,0,0,10,0,0,0,20,30])};
async function main(){
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/model-transform.js','utf8').replace(/^export /gm,''),context);
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/model-preview.js','utf8').replace(/^import[^\n]+\n/gm,''),context);await flush();
 assert.deepEqual(preparing,[true,false],'3MF preparation gates jobs until HTTP headers arrive');
 assert.equal(workers.length,1,'model loads BEFORE slicing');workers[0].onmessage({data:{result}});
 assert.match(el('model-dimensions').textContent,/10.00 × 20.00 × 30.00/);assert.match(el('model-message').textContent,/2 skipped/);
 el('model-wireframe').checked=true;el('model-wireframe').change();assert.equal(views[0].wire,true);
 el('model-scale').value='50';el('model-scale').input();
 assert.equal(drafts.at(-1).transform.scale,.5);assert.equal(el('model-manual').checked,true);
 assert.match(el('model-dimensions').textContent,/5.00 × 10.00 × 15.00/);
 el('model-x').value='80';el('model-x').input();assert.match(drafts.at(-1).error,/finite/);assert.equal(views[0].layout,null);
 el('model-x').value='10';el('model-x').input();assert.equal(drafts.at(-1).error,'');
 const before=views[0].clears;
 state={...state,busy:true,phase:'slicing',slice_settings:{},model_transform:{scale:.5,x:-20,y:0,rotate_z:90}};handlers['finder-artifact-state']({detail:state});
 state={...state,busy:false,phase:'review',artifact:true,sha256:'b'.repeat(64)};handlers['finder-artifact-state']({detail:state});
 assert.equal(el('model-x').value,'-20');assert.equal(el('model-transform-fields').disabled,true,'Slice locks controls to server snapshot');
 assert.equal(workers.length,1);assert.equal(views[0].clears,before,'Slice output hash never replaces the original model');
 state={...state,model:false};handlers['finder-artifact-state']({detail:state});assert(views[0].clears>before);
 state={...state,model:true,source_sha256:'c'.repeat(64)};handlers['finder-artifact-state']({detail:state});await flush();
 const old=workers.at(-1);state={...state,model:false};handlers['finder-artifact-state']({detail:state});
 assert(old.terminated);old.onmessage({data:{result}});assert.equal(el('model-dimensions').textContent,'');
 state={...state,model:true};handlers['finder-artifact-state']({detail:state});await flush();
 workers.at(-1).onmessage({data:{error:'bad STL'}});const count=workers.length;
 handlers['finder-artifact-state']({detail:state});await flush();assert.equal(workers.length,count,'unchanged failed model is not retried automatically');
 el('model-reload').click();await flush();assert.equal(workers.length,count+1);
 el('model-enabled').checked=false;el('model-enabled').change({target:el('model-enabled')});assert(workers.at(-1).terminated);
 fail=true;const poll=[...timers.values()].find(t=>t.ms===2000);await poll.fn();await flush();assert.match(el('model-message').textContent,/Cannot|failure/);
 assert(requests.every(r=>['/api/model','/api/state','/api/config'].includes(r.url)),'model preview cannot slice/save/query a printer');
 console.log('Model preview before Slice, stable source identity, cancellation, wireframe and GET-only checks passed.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
