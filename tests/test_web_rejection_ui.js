const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),posts=[];let status=507;
let state={phase:'model_ready',busy:false,model:true,name:'part.stl',artifact:false,source_id:'slot',source_sha256:'a'.repeat(64)};
function el(id){if(!elements.has(id))elements.set(id,{value:id==='brim-mode'?'profile':id==='brim-width'?'5':['hole-compensation','contour-compensation'].includes(id)?'0':'',checked:false,disabled:false,textContent:'',handlers:{},classList:{add(){},remove(){}},addEventListener(k,f){this.handlers[k]=f;}});return elements.get(id);}
const ctx={document:{getElementById:el},XMLHttpRequest:class{},setTimeout(){return 1;},clearTimeout(){},
 async fetch(url,opts={}){
  if(opts.method==='POST'){
   posts.push(url);
   if(status!==200)return{ok:false,status,json:async()=>({error:status===507?'Web storage quota: used + reserved >256 MiB. Operation was not started. Stop status polling (not print cancel).':'synthetic server I/O failure'})};
   state={...state,phase:'review',artifact:true,sliced:true};
  }
  return{ok:true,status:200,json:async()=>url==='/api/config'?{token:'t',slicing_enabled:true,upload_enabled:false,job_controls_enabled:false}:{...state}};
 }};
const flush=()=>new Promise(r=>setImmediate(r));
async function main(){
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/app.js','utf8'),ctx);await flush();
 assert.equal(el('slice').disabled,false);el('slice').handlers.click();await flush();
 assert.equal(posts.length,1);assert.equal(el('slice').disabled,false,'definite preflight507 must not latch unknown-operation lock');
 assert.match(el('action-error').textContent,/Request rejected.*storage quota/);assert.match(el('action-error').textContent,/Stop status polling/);
 await flush();assert.equal(posts.length,1,'rejection never causes automatic retry');
 status=200;el('slice').handlers.click();await flush();assert.equal(posts.length,2);assert.equal(el('slice').disabled,true);
 state={...state,phase:'model_ready',artifact:false,sliced:false};el('refresh').handlers.click();await flush();status=500;
 el('slice').handlers.click();await flush();assert.equal(el('slice').disabled,true,'5xx may follow uncertain I/O; keep conservative lock');
 assert.match(el('action-error').textContent,/Response unknown/);el('slice').handlers.click();await flush();assert.equal(posts.length,3);
 el('refresh').handlers.click();await flush();assert.equal(el('slice').disabled,false);assert.equal(el('action-error').textContent,'');
 console.log('Definite quota/preflight rejection stays actionable and visible; unknown server I/O stays locked with no retry.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
