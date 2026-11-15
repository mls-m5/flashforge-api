// Compose real page + editor controllers with an event bus; no browser/GPU/native/client.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),listeners=new Map(),timers=new Map(),posts=[],workers=[];let timer=0,losePost=false;
let state={model:true,phase:'model_ready',busy:false,name:'part.stl',suggested_name:'part.gcode',source_id:'one',source_sha256:'a'.repeat(64),sha256:'a'.repeat(64),slice_settings:null,model_transform:null,artifact:false};
function el(id){if(!elements.has(id))elements.set(id,{value:id==='brim-mode'?'profile':id==='brim-width'?'5':['hole-compensation','contour-compensation'].includes(id)?'0':'',checked:id==='model-enabled',disabled:false,textContent:'',handlers:{},classList:{add(){},remove(){}},addEventListener(k,f){this.handlers[k]=f;}});return elements.get(id);}
class Event{constructor(type,init={}){this.type=type;Object.assign(this,init);this.defaultPrevented=false;}preventDefault(){if(this.cancelable)this.defaultPrevented=true;}}
const result={triangles:1,degenerate:0,positions:new Float32Array([0,0,0,10,0,0,0,20,30]),dimensions:[10,20,30]};
const ctx={document:{getElementById:el,addEventListener(k,f){if(!listeners.has(k))listeners.set(k,[]);listeners.get(k).push(f);},dispatchEvent(e){for(const f of listeners.get(e.type)||[])f(e);return !e.defaultPrevented;}},
 window:{addEventListener(){}},CustomEvent:Event,Event,XMLHttpRequest:class{},AbortController,
 ToolpathView:class{clear(){}setModel(){}setModelLayout(){}wireframe(){}reset(){}},
 Worker:class{constructor(){workers.push(this);}terminate(){this.dead=true;}postMessage(){Promise.resolve().then(()=>{if(!this.dead)this.onmessage({data:{result}});});}},
 setTimeout(fn,ms){timers.set(++timer,{fn,ms});return timer;},clearTimeout(id){timers.delete(id);},
 async fetch(url,opts={}){
  if(opts.method==='POST'){posts.push({url,data:JSON.parse(opts.body)});if(losePost)throw Error('lost POST response');throw Error('unexpected action');}
  if(url==='/api/config')return{ok:true,json:async()=>({token:'token',target:'offline',slicing_enabled:true,upload_enabled:false,job_controls_enabled:false})};
  if(url==='/api/state')return{ok:true,json:async()=>({...state})};
  if(url==='/api/model')return{ok:true,headers:{get:k=>k==='ETag'?'"'+state.source_sha256+'"':k==='X-Skipped-Facets'?'0':'10'},arrayBuffer:async()=>new ArrayBuffer(10)};
  throw Error('unexpected GET '+url);
 }};
const flush=()=>new Promise(r=>setImmediate(r));
async function poll(){const t=[...timers.values()].find(t=>t.ms===2000);assert(t);await t.fn();await flush();}
async function main(){
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/model-transform.js','utf8').replace(/^export /gm,''),ctx);
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/app.js','utf8'),ctx);
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/model-preview.js','utf8').replace(/^import[^\n]+\n/gm,''),ctx);await flush();await flush();
 assert.equal(el('slice').disabled,false);el('model-x').value='30';el('model-x').handlers.input();await flush();assert.equal(el('model-manual').checked,true);
 state={...state,busy:true,phase:'slicing',slice_settings:{},model_transform:{scale:.5,rotate_z:90,x:-20,y:0}};
 await poll();assert.equal(el('model-x').value,'-20');assert.equal(el('model-transform-fields').disabled,true);assert.equal(el('slice').disabled,true);
 el('brim-mode').handlers.change();await flush();assert.equal(el('model-x').value,'-20','parent rendering must not restore stale pre-slice state');assert.equal(el('model-transform-fields').disabled,true);
 state={...state,busy:false,phase:'review',artifact:true,sliced:true,sha256:'b'.repeat(64)};await poll();assert.equal(workers.length,1);assert.equal(el('slice').disabled,true);
 state={...state,phase:'model_ready',source_id:'two',slice_settings:null,model_transform:null,artifact:false,sliced:false,sha256:'a'.repeat(64)};
 await poll();assert.equal(workers.length,2,'same bytes reselected into a new slot reset the editor');assert.equal(el('model-x').value,'0');assert.equal(el('model-manual').checked,false);assert.equal(el('slice').disabled,false);
 losePost=true;el('slice').handlers.click();await flush();assert.equal(posts.length,1);assert.equal(posts[0].data.source_id,'two');assert.equal(el('file').disabled,true);
 state={...state,phase:'review',slice_settings:{},artifact:true,sliced:true,sha256:'c'.repeat(64)};
 await poll();assert.equal(el('file').disabled,true,'automatic cached observations never clear an uncertain operation');assert.match(el('error').textContent,/lost POST/);
 el('refresh').handlers.click();await flush();assert.equal(el('error').textContent,'');assert.equal(posts.length,1,'no automatic save/start/retry');
 console.log('Composed editor/page source-slot epochs, remote snapshot locking and uncertain-job veto passed.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
