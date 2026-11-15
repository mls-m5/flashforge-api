const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),posts=[];const config={token:'token',target:'dummy',owned_dummy:true,upload_enabled:true,job_controls_enabled:true};
const fresh=id=>({phase:'file_ready',busy:false,artifact:true,saved:false,name:'source.gcode',suggested_name:'selected.gcode',source_id:id,sha256:'a'.repeat(64),job_result:'not_requested'});
let state=fresh('one');
function el(id){if(!elements.has(id))elements.set(id,{value:'',checked:id==='start-after-upload',disabled:false,handlers:{},textContent:'',classList:{add(){},remove(){}},addEventListener(k,f){this.handlers[k]=f;}});return elements.get(id);}
const ctx={document:{getElementById:el},XMLHttpRequest:class{},confirm(){throw Error('No popups');},setTimeout(){return 1;},clearTimeout(){},
 async fetch(url,opts={}){
  if(opts.method==='POST'){
   const data=JSON.parse(opts.body);posts.push({url,data});assert.equal(url,'/api/save','browser must not independently POST a follow-up start');
   state={...state,phase:data.start_after_upload?'start_acknowledged':'saved',saved:true,saved_name:data.remote_name,save_id:'saved-id',start_attempted:data.start_after_upload,start_after_upload:data.start_after_upload,job_result:data.start_after_upload?'start_acknowledged':'not_requested'};
  }
  return{ok:true,json:async()=>url==='/api/config'?config:{...state}};
 }};
const flush=()=>new Promise(r=>setImmediate(r));
async function main(){
 assert.match(fs.readFileSync('finderlab/webstatic/index.html','utf8'),/id="start-after-upload"[^>]*checked/);
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/app.js','utf8'),ctx);await flush();
 assert.equal(el('start-after-upload').checked,true);assert.equal(el('start-after-upload').disabled,false);
 assert.match(el('save').textContent,/Save \+ start selected.gcode on dummy/);
 el('save').handlers.click();el('save').handlers.click();await flush();
 assert.equal(posts.length,1);assert.equal(posts[0].data.start_after_upload,true);assert.equal(posts[0].data.source_id,'one');assert.equal(posts[0].data.artifact_sha256,'a'.repeat(64));
 assert.equal(el('start').disabled,true);assert.match(el('job-result').textContent,/Virtual job started/);
 state=fresh('two');el('refresh').handlers.click();await flush();
 el('start-after-upload').checked=false;el('start-after-upload').handlers.change();assert.match(el('save').textContent,/no start/);
 el('refresh').handlers.click();await flush();assert.equal(el('start-after-upload').checked,false,'refresh must not re-check an explicit save-only preference');
 el('save').handlers.click();await flush();assert.equal(posts.length,2);assert.equal(posts[1].data.start_after_upload,false);
 state=fresh('three');config.job_controls_enabled=false;el('refresh').handlers.click();await flush();
 assert.equal(el('start-after-upload').disabled,true);assert.equal(el('start-after-upload').checked,false);assert.match(el('save').textContent,/no start/);
 console.log('Checked-by-default combined intent, explicit save-only, capability gating, exact identity, no popup/double-click/client-side retry passed.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
