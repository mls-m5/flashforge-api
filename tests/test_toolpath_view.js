// Real vendored Three.js geometry/math, mocked WebGL and orbit host only.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
async function main(){
 const source=fs.readFileSync('finderlab/webstatic/vendor/three/three.module.min.js','utf8');
 const T=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
 class Renderer{constructor(){this.domElement={addEventListener(){}};}setPixelRatio(r){this.ratio=r;}setSize(w,h){this.size=[w,h];}render(){this.renders=(this.renders||0)+1;}}
 class Controls{constructor(){this.target=new T.Vector3();}addEventListener(){}update(){}}
 const context={THREE:{...T,WebGLRenderer:Renderer},OrbitControls:Controls,window:{devicePixelRatio:4},
  ResizeObserver:class{constructor(fn){this.fn=fn;}observe(){}},Event:class{}};
 const script=fs.readFileSync('finderlab/webstatic/toolpath-view.js','utf8').replace(/^import[^\n]+\n/gm,'').replace('export class ToolpathView','class ToolpathView')+'\nglobalThis.View=ToolpathView;';
 vm.runInNewContext(script,context);
 const container={clientWidth:600,append(){},dispatchEvent(){}};const v=new context.View(container);
 assert.equal(v.renderer.ratio,2);assert.deepEqual(v.renderer.size,[600,380]);
 const data={positions:new Float32Array([0,0,.2,1,0,.2, 1,0,.2,1,1,.4, 1,1,.4,0,1,.4]),
  kinds:new Uint8Array([0,1,2]),heights:new Float32Array([.2,.4,.4]),counts:{extrusion:1,travel:1,unknown:1}};
 v.setToolpath(data);assert.equal(v.paths.length,3);assert.equal(v.paths[1].visible,false);
 for(const p of v.paths){assert.equal(p.geometry.getAttribute('position').count,2);assert.equal(p.geometry.getAttribute('segmentHeight').count,2);}
 v.filter(.2,true);assert.equal(v.paths[1].visible,true);
 assert(v.paths.every(p=>p.material.uniforms.maximumHeight.value===.2));
 assert(v.camera.near>0 && v.camera.far>v.camera.near);
 let disposed=0;for(const p of v.paths){p.geometry.addEventListener('dispose',()=>disposed++);p.material.addEventListener('dispose',()=>disposed++);}
 v.clear();assert.equal(v.paths.length,0);assert.equal(disposed,6);
 const vertices=new Float32Array([10,20,30,11,20,30,10,21,30]);
 v.setModel({positions:vertices,normals:new Float32Array([0,0,1,0,0,1,0,0,1])});
 assert.equal(v.paths.length,1);assert.equal(v.paths[0].isMesh,true);
 assert.deepEqual(v.paths[0].position.toArray(),[-10.5,-20.5,-30]);
 assert.deepEqual(v.bounds.min.toArray(),[-.5,-.5,0]);
 assert.equal(vertices[0],10,'display-only placement never modifies source vertices');
 v.wireframe(true);assert.equal(v.paths[0].material.wireframe,true);
 v.filter(.2,false);assert.equal(v.paths[0].visible,true);
 console.log('Vendored Three geometry batching, height uniforms, camera and disposal checks passed (no GPU).');
}main().catch(e=>{console.error(e);process.exitCode=1;});
