const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const elements=new Map(),listeners={},posts=[];
let state={phase:'review',busy:false,artifact:true,sliced:true,saved:false,name:'model.stl',suggested_name:'model.gcode',sha256:'a'.repeat(64),source_id:'slot',source_sha256:'s'.repeat(64),gx_metadata:{print_seconds:1},gx_generated:false};
function el(id){if(!elements.has(id))elements.set(id,{value:'',checked:false,hidden:false,textContent:'',disabled:false,attrs:{},handlers:{},classList:{add(){},remove(){}},addEventListener(k,f){this.handlers[k]=f;},getAttribute(k){return k==='src'?this.src:this.attrs[k];},removeAttribute(k){delete this[k];delete this.attrs[k];}});return elements.get(id);}
const ctx={document:{getElementById:el,addEventListener(k,f){listeners[k]=f;}},XMLHttpRequest:class{},setTimeout(){return 1;},clearTimeout(){},confirm(){throw Error('no dialogs');},
 async fetch(url,opts={}){
  if(opts.method==='POST'){
   const data=JSON.parse(opts.body);posts.push({url,data});assert.equal(url,'/api/gx');
   assert.equal(data.artifact_sha256,'a'.repeat(64));assert.equal(data.source_id,'slot');
   state={...state,gx_generated:true,sha256:'b'.repeat(64),suggested_name:'model.gx'};
  }
  return{ok:true,json:async()=>url==='/api/config'?{token:'token',slicing_enabled:true,upload_enabled:true,job_controls_enabled:false, sliced_upload_enabled:false}:{...state}};
 }};
const flush=()=>new Promise(r=>setImmediate(r));
async function main(){
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/app.js','utf8'),ctx);await flush();
 assert.equal(posts.length,0,'Slice/state changes cannot automatically create/upload GX');assert.equal(el('create-gx').disabled,false);
 el('create-gx').handlers.click();el('create-gx').handlers.click();await flush();
 assert.equal(posts.length,1);assert.equal(el('create-gx').disabled,true);assert.equal(el('remote').value,'model.gx');
 assert.equal(el('gx-thumbnail').src,'/api/gx-thumbnail?v='+'b'.repeat(64));assert.equal(el('gx-thumbnail').hidden,false);
 assert.equal(el('save').disabled,true,'GX never bypasses generated-output upload gate');
 assert.match(el('gx-status').textContent,/unchanged G-code/);
 state={...state,gx_generated:false,gx_metadata:null,phase:'empty',artifact:false,source_id:'new',suggested_name:''};el('refresh').handlers.click();await flush();
 assert.equal(el('gx-thumbnail').hidden,true);assert.equal(el('gx-thumbnail').src,undefined);assert.equal(el('create-gx').disabled,true);assert.equal(posts.length,1);
 console.log('GX UI explicit single action, exact hash/slot, filename update, protected upload gate and stale image clearing passed.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
