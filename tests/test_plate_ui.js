const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const els=new Map(),handlers={},drafts=[],removals=[],requests=[],views=[];
let state={phase:'model_ready',busy:false,model:true,name:'2 models',source_id:'plate-one',source_sha256:'a'.repeat(64),slice_settings:null,
 models:[{id:'a',name:'a.stl',sha256:'a'.repeat(64)},{id:'b',name:'b.stl',sha256:'b'.repeat(64)}]};
const data={triangles:1,positions:new Float32Array([0,0,0,4,0,0,0,2,3]),normals:new Float32Array(9)};
function el(id){if(!els.has(id))els.set(id,{value:'',handlers:{},textContent:'',hidden:false,disabled:false,children:[],addEventListener(k,f){this.handlers[k]=f;},replaceChildren(){this.children=[];},append(e){this.children.push(e);}});return els.get(id);}
class Event{constructor(type,opts){this.type=type;this.detail=opts.detail;}}
class View{constructor(){views.push(this);this.renderer={domElement:{handlers:{},addEventListener(k,f){this.handlers[k]=f;}}};}reset(){}clear(){}setPlate(entries,selected){this.entries=entries;this.selected=selected;}pickModel(){return 'b';}}
const ctx={document:{getElementById:el,createElement:()=>({}),addEventListener(k,f){handlers[k]=f;},dispatchEvent(e){if(e.type==='finder-model-transform')drafts.push(e.detail);if(e.type==='finder-remove-model')removals.push(e.detail);}},window:{addEventListener(){}},CustomEvent:Event,ToolpathView:View,AbortController,setTimeout(){return 1;},clearTimeout(){},
 Worker:class{postMessage(){Promise.resolve().then(()=>this.onmessage({data:{result:data}}));}terminate(){}},
 async fetch(url,opts){requests.push({url,opts});if(url==='/api/config')return{ok:true,json:async()=>({token:'token'})};
  const id=url.endsWith('=a')?'a':'b';assert.equal(opts.headers['If-Match'],'"'+id.repeat(64)+'"');
  return{ok:true,headers:{get:k=>k==='ETag'?'"'+id.repeat(64)+'"':'10'},arrayBuffer:async()=>new ArrayBuffer(10)};
 }};
const flush=()=>new Promise(r=>setImmediate(r));
async function main(){
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/model-transform.js','utf8').replace(/^export /gm,''),ctx);
 vm.runInNewContext(fs.readFileSync('finderlab/webstatic/plate-preview.js','utf8').replace(/^import[^\n]+\n/gm,''),ctx);
 handlers['finder-artifact-state']({detail:state});await flush();await flush();
 assert.equal(drafts.at(-1).error,'');assert.equal(drafts.at(-1).plate.length,2);assert.equal(el('plate-section').hidden,false);
 el('plate-model').value='b';el('plate-model').handlers.change();assert.equal(views[0].selected,'b');
 el('plate-x').value='-45';el('plate-x').handlers.input();assert.match(drafts.at(-1).error,/overlap/);
 el('plate-x').value='35';el('plate-x').handlers.input();assert.equal(drafts.at(-1).error,'');assert.equal(drafts.at(-1).plate[1].transform.x,35);
 const old=JSON.stringify(drafts.at(-1));handlers['finder-artifact-state']({detail:{...state}});await flush();assert.equal(JSON.stringify(drafts.at(-1)),old,'cached state must not reset local drafts');
 el('plate-remove').handlers.click();assert.deepEqual(JSON.parse(JSON.stringify(removals[0])),{source_id:'plate-one',model_id:'b'});
 state={...state,busy:true,phase:'slicing',slice_settings:{},plate:[{id:'a',transform:{scale:1,x:-25,y:0,rotate_x:0,rotate_y:0,rotate_z:0}},{id:'b',transform:{scale:.5,x:25,y:0,rotate_x:0,rotate_y:0,rotate_z:90}}]};
 handlers['finder-artifact-state']({detail:state});assert.equal(el('plate-fields').disabled,true);assert.equal(el('plate-scale').value,'50');assert.equal(drafts.at(-1).locked,true);
 state={...state,models:[state.models[0]],source_id:'new',busy:false,phase:'model_ready',slice_settings:null};handlers['finder-artifact-state']({detail:state});assert.equal(el('plate-section').hidden,true);assert.equal(el('single-model-section').hidden,false);
 assert(requests.every(r=>!r.opts?.method||r.opts.method==='GET'),'controller never sends slice/save/print commands');
 console.log('Plate preview loads all models, selects/edits independently, checks overlap, freezes snapshots and removes explicitly.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
