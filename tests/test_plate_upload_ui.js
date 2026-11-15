const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const els=new Map(),requests=[],xhrs=[],listeners={};let state={phase:'empty',busy:false};
function el(id){if(!els.has(id))els.set(id,{value:id==='brim-mode'?'profile':id==='brim-width'?'5':'',checked:false,disabled:false,textContent:'',handlers:{},classList:{add(){},remove(){}},addEventListener(k,f){this.handlers[k]=f;}});return els.get(id);}
class XHR{constructor(){xhrs.push(this);this.upload={};}open(method,url){this.url=url;}setRequestHeader(){}send(file){this.file=file;}finish(next){state=next;this.status=200;this.responseText=JSON.stringify(next);this.onload();}}
const ctx={document:{getElementById:el,addEventListener(k,f){listeners[k]=f;}},XMLHttpRequest:XHR,setTimeout(){return 1;},clearTimeout(){},
 async fetch(url,opts={}){requests.push({url,opts});return{ok:true,json:async()=>url==='/api/config'?{token:'t',slicing_enabled:true,upload_enabled:false,model_limit:64*1024*1024,print_limit:8*1024*1024}:state};}};
const flush=()=>new Promise(r=>setImmediate(r));
const model=(id)=>({id,name:id+'.stl',sha256:id.repeat(64),size:100});
async function main(){
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/app.js','utf8'),ctx);await flush();
 el('file').handlers.change({target:{files:[{name:'a.stl',size:100},{name:'b.stl',size:100}]}});
 assert.equal(xhrs.length,1,'receive files serially, not concurrent slot races');assert.equal(el('file').disabled,true);
 xhrs[0].finish({phase:'model_ready',model:true,busy:false,models:[model('a')],source_id:'one',source_sha256:'a'.repeat(64)});
 assert.equal(xhrs.length,2);xhrs[1].finish({phase:'model_ready',model:true,busy:false,models:[model('a'),model('b')],source_id:'two',source_sha256:'a'.repeat(64)});
 assert.equal(el('file').disabled,false,'existing unsliced STL must not disable adding another');
 assert.equal(el('slice').disabled,true,'multiple models cannot slice before an identity-bound layout draft exists');
 listeners['finder-model-transform']({detail:{source_id:'two',source_sha256:'a'.repeat(64),error:'',locked:false,plate:[{id:'a',transform:{x:-25}},{id:'b',transform:{x:25}}]}});await flush();assert.equal(el('slice').disabled,false);
 el('file').handlers.change({target:{files:[{name:'c.stl',size:100}]}});assert.equal(xhrs.length,3);xhrs[2].onerror();
 assert.equal(el('file').disabled,true,'lost receive remains uncertain; no next file retry');assert.equal(xhrs.length,3);
 assert(requests.every(r=>!r.opts.method),'selecting models never auto-slices/saves/starts');
 console.log('Multiple-file receive is serial, permits further STL additions and retains lost-response/no-auto-job gates.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
