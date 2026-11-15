// Controller contract using mocked renderer/worker/HTTP, not WebGL acceptance.
const assert = require('node:assert/strict'), fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),handlers={},calls=[],workers=[],timers=new Map(),views=[];
const windowHandlers={}; let holdState=null;
let id=0, state={artifact:true,busy:false,name:'part.gcode',sha256:'a'.repeat(64)}, fail=false;
function el(key){if(!elements.has(key))elements.set(key,{value:'0',checked:key==='preview-enabled',disabled:false,textContent:'',
 addEventListener(name,fn){this[name]=fn;}});return elements.get(key);}
class View{constructor(){views.push(this);this.clears=0;}clear(){this.clears++;}setToolpath(data){this.data=data;}filter(h,t){this.height=h;this.travel=t;}reset(){this.resetCalled=true;}}
class Worker{constructor(url){assert.equal(url,'/toolpath-worker.js');workers.push(this);}postMessage(data){this.input=data;}terminate(){this.terminated=true;}}
const context={document:{getElementById:el,addEventListener:(name,fn)=>handlers[name]=fn},window:{addEventListener(name,fn){windowHandlers[name]=fn;}},
 ToolpathView:View,Worker,AbortController,setTimeout(fn,ms){timers.set(++id,{fn,ms});return id;},clearTimeout(id){timers.delete(id);},
 async fetch(url,options={}){calls.push({url,options});assert(!options.method || options.method==='GET');
 if(fail)throw Error('synthetic failed read');
 if(url==='/api/state'){if(holdState)await new Promise(resolve=>{holdState.resolve=resolve;});return{ok:true,json:async()=>({...state})};}
 assert.equal(url,'/api/artifact');assert.equal(options.headers['If-Match'],'"'+state.sha256+'"');
 return{ok:true,headers:{get:k=>k==='ETag'?'"'+state.sha256+'"':'10'},arrayBuffer:async()=>new ArrayBuffer(10)};}};
const flush=()=>new Promise(r=>setImmediate(r));
const result={layers:[.2,.4],counts:{extrusion:2,travel:1,unknown:0,unresolved:1,unsupported:0},warnings:['unmodeled homing'],limitations:'Not print approval'};
async function main(){
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/preview.js','utf8').replace(/^import[^\n]+\n/,''),context);await flush();
 assert.equal(workers.length,1);assert.equal(workers[0].input.options.assumeAbsoluteE,false);
 workers[0].onmessage({data:{result}});assert(workers[0].terminated);assert.equal(el('preview-layer').max,'2');
 assert.match(el('preview-warnings').textContent,/homing/);
 el('preview-layer').value='0';el('preview-layer').input();assert.equal(views[0].height,.2);
 el('preview-travel').checked=true;el('preview-travel').change();assert.equal(views[0].travel,true);
 handlers['finder-artifact-state']({detail:{...state,busy:true}});assert(el('preview-layer').disabled);
 handlers['finder-artifact-state']({detail:state});await flush();assert.equal(workers.length,2);
 const old=workers[1];handlers['finder-artifact-state']({detail:{artifact:false,busy:false}});
 assert(old.terminated);old.onmessage({data:{result}});assert(el('preview-layer').disabled,'stale worker cannot replace cleared/new artifact');
 state={...state,sha256:'b'.repeat(64)};handlers['finder-artifact-state']({detail:state});await flush();
 workers.at(-1).onmessage({data:{error:'unsupported file'}});assert.match(el('preview-message').textContent,/unsupported file/);
 const count=workers.length;handlers['finder-artifact-state']({detail:state});await flush();assert.equal(workers.length,count,'errors do not cause an automatic parse retry loop');
 el('preview-reload').click();await flush();assert.equal(workers.length,count+1);
 el('preview-enabled').checked=false;el('preview-enabled').change({target:el('preview-enabled')});
 assert(workers.at(-1).terminated);assert.match(el('preview-message').textContent,/paused/);
 const before=calls.filter(c=>c.url==='/api/state').length;
 const held={};holdState=held;el('preview-reload').click();await flush();
 el('preview-reload').click();el('preview-reload').click();await flush();
 assert.equal(calls.filter(c=>c.url==='/api/state').length,before+1,'cached state polls cannot overlap');
 held.resolve();holdState=null;await flush();
 const queued=[...timers.values()].find(t=>t.ms===0);assert(queued);await queued.fn();await flush();
 assert.equal(calls.filter(c=>c.url==='/api/state').length,before+2,'at most one pending refresh is retained');
 fail=true;const poll=[...timers.values()].find(t=>t.ms===2000);await poll.fn();await flush();assert(el('preview-layer').disabled);
 windowHandlers.pagehide();assert.equal(timers.size,0,'page hide stops polling');
 assert(calls.every(c=>['/api/state','/api/artifact'].includes(c.url)),'preview cannot mutate or query the printer');
 console.log('Preview controller identity, cancellation, no-retry, layers and GET-only tests passed.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
