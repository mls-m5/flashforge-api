const assert=require('node:assert/strict'),fs=require('node:fs');
async function main(){
 const {modelLayout,normalizeTransform}=await import('data:text/javascript;base64,'+Buffer.from(fs.readFileSync('finderlab/webstatic/model-transform.js')).toString('base64'));
 const THREE=await import('../finderlab/webstatic/vendor/three/three.module.min.js');
 const positions=new Float32Array([10,20,30,14,20,30,10,22,33]);const original=[...positions];
 let result=modelLayout(positions,{scale:2,rotate_x:90,x:30,y:-15});
 result.bounds.flat().forEach((v,i)=>assert(Math.abs(v-[26,34,-18,-12,0,4][i])<1e-9));
 assert(result.fits);assert(!modelLayout(positions,{x:70}).fits);
 const t={scale:.7,rotate_x:17,rotate_y:-28,rotate_z:63,x:-21,y:24};result=modelLayout(positions,t);
 const rotation=new THREE.Matrix4().makeRotationFromEuler(new THREE.Euler(17*Math.PI/180,-28*Math.PI/180,63*Math.PI/180,'ZYX'));
 const vectors=[];for(let i=0;i<positions.length;i+=3)vectors.push(new THREE.Vector3(...positions.slice(i,i+3)).sub(new THREE.Vector3(12,21,31.5)).multiplyScalar(.7).applyMatrix4(rotation));
 const box=new THREE.Box3().setFromPoints(vectors),center=box.getCenter(new THREE.Vector3());const delta=new THREE.Vector3(-21-center.x,24-center.y,-box.min.z);
 const matrix=new THREE.Matrix4().set(...result.matrix);
 vectors.forEach((p,i)=>{const got=new THREE.Vector3(...positions.slice(i*3,i*3+3)).applyMatrix4(matrix);assert(got.distanceTo(p.add(delta))<1e-10);});
 assert.deepEqual([...positions],original);
 for(const t of [{scale:0},{scale:true},{rotate_x:Infinity},{x:71},{z:0},{x:'1'},{scale:NaN},{constructor:0},JSON.parse('{"__proto__":0}')])assert.throws(()=>normalizeTransform(t));
 console.log('Model transform math matches independent Three Euler/vertex operations; bounds/limits and immutability passed.');
}main().catch(e=>{console.error(e);process.exitCode=1;});
